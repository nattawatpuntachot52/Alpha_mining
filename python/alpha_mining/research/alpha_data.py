"""Asset registry + multi-timeframe data loading for the Daily Alpha Mining Factory.

Assets
------
* ``ETHUSDT`` — Binance USD-M perpetual klines (Binance Vision ``um``).
* ``XAUUSD``  — spot gold. GitHub Actions runners have no MT5 terminal, so the default public feed is
  the gold-backed ``PAXGUSDT`` spot market (Binance Vision ``spot``) which tracks LBMA gold. It trades
  24/7 (no weekend gaps) and so is a PROXY for broker XAUUSD; every run records this in the loader
  metadata. A local MT5/CSV export (``--local-dir``) overrides the proxy for exact broker data.

Timeframes
----------
Native Binance Vision intervals (``5m``..``1d``) are downloaded directly. ``1m`` data or any local 1m
CSV can be causally resampled with :func:`resample_bars` (bucket = UTC epoch-aligned, only the bars
that actually exist inside a bucket are aggregated, bar time = bucket open).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

from ..strategy.lgb154 import Bar
from .alpha_signals import TIMEFRAME_MS, Series
from .kline_loader import HttpGetTransport, fetch_binance_vision_klines, load_local_klines


@dataclass(frozen=True)
class AssetConfig:
    symbol: str
    vision_symbol: str
    market: str
    cost_bps_per_side: float
    is_proxy: bool
    description: str


ASSETS: dict[str, AssetConfig] = {
    "XAUUSD": AssetConfig(
        symbol="XAUUSD",
        vision_symbol="PAXGUSDT",
        market="spot",
        cost_bps_per_side=2.0,
        is_proxy=True,
        description="Gold. Public feed = PAXGUSDT (gold-backed token, 24/7) as XAUUSD proxy; ~2 bps/side spread+slippage.",
    ),
    "ETHUSDT": AssetConfig(
        symbol="ETHUSDT",
        vision_symbol="ETHUSDT",
        market="um",
        cost_bps_per_side=5.0,
        is_proxy=False,
        description="Binance USD-M ETHUSDT perpetual; 5 bps/side (taker fee + slippage).",
    ),
}

# Lookback window (days) per timeframe: long enough for >=100 trades on slow models, short enough for CI.
DEFAULT_DAYS_BY_TIMEFRAME: dict[str, int] = {
    "1m": 90,
    "5m": 540,
    "15m": 900,
    "30m": 1100,
    "1h": 1460,
    "4h": 1825,
    "1d": 2190,
}


def resample_bars(bars: Sequence[Bar], tf_ms: int) -> list[Bar]:
    """Causally aggregate ascending lower-timeframe bars into UTC epoch-aligned ``tf_ms`` buckets."""
    if tf_ms <= 0:
        raise ValueError("tf_ms must be positive")
    out: list[Bar] = []
    cur_bucket: int | None = None
    o = h = l = c = v = 0.0
    for b in bars:
        bucket = (int(b.open_time_ms) // tf_ms) * tf_ms
        if bucket != cur_bucket:
            if cur_bucket is not None:
                out.append(Bar(open_time_ms=cur_bucket, open=o, high=h, low=l, close=c, volume=v, close_time_ms=cur_bucket + tf_ms - 1))
            cur_bucket = bucket
            o, h, l, c, v = float(b.open), float(b.high), float(b.low), float(b.close), float(b.volume)
        else:
            h = max(h, float(b.high))
            l = min(l, float(b.low))
            c = float(b.close)
            v += float(b.volume)
    if cur_bucket is not None:
        out.append(Bar(open_time_ms=cur_bucket, open=o, high=h, low=l, close=c, volume=v, close_time_ms=cur_bucket + tf_ms - 1))
    return out


def _clean(bars: Sequence[Bar]) -> list[Bar]:
    return [b for b in bars if b.open > 0 and b.high > 0 and b.low > 0 and b.close > 0 and b.high >= b.low]


def load_asset_series(
    asset: str,
    timeframe: str,
    *,
    days: int | None = None,
    end_date: date | None = None,
    cache_dir: Path,
    local_dir: Path | None = None,
    transport: HttpGetTransport | None = None,
    max_workers: int = 8,
) -> tuple[Series, dict[str, Any]]:
    """Load bars for ``asset`` at ``timeframe`` and return ``(Series, loader_meta)``."""
    cfg = ASSETS.get(asset)
    if cfg is None:
        raise ValueError(f"unknown asset {asset!r}; known: {sorted(ASSETS)}")
    tf_ms = TIMEFRAME_MS.get(timeframe)
    if tf_ms is None:
        raise ValueError(f"unknown timeframe {timeframe!r}; known: {sorted(TIMEFRAME_MS)}")
    n_days = int(days or DEFAULT_DAYS_BY_TIMEFRAME[timeframe])
    end_d = end_date or (datetime.now(timezone.utc).date() - timedelta(days=1))
    start_d = end_d - timedelta(days=max(2, n_days) - 1)

    meta: dict[str, Any] = {
        "asset": asset,
        "timeframe": timeframe,
        "requested_days": n_days,
        "is_proxy": cfg.is_proxy,
        "cost_bps_per_side": cfg.cost_bps_per_side,
    }

    bars: list[Bar] | None = None
    if local_dir is not None:
        native = local_dir / f"{asset}_{timeframe}.csv"
        base_1m = local_dir / f"{asset}_1m.csv"
        if native.is_file():
            bars = load_local_klines(native)
            meta.update({"source": "local", "path": str(native)})
        elif base_1m.is_file():
            bars = resample_bars(load_local_klines(base_1m), tf_ms)
            meta.update({"source": "local_resampled_1m", "path": str(base_1m)})
    if bars is None:
        bars, stats = fetch_binance_vision_klines(
            symbol=cfg.vision_symbol,
            interval=timeframe,
            market=cfg.market,
            start_date=start_d,
            end_date=end_d,
            cache_dir=cache_dir,
            max_workers=max_workers,
            transport=transport,
        )
        meta.update({"source": f"binance_vision:{cfg.market}:{cfg.vision_symbol}"})
        meta.update({k: int(v) for k, v in stats.items()})

    bars = _clean(bars)
    if len(bars) < 200:
        raise RuntimeError(f"insufficient {asset} {timeframe} bars loaded ({len(bars)}); meta={meta}")
    series = Series.from_bars(bars, tf_ms)
    meta["bars"] = len(series)
    meta["first_bar_utc"] = datetime.fromtimestamp(series.t[0] / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    meta["last_bar_utc"] = datetime.fromtimestamp(series.t[-1] / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    return series, meta
