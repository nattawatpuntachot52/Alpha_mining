"""Unified 1-minute Kline & Funding Rate loader for backtesting.

Supports four transparent sources without hard third-party dependencies:
1. Official Binance Vision bulk archive (`https://data.binance.vision`) — fastest path
   for 1,000+ days (~1.44M 1m bars) across `um` (USD-M Futures), `cm` (COIN-M Futures),
   and `spot`, plus real 8-hour historical Funding Rate ZIPs.
2. Public Binance REST API (`https://data-api.binance.vision/api/v3/klines`) for recent
   Spot 1m windows or live tails.
3. Local CSV / `.csv.zip` files (Binance 12-column format or standard OHLCV headers).
4. Local Parquet files / directories (lazy `pyarrow` import; compatible with our own
   `binance_collector.py` daily Zstd Parquet outputs).
"""

from __future__ import annotations

import csv
import io
import json
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence

from ..strategy.lgb154 import Bar

BINANCE_VISION_BASE = "https://data.binance.vision"
BINANCE_DATA_API_BASE = "https://data-api.binance.vision"

HttpGetTransport = Callable[[str, float], tuple[int, bytes]]


def _default_http_get(url: str, timeout: float) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": "alpha-mining-backtest/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), b""


def _normalize_ts_ms(raw: int | float | str) -> int:
    """Normalize seconds (10-digit), milliseconds (13-digit), or microseconds (16-digit) to UTC ms."""
    val = str(raw).strip()
    if val.isdigit():
        num = int(val)
    else:
        try:
            num = int(float(val))
        except ValueError:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
    if num >= 10**15:  # Binance Vision Spot 2025+ microsecond timestamps
        return num // 1000
    if num < 10**11:  # Unix seconds
        return num * 1000
    return num


def parse_kline_csv_stream(text_stream: Iterable[str]) -> list[Bar]:
    """Parse Binance Vision 12-column CSV (with or without header) or standard OHLCV CSV."""
    reader = csv.reader(text_stream)
    rows_iter = iter(reader)
    first = next(rows_iter, None)
    if first is None:
        return []

    bars: list[Bar] = []
    header_map: dict[str, int] | None = None

    first_token = first[0].strip().lower() if first else ""
    if first_token and not first_token.replace(".", "", 1).isdigit():
        # Headered CSV
        header_map = {col.strip().lower(): i for i, col in enumerate(first)}
    else:
        # Headerless Binance 12-column row
        if len(first) >= 6:
            bars.append(
                Bar(
                    open_time_ms=_normalize_ts_ms(first[0]),
                    open=float(first[1]),
                    high=float(first[2]),
                    low=float(first[3]),
                    close=float(first[4]),
                    volume=float(first[5]),
                    close_time_ms=_normalize_ts_ms(first[6]) if len(first) > 6 and first[6] else 0,
                )
            )

    if header_map is not None:
        ts_col = next(
            (header_map[k] for k in ("open_time", "open_time_ms", "timestamp", "time", "datetime", "date") if k in header_map),
            0,
        )
        o_col = header_map.get("open", 1)
        h_col = header_map.get("high", 2)
        l_col = header_map.get("low", 3)
        c_col = header_map.get("close", 4)
        v_col = header_map.get("volume", 5)
        ct_col = header_map.get("close_time", header_map.get("close_time_ms", -1))

        for row in rows_iter:
            if not row or len(row) <= max(ts_col, o_col, h_col, l_col, c_col):
                continue
            bars.append(
                Bar(
                    open_time_ms=_normalize_ts_ms(row[ts_col]),
                    open=float(row[o_col]),
                    high=float(row[h_col]),
                    low=float(row[l_col]),
                    close=float(row[c_col]),
                    volume=float(row[v_col]) if 0 <= v_col < len(row) and row[v_col] else 0.0,
                    close_time_ms=_normalize_ts_ms(row[ct_col]) if 0 <= ct_col < len(row) and row[ct_col] else 0,
                )
            )
    else:
        for row in rows_iter:
            if len(row) < 6:
                continue
            bars.append(
                Bar(
                    open_time_ms=_normalize_ts_ms(row[0]),
                    open=float(row[1]),
                    high=float(row[2]),
                    low=float(row[3]),
                    close=float(row[4]),
                    volume=float(row[5]),
                    close_time_ms=_normalize_ts_ms(row[6]) if len(row) > 6 and row[6] else 0,
                )
            )
    return bars


def load_klines_from_zip_bytes(raw_zip: bytes) -> list[Bar]:
    """Extract and parse klines from a Binance Vision `.zip` archive in memory."""
    bars: list[Bar] = []
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        for member in sorted(zf.namelist()):
            if member.endswith(".csv"):
                with zf.open(member) as fh:
                    bars.extend(parse_kline_csv_stream(io.TextIOWrapper(fh, encoding="utf-8")))
    return bars


def load_funding_from_zip_bytes(raw_zip: bytes) -> dict[int, float]:
    """Extract and parse `{calc_time_ms: funding_rate}` from a Binance Vision fundingRate `.zip`."""
    rates: dict[int, float] = {}
    with zipfile.ZipFile(io.BytesIO(raw_zip)) as zf:
        for member in sorted(zf.namelist()):
            if not member.endswith(".csv"):
                continue
            with zf.open(member) as fh:
                reader = csv.reader(io.TextIOWrapper(fh, encoding="utf-8"))
                for row in reader:
                    if len(row) < 3:
                        continue
                    head = row[0].strip().lower()
                    if head and not head.isdigit():
                        continue
                    ts_ms = _normalize_ts_ms(row[0])
                    # Round to nearest 8h funding boundary (some historical rows are +1..+5 ms)
                    boundary_ms = round(ts_ms / 28_800_000) * 28_800_000
                    rates[boundary_ms] = float(row[2])
    return rates


def load_local_klines(
    path: Path,
    *,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> list[Bar]:
    """Load klines from a local `.csv`, `.zip`, `.parquet`, or directory of those files."""
    if not path.exists():
        raise FileNotFoundError(f"dataset path not found: {path}")

    files: list[Path]
    if path.is_dir():
        files = sorted(
            p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in {".csv", ".zip", ".parquet"}
        )
    else:
        files = [path]

    all_bars: list[Bar] = []
    for f in files:
        suf = f.suffix.lower()
        if suf == ".csv":
            with f.open("r", encoding="utf-8") as fh:
                all_bars.extend(parse_kline_csv_stream(fh))
        elif suf == ".zip":
            all_bars.extend(load_klines_from_zip_bytes(f.read_bytes()))
        elif suf == ".parquet":
            try:
                import pyarrow.parquet as pq  # type: ignore[import-not-found]
            except ImportError as exc:
                raise RuntimeError(
                    "reading .parquet datasets requires pyarrow (install pyarrow or pass .csv/.zip)"
                ) from exc
            table = pq.read_table(f)
            cols = {name.lower(): name for name in table.column_names}
            ts_name = next(
                (cols[k] for k in ("open_time_ms", "open_time", "timestamp", "time") if k in cols),
                None,
            )
            if ts_name is None:
                raise ValueError(f"parquet file {f} missing timestamp column")
            pydict = table.to_pydict()
            ts_vals = pydict[ts_name]
            opens = pydict[cols["open"]]
            highs = pydict[cols["high"]]
            lows = pydict[cols["low"]]
            closes = pydict[cols["close"]]
            vols = pydict[cols["volume"]] if "volume" in cols else [0.0] * len(ts_vals)
            for i in range(len(ts_vals)):
                all_bars.append(
                    Bar(
                        open_time_ms=_normalize_ts_ms(ts_vals[i]),
                        open=float(opens[i]),
                        high=float(highs[i]),
                        low=float(lows[i]),
                        close=float(closes[i]),
                        volume=float(vols[i]),
                    )
                )

    return _deduplicate_and_filter_bars(all_bars, start_ms=start_ms, end_ms=end_ms)


def _deduplicate_and_filter_bars(
    bars: Sequence[Bar],
    *,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> list[Bar]:
    by_ts: dict[int, Bar] = {}
    for b in bars:
        if start_ms is not None and b.open_time_ms < start_ms:
            continue
        if end_ms is not None and b.open_time_ms > end_ms:
            continue
        by_ts[b.open_time_ms] = b
    return [by_ts[k] for k in sorted(by_ts)]


def _iter_months(start_day: date, end_day: date) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    y, m = start_day.year, start_day.month
    while (y, m) <= (end_day.year, end_day.month):
        months.append((y, m))
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return months


def _vision_market_prefix(market: str) -> str:
    m = market.strip().lower()
    if m == "um":
        return "data/futures/um"
    if m == "cm":
        return "data/futures/cm"
    if m == "spot":
        return "data/spot"
    raise ValueError(f"unsupported Binance Vision market {market!r}; expected 'um', 'cm', or 'spot'")


def fetch_binance_vision_klines(
    *,
    symbol: str,
    interval: str = "1m",
    market: str = "um",
    start_date: date,
    end_date: date,
    cache_dir: Path,
    max_workers: int = 8,
    transport: HttpGetTransport | None = None,
    timeout: float = 30.0,
) -> tuple[list[Bar], dict[str, int]]:
    """Download/cache official Binance Vision monthly + daily ZIP archives and return sorted Bars."""
    if end_date < start_date:
        raise ValueError("end_date must be >= start_date")
    http_get = transport or _default_http_get
    prefix = _vision_market_prefix(market)
    sym = symbol.upper()
    target_dir = cache_dir / market.lower() / sym / interval
    target_dir.mkdir(parents=True, exist_ok=True)

    today_utc = datetime.now(timezone.utc).date()
    current_ym = (today_utc.year, today_utc.month)

    months = _iter_months(start_date, end_date)
    monthly_jobs: list[tuple[str, Path]] = []
    daily_jobs: list[tuple[str, Path]] = []

    for y, m in months:
        if (y, m) < current_ym:
            fname = f"{sym}-{interval}-{y:04d}-{m:02d}.zip"
            url = f"{BINANCE_VISION_BASE}/{prefix}/monthly/klines/{sym}/{interval}/{fname}"
            monthly_jobs.append((url, target_dir / fname))
        else:
            # Current incomplete month: fetch completed daily ZIPs up to min(end_date, today - 1)
            day_start = max(start_date, date(y, m, 1))
            day_end = min(end_date, today_utc - timedelta(days=1))
            cur = day_start
            while cur <= day_end:
                fname = f"{sym}-{interval}-{cur.strftime('%Y-%m-%d')}.zip"
                url = f"{BINANCE_VISION_BASE}/{prefix}/daily/klines/{sym}/{interval}/{fname}"
                daily_jobs.append((url, target_dir / fname))
                cur += timedelta(days=1)

    all_jobs = monthly_jobs + daily_jobs
    stats = {"cached_files": 0, "downloaded_files": 0, "missing_files": 0}

    def _fetch_one(url: str, dest: Path) -> tuple[Path | None, str]:
        if dest.is_file() and dest.stat().st_size > 0:
            return dest, "cached"
        status, payload = http_get(url, timeout)
        if status == 200 and payload:
            tmp = dest.with_suffix(".zip.tmp")
            tmp.write_bytes(payload)
            tmp.replace(dest)
            return dest, "downloaded"
        return None, "missing"

    resolved_files: list[Path] = []
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        futs = [pool.submit(_fetch_one, url, dest) for url, dest in all_jobs]
        for fut in as_completed(futs):
            path_out, status_str = fut.result()
            if status_str == "cached" and path_out is not None:
                stats["cached_files"] += 1
                resolved_files.append(path_out)
            elif status_str == "downloaded" and path_out is not None:
                stats["downloaded_files"] += 1
                resolved_files.append(path_out)
            else:
                stats["missing_files"] += 1

    start_ms = int(datetime(start_date.year, start_date.month, start_date.day, tzinfo=timezone.utc).timestamp() * 1000)
    end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, 999000, tzinfo=timezone.utc)
    end_ms = int(end_dt.timestamp() * 1000)

    bars: list[Bar] = []
    for zpath in sorted(resolved_files):
        bars.extend(load_klines_from_zip_bytes(zpath.read_bytes()))

    deduped = _deduplicate_and_filter_bars(bars, start_ms=start_ms, end_ms=end_ms)
    stats["bar_count"] = len(deduped)
    return deduped, stats


def fetch_binance_vision_funding_rates(
    *,
    symbol: str,
    market: str = "um",
    start_date: date,
    end_date: date,
    cache_dir: Path,
    max_workers: int = 8,
    transport: HttpGetTransport | None = None,
    timeout: float = 20.0,
) -> dict[int, float]:
    """Download/cache historical 8-hour Binance Funding Rates for `um` or `cm` perpetuals."""
    if market.lower() not in {"um", "cm"}:
        return {}
    http_get = transport or _default_http_get
    prefix = _vision_market_prefix(market)
    sym = symbol.upper()
    target_dir = cache_dir / market.lower() / sym / "fundingRate"
    target_dir.mkdir(parents=True, exist_ok=True)

    today_utc = datetime.now(timezone.utc).date()
    current_ym = (today_utc.year, today_utc.month)
    jobs: list[tuple[str, Path]] = []
    for y, m in _iter_months(start_date, end_date):
        if (y, m) < current_ym:
            fname = f"{sym}-fundingRate-{y:04d}-{m:02d}.zip"
            url = f"{BINANCE_VISION_BASE}/{prefix}/monthly/fundingRate/{sym}/{fname}"
            jobs.append((url, target_dir / fname))

    def _fetch_one(url: str, dest: Path) -> Path | None:
        if dest.is_file() and dest.stat().st_size > 0:
            return dest
        status, payload = http_get(url, timeout)
        if status == 200 and payload:
            tmp = dest.with_suffix(".zip.tmp")
            tmp.write_bytes(payload)
            tmp.replace(dest)
            return dest
        return None

    files: list[Path] = []
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        futs = [pool.submit(_fetch_one, u, d) for u, d in jobs]
        for fut in as_completed(futs):
            p = fut.result()
            if p is not None:
                files.append(p)

    rates: dict[int, float] = {}
    for fp in sorted(files):
        rates.update(load_funding_from_zip_bytes(fp.read_bytes()))
    return rates


def fetch_data_api_spot_klines(
    *,
    symbol: str,
    interval: str = "1m",
    start_ms: int,
    end_ms: int,
    transport: HttpGetTransport | None = None,
    timeout: float = 20.0,
) -> list[Bar]:
    """Fetch public Spot klines via `https://data-api.binance.vision/api/v3/klines` (paginated)."""
    http_get = transport or _default_http_get
    bars: list[Bar] = []
    cursor = int(start_ms)
    sym = symbol.upper()

    while cursor <= end_ms:
        qs = urllib.parse.urlencode(
            {
                "symbol": sym,
                "interval": interval,
                "startTime": cursor,
                "endTime": end_ms,
                "limit": 1000,
            }
        )
        url = f"{BINANCE_DATA_API_BASE}/api/v3/klines?{qs}"
        status, payload = http_get(url, timeout)
        if status != 200:
            raise RuntimeError(f"data-api.binance.vision klines failed with HTTP {status}")
        rows = json.loads(payload.decode("utf-8"))
        if not rows:
            break
        for r in rows:
            bars.append(
                Bar(
                    open_time_ms=int(r[0]),
                    open=float(r[1]),
                    high=float(r[2]),
                    low=float(r[3]),
                    close=float(r[4]),
                    volume=float(r[5]),
                    close_time_ms=int(r[6]),
                )
            )
        last_open = int(rows[-1][0])
        if last_open < cursor or len(rows) < 1000:
            break
        cursor = last_open + 60_000
    return _deduplicate_and_filter_bars(bars, start_ms=start_ms, end_ms=end_ms)
