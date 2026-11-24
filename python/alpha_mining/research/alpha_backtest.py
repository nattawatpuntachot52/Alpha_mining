"""Causal directional (long / short / two-way) backtest engine for the Daily Alpha Mining Factory.

Execution model (zero lookahead):
    * ``desired[i]`` is decided at the CLOSE of bar ``i`` and filled at the OPEN of bar ``i + 1``.
    * Costs are modelled as adverse price slippage of ``cost_bps_per_side`` on every fill.
    * Optional intrabar SL / TP as a percent of entry price (if both are touched inside one bar the
      stop-loss is assumed to fill first), optional time-stop in bars.
    * After any SL / TP / time-stop exit the engine stays flat until the signal CHANGES, so a stopped
      position is never re-entered on the very next bar for the same unchanged signal state.
    * Position size is 1x current equity (no leverage, fully compounded), so every model is
      directly comparable across symbols and timeframes.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Sequence

from .alpha_signals import DAY_MS, Series

_ND = statistics.NormalDist()


@dataclass(frozen=True)
class AlphaBacktestOptions:
    cost_bps_per_side: float = 2.0
    sl_pct: float = 0.0
    tp_pct: float = 0.0
    time_stop_bars: int = 0
    oos_fraction: float = 0.3
    periods_per_year: float = 365.0
    initial_capital: float = 10_000.0

    def validate(self) -> None:
        for name in ("cost_bps_per_side", "sl_pct", "tp_pct", "initial_capital"):
            v = getattr(self, name)
            if not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
                raise ValueError(f"{name} must be a finite number >= 0, got {v!r}")
        if self.sl_pct >= 100.0:
            raise ValueError("sl_pct must be < 100")
        if not 0.05 <= self.oos_fraction <= 0.6:
            raise ValueError("oos_fraction must be within [0.05, 0.6]")
        if self.time_stop_bars < 0:
            raise ValueError("time_stop_bars must be >= 0")


@dataclass
class AlphaResult:
    symbol: str
    timeframe: str
    direction: str
    bar_count: int
    start_utc: str
    end_utc: str
    days_covered: float
    metrics: dict[str, Any] = field(default_factory=dict)
    daily_series: dict[str, Any] = field(default_factory=dict)

    def summary_dict(self) -> dict[str, Any]:
        out = {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "bar_count": self.bar_count,
            "window_start_utc": self.start_utc,
            "window_end_utc": self.end_utc,
            "days_covered": self.days_covered,
        }
        out.update(self.metrics)
        return out


def _iso(ms: int) -> str:
    return date.fromordinal(ms // DAY_MS + 719163).isoformat()


def _stats(rets: Sequence[float], ppy: float) -> tuple[float, float, float]:
    """Return (total_return, sharpe_ann, max_dd) of compounded daily returns."""
    if not rets:
        return 0.0, 0.0, 0.0
    eq = 1.0
    peak = 1.0
    mdd = 0.0
    for r in rets:
        eq *= 1.0 + r
        peak = max(peak, eq)
        if peak > 0:
            mdd = max(mdd, 1.0 - eq / peak)
    sd = statistics.pstdev(rets) if len(rets) > 1 else 0.0
    sharpe = (statistics.fmean(rets) / sd * math.sqrt(ppy)) if sd > 1e-12 else 0.0
    return eq - 1.0, sharpe, mdd


def _beta_corr(a: Sequence[float], b: Sequence[float]) -> tuple[float, float]:
    n = min(len(a), len(b))
    if n < 3:
        return 0.0, 0.0
    a, b = a[-n:], b[-n:]
    ma, mb = statistics.fmean(a), statistics.fmean(b)
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (n - 1)
    va = sum((x - ma) ** 2 for x in a) / (n - 1)
    vb = sum((y - mb) ** 2 for y in b) / (n - 1)
    beta = cov / vb if vb > 1e-18 else 0.0
    corr = cov / math.sqrt(va * vb) if va > 1e-18 and vb > 1e-18 else 0.0
    return beta, corr


def _psr(rets: Sequence[float]) -> float:
    """Probabilistic Sharpe Ratio vs 0 (Bailey & Lopez de Prado) on daily returns."""
    n = len(rets)
    if n < 10:
        return 0.0
    mu = statistics.fmean(rets)
    sd = statistics.pstdev(rets)
    if sd <= 1e-12:
        return 0.0
    sr = mu / sd
    z = [(r - mu) / sd for r in rets]
    skew = sum(x**3 for x in z) / n
    kurt = sum(x**4 for x in z) / n
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if denom <= 1e-12:
        return 0.0
    return _ND.cdf(sr * math.sqrt(n - 1) / math.sqrt(denom))


def run_alpha_backtest(
    series: Series,
    desired: Sequence[int],
    opt: AlphaBacktestOptions,
    *,
    symbol: str = "",
    timeframe: str = "",
    direction: str = "long_only",
) -> AlphaResult:
    opt.validate()
    n = len(series)
    if n < 50:
        raise ValueError(f"insufficient bars for backtest ({n} < 50)")
    if len(desired) != n:
        raise ValueError("desired positions length must equal number of bars")
    cost = opt.cost_bps_per_side / 10_000.0
    sl = opt.sl_pct / 100.0
    tp = opt.tp_pct / 100.0
    o_, h_, l_, c_ = series.o, series.h, series.l, series.c

    cur_eq = 1.0
    eq = [1.0] * n
    pos = 0
    eq_entry = 1.0
    entry_net = 0.0
    entry_raw = 0.0
    entry_i = 0
    bars_in = 0
    blocked = 0
    exposure_bars = 0
    trades: list[tuple[int, int, int, float]] = []

    def close_trade(px_raw: float, idx: int) -> None:
        nonlocal cur_eq, pos
        exit_net = px_raw * (1.0 - pos * cost)
        r = pos * (exit_net / entry_net - 1.0)
        cur_eq = max(eq_entry * (1.0 + r), 0.0)
        trades.append((entry_i, idx, pos, r))
        pos = 0

    for j in range(1, n):
        want = int(desired[j - 1])
        if want != blocked:
            blocked = 0
        if blocked != 0 and want == blocked:
            want = 0
        o, h, l, c = o_[j], h_[j], l_[j], c_[j]

        if pos != 0 and want != pos:
            close_trade(o, j)
        if pos == 0 and want != 0:
            pos = want
            eq_entry = cur_eq
            entry_raw = o
            entry_net = o * (1.0 + pos * cost)
            entry_i = j
            bars_in = 0

        if pos != 0:
            exposure_bars += 1
            bars_in += 1
            exit_px: float | None = None
            if sl > 0 or tp > 0:
                if pos == 1:
                    sl_lvl = entry_raw * (1.0 - sl) if sl > 0 else None
                    tp_lvl = entry_raw * (1.0 + tp) if tp > 0 else None
                    if sl_lvl is not None and o <= sl_lvl:
                        exit_px = o
                    elif tp_lvl is not None and o >= tp_lvl:
                        exit_px = o
                    elif sl_lvl is not None and l <= sl_lvl:
                        exit_px = sl_lvl
                    elif tp_lvl is not None and h >= tp_lvl:
                        exit_px = tp_lvl
                else:
                    sl_lvl = entry_raw * (1.0 + sl) if sl > 0 else None
                    tp_lvl = entry_raw * (1.0 - tp) if tp > 0 else None
                    if sl_lvl is not None and o >= sl_lvl:
                        exit_px = o
                    elif tp_lvl is not None and o <= tp_lvl:
                        exit_px = o
                    elif sl_lvl is not None and h >= sl_lvl:
                        exit_px = sl_lvl
                    elif tp_lvl is not None and l <= tp_lvl:
                        exit_px = tp_lvl
            if exit_px is None and opt.time_stop_bars > 0 and bars_in >= opt.time_stop_bars:
                exit_px = c
            if exit_px is not None:
                side = pos
                close_trade(exit_px, j)
                blocked = side
            else:
                cur_eq = max(eq_entry * (1.0 + pos * (c / entry_net - 1.0)), 0.0)
        eq[j] = cur_eq

    if pos != 0:
        close_trade(c_[-1], n - 1)
        eq[-1] = cur_eq

    # ---- bar-level max drawdown
    peak = 0.0
    max_dd = 0.0
    for v in eq:
        peak = max(peak, v)
        if peak > 0:
            max_dd = max(max_dd, 1.0 - v / peak)

    # ---- daily aggregation (UTC)
    last_eq: dict[int, float] = {}
    last_px: dict[int, float] = {}
    for i in range(n):
        d = series.t[i] // DAY_MS
        last_eq[d] = eq[i]
        last_px[d] = c_[i]
    d0, d1 = min(last_eq), max(last_eq)
    daily_eq: list[float] = []
    daily_px: list[float] = []
    prev_e, prev_p = 1.0, c_[0]
    for d in range(d0, d1 + 1):
        prev_e = last_eq.get(d, prev_e)
        prev_p = last_px.get(d, prev_p)
        daily_eq.append(prev_e)
        daily_px.append(prev_p)
    rets: list[float] = []
    bh: list[float] = []
    pe, pp = 1.0, c_[0]
    for e, px in zip(daily_eq, daily_px):
        rets.append(e / pe - 1.0 if pe > 0 else 0.0)
        bh.append(px / pp - 1.0 if pp > 0 else 0.0)
        pe, pp = e, px

    ppy = opt.periods_per_year
    total_ret, sharpe, _ = _stats(rets, ppy)
    bh_total = c_[-1] / c_[0] - 1.0
    days = max(len(rets), 1)
    years = days / 365.25
    end_eq = max(eq[-1], 0.0)
    cagr = (end_eq ** (1.0 / years) - 1.0) if (years >= 0.25 and end_eq > 0) else total_ret
    downside = [min(r, 0.0) for r in rets]
    dd_dev = math.sqrt(sum(x * x for x in downside) / len(downside)) if downside else 0.0
    sortino = (statistics.fmean(rets) / dd_dev * math.sqrt(ppy)) if dd_dev > 1e-12 else 0.0
    calmar = (cagr / max_dd) if max_dd > 1e-9 else 0.0

    split_bar = int(n * (1.0 - opt.oos_fraction))
    split_day = series.t[split_bar] // DAY_MS - d0
    is_rets, oos_rets = rets[:split_day], rets[split_day:]
    is_ret, is_sharpe, is_dd = _stats(is_rets, ppy)
    oos_ret, oos_sharpe, oos_dd = _stats(oos_rets, ppy)
    beta, corr = _beta_corr(rets, bh)

    tr_rets = [t[3] for t in trades]
    wins = [r for r in tr_rets if r > 0]
    losses = [r for r in tr_rets if r < 0]
    gross_w, gross_l = sum(wins), -sum(losses)
    profit_factor = (gross_w / gross_l) if gross_l > 1e-12 else (999.0 if gross_w > 0 else 0.0)
    avg_hold_bars = statistics.fmean([t[1] - t[0] for t in trades]) if trades else 0.0
    long_n = sum(1 for t in trades if t[2] == 1)

    metrics: dict[str, Any] = {
        "total_return_pct": round(total_ret * 100.0, 4),
        "cagr_pct": round(cagr * 100.0, 4),
        "max_drawdown_pct": round(max_dd * 100.0, 4),
        "sharpe_daily_ann": round(sharpe, 4),
        "sortino_daily_ann": round(sortino, 4),
        "calmar_ratio": round(calmar, 4),
        "psr_vs_zero": round(_psr(rets), 4),
        "daily_sharpe_raw": round((statistics.fmean(rets) / statistics.pstdev(rets)) if len(rets) > 1 and statistics.pstdev(rets) > 1e-12 else 0.0, 6),
        "trades": len(trades),
        "long_trades": long_n,
        "short_trades": len(trades) - long_n,
        "win_rate_pct": round(len(wins) / len(trades) * 100.0, 2) if trades else 0.0,
        "profit_factor": round(profit_factor, 4),
        "avg_trade_pct": round(statistics.fmean(tr_rets) * 100.0, 4) if tr_rets else 0.0,
        "avg_hold_bars": round(avg_hold_bars, 2),
        "exposure_pct": round(exposure_bars / (n - 1) * 100.0, 2),
        "buy_hold_return_pct": round(bh_total * 100.0, 4),
        "excess_vs_buy_hold_pct": round((total_ret - bh_total) * 100.0, 4),
        "beta_to_underlying": round(beta, 4),
        "corr_to_underlying": round(corr, 4),
        "is_return_pct": round(is_ret * 100.0, 4),
        "is_sharpe_ann": round(is_sharpe, 4),
        "is_max_drawdown_pct": round(is_dd * 100.0, 4),
        "oos_return_pct": round(oos_ret * 100.0, 4),
        "oos_sharpe_ann": round(oos_sharpe, 4),
        "oos_max_drawdown_pct": round(oos_dd * 100.0, 4),
        "oos_fraction": opt.oos_fraction,
        "oos_days": len(oos_rets),
        "initial_capital": opt.initial_capital,
        "ending_equity_usd": round(opt.initial_capital * end_eq, 2),
        "cost_bps_per_side": opt.cost_bps_per_side,
        "sl_pct": opt.sl_pct,
        "tp_pct": opt.tp_pct,
        "time_stop_bars": opt.time_stop_bars,
        "liquidated": bool(end_eq <= 0.0),
    }
    daily_series = {
        "start_date": _iso(series.t[0]),
        "strategy_bp": [int(round(r * 10_000.0)) for r in rets],
        "underlying_bp": [int(round(r * 10_000.0)) for r in bh],
        "oos_start_index": max(split_day, 0),
    }
    return AlphaResult(
        symbol=symbol,
        timeframe=timeframe,
        direction=direction,
        bar_count=n,
        start_utc=_iso(series.t[0]),
        end_utc=_iso(series.t[-1]),
        days_covered=float(len(rets)),
        metrics=metrics,
        daily_series=daily_series,
    )
