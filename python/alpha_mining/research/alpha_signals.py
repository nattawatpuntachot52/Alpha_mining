"""Causal directional Alpha signal families for the Daily Alpha Mining Factory.

Every family returns ``desired[i] in {-1, 0, +1}``: the position the strategy WANTS to hold during
bar ``i + 1`` using ONLY information available at the close of bar ``i`` (zero lookahead). The
backtest engine fills it at the open of bar ``i + 1``. Causality is enforced by a unit test that
truncates the series and verifies the prefix of the signal never changes.

Families (all multi-timeframe, usable on XAUUSD and ETHUSDT):
    momentum_roc, ma_cross, heiken_ma_cross, donchian_breakout, session_time, impulse_efficiency,
    ibs_reversion, rsi_reversion, rsi_regime, bollinger_reversion, vol_expansion_breakout,
    asia_range_breakout, calendar_turn
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Sequence

NAN = float("nan")
DAY_MS = 86_400_000
HOUR_MS = 3_600_000

TIMEFRAME_MS: dict[str, int] = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}

DIRECTIONS = ("long_only", "short_only", "long_short")


class AlphaSpecError(ValueError):
    """Raised for an invalid alpha strategy spec."""


@dataclass(frozen=True)
class Series:
    """Struct-of-arrays OHLC series (UTC bar open times in ms)."""

    t: tuple[int, ...]
    o: tuple[float, ...]
    h: tuple[float, ...]
    l: tuple[float, ...]
    c: tuple[float, ...]
    tf_ms: int

    def __len__(self) -> int:
        return len(self.c)

    @staticmethod
    def from_bars(bars: Sequence[Any], tf_ms: int) -> "Series":
        return Series(
            t=tuple(int(b.open_time_ms) for b in bars),
            o=tuple(float(b.open) for b in bars),
            h=tuple(float(b.high) for b in bars),
            l=tuple(float(b.low) for b in bars),
            c=tuple(float(b.close) for b in bars),
            tf_ms=int(tf_ms),
        )

    def truncate(self, n: int) -> "Series":
        return Series(self.t[:n], self.o[:n], self.h[:n], self.l[:n], self.c[:n], self.tf_ms)


# --------------------------------------------------------------------------- indicators


def sma(vals: Sequence[float], n: int) -> list[float]:
    out = [NAN] * len(vals)
    if n < 1:
        raise AlphaSpecError("sma period must be >= 1")
    s = 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(vals: Sequence[float], n: int) -> list[float]:
    out = [NAN] * len(vals)
    if n < 1:
        raise AlphaSpecError("ema period must be >= 1")
    if not vals:
        return out
    a = 2.0 / (n + 1.0)
    cur = vals[0]
    for i, v in enumerate(vals):
        cur = v if i == 0 else a * v + (1.0 - a) * cur
        if i >= n - 1:
            out[i] = cur
    return out


def rolling_std(vals: Sequence[float], n: int) -> list[float]:
    out = [NAN] * len(vals)
    s = 0.0
    s2 = 0.0
    for i, v in enumerate(vals):
        s += v
        s2 += v * v
        if i >= n:
            old = vals[i - n]
            s -= old
            s2 -= old * old
        if i >= n - 1:
            m = s / n
            var = max(s2 / n - m * m, 0.0)
            out[i] = math.sqrt(var)
    return out


def prev_window_extreme(vals: Sequence[float], n: int, *, is_max: bool) -> list[float]:
    """Extreme of ``vals[i-n .. i-1]`` (previous n bars, excluding bar i)."""
    out = [NAN] * len(vals)
    dq: deque[int] = deque()
    for i in range(len(vals)):
        # window for i is [i-n, i-1]
        while dq and dq[0] < i - n:
            dq.popleft()
        if i >= n and dq:
            out[i] = vals[dq[0]]
        # push i for future windows
        if is_max:
            while dq and vals[dq[-1]] <= vals[i]:
                dq.pop()
        else:
            while dq and vals[dq[-1]] >= vals[i]:
                dq.pop()
        dq.append(i)
    return out


def true_range(h: Sequence[float], l: Sequence[float], c: Sequence[float]) -> list[float]:
    tr = [h[0] - l[0]] if h else []
    for i in range(1, len(c)):
        tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    return tr


def atr_wilder(h: Sequence[float], l: Sequence[float], c: Sequence[float], n: int) -> list[float]:
    tr = true_range(h, l, c)
    out = [NAN] * len(tr)
    if len(tr) < n:
        return out
    cur = sum(tr[:n]) / n
    out[n - 1] = cur
    for i in range(n, len(tr)):
        cur = (cur * (n - 1) + tr[i]) / n
        out[i] = cur
    return out


def rsi_wilder(c: Sequence[float], n: int) -> list[float]:
    out = [NAN] * len(c)
    if len(c) <= n:
        return out
    gain = 0.0
    loss = 0.0
    for i in range(1, n + 1):
        d = c[i] - c[i - 1]
        gain += max(d, 0.0)
        loss += max(-d, 0.0)
    avg_g = gain / n
    avg_l = loss / n
    out[n] = 100.0 if avg_l == 0 else 100.0 - 100.0 / (1.0 + avg_g / avg_l)
    for i in range(n + 1, len(c)):
        d = c[i] - c[i - 1]
        avg_g = (avg_g * (n - 1) + max(d, 0.0)) / n
        avg_l = (avg_l * (n - 1) + max(-d, 0.0)) / n
        out[i] = 100.0 if avg_l == 0 else 100.0 - 100.0 / (1.0 + avg_g / avg_l)
    return out


def heiken_ashi_close_open(s: Series) -> tuple[list[float], list[float]]:
    ha_c = [(s.o[i] + s.h[i] + s.l[i] + s.c[i]) / 4.0 for i in range(len(s))]
    ha_o = [0.0] * len(s)
    for i in range(len(s)):
        ha_o[i] = (s.o[i] + s.c[i]) / 2.0 if i == 0 else (ha_o[i - 1] + ha_c[i - 1]) / 2.0
    return ha_c, ha_o


# --------------------------------------------------------------------------- calendar helpers


def _next_bar_epoch_days_hours(s: Series) -> tuple[list[int], list[int]]:
    """Epoch-day index and UTC hour of the NEXT bar's open (the bar the decision applies to)."""
    days: list[int] = []
    hours: list[int] = []
    for t in s.t:
        nt = t + s.tf_ms
        days.append(nt // DAY_MS)
        hours.append((nt // HOUR_MS) % 24)
    return days, hours


_DATE_CACHE: dict[int, date] = {}


def _date_of_epoch_day(d: int) -> date:
    cached = _DATE_CACHE.get(d)
    if cached is None:
        cached = date.fromordinal(d + 719163)
        _DATE_CACHE[d] = cached
    return cached


def _weekday_of_epoch_day(d: int) -> int:
    return (d + 3) % 7  # Monday=0 ... Sunday=6 (1970-01-01 was a Thursday)


def _in_hour_window(hour: int, start: int, end: int) -> bool:
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


# --------------------------------------------------------------------------- family helpers


def _p(p: dict[str, Any], key: str, default: Any, cast: Callable[[Any], Any] = float) -> Any:
    val = p.get(key, default)
    try:
        out = cast(val)
    except (TypeError, ValueError) as exc:
        raise AlphaSpecError(f"invalid parameter {key}={val!r}") from exc
    if isinstance(out, float) and not math.isfinite(out):
        raise AlphaSpecError(f"non-finite parameter {key}={val!r}")
    return out


def _finite(*xs: float) -> bool:
    return all(not math.isnan(x) for x in xs)


def _state_cross(
    fast: Sequence[float],
    slow: Sequence[float],
    allow_long: bool,
    allow_short: bool,
    block_entry_weekdays: Sequence[int],
    next_days: Sequence[int],
) -> list[int]:
    """Event-based crossover machine (MT5-faithful): act only on a fast/slow cross.

    Cross up   -> close short; open long if allowed and the next bar's weekday is not blocked.
    Cross down -> close long;  open short if allowed and the next bar's weekday is not blocked.
    Blocked-weekday entries stay flat until the next cross (they are NOT re-attempted).
    """
    n = len(fast)
    out = [0] * n
    pos = 0
    prev_state = 0
    blocked = set(int(x) for x in block_entry_weekdays)
    for i in range(n):
        f, s_ = fast[i], slow[i]
        if _finite(f, s_):
            state = 1 if f > s_ else (-1 if f < s_ else prev_state)
            if prev_state != 0 and state != prev_state:
                day_blocked = bool(blocked) and _weekday_of_epoch_day(next_days[i]) in blocked
                if state == 1:
                    pos = 1 if (allow_long and not day_blocked) else 0
                else:
                    pos = -1 if (allow_short and not day_blocked) else 0
            prev_state = state
        out[i] = pos
    return out


# --------------------------------------------------------------------------- families


def sig_momentum_roc(s: Series, p: dict[str, Any], allow_long: bool, allow_short: bool) -> list[int]:
    k = _p(p, "lookback", 14, int)
    thr = _p(p, "threshold_pct", 0.0) / 100.0
    if k < 1:
        raise AlphaSpecError("lookback must be >= 1")
    c = s.c
    out = [0] * len(c)
    for i in range(k, len(c)):
        roc = c[i] / c[i - k] - 1.0
        if roc > thr and allow_long:
            out[i] = 1
        elif roc < -thr and allow_short:
            out[i] = -1
    return out


def _ma(kind: str, vals: Sequence[float], n: int) -> list[float]:
    if kind == "sma":
        return sma(vals, n)
    if kind == "ema":
        return ema(vals, n)
    raise AlphaSpecError(f"unknown ma kind {kind!r}")


def sig_ma_cross(s: Series, p: dict[str, Any], allow_long: bool, allow_short: bool) -> list[int]:
    kind = str(p.get("ma", "sma")).lower()
    fast_n = _p(p, "fast", 20, int)
    slow_n = _p(p, "slow", 50, int)
    if fast_n >= slow_n:
        raise AlphaSpecError("fast must be < slow")
    fast = _ma(kind, s.c, fast_n)
    slow = _ma(kind, s.c, slow_n)
    nd, _ = _next_bar_epoch_days_hours(s)
    return _state_cross(fast, slow, allow_long, allow_short, list(p.get("block_entry_weekdays", [])), nd)


def sig_heiken_ma_cross(s: Series, p: dict[str, Any], allow_long: bool, allow_short: bool) -> list[int]:
    kind = str(p.get("ma", "sma")).lower()
    fast_n = _p(p, "fast", 12, int)
    slow_n = _p(p, "slow", 26, int)
    if fast_n >= slow_n:
        raise AlphaSpecError("fast must be < slow")
    ha_c, _ = heiken_ashi_close_open(s)
    fast = _ma(kind, ha_c, fast_n)
    slow = _ma(kind, ha_c, slow_n)
    nd, _ = _next_bar_epoch_days_hours(s)
    return _state_cross(fast, slow, allow_long, allow_short, list(p.get("block_entry_weekdays", [])), nd)


def sig_donchian_breakout(s: Series, p: dict[str, Any], allow_long: bool, allow_short: bool) -> list[int]:
    entry_n = _p(p, "entry", 40, int)
    exit_n = _p(p, "exit", 10, int)
    atr_n = _p(p, "atr_period", 14, int)
    squeeze = _p(p, "squeeze_ratio", 0.0)
    if entry_n < 2 or exit_n < 1:
        raise AlphaSpecError("entry must be >= 2 and exit >= 1")
    hh = prev_window_extreme(s.h, entry_n, is_max=True)
    ll = prev_window_extreme(s.l, entry_n, is_max=False)
    xh = prev_window_extreme(s.h, exit_n, is_max=True)
    xl = prev_window_extreme(s.l, exit_n, is_max=False)
    atr_fast = atr_wilder(s.h, s.l, s.c, atr_n) if squeeze > 0 else []
    atr_slow = sma(atr_fast, atr_n * 4) if squeeze > 0 else []
    c = s.c
    out = [0] * len(c)
    pos = 0
    for i in range(len(c)):
        if not _finite(hh[i], ll[i], xh[i], xl[i]):
            continue
        if pos == 1 and c[i] < xl[i]:
            pos = 0
        elif pos == -1 and c[i] > xh[i]:
            pos = 0
        if pos == 0:
            ok = True
            if squeeze > 0:
                a, b = atr_fast[i - 1] if i else NAN, atr_slow[i - 1] if i else NAN
                ok = _finite(a, b) and b > 0 and a <= squeeze * b
            if ok and allow_long and c[i] > hh[i]:
                pos = 1
            elif ok and allow_short and c[i] < ll[i]:
                pos = -1
        out[i] = pos
    return out


def sig_session_time(s: Series, p: dict[str, Any], allow_long: bool, allow_short: bool) -> list[int]:
    start = _p(p, "start_hour_utc", 20, int) % 24
    end = _p(p, "end_hour_utc", 4, int) % 24
    mode = str(p.get("mode", "long_inside"))
    weekdays = set(int(x) for x in p.get("weekdays", []))
    if mode not in {"long_inside", "short_inside", "long_inside_short_outside"}:
        raise AlphaSpecError(f"unknown session mode {mode!r}")
    days, hours = _next_bar_epoch_days_hours(s)
    out = [0] * len(s)
    for i in range(len(s)):
        inside = _in_hour_window(hours[i], start, end)
        if weekdays and _weekday_of_epoch_day(days[i]) not in weekdays:
            inside = False
        if mode == "long_inside":
            out[i] = 1 if inside else 0
        elif mode == "short_inside":
            out[i] = -1 if inside else 0
        else:
            out[i] = 1 if inside else -1
        if out[i] == 1 and not allow_long:
            out[i] = 0
        if out[i] == -1 and not allow_short:
            out[i] = 0
    return out


def sig_impulse_efficiency(s: Series, p: dict[str, Any], allow_long: bool, allow_short: bool) -> list[int]:
    k = _p(p, "k", 3, int)
    w = _p(p, "w", 20, int)
    z_th = _p(p, "z_threshold", 2.0)
    er_th = _p(p, "er_threshold", 0.75)
    hold = _p(p, "hold_bars", 12, int)
    mode = str(p.get("mode", "continuation"))
    if mode not in {"continuation", "reversal"}:
        raise AlphaSpecError(f"unknown impulse mode {mode!r}")
    c = s.c
    n = len(c)
    ret1 = [0.0] * n
    for i in range(1, n):
        ret1[i] = math.log(c[i] / c[i - 1]) if c[i - 1] > 0 and c[i] > 0 else 0.0
    absd = [0.0] * n
    for i in range(1, n):
        absd[i] = abs(c[i] - c[i - 1])
    out = [0] * n
    remaining = 0
    side = 0
    cum_abs = [0.0] * n
    run = 0.0
    for i in range(n):
        run += absd[i]
        cum_abs[i] = run
    for i in range(k + w, n):
        # pre-move volatility uses bars strictly BEFORE the impulse window: (i-k-w, i-k]
        seg = ret1[i - k - w + 1 : i - k + 1]
        rms = math.sqrt(sum(x * x for x in seg) / w)
        move = math.log(c[i] / c[i - k]) if c[i - k] > 0 else 0.0
        path = cum_abs[i] - cum_abs[i - k]
        er = abs(c[i] - c[i - k]) / path if path > 0 else 0.0
        z = move / (rms * math.sqrt(k)) if rms > 0 else 0.0
        if abs(z) >= z_th and er >= er_th:
            direction = 1 if z > 0 else -1
            if mode == "reversal":
                direction = -direction
            if (direction == 1 and allow_long) or (direction == -1 and allow_short):
                side = direction
                remaining = hold
        if remaining > 0:
            out[i] = side
            remaining -= 1
    return out


def sig_ibs_reversion(s: Series, p: dict[str, Any], allow_long: bool, allow_short: bool) -> list[int]:
    low_th = _p(p, "low_threshold", 0.2)
    high_th = _p(p, "high_threshold", 0.8)
    exit_long = _p(p, "exit_long", 0.7)
    exit_short = _p(p, "exit_short", 0.3)
    trend_n = _p(p, "trend_sma", 0, int)
    max_hold = _p(p, "max_hold", 10, int)
    trend = sma(s.c, trend_n) if trend_n > 0 else []
    out = [0] * len(s)
    pos = 0
    held = 0
    for i in range(len(s)):
        rng = s.h[i] - s.l[i]
        ibs = (s.c[i] - s.l[i]) / rng if rng > 0 else 0.5
        if pos != 0:
            held += 1
            if (pos == 1 and ibs >= exit_long) or (pos == -1 and ibs <= exit_short) or held >= max_hold:
                pos = 0
        if pos == 0:
            ok_trend_long = ok_trend_short = True
            if trend_n > 0:
                if math.isnan(trend[i]):
                    ok_trend_long = ok_trend_short = False
                else:
                    ok_trend_long = s.c[i] > trend[i]
                    ok_trend_short = s.c[i] < trend[i]
            if allow_long and ibs <= low_th and ok_trend_long:
                pos, held = 1, 0
            elif allow_short and ibs >= high_th and ok_trend_short:
                pos, held = -1, 0
        out[i] = pos
    return out


def sig_rsi_reversion(s: Series, p: dict[str, Any], allow_long: bool, allow_short: bool) -> list[int]:
    n = _p(p, "period", 14, int)
    buy_below = _p(p, "buy_below", 30.0)
    sell_above = _p(p, "sell_above", 70.0)
    exit_long = _p(p, "exit_long", 50.0)
    exit_short = _p(p, "exit_short", 50.0)
    rsi = rsi_wilder(s.c, n)
    out = [0] * len(s)
    pos = 0
    for i in range(len(s)):
        r = rsi[i]
        if math.isnan(r):
            continue
        if pos == 1 and r >= exit_long:
            pos = 0
        elif pos == -1 and r <= exit_short:
            pos = 0
        if pos == 0:
            if allow_long and r <= buy_below:
                pos = 1
            elif allow_short and r >= sell_above:
                pos = -1
        out[i] = pos
    return out


def sig_rsi_regime(s: Series, p: dict[str, Any], allow_long: bool, allow_short: bool) -> list[int]:
    n = _p(p, "period", 14, int)
    hi = _p(p, "upper", 55.0)
    mid = _p(p, "mid", 50.0)
    lo = _p(p, "lower", 45.0)
    rsi = rsi_wilder(s.c, n)
    out = [0] * len(s)
    pos = 0
    for i in range(len(s)):
        r = rsi[i]
        if math.isnan(r):
            continue
        if pos == 1 and r < mid:
            pos = 0
        elif pos == -1 and r > mid:
            pos = 0
        if pos == 0:
            if allow_long and r > hi:
                pos = 1
            elif allow_short and r < lo:
                pos = -1
        out[i] = pos
    return out


def sig_bollinger_reversion(s: Series, p: dict[str, Any], allow_long: bool, allow_short: bool) -> list[int]:
    n = _p(p, "period", 20, int)
    k = _p(p, "k", 2.0)
    exit_z = _p(p, "exit_z", 0.0)
    mean = sma(s.c, n)
    sd = rolling_std(s.c, n)
    out = [0] * len(s)
    pos = 0
    for i in range(len(s)):
        if not _finite(mean[i], sd[i]) or sd[i] <= 0:
            continue
        z = (s.c[i] - mean[i]) / sd[i]
        if pos == 1 and z >= exit_z:
            pos = 0
        elif pos == -1 and z <= -exit_z:
            pos = 0
        if pos == 0:
            if allow_long and z <= -k:
                pos = 1
            elif allow_short and z >= k:
                pos = -1
        out[i] = pos
    return out


def sig_vol_expansion_breakout(s: Series, p: dict[str, Any], allow_long: bool, allow_short: bool) -> list[int]:
    n = _p(p, "atr_period", 14, int)
    k = _p(p, "k_atr", 1.5)
    hold = _p(p, "hold_bars", 6, int)
    atr = atr_wilder(s.h, s.l, s.c, n)
    out = [0] * len(s)
    remaining = 0
    side = 0
    for i in range(1, len(s)):
        a = atr[i - 1]
        if not math.isnan(a) and a > 0:
            d = s.c[i] - s.c[i - 1]
            if d > k * a and allow_long:
                side, remaining = 1, hold
            elif d < -k * a and allow_short:
                side, remaining = -1, hold
        if remaining > 0:
            out[i] = side
            remaining -= 1
    return out


def sig_asia_range_breakout(s: Series, p: dict[str, Any], allow_long: bool, allow_short: bool) -> list[int]:
    r0 = _p(p, "range_start_hour_utc", 0, int)
    r1 = _p(p, "range_end_hour_utc", 7, int)
    eod = _p(p, "eod_hour_utc", 20, int)
    max_range_pct = _p(p, "max_range_pct", 0.0) / 100.0
    if not (0 <= r0 < r1 <= eod <= 24):
        raise AlphaSpecError("require 0 <= range_start < range_end <= eod <= 24 (same UTC day)")
    out = [0] * len(s)
    cur_day = -1
    hi = NAN
    lo = NAN
    pos = 0
    traded = False
    for i in range(len(s)):
        t_ = s.t[i]
        day = t_ // DAY_MS
        hour = (t_ // HOUR_MS) % 24
        if day != cur_day:
            cur_day, hi, lo, pos, traded = day, NAN, NAN, 0, False
        if r0 <= hour < r1:
            hi = s.h[i] if math.isnan(hi) else max(hi, s.h[i])
            lo = s.l[i] if math.isnan(lo) else min(lo, s.l[i])
        nxt = t_ + s.tf_ms
        next_day = nxt // DAY_MS
        next_hour = (nxt // HOUR_MS) % 24
        if next_day != day or next_hour >= eod or next_hour < r1:
            pos = 0
            out[i] = 0
            continue
        if pos == 0 and not traded and hour >= r1 and _finite(hi, lo):
            width_ok = max_range_pct <= 0 or (hi - lo) / s.c[i] <= max_range_pct
            if width_ok:
                if allow_long and s.c[i] > hi:
                    pos, traded = 1, True
                elif allow_short and s.c[i] < lo:
                    pos, traded = -1, True
        out[i] = pos
    return out


def sig_calendar_turn(s: Series, p: dict[str, Any], allow_long: bool, allow_short: bool) -> list[int]:
    ranges = [tuple(int(x) for x in r) for r in p.get("days_of_month", [])]
    weekdays = set(int(x) for x in p.get("weekdays", []))
    side = -1 if str(p.get("side", "long")).lower() == "short" else 1
    if side == 1 and not allow_long:
        return [0] * len(s)
    if side == -1 and not allow_short:
        return [0] * len(s)
    if not ranges and not weekdays:
        raise AlphaSpecError("calendar_turn needs days_of_month and/or weekdays")
    days, _ = _next_bar_epoch_days_hours(s)
    out = [0] * len(s)
    for i in range(len(s)):
        d = _date_of_epoch_day(days[i])
        ok_dom = True
        if ranges:
            ok_dom = any((a <= d.day <= b) if a <= b else (d.day >= a or d.day <= b) for a, b in ranges)
        ok_wd = (not weekdays) or (_weekday_of_epoch_day(days[i]) in weekdays)
        out[i] = side if (ok_dom and ok_wd) else 0
    return out


FAMILIES: dict[str, Callable[[Series, dict[str, Any], bool, bool], list[int]]] = {
    "momentum_roc": sig_momentum_roc,
    "ma_cross": sig_ma_cross,
    "heiken_ma_cross": sig_heiken_ma_cross,
    "donchian_breakout": sig_donchian_breakout,
    "session_time": sig_session_time,
    "impulse_efficiency": sig_impulse_efficiency,
    "ibs_reversion": sig_ibs_reversion,
    "rsi_reversion": sig_rsi_reversion,
    "rsi_regime": sig_rsi_regime,
    "bollinger_reversion": sig_bollinger_reversion,
    "vol_expansion_breakout": sig_vol_expansion_breakout,
    "asia_range_breakout": sig_asia_range_breakout,
    "calendar_turn": sig_calendar_turn,
}


def build_positions(series: Series, family: str, params: dict[str, Any], direction: str) -> list[int]:
    """Compute the causal desired-position vector for a spec."""
    fn = FAMILIES.get(family)
    if fn is None:
        raise AlphaSpecError(f"unknown signal family {family!r}; known: {sorted(FAMILIES)}")
    if direction not in DIRECTIONS:
        raise AlphaSpecError(f"invalid direction {direction!r}; expected one of {DIRECTIONS}")
    allow_long = direction in {"long_only", "long_short"}
    allow_short = direction in {"short_only", "long_short"}
    pos = fn(series, dict(params), allow_long, allow_short)
    if len(pos) != len(series):
        raise AlphaSpecError(f"family {family} returned {len(pos)} signals for {len(series)} bars")
    return pos
