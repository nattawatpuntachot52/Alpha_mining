"""Pure deterministic LGB154 V3 strategy math and pluggable SignalProvider interface.

Maintains 1:1 Decimal parity with Binance LGB154 Python V3 (`STRATEGY_PARITY.md`) across:
- Descending geometric grid levels rounded DOWN to tick size, low-inclusive.
- Within-spacing proximity checks (`abs(a - b) < min(a, b) * pct / 100 - tick * 0.01`).
- Closed-candle Heikin-Ashi (`+1` GREEN, `-1` RED, `0` NEUTRAL) with zero lookahead.
- Partial-fill recovery sizing (`missing_qty` never subtracts sells).
- USD-M (`PROFIT_PLUS_COMMISSION` and `NET`) and COIN-M Inverse (`NET` ETH basis) TP pricing.
- Pluggable `SignalProvider` interface so alternative closed-bar signals (EMA Cross,
  RSI Regime, Supertrend, or custom user callables) can be A/B tested on the exact same
  grid, inventory, fee, funding, and risk engine.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Any, Callable, Mapping, Protocol, Sequence

ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")


def to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ValueError(f"boolean is not a valid Decimal: {value!r}")
    return Decimal(str(value))


def round_down(value: Any, step: Any) -> Decimal:
    d_val = to_decimal(value)
    d_step = to_decimal(step)
    if d_step <= ZERO:
        raise ValueError(f"step must be positive, got {step!r}")
    return (d_val / d_step).to_integral_value(rounding=ROUND_FLOOR) * d_step


def round_up(value: Any, step: Any) -> Decimal:
    d_val = to_decimal(value)
    d_step = to_decimal(step)
    if d_step <= ZERO:
        raise ValueError(f"step must be positive, got {step!r}")
    return (d_val / d_step).to_integral_value(rounding=ROUND_CEILING) * d_step


def build_grid_levels(
    high: Any,
    low: Any,
    spacing_pct: Any,
    tick: Any,
    *,
    limit: int = 100_000,
) -> tuple[tuple[int, Decimal], ...]:
    """Generate descending geometric grid levels rounded down to tick, inclusive of low."""
    d_high = to_decimal(high)
    d_low = to_decimal(low)
    d_spacing = to_decimal(spacing_pct)
    d_tick = to_decimal(tick)
    if d_low <= ZERO or d_high <= d_low or not (ZERO < d_spacing < HUNDRED):
        raise ValueError(f"invalid grid parameters: high={high}, low={low}, spacing_pct={spacing_pct}")
    ratio = ONE - d_spacing / HUNDRED
    levels: list[tuple[int, Decimal]] = []
    price = d_high
    for idx in range(limit):
        if price < d_low:
            return tuple(levels)
        levels.append((idx, round_down(price, d_tick)))
        price *= ratio
    raise ValueError(f"grid exceeds limit={limit} levels")


def within_spacing(a: Any, b: Any, spacing_pct: Any, tick: Any) -> bool:
    """Exact LGB154 proximity guard preventing overlapping grid orders."""
    d_a = to_decimal(a)
    d_b = to_decimal(b)
    d_pct = to_decimal(spacing_pct)
    d_tick = to_decimal(tick)
    lower = min(d_a, d_b)
    return lower <= ZERO or abs(d_a - d_b) < (lower * d_pct / HUNDRED - d_tick * Decimal("0.01"))


def missing_qty(target_qty: Any, cumulative_buy_qty: Any, active_buy_qty: Any, step: Any) -> Decimal:
    """Partial-fill recovery quantity; never subtracts sells and guards against overbuy."""
    raw = to_decimal(target_qty) - to_decimal(cumulative_buy_qty) - to_decimal(active_buy_qty)
    return round_down(max(ZERO, raw), step)


def ha_closed_decimal_window(candles: Sequence[Mapping[str, Any]], lookback: int = 200) -> int:
    """Reference exact-Decimal Heikin-Ashi signal from LGB154 V3 (`bot.py::ha_closed`).

    Expects `candles` in ascending time order where the FINAL element is the current
    unclosed bar (`candles[-lookback:-1]` evaluates strictly closed bars only).
    """
    if len(candles) < 5:
        return 0
    closed = candles[-lookback:-1]
    ho: Decimal | None = None
    hc: Decimal | None = None
    four = Decimal("4")
    two = Decimal("2")
    for c in closed:
        o = to_decimal(c["open"])
        h = to_decimal(c["high"])
        l = to_decimal(c["low"])
        cl = to_decimal(c["close"])
        nc = (o + h + l + cl) / four
        no = (o + cl) / two if ho is None else (ho + hc) / two  # type: ignore[operator]
        ho, hc = no, nc
    if hc is None or ho is None:
        return 0
    return 1 if hc > ho else (-1 if hc < ho else 0)


@dataclass(frozen=True)
class RpRange:
    """Explicit Risk-Parameter / Bullet budget assigned to a grid index range."""

    from_grid: int
    to_grid: int
    rp_id: str
    max_quantity: Decimal
    max_notional_usdt: Decimal

    def __post_init__(self) -> None:
        if self.from_grid < 0 or self.to_grid < self.from_grid:
            raise ValueError(f"invalid RP grid range [{self.from_grid}, {self.to_grid}]")
        if not self.rp_id.strip():
            raise ValueError("rp_id must be non-empty")
        if self.max_quantity <= ZERO or self.max_notional_usdt <= ZERO:
            raise ValueError("RP max_quantity and max_notional_usdt must be positive")


@dataclass(frozen=True)
class Lgb154Config:
    """Immutable LGB154 V3 strategy configuration (USD-M linear or COIN-M inverse)."""

    bot_id: str = "LGB154V3"
    symbol: str = "ETHUSDT"
    product_type: str = "USD_M"  # "USD_M" | "COIN_M"
    contract_size_usd: Decimal = Decimal("10")  # used only when product_type == "COIN_M"
    high: Decimal = Decimal("2500")
    low: Decimal = Decimal("2000")
    spacing_pct: Decimal = Decimal("0.20")
    tick_size: Decimal = Decimal("0.01")
    step_size: Decimal = Decimal("0.001")
    min_qty: Decimal = Decimal("0.001")
    min_notional: Decimal = Decimal("5")
    order_quantity: Decimal = Decimal("0.01")
    max_entry_order_quantity: Decimal = Decimal("0.01")
    max_entry_order_notional_usdt: Decimal = Decimal("25")
    orders_per_batch: int = 5
    max_position_quantity: Decimal = Decimal("0.40")
    max_notional_usdt: Decimal = Decimal("1000")
    check_global_notional: bool = True
    leverage: Decimal = Decimal("10")
    maintenance_margin_rate: Decimal = Decimal("0.005")
    # Take-profit settings
    tp_pricing_mode: str = "PROFIT_PLUS_COMMISSION"  # "PROFIT_PLUS_COMMISSION" | "NET"
    tp_percent: Decimal = Decimal("0.25")
    commission_buffer_percent: Decimal = Decimal("0.20")
    net_profit_percent: Decimal = Decimal("0.25")
    require_ha_red: bool = True
    cancel_tp_when_invalid: bool = True
    # Fee & funding settings
    maker_fee_rate: Decimal = Decimal("0.0002")  # 2 bps Binance UM Maker
    taker_fee_rate: Decimal = Decimal("0.0005")  # 5 bps Binance UM Taker
    fallback_exit_fee_percent: Decimal = Decimal("0.10")
    extra_buffer_percent: Decimal = Decimal("0.01")
    extra_buffer_usdt: Decimal = ZERO
    extra_buffer_eth: Decimal = ZERO
    include_funding_cost: bool = True
    allow_funding_credit_to_reduce_tp: bool = False
    ownership_mode: str = "STRICT"  # "STRICT" | "MANAGED_ONLY"
    # Emergency whole-account guards (0 = disabled, matching settings.live.json)
    max_loss_usdt: Decimal = ZERO
    equity_target_usdt: Decimal = ZERO
    rp_ranges: tuple[RpRange, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.product_type not in {"USD_M", "COIN_M"}:
            raise ValueError(f"unsupported product_type: {self.product_type!r}")
        if self.tp_pricing_mode not in {"PROFIT_PLUS_COMMISSION", "NET"}:
            raise ValueError(f"unsupported tp_pricing_mode: {self.tp_pricing_mode!r}")
        if self.product_type == "COIN_M" and self.tp_pricing_mode != "NET":
            raise ValueError("COIN_M requires tp_pricing_mode='NET'")
        if self.orders_per_batch < 1:
            raise ValueError("orders_per_batch must be >= 1")
        if self.leverage <= ZERO:
            raise ValueError("leverage must be positive")
        if self.maker_fee_rate < ZERO or self.taker_fee_rate < ZERO:
            raise ValueError("fee rates must be non-negative")
        levels = build_grid_levels(self.high, self.low, self.spacing_pct, self.tick_size)
        if not levels:
            raise ValueError("grid produced 0 levels")
        if not self.rp_ranges:
            default_rp = RpRange(
                from_grid=0,
                to_grid=levels[-1][0],
                rp_id="RP001",
                max_quantity=self.max_position_quantity,
                max_notional_usdt=self.max_notional_usdt,
            )
            object.__setattr__(self, "rp_ranges", (default_rp,))

    @property
    def is_coinm(self) -> bool:
        return self.product_type == "COIN_M"

    def quote_notional(self, qty: Decimal, price: Decimal) -> Decimal:
        if self.is_coinm:
            return qty * self.contract_size_usd
        return qty * price

    def rp_rule_for_grid(self, grid: int) -> RpRange:
        matches = [r for r in self.rp_ranges if r.from_grid <= grid <= r.to_grid]
        if len(matches) != 1:
            raise ValueError(f"grid {grid} matched {len(matches)} RP rules; unique mapping required")
        return matches[0]

    @classmethod
    def ethusdt_usdm_default(cls) -> Lgb154Config:
        """Exact parameters from LGB154 V3 `settings.live.json` (ETHUSDT USD-M)."""
        return cls(
            bot_id="LGB154V3",
            symbol="ETHUSDT",
            product_type="USD_M",
            high=Decimal("2500"),
            low=Decimal("2000"),
            spacing_pct=Decimal("0.20"),
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.001"),
            min_qty=Decimal("0.001"),
            min_notional=Decimal("5"),
            order_quantity=Decimal("0.01"),
            max_entry_order_quantity=Decimal("0.01"),
            max_entry_order_notional_usdt=Decimal("25"),
            orders_per_batch=5,
            max_position_quantity=Decimal("0.40"),
            max_notional_usdt=Decimal("1000"),
            check_global_notional=False,
            leverage=Decimal("10"),
            tp_pricing_mode="PROFIT_PLUS_COMMISSION",
            tp_percent=Decimal("0.25"),
            commission_buffer_percent=Decimal("0.20"),
            net_profit_percent=Decimal("0.25"),
            require_ha_red=True,
            cancel_tp_when_invalid=True,
            maker_fee_rate=Decimal("0.0002"),
            taker_fee_rate=Decimal("0.0005"),
            fallback_exit_fee_percent=Decimal("0.10"),
            extra_buffer_percent=Decimal("0.01"),
            include_funding_cost=True,
            allow_funding_credit_to_reduce_tp=False,
            ownership_mode="MANAGED_ONLY",
            rp_ranges=(
                RpRange(
                    from_grid=0,
                    to_grid=111,
                    rp_id="RP001",
                    max_quantity=Decimal("0.40"),
                    max_notional_usdt=Decimal("1000"),
                ),
            ),
        )

    @classmethod
    def ethusd_coinm_default(cls) -> Lgb154Config:
        """Exact parameters from LGB154 V3 `settings.coinm.live.json` (ETHUSD_PERP COIN-M)."""
        return cls(
            bot_id="ETHCMR3",
            symbol="ETHUSD_PERP",
            product_type="COIN_M",
            contract_size_usd=Decimal("10"),
            high=Decimal("2000"),
            low=Decimal("1500"),
            spacing_pct=Decimal("1"),
            tick_size=Decimal("0.01"),
            step_size=Decimal("1"),
            min_qty=Decimal("1"),
            min_notional=Decimal("10"),
            order_quantity=Decimal("1"),
            max_entry_order_quantity=Decimal("1"),
            max_entry_order_notional_usdt=Decimal("10"),
            orders_per_batch=5,
            max_position_quantity=Decimal("60"),
            max_notional_usdt=Decimal("600"),
            check_global_notional=False,
            leverage=Decimal("10"),
            tp_pricing_mode="NET",
            tp_percent=Decimal("1"),
            commission_buffer_percent=ZERO,
            net_profit_percent=Decimal("1"),
            require_ha_red=True,
            cancel_tp_when_invalid=True,
            maker_fee_rate=Decimal("0.0002"),
            taker_fee_rate=Decimal("0.0005"),
            fallback_exit_fee_percent=Decimal("0.10"),
            extra_buffer_percent=ZERO,
            extra_buffer_usdt=ZERO,
            extra_buffer_eth=ZERO,
            include_funding_cost=True,
            allow_funding_credit_to_reduce_tp=False,
            ownership_mode="MANAGED_ONLY",
            rp_ranges=(
                RpRange(
                    from_grid=0,
                    to_grid=28,
                    rp_id="CMRP001",
                    max_quantity=Decimal("60"),
                    max_notional_usdt=Decimal("600"),
                ),
            ),
        )


def compute_tp_threshold(
    *,
    open_qty: Decimal,
    cost_basis: Decimal,
    entry_fee_open: Decimal,
    funding_open: Decimal,
    cfg: Lgb154Config,
) -> Decimal | None:
    """Compute exact minimum bid threshold before arming a SELL LIMIT TP (1:1 LGB154 V3 parity).

    Note: `cost_basis` is USDT notional sum for USD-M, and ETH basis sum `sum(qty * 10 / price)`
    for COIN-M Inverse.
    """
    if open_qty <= ZERO:
        return None
    if cfg.is_coinm:
        if cfg.tp_pricing_mode != "NET":
            raise ValueError("COIN_M requires NET ETH take profit")
        if cfg.net_profit_percent < ZERO:
            raise ValueError("negative NET target")
        if cfg.include_funding_cost and cfg.ownership_mode != "MANAGED_ONLY":
            fund = funding_open if cfg.allow_funding_credit_to_reduce_tp else min(ZERO, funding_open)
        else:
            fund = ZERO
        entry_fee = max(ZERO, entry_fee_open)
        rate = (cfg.fallback_exit_fee_percent + cfg.extra_buffer_percent) / HUNDRED
        fixed = cfg.extra_buffer_eth
        if rate < ZERO or fixed < ZERO:
            raise ValueError("negative COIN_M fee buffer")
        denom = cost_basis * (ONE - cfg.net_profit_percent / HUNDRED) - entry_fee + fund - fixed
        if denom <= ZERO:
            raise ValueError("inverse TP denominator is nonpositive")
        return open_qty * cfg.contract_size_usd * (ONE + rate) / denom

    if cfg.tp_pricing_mode == "PROFIT_PLUS_COMMISSION":
        if cfg.tp_percent < ZERO or cfg.commission_buffer_percent < ZERO:
            raise ValueError("negative TP/commission markup")
        return (cost_basis / open_qty) * (ONE + (cfg.tp_percent + cfg.commission_buffer_percent) / HUNDRED)

    if cfg.tp_pricing_mode == "NET":
        if cfg.net_profit_percent < ZERO:
            raise ValueError("negative NET target")
        profit = cost_basis * cfg.net_profit_percent / HUNDRED
        if cfg.include_funding_cost:
            fund_credit = funding_open if cfg.allow_funding_credit_to_reduce_tp else min(ZERO, funding_open)
        else:
            fund_credit = ZERO
        fee = max(ZERO, entry_fee_open)
        denom = open_qty * (ONE - (cfg.fallback_exit_fee_percent + cfg.extra_buffer_percent) / HUNDRED)
        if denom <= ZERO:
            raise ValueError("TP denominator is nonpositive")
        return (cost_basis + profit + fee - fund_credit + cfg.extra_buffer_usdt) / denom

    raise ValueError(f"unsupported TP pricing mode: {cfg.tp_pricing_mode!r}")


def compute_net_tp_price(
    *,
    open_qty: Decimal,
    cost_basis: Decimal,
    entry_fee_open: Decimal,
    funding_open: Decimal,
    bid: Decimal,
    cfg: Lgb154Config,
) -> Decimal | None:
    """Exact LGB154 V3 `net_tp_price` returning LIMIT SELL price or None if bid < threshold."""
    threshold = compute_tp_threshold(
        open_qty=open_qty,
        cost_basis=cost_basis,
        entry_fee_open=entry_fee_open,
        funding_open=funding_open,
        cfg=cfg,
    )
    if threshold is None or bid < threshold:
        return None
    return round_up(max(threshold, bid + cfg.tick_size * Decimal("2")), cfg.tick_size)


# =============================================================================
# Pluggable Closed-Bar SignalProvider Interface (Zero-Lookahead Contract)
# =============================================================================


@dataclass(frozen=True, slots=True)
class Bar:
    """Single OHLCV bar in ascending open_time_ms order."""

    open_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    close_time_ms: int = 0


class SignalProvider(Protocol):
    """Strictly causal signal plugin evaluated ONLY on closed bars.

    Contract:
    - `on_closed_bar(bar)` receives the most recently CLOSED bar (`B_{t-1}`) and MUST return:
      `+1` (GREEN: arm/permit BUY grid cycle, cancel SELLs),
      `-1` (RED: cancel pending BUYs, arm/validate conditional TP SELLs), or
      `0` (NEUTRAL: cancel pending BUYs and SELLs, hold filled inventory).
    - Implementations MUST NEVER peek at future bars (`B_t`, `B_{t+1}`, ...).
    """

    @property
    def name(self) -> str: ...

    def reset(self) -> None: ...

    def on_closed_bar(self, bar: Bar) -> int: ...


class HeikinAshiSignal:
    """Baseline LGB154 V3 closed-bar Heikin-Ashi signal (`O(1)` streaming, exact parity).

    Matches `bot.py::ha_closed(candles, lookback=200)` which requires at least 4 closed bars
    (`len(candles) >= 5` including the current unclosed bar) before returning `+1/-1`.
    """

    def __init__(self, *, min_closed_bars: int = 4, name: str = "ha_1m") -> None:
        self._min_closed_bars = max(1, int(min_closed_bars))
        self._name = name
        self._count = 0
        self._ho: float | None = None
        self._hc: float | None = None

    @property
    def name(self) -> str:
        return self._name

    def reset(self) -> None:
        self._count = 0
        self._ho = None
        self._hc = None

    def on_closed_bar(self, bar: Bar) -> int:
        nc = 0.25 * (bar.open + bar.high + bar.low + bar.close)
        if self._ho is None or self._hc is None:
            no = 0.5 * (bar.open + bar.close)
        else:
            no = 0.5 * (self._ho + self._hc)
        self._ho = no
        self._hc = nc
        self._count += 1
        if self._count < self._min_closed_bars:
            return 0
        if nc > no:
            return 1
        if nc < no:
            return -1
        return 0


class EmaCrossSignal:
    """Fast/Slow EMA crossover signal (`+1` when EMA_fast > EMA_slow, `-1` when below)."""

    def __init__(self, fast_period: int = 9, slow_period: int = 21, *, name: str | None = None) -> None:
        if fast_period < 1 or slow_period <= fast_period:
            raise ValueError("require 1 <= fast_period < slow_period")
        self.fast_period = int(fast_period)
        self.slow_period = int(slow_period)
        self._name = name or f"ema_{self.fast_period}_{self.slow_period}"
        self._alpha_fast = 2.0 / (self.fast_period + 1.0)
        self._alpha_slow = 2.0 / (self.slow_period + 1.0)
        self._count = 0
        self._ema_fast: float | None = None
        self._ema_slow: float | None = None

    @property
    def name(self) -> str:
        return self._name

    def reset(self) -> None:
        self._count = 0
        self._ema_fast = None
        self._ema_slow = None

    def on_closed_bar(self, bar: Bar) -> int:
        c = bar.close
        if self._ema_fast is None or self._ema_slow is None:
            self._ema_fast = c
            self._ema_slow = c
        else:
            self._ema_fast = self._alpha_fast * c + (1.0 - self._alpha_fast) * self._ema_fast
            self._ema_slow = self._alpha_slow * c + (1.0 - self._alpha_slow) * self._ema_slow
        self._count += 1
        if self._count < self.slow_period:
            return 0
        if self._ema_fast > self._ema_slow:
            return 1
        if self._ema_fast < self._ema_slow:
            return -1
        return 0


class RsiRegimeSignal:
    """Wilder RSI signal supporting both mean-reversion (`buy_below` / `sell_above`) and trend modes.

    - `mode="reversion"` (default for grids): `+1` when RSI <= `buy_below` (oversold dip),
      `-1` when RSI >= `sell_above` (bounce/overbought TP arm), `0` in neutral band.
    - `mode="trend"`: `+1` when RSI > `sell_above`, `-1` when RSI < `buy_below`, `0` in between.
    """

    def __init__(
        self,
        period: int = 14,
        *,
        buy_below: float = 40.0,
        sell_above: float = 60.0,
        mode: str = "reversion",
        name: str | None = None,
    ) -> None:
        if period < 2:
            raise ValueError("RSI period must be >= 2")
        if mode not in {"reversion", "trend"}:
            raise ValueError(f"unsupported RSI mode {mode!r}")
        if not (0.0 < buy_below <= sell_above < 100.0):
            raise ValueError("require 0 < buy_below <= sell_above < 100")
        self.period = int(period)
        self.buy_below = float(buy_below)
        self.sell_above = float(sell_above)
        self.mode = mode
        self._name = name or f"rsi_{mode}_{self.period}_{int(buy_below)}_{int(sell_above)}"
        self._prev_close: float | None = None
        self._count = 0
        self._gain_sum = 0.0
        self._loss_sum = 0.0
        self._avg_gain: float | None = None
        self._avg_loss: float | None = None

    @property
    def name(self) -> str:
        return self._name

    def reset(self) -> None:
        self._prev_close = None
        self._count = 0
        self._gain_sum = 0.0
        self._loss_sum = 0.0
        self._avg_gain = None
        self._avg_loss = None

    def on_closed_bar(self, bar: Bar) -> int:
        c = bar.close
        if self._prev_close is None:
            self._prev_close = c
            return 0
        delta = c - self._prev_close
        self._prev_close = c
        gain = delta if delta > 0.0 else 0.0
        loss = -delta if delta < 0.0 else 0.0
        self._count += 1

        if self._count < self.period:
            self._gain_sum += gain
            self._loss_sum += loss
            return 0
        if self._count == self.period:
            self._gain_sum += gain
            self._loss_sum += loss
            self._avg_gain = self._gain_sum / self.period
            self._avg_loss = self._loss_sum / self.period
        else:
            assert self._avg_gain is not None and self._avg_loss is not None
            self._avg_gain = (self._avg_gain * (self.period - 1) + gain) / self.period
            self._avg_loss = (self._avg_loss * (self.period - 1) + loss) / self.period

        assert self._avg_gain is not None and self._avg_loss is not None
        if self._avg_loss == 0.0:
            rsi = 100.0 if self._avg_gain > 0.0 else 50.0
        else:
            rs = self._avg_gain / self._avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

        if self.mode == "reversion":
            if rsi <= self.buy_below:
                return 1
            if rsi >= self.sell_above:
                return -1
            return 0
        if rsi > self.sell_above:
            return 1
        if rsi < self.buy_below:
            return -1
        return 0


class SupertrendSignal:
    """Wilder-ATR Supertrend direction signal (`+1` bullish, `-1` bearish)."""

    def __init__(self, atr_period: int = 10, multiplier: float = 3.0, *, name: str | None = None) -> None:
        if atr_period < 2 or multiplier <= 0.0:
            raise ValueError("require atr_period >= 2 and multiplier > 0")
        self.atr_period = int(atr_period)
        self.multiplier = float(multiplier)
        self._name = name or f"supertrend_{self.atr_period}_{self.multiplier:g}"
        self._prev_close: float | None = None
        self._count = 0
        self._tr_sum = 0.0
        self._atr: float | None = None
        self._final_upper: float | None = None
        self._final_lower: float | None = None
        self._trend = 0

    @property
    def name(self) -> str:
        return self._name

    def reset(self) -> None:
        self._prev_close = None
        self._count = 0
        self._tr_sum = 0.0
        self._atr = None
        self._final_upper = None
        self._final_lower = None
        self._trend = 0

    def on_closed_bar(self, bar: Bar) -> int:
        if self._prev_close is None:
            tr = bar.high - bar.low
        else:
            tr = max(
                bar.high - bar.low,
                abs(bar.high - self._prev_close),
                abs(bar.low - self._prev_close),
            )
        self._count += 1
        if self._count < self.atr_period:
            self._tr_sum += tr
            self._prev_close = bar.close
            return 0
        if self._count == self.atr_period:
            self._tr_sum += tr
            self._atr = self._tr_sum / self.atr_period
        else:
            assert self._atr is not None
            self._atr = (self._atr * (self.atr_period - 1) + tr) / self.atr_period

        assert self._atr is not None
        hl2 = 0.5 * (bar.high + bar.low)
        basic_upper = hl2 + self.multiplier * self._atr
        basic_lower = hl2 - self.multiplier * self._atr

        if self._final_upper is None or self._final_lower is None or self._prev_close is None:
            self._final_upper = basic_upper
            self._final_lower = basic_lower
            self._trend = 1 if bar.close >= hl2 else -1
        else:
            if basic_upper < self._final_upper or self._prev_close > self._final_upper:
                final_upper = basic_upper
            else:
                final_upper = self._final_upper

            if basic_lower > self._final_lower or self._prev_close < self._final_lower:
                final_lower = basic_lower
            else:
                final_lower = self._final_lower

            if self._trend == -1 and bar.close > final_upper:
                self._trend = 1
            elif self._trend == 1 and bar.close < final_lower:
                self._trend = -1

            self._final_upper = final_upper
            self._final_lower = final_lower

        self._prev_close = bar.close
        return self._trend


class CallableSignal:
    """Adapter turning any stateless/stateful `(bar: Bar) -> int` callable into a SignalProvider."""

    def __init__(self, name: str, fn: Callable[[Bar], int], *, reset_fn: Callable[[], None] | None = None) -> None:
        if not name.strip():
            raise ValueError("signal name must be non-empty")
        self._name = name
        self._fn = fn
        self._reset_fn = reset_fn

    @property
    def name(self) -> str:
        return self._name

    def reset(self) -> None:
        if self._reset_fn is not None:
            self._reset_fn()

    def on_closed_bar(self, bar: Bar) -> int:
        val = int(self._fn(bar))
        if val not in (-1, 0, 1):
            raise ValueError(f"SignalProvider {self._name!r} must return -1, 0, or 1; got {val!r}")
        return val


def create_signal_provider(spec: str) -> SignalProvider:
    """Factory creating built-in SignalProviders from compact CLI names.

    Supported specs:
    - `ha_1m` (Baseline LGB154 V3 Heikin-Ashi)
    - `ema_cross` or `ema_9_21` / `ema_<fast>_<slow>`
    - `rsi_reversion` or `rsi_reversion_<period>_<buy>_<sell>`
    - `rsi_trend` or `rsi_trend_<period>_<low>_<high>`
    - `supertrend` or `supertrend_<atr>_<mult>`
    """
    key = spec.strip().lower()
    if key in {"ha", "ha_1m", "baseline"}:
        return HeikinAshiSignal(name="ha_1m")
    if key == "ema_cross":
        return EmaCrossSignal(9, 21)
    if key.startswith("ema_"):
        parts = key.split("_")
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            return EmaCrossSignal(int(parts[1]), int(parts[2]), name=key)
    if key == "rsi_reversion":
        return RsiRegimeSignal(14, buy_below=40.0, sell_above=60.0, mode="reversion")
    if key.startswith("rsi_reversion_"):
        parts = key.split("_")
        if len(parts) == 5:
            return RsiRegimeSignal(
                int(parts[2]),
                buy_below=float(parts[3]),
                sell_above=float(parts[4]),
                mode="reversion",
                name=key,
            )
    if key == "rsi_trend":
        return RsiRegimeSignal(14, buy_below=50.0, sell_above=50.0, mode="trend")
    if key.startswith("rsi_trend_"):
        parts = key.split("_")
        if len(parts) == 5:
            return RsiRegimeSignal(
                int(parts[2]),
                buy_below=float(parts[3]),
                sell_above=float(parts[4]),
                mode="trend",
                name=key,
            )
    if key == "supertrend":
        return SupertrendSignal(10, 3.0)
    if key.startswith("supertrend_"):
        parts = key.split("_")
        if len(parts) == 3:
            val_mult = float(parts[2])
            if not math.isfinite(val_mult):
                raise ValueError(f"invalid supertrend multiplier: {spec!r}")
            return SupertrendSignal(int(parts[1]), val_mult, name=key)
    raise ValueError(
        f"unknown signal spec {spec!r}; try one of: ha_1m, ema_9_21, ema_12_26, "
        "rsi_reversion, rsi_trend, supertrend, supertrend_10_3"
    )
