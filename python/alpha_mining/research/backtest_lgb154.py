"""Event-driven 1-minute Limit-Order Backtest Engine for LGB154 V3 (Pluggable Signals).

Design principles:
- **Zero lookahead:** At bar `B_t` open, decisions see ONLY closed bars `B_0..B_{t-1}`
  and opening quote derived from `B_t.open`. Fills execute strictly AFTER decisions using
  `B_t.low` / `B_t.high`.
- **Exact LGB154 V3 Decimal parity:** Descending geometric grid, spacing guard, 1 batch
  per NEW GREEN cycle, `WAIT_OLD_PENDING`, partial-fill recovery, exposure curve
  `min((idx+1)*q, max_pos)`, RP budgets, and USD-M (`PROFIT_PLUS_COMMISSION` / `NET`) +
  COIN-M Inverse (`NET` ETH basis) take-profit accounting.
- **Honest Quant Research Gate diagnostics:** Mark-to-Market equity & worst intra-bar
  drawdown, liquidation check, real 8h funding rate settlement, `strict_cross` vs `touch`
  fill sensitivity, idle/underwater time breakdown, and automated crash stress tests.
- **Fast at scale:** Pre-cached exact per-group TP thresholds + float fast-path guards
  allow 1,000+ days (~1.44M 1m bars) to finish in seconds while keeping exact Decimal fills.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Mapping, Sequence

from ..strategy.lgb154 import (
    Bar,
    HeikinAshiSignal,
    Lgb154Config,
    SignalProvider,
    ZERO,
    build_grid_levels,
    compute_net_tp_price,
    compute_tp_threshold,
    missing_qty,
    round_down,
    round_up,
    to_decimal,
    within_spacing,
)

EIGHT_HOURS_MS = 28_800_000
ONE_DAY_MS = 86_400_000


@dataclass(frozen=True)
class BacktestOptions:
    """Execution, cost, and simulation assumptions (explicitly logged in every report)."""

    initial_capital: Decimal = Decimal("1000")  # USDT for USD_M; ETH for COIN_M
    fill_mode: str = "strict_cross"  # "strict_cross" (conservative) | "touch" (optimistic)
    half_spread_ticks: int = 1  # bid = open - k*tick, ask = open + k*tick (ask > bid)
    default_funding_rate_8h: float = 0.0001  # +0.01% per 8h fallback when historical map absent
    use_funding: bool = True
    record_trades: bool = True
    recovery_mode: str = "partial_only"  # "partial_only" (clean) | "legacy_v3" (bot.py L2417 zero-fill zombie parity)

    def __post_init__(self) -> None:
        if self.initial_capital <= ZERO:
            raise ValueError("initial_capital must be positive")
        if self.fill_mode not in {"strict_cross", "touch"}:
            raise ValueError(f"fill_mode must be 'strict_cross' or 'touch', got {self.fill_mode!r}")
        if self.half_spread_ticks < 1:
            raise ValueError("half_spread_ticks must be >= 1 so ask > bid")
        if self.recovery_mode not in {"partial_only", "legacy_v3"}:
            raise ValueError(
                f"recovery_mode must be 'partial_only' or 'legacy_v3', got {self.recovery_mode!r}"
            )


@dataclass
class _GroupState:
    group_id: str
    rp_id: str
    grid: int
    price: Decimal
    price_f: float
    target_qty: Decimal
    cumulative_buy_qty: Decimal = ZERO
    open_qty: Decimal = ZERO
    cost_basis: Decimal = ZERO  # USDT notional (USD_M) or ETH basis (COIN_M)
    entry_fee_open: Decimal = ZERO
    funding_open: Decimal = ZERO  # signed: negative = paid by long, positive = received
    first_fill_ms: int = 0
    tp_threshold: Decimal | None = None
    tp_threshold_f: float = math.inf


@dataclass
class _PendingOrder:
    order_id: int
    group_id: str
    rp_id: str
    grid: int
    side: str  # "BUY" | "SELL"
    qty: Decimal
    price: Decimal
    price_f: float
    role: str
    placed_ms: int


@dataclass(frozen=True)
class ClosedTrade:
    group_id: str
    grid: int
    entry_time_ms: int
    exit_time_ms: int
    hold_minutes: float
    qty: float
    avg_entry_price: float
    exit_price: float
    gross_pnl: float
    fees: float
    funding: float
    net_pnl: float


@dataclass
class BacktestResult:
    symbol: str
    product_type: str
    settlement_unit: str
    signal_name: str
    fill_mode: str
    start_utc: str
    end_utc: str
    bar_count: int
    days_covered: float
    zone_high: float
    zone_low: float
    spacing_pct: float
    grid_levels_count: int
    initial_capital: float
    ending_equity: float
    total_mtm_pnl: float
    total_mtm_return_pct: float
    realized_net_pnl: float
    realized_gross_pnl: float
    unrealized_pnl_end: float
    total_fees_paid: float
    total_funding_pnl: float
    max_drawdown_abs: float
    max_drawdown_pct: float
    worst_unrealized_pnl: float
    worst_equity: float
    would_liquidate: bool
    liquidation_bar_utc: str | None
    sharpe_daily_ann: float
    sortino_daily_ann: float
    calmar_ratio: float
    buy_fills: int
    sell_fills: int
    closed_trades_count: int
    win_rate_pct: float
    avg_trade_net_pnl: float
    avg_hold_minutes: float
    max_open_qty: float
    max_open_notional: float
    ending_open_qty: float
    bars_in_zone_pct: float
    bars_below_low_pct: float
    bars_above_high_pct: float
    emergency_stop_triggered: str | None
    funding_events_applied: int
    historical_funding_hits: int
    buy_volume_eth: float = 0.0
    sell_volume_eth: float = 0.0
    turnover_usd: float = 0.0
    max_utilization_pct: float = 0.0
    avg_weekly_cf_usd: float = 0.0
    weekly_count: int = 0
    beta_to_eth: float = 0.0
    corr_to_eth: float = 0.0
    trades: list[ClosedTrade] = field(default_factory=list)
    daily_series: dict[str, Any] = field(default_factory=dict)

    def summary_dict(self) -> dict[str, Any]:
        d = dict(self.__dict__)
        d.pop("trades", None)
        d.pop("daily_series", None)
        return d


def _ms_to_iso(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ms_to_date_str(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")


def _iso_week_key(date_str: str) -> str:
    y, m, d = (int(x) for x in date_str.split("-"))
    iso_y, iso_w, _ = datetime(y, m, d, tzinfo=timezone.utc).isocalendar()
    return f"{iso_y:04d}-W{iso_w:02d}"


def _consecutive_iso_weeks(start_date_str: str, end_date_str: str) -> list[str]:
    sy, sm, sd = (int(x) for x in start_date_str.split("-"))
    ey, em, ed = (int(x) for x in end_date_str.split("-"))
    cur = datetime(sy, sm, sd, tzinfo=timezone.utc).date()
    end = datetime(ey, em, ed, tzinfo=timezone.utc).date()
    weeks: list[str] = []
    seen: set[str] = set()
    while cur <= end:
        iso_y, iso_w, _ = cur.isocalendar()
        wk = f"{iso_y:04d}-W{iso_w:02d}"
        if wk not in seen:
            seen.add(wk)
            weeks.append(wk)
        cur += timedelta(days=1)
    return weeks


def compute_beta_and_corr(series_y: Sequence[float], series_x: Sequence[float]) -> tuple[float, float]:
    """Compute OLS Beta (Cov(y, x) / Var(x)) and Pearson Correlation between equal-length return series."""
    n = min(len(series_y), len(series_x))
    if n < 2:
        return 0.0, 0.0
    my = sum(series_y[:n]) / n
    mx = sum(series_x[:n]) / n
    cov = 0.0
    vx = 0.0
    vy = 0.0
    for i in range(n):
        dy = series_y[i] - my
        dx = series_x[i] - mx
        cov += dy * dx
        vx += dx * dx
        vy += dy * dy
    beta = (cov / vx) if vx > 1e-18 else 0.0
    denom = math.sqrt(vx * vy)
    corr = (cov / denom) if denom > 1e-18 else 0.0
    return beta, corr


def _refresh_group_tp(group: _GroupState, cfg: Lgb154Config) -> None:
    if group.open_qty <= ZERO:
        group.tp_threshold = None
        group.tp_threshold_f = math.inf
        return
    th = compute_tp_threshold(
        open_qty=group.open_qty,
        cost_basis=group.cost_basis,
        entry_fee_open=group.entry_fee_open,
        funding_open=group.funding_open,
        cfg=cfg,
    )
    group.tp_threshold = th
    group.tp_threshold_f = float(th) if th is not None else math.inf


def run_lgb154_backtest(
    bars: Sequence[Bar],
    cfg: Lgb154Config,
    *,
    signal_provider: SignalProvider | None = None,
    options: BacktestOptions | None = None,
    funding_rates_8h: Mapping[int, float] | None = None,
) -> BacktestResult:
    """Run a strictly causal, event-driven 1m Limit-Order backtest of LGB154 V3."""
    if len(bars) < 2:
        raise ValueError("backtest requires at least 2 bars")

    opt = options or BacktestOptions()
    sig_prov: SignalProvider = signal_provider or HeikinAshiSignal(name="ha_1m")
    sig_prov.reset()

    levels = build_grid_levels(cfg.high, cfg.low, cfg.spacing_pct, cfg.tick_size)
    levels_with_f = [(idx, p, float(p), cfg.rp_rule_for_grid(idx)) for idx, p in levels]
    neg_level_prices_f = [-p_f for _, _, p_f, _ in levels_with_f]
    zone_high_f = float(cfg.high)
    zone_low_f = float(cfg.low)
    tick_d = cfg.tick_size
    tick_f = float(tick_d)
    half_spread_d = tick_d * Decimal(opt.half_spread_ticks)
    half_spread_f = float(half_spread_d)
    strict_cross = opt.fill_mode == "strict_cross"
    maker_fee = cfg.maker_fee_rate
    taker_fee = cfg.taker_fee_rate
    is_coinm = cfg.is_coinm
    contract_size = cfg.contract_size_usd
    contract_size_f = float(contract_size)
    maint_rate_f = float(cfg.maintenance_margin_rate)
    init_cap_d = opt.initial_capital
    init_cap_f = float(init_cap_d)
    max_loss_d = cfg.max_loss_usdt
    eq_target_d = cfg.equity_target_usdt
    has_emergency = (max_loss_d > ZERO) or (eq_target_d > ZERO)
    fund_map = funding_rates_8h or {}
    default_fund_rate = float(opt.default_funding_rate_8h)

    # Active portfolio state
    groups: dict[str, _GroupState] = {}
    open_groups: dict[str, _GroupState] = {}  # subset where open_qty > 0
    recovery_groups: dict[str, _GroupState] = {}  # subset where cumulative_buy_qty < target_qty
    pending_buys: dict[int, _PendingOrder] = {}
    pending_sells: dict[int, _PendingOrder] = {}  # keyed by order_id
    sell_by_group: dict[str, int] = {}

    next_group_num = 1
    next_order_id = 1
    prev_sig = 0
    batch_sent = False

    # Running cached float bounds for fast inner loop
    max_pending_buy_f = -math.inf
    min_pending_sell_f = math.inf
    min_open_tp_f = math.inf
    open_qty_total = ZERO
    open_cost_total = ZERO
    open_qty_f = 0.0
    open_cost_f = 0.0

    # Accounting accumulators (in settlement unit: USDT for USD_M, ETH for COIN_M)
    realized_gross = ZERO
    realized_net = ZERO
    total_fees = ZERO
    total_funding = ZERO
    open_entry_fees_total = ZERO
    open_funding_total = ZERO

    buy_fills = 0
    sell_fills = 0
    buy_vol_f = 0.0
    sell_vol_f = 0.0
    turnover_usd_f = 0.0
    max_util_usd_seen = 0.0
    closed_trades: list[ClosedTrade] = []
    day_realized_cf: dict[int, float] = defaultdict(float)
    wins = 0
    total_hold_min = 0.0
    funding_events = 0
    hist_funding_hits = 0

    peak_equity = init_cap_f
    worst_equity = init_cap_f
    max_dd_abs = 0.0
    max_dd_pct = 0.0
    worst_unrealized = 0.0
    would_liquidate = False
    liquidation_bar_ms: int | None = None
    emergency_triggered: str | None = None

    max_open_qty_seen = 0.0
    max_open_notional_seen = 0.0
    bars_in_zone = 0
    bars_below_low = 0
    bars_above_high = 0

    first_open_f = bars[0].open if bars[0].open > 0.0 else max(bars[0].close, 1e-9)
    first_date_str = _ms_to_date_str(bars[0].open_time_ms)
    daily_dates: list[str] = [first_date_str]
    daily_equities: list[float] = [init_cap_f]
    daily_eth_closes: list[float] = [bars[0].close]
    daily_cf_series: list[float] = [0.0]
    daily_dd_series: list[float] = [0.0]
    daily_inv_series: list[float] = [0.0]
    daily_cap_series: list[float] = [0.0]
    last_day_bucket = bars[0].open_time_ms // ONE_DAY_MS
    last_funding_bucket = bars[0].open_time_ms // EIGHT_HOURS_MS

    def _recompute_order_bounds() -> None:
        nonlocal max_pending_buy_f, min_pending_sell_f
        max_pending_buy_f = max((o.price_f for o in pending_buys.values()), default=-math.inf)
        min_pending_sell_f = min((o.price_f for o in pending_sells.values()), default=math.inf)

    def _recompute_tp_bound() -> None:
        nonlocal min_open_tp_f
        min_open_tp_f = min((g.tp_threshold_f for g in open_groups.values()), default=math.inf)

    def _cancel_all_buys() -> None:
        nonlocal max_pending_buy_f
        if pending_buys:
            pending_buys.clear()
            max_pending_buy_f = -math.inf

    def _cancel_all_sells() -> None:
        nonlocal min_pending_sell_f
        if pending_sells:
            pending_sells.clear()
            sell_by_group.clear()
            min_pending_sell_f = math.inf

    def _mtm_unrealized_and_equity(mark_f: float) -> tuple[float, float]:
        if open_qty_f <= 0.0:
            eq = init_cap_f + float(realized_net) + float(open_funding_total) - float(open_entry_fees_total)
            return 0.0, eq
        if is_coinm:
            unreal = open_cost_f - (open_qty_f * contract_size_f / mark_f)
        else:
            unreal = open_qty_f * mark_f - open_cost_f
        eq = init_cap_f + float(realized_net) + float(open_funding_total) - float(open_entry_fees_total) + unreal
        return unreal, eq

    def _maintenance_margin(mark_f: float) -> float:
        if open_qty_f <= 0.0:
            return 0.0
        if is_coinm:
            return (open_qty_f * contract_size_f / mark_f) * maint_rate_f
        return (open_qty_f * mark_f) * maint_rate_f

    def _utilized_capital_usd() -> float:
        inv_usd = (open_qty_f * contract_size_f) if is_coinm else open_cost_f
        if not pending_buys:
            return inv_usd
        if is_coinm:
            pend_usd = sum(float(o.qty) * contract_size_f for o in pending_buys.values())
        else:
            pend_usd = sum(float(o.qty) * o.price_f for o in pending_buys.values())
        return inv_usd + pend_usd

    def _force_market_close_all(close_price_d: Decimal, ts_ms: int) -> None:
        nonlocal open_qty_total, open_cost_total, open_qty_f, open_cost_f
        nonlocal realized_gross, realized_net, total_fees, open_entry_fees_total, open_funding_total
        nonlocal sell_fills, sell_vol_f, turnover_usd_f, wins, total_hold_min
        _cancel_all_buys()
        _cancel_all_sells()
        for gid in list(open_groups.keys()):
            g = open_groups[gid]
            q = g.open_qty
            if q <= ZERO:
                continue
            rel_cost = g.cost_basis
            rel_entry_fee = g.entry_fee_open
            rel_fund = g.funding_open
            if is_coinm:
                exit_basis = q * contract_size / close_price_d
                gross = rel_cost - exit_basis
                exit_fee = exit_basis * taker_fee
                avg_entry_f = float(q * contract_size / rel_cost) if rel_cost > ZERO else float(g.price)
                turnover_usd_f += float(q) * contract_size_f
            else:
                gross = q * close_price_d - rel_cost
                exit_fee = q * close_price_d * taker_fee
                avg_entry_f = float(rel_cost / q)
                turnover_usd_f += float(q * close_price_d)
            net = gross - rel_entry_fee - exit_fee + rel_fund

            realized_gross += gross
            realized_net += net
            day_realized_cf[ts_ms // ONE_DAY_MS] += float(net)
            total_fees += exit_fee
            open_entry_fees_total -= rel_entry_fee
            open_funding_total -= rel_fund
            open_qty_total -= q
            open_cost_total -= rel_cost
            sell_fills += 1
            sell_vol_f += float(q)

            hold_m = max(0.0, (ts_ms - g.first_fill_ms) / 60_000.0) if g.first_fill_ms else 0.0
            total_hold_min += hold_m
            if net > ZERO:
                wins += 1
            if opt.record_trades:
                closed_trades.append(
                    ClosedTrade(
                        group_id=g.group_id,
                        grid=g.grid,
                        entry_time_ms=g.first_fill_ms,
                        exit_time_ms=ts_ms,
                        hold_minutes=hold_m,
                        qty=float(q),
                        avg_entry_price=avg_entry_f,
                        exit_price=float(close_price_d),
                        gross_pnl=float(gross),
                        fees=float(rel_entry_fee + exit_fee),
                        funding=float(rel_fund),
                        net_pnl=float(net),
                    )
                )

            g.open_qty = ZERO
            g.cost_basis = ZERO
            g.entry_fee_open = ZERO
            g.funding_open = ZERO
            _refresh_group_tp(g, cfg)
            open_groups.pop(gid, None)
        open_qty_f = float(open_qty_total)
        open_cost_f = float(open_cost_total)
        _recompute_tp_bound()

    def _place_buy_batch(ask_d: Decimal, ts_ms: int) -> None:
        nonlocal next_group_num, next_order_id, max_pending_buy_f, max_util_usd_seen
        if pending_buys:
            return  # WAIT_OLD_PENDING

        ask_limit_d = ask_d - tick_d
        ask_limit_f = float(ask_limit_d)
        if ask_limit_f <= zone_low_f:
            return
        if not recovery_groups and (open_qty_total + cfg.order_quantity > cfg.max_position_quantity):
            return

        committed = open_qty_total
        gross = ZERO
        rp_qty: dict[str, Decimal] = defaultdict(lambda: ZERO)
        rp_gross: dict[str, Decimal] = defaultdict(lambda: ZERO)
        busy: list[tuple[str, Decimal]] = []
        busy_sorted: list[tuple[float, Decimal]] = []

        for g in open_groups.values():
            avg_open = (
                (g.open_qty * contract_size / g.cost_basis)
                if (is_coinm and g.cost_basis > ZERO)
                else (g.cost_basis / g.open_qty)
            )
            gross += cfg.quote_notional(g.open_qty, g.price)
            rp_qty[g.rp_id] += g.open_qty
            rp_gross[g.rp_id] += cfg.quote_notional(g.open_qty, avg_open)
            busy.append((g.group_id, g.price))
            busy_sorted.append((g.price_f, g.price))
        busy_sorted.sort(key=lambda item: item[0])
        busy_keys = [item[0] for item in busy_sorted]

        def _nearby_exact_neighbors(price_d: Decimal, price_f: float) -> bool:
            if not busy_keys:
                return False
            pos = bisect_left(busy_keys, price_f)
            if pos > 0 and within_spacing(price_d, busy_sorted[pos - 1][1], cfg.spacing_pct, tick_d):
                return True
            if pos < len(busy_sorted) and within_spacing(price_d, busy_sorted[pos][1], cfg.spacing_pct, tick_d):
                return True
            return False

        def _nearby_ignore(price_d: Decimal, ignore_gid: str) -> bool:
            return any(
                gid != ignore_gid and within_spacing(price_d, bp, cfg.spacing_pct, tick_d)
                for gid, bp in busy
            )

        plan: list[tuple[_GroupState, Decimal, str]] = []

        def _admit(g: _GroupState, q: Decimal, role: str, rule: Any) -> bool:
            nonlocal committed, gross
            notional = cfg.quote_notional(q, g.price)
            if q > cfg.max_entry_order_quantity or notional > cfg.max_entry_order_notional_usdt:
                return False
            if committed + q > cfg.max_position_quantity:
                return False
            if cfg.check_global_notional and gross + notional > cfg.max_notional_usdt:
                return False
            if rp_qty[g.rp_id] + q > rule.max_quantity or rp_gross[g.rp_id] + notional > rule.max_notional_usdt:
                return False
            plan.append((g, q, role))
            busy.append((g.group_id, g.price))
            ins_pos = bisect_left(busy_keys, g.price_f)
            busy_keys.insert(ins_pos, g.price_f)
            busy_sorted.insert(ins_pos, (g.price_f, g.price))
            committed += q
            gross += notional
            rp_qty[g.rp_id] += q
            rp_gross[g.rp_id] += notional
            return True

        # 1. Partial-fill recovery first (ordered by grid index, matching bot.py L2415)
        if recovery_groups:
            for g in sorted(recovery_groups.values(), key=lambda v: v.grid):
                if len(plan) >= cfg.orders_per_batch:
                    break
                if g.cumulative_buy_qty >= g.target_qty:
                    continue
                if not (cfg.low <= g.price <= cfg.high) or g.price >= ask_limit_d:
                    continue
                if _nearby_ignore(g.price, g.group_id):
                    continue
                q = missing_qty(g.target_qty, g.cumulative_buy_qty, ZERO, cfg.step_size)
                if q < cfg.min_qty or cfg.quote_notional(q, g.price) < cfg.min_notional:
                    continue
                rule = cfg.rp_rule_for_grid(g.grid)
                _admit(g, q, "RECOVERY", rule)

        # 2. New geometric grid entries (O(log N) binary-search start + O(log K) exact neighbor spacing)
        if len(plan) < cfg.orders_per_batch:
            rec_grid_set = (
                {g.grid for g in recovery_groups.values() if g.cumulative_buy_qty < g.target_qty}
                if recovery_groups
                else ()
            )
            start_pos = bisect_right(neg_level_prices_f, -ask_limit_f)
            q = cfg.order_quantity
            for k in range(start_pos, len(levels_with_f)):
                if len(plan) >= cfg.orders_per_batch:
                    break
                idx, p_d, p_f, rule = levels_with_f[k]
                if p_d >= ask_limit_d:
                    continue
                if rec_grid_set and idx in rec_grid_set:
                    continue
                if _nearby_exact_neighbors(p_d, p_f):
                    continue
                target_cap = min(Decimal(idx + 1) * q, cfg.max_position_quantity)
                if committed + q > target_cap or cfg.quote_notional(q, p_d) < cfg.min_notional:
                    continue
                gid = f"g{next_group_num:08d}"
                cand = _GroupState(
                    group_id=gid,
                    rp_id=rule.rp_id,
                    grid=idx,
                    price=p_d,
                    price_f=p_f,
                    target_qty=q,
                )
                if _admit(cand, q, "ENTRY", rule):
                    next_group_num += 1

        legacy_recovery = opt.recovery_mode == "legacy_v3"
        for g, q, role in plan:
            if role == "ENTRY":
                groups[g.group_id] = g
                if legacy_recovery:
                    recovery_groups[g.group_id] = g
            oid = next_order_id
            next_order_id += 1
            pending_buys[oid] = _PendingOrder(
                order_id=oid,
                group_id=g.group_id,
                rp_id=g.rp_id,
                grid=g.grid,
                side="BUY",
                qty=q,
                price=g.price,
                price_f=g.price_f,
                role=role,
                placed_ms=ts_ms,
            )
        if plan:
            _recompute_order_bounds()
            util_placed = _utilized_capital_usd()
            if util_placed > max_util_usd_seen:
                max_util_usd_seen = util_placed

    # Main strictly causal bar loop (decision on B_{i-1} at B_i open -> fill during B_i)
    for i in range(1, len(bars)):
        prev_bar = bars[i - 1]
        bar = bars[i]
        ts_ms = bar.open_time_ms
        open_f = bar.open
        high_f = bar.high
        low_f = bar.low
        close_f = bar.close

        # Zone coverage accounting
        if low_f > zone_high_f:
            bars_above_high += 1
        elif high_f < zone_low_f:
            bars_below_low += 1
        else:
            bars_in_zone += 1

        # Step 1: Closed-bar signal from B_{i-1} (zero lookahead!)
        sig = sig_prov.on_closed_bar(prev_bar)

        if emergency_triggered is None:
            # Cycle state machine (1:1 bot.py L2663-2666)
            if sig == 1 and prev_sig != 1:
                batch_sent = False
            elif sig != 1:
                batch_sent = False
            prev_sig = sig

            bid_f = open_f - half_spread_f
            ask_f = open_f + half_spread_f
            if bid_f <= 0.0:
                bid_f = max(tick_f, open_f * 0.9999)
                ask_f = bid_f + 2.0 * tick_f

            # Step 2: Order management at B_i open
            if sig != 1:
                _cancel_all_buys()
                if sig == 0:
                    _cancel_all_sells()
                else:
                    # sig == -1 (RED): validate existing SELLs & arm new TP SELLs
                    if open_groups:
                        bid_d: Decimal | None = None
                        if cfg.cancel_tp_when_invalid and pending_sells:
                            for oid in list(pending_sells.keys()):
                                ord_s = pending_sells[oid]
                                g = open_groups.get(ord_s.group_id)
                                if g is None:
                                    pending_sells.pop(oid, None)
                                    sell_by_group.pop(ord_s.group_id, None)
                                    continue
                                if bid_f < g.tp_threshold_f + 1e-9:
                                    if bid_d is None:
                                        bid_d = round_down(f"{bid_f:.8f}", tick_d)
                                    if g.tp_threshold is None or bid_d < g.tp_threshold:
                                        pending_sells.pop(oid, None)
                                        sell_by_group.pop(ord_s.group_id, None)
                            _recompute_order_bounds()

                        if bid_f >= min_open_tp_f - 1e-9:
                            if bid_d is None:
                                bid_d = round_down(f"{bid_f:.8f}", tick_d)
                            placed_any = False
                            for g in open_groups.values():
                                if g.group_id in sell_by_group:
                                    continue
                                if bid_f < g.tp_threshold_f - 1e-9:
                                    continue
                                tp_price = compute_net_tp_price(
                                    open_qty=g.open_qty,
                                    cost_basis=g.cost_basis,
                                    entry_fee_open=g.entry_fee_open,
                                    funding_open=g.funding_open,
                                    bid=bid_d,
                                    cfg=cfg,
                                )
                                if tp_price is None:
                                    continue
                                q_sell = round_down(g.open_qty, cfg.step_size)
                                if q_sell < cfg.min_qty or cfg.quote_notional(q_sell, tp_price) < cfg.min_notional:
                                    continue
                                oid = next_order_id
                                next_order_id += 1
                                pending_sells[oid] = _PendingOrder(
                                    order_id=oid,
                                    group_id=g.group_id,
                                    rp_id=g.rp_id,
                                    grid=g.grid,
                                    side="SELL",
                                    qty=q_sell,
                                    price=tp_price,
                                    price_f=float(tp_price),
                                    role="TP",
                                    placed_ms=ts_ms,
                                )
                                sell_by_group[g.group_id] = oid
                                placed_any = True
                            if placed_any:
                                _recompute_order_bounds()
            else:
                # sig == +1 (GREEN)
                _cancel_all_sells()
                if pending_buys and (ask_f - tick_f <= max_pending_buy_f + 1e-9):
                    ask_d_chk = round_up(f"{ask_f:.8f}", tick_d)
                    removed = False
                    for oid in list(pending_buys.keys()):
                        ob = pending_buys[oid]
                        if ob.price < cfg.low or ob.price > cfg.high or ob.price >= ask_d_chk - tick_d:
                            pending_buys.pop(oid, None)
                            removed = True
                    if removed:
                        _recompute_order_bounds()

                if not batch_sent:
                    batch_sent = True
                    if not pending_buys and open_f > zone_low_f:
                        ask_d = round_up(f"{ask_f:.8f}", tick_d)
                        _place_buy_batch(ask_d, ts_ms)

            # Step 3: Intra-bar Limit-Order Fills during B_i
            if pending_buys and (low_f < max_pending_buy_f if strict_cross else low_f <= max_pending_buy_f):
                filled_ids: list[int] = []
                for oid, ob in pending_buys.items():
                    if (low_f < ob.price_f) if strict_cross else (low_f <= ob.price_f):
                        filled_ids.append(oid)
                if filled_ids:
                    for oid in filled_ids:
                        ob = pending_buys.pop(oid)
                        g = groups[ob.group_id]
                        q = ob.qty
                        p = ob.price
                        if is_coinm:
                            added_cost = q * contract_size / p
                            fee = added_cost * maker_fee
                        else:
                            added_cost = q * p
                            fee = added_cost * maker_fee
                        if g.first_fill_ms == 0:
                            g.first_fill_ms = ts_ms
                        g.cumulative_buy_qty += q
                        g.open_qty += q
                        g.cost_basis += added_cost
                        g.entry_fee_open += fee
                        _refresh_group_tp(g, cfg)
                        open_groups[g.group_id] = g
                        if g.cumulative_buy_qty >= g.target_qty:
                            recovery_groups.pop(g.group_id, None)
                        elif g.cumulative_buy_qty > ZERO:
                            recovery_groups[g.group_id] = g

                        open_qty_total += q
                        open_cost_total += added_cost
                        open_entry_fees_total += fee
                        total_fees += fee
                        buy_fills += 1
                        buy_vol_f += float(q)
                        turnover_usd_f += float(q) * contract_size_f if is_coinm else float(q * p)
                    open_qty_f = float(open_qty_total)
                    open_cost_f = float(open_cost_total)
                    util_now = _utilized_capital_usd()
                    if util_now > max_util_usd_seen:
                        max_util_usd_seen = util_now
                    _recompute_order_bounds()
                    _recompute_tp_bound()

            if pending_sells and (high_f > min_pending_sell_f if strict_cross else high_f >= min_pending_sell_f):
                filled_sids: list[int] = []
                for oid, osell in pending_sells.items():
                    if (high_f > osell.price_f) if strict_cross else (high_f >= osell.price_f):
                        filled_sids.append(oid)
                if filled_sids:
                    for oid in filled_sids:
                        osell = pending_sells.pop(oid)
                        sell_by_group.pop(osell.group_id, None)
                        g = open_groups.get(osell.group_id)
                        if g is None or g.open_qty <= ZERO:
                            continue
                        q = min(osell.qty, g.open_qty)
                        ratio = q / g.open_qty
                        rel_cost = g.cost_basis * ratio
                        rel_entry_fee = g.entry_fee_open * ratio
                        rel_fund = g.funding_open * ratio
                        if is_coinm:
                            exit_basis = q * contract_size / osell.price
                            gross = rel_cost - exit_basis
                            exit_fee = exit_basis * maker_fee
                            avg_entry_f = float(q * contract_size / rel_cost) if rel_cost > ZERO else g.price_f
                            turnover_usd_f += float(q) * contract_size_f
                        else:
                            gross = q * osell.price - rel_cost
                            exit_fee = q * osell.price * maker_fee
                            avg_entry_f = float(rel_cost / q)
                            turnover_usd_f += float(q * osell.price)
                        net = gross - rel_entry_fee - exit_fee + rel_fund

                        realized_gross += gross
                        realized_net += net
                        day_realized_cf[ts_ms // ONE_DAY_MS] += float(net)
                        total_fees += exit_fee
                        open_entry_fees_total -= rel_entry_fee
                        open_funding_total -= rel_fund
                        open_qty_total -= q
                        open_cost_total -= rel_cost
                        sell_fills += 1
                        sell_vol_f += float(q)

                        hold_m = max(0.0, (ts_ms - g.first_fill_ms) / 60_000.0) if g.first_fill_ms else 0.0
                        total_hold_min += hold_m
                        if net > ZERO:
                            wins += 1
                        if opt.record_trades:
                            closed_trades.append(
                                ClosedTrade(
                                    group_id=g.group_id,
                                    grid=g.grid,
                                    entry_time_ms=g.first_fill_ms,
                                    exit_time_ms=ts_ms,
                                    hold_minutes=hold_m,
                                    qty=float(q),
                                    avg_entry_price=avg_entry_f,
                                    exit_price=osell.price_f,
                                    gross_pnl=float(gross),
                                    fees=float(rel_entry_fee + exit_fee),
                                    funding=float(rel_fund),
                                    net_pnl=float(net),
                                )
                            )

                        g.open_qty -= q
                        g.cost_basis -= rel_cost
                        g.entry_fee_open -= rel_entry_fee
                        g.funding_open -= rel_fund
                        if g.open_qty <= ZERO:
                            g.open_qty = ZERO
                            g.cost_basis = ZERO
                            g.entry_fee_open = ZERO
                            g.funding_open = ZERO
                            open_groups.pop(g.group_id, None)
                        _refresh_group_tp(g, cfg)
                    open_qty_f = float(open_qty_total)
                    open_cost_f = float(open_cost_total)
                    _recompute_order_bounds()
                    _recompute_tp_bound()

            # Step 4: 8-hour Funding Settlement (00:00, 08:00, 16:00 UTC)
            fund_bucket = ts_ms // EIGHT_HOURS_MS
            if fund_bucket > last_funding_bucket:
                if opt.use_funding and open_qty_total > ZERO:
                    boundary_ms = fund_bucket * EIGHT_HOURS_MS
                    if boundary_ms in fund_map:
                        rate_f = fund_map[boundary_ms]
                        hist_funding_hits += 1
                    else:
                        rate_f = default_fund_rate
                    if rate_f != 0.0:
                        rate_d = to_decimal(f"{rate_f:.10f}")
                        mark_d = to_decimal(f"{open_f:.8f}")
                        # Long pays positive funding rate, receives negative funding rate
                        if is_coinm:
                            total_cashflow = -(open_qty_total * contract_size / mark_d) * rate_d
                        else:
                            total_cashflow = -(open_qty_total * mark_d) * rate_d
                        total_funding += total_cashflow
                        open_funding_total += total_cashflow
                        for g in open_groups.values():
                            share = g.open_qty / open_qty_total
                            g.funding_open += total_cashflow * share
                            _refresh_group_tp(g, cfg)
                        _recompute_tp_bound()
                        funding_events += 1
                last_funding_bucket = fund_bucket

        # Step 5: Mark-to-Market Risk, Drawdown & Liquidation Diagnostics
        if open_qty_f > 0.0:
            if open_qty_f > max_open_qty_seen:
                max_open_qty_seen = open_qty_f
            notional_now = (open_qty_f * contract_size_f) if is_coinm else (open_qty_f * high_f)
            if notional_now > max_open_notional_seen:
                max_open_notional_seen = notional_now

            # Worst intra-bar drawdown evaluated at bar.low for a LONG-only grid
            unreal_low, eq_low = _mtm_unrealized_and_equity(low_f)
            if unreal_low < worst_unrealized:
                worst_unrealized = unreal_low
            if eq_low < worst_equity:
                worst_equity = eq_low
            if eq_low > peak_equity:
                peak_equity = eq_low
            dd_abs = peak_equity - eq_low
            if dd_abs > max_dd_abs:
                max_dd_abs = dd_abs
            dd_pct = (dd_abs / peak_equity * 100.0) if peak_equity > 0.0 else 0.0
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct
            if not would_liquidate and eq_low <= _maintenance_margin(low_f):
                would_liquidate = True
                liquidation_bar_ms = ts_ms

            # Peak equity update at bar.high
            _, eq_high = _mtm_unrealized_and_equity(high_f)
            if eq_high > peak_equity:
                peak_equity = eq_high

            # Optional emergency stops evaluated at bar.close
            if has_emergency and emergency_triggered is None:
                _, eq_close = _mtm_unrealized_and_equity(close_f)
                eq_close_d = to_decimal(f"{eq_close:.8f}")
                if max_loss_d > ZERO and eq_close_d <= init_cap_d - max_loss_d:
                    emergency_triggered = "MAX_LOSS"
                    _force_market_close_all(to_decimal(f"{close_f:.8f}"), ts_ms)
                elif eq_target_d > ZERO and eq_close_d >= init_cap_d + eq_target_d:
                    emergency_triggered = "EQUITY_TARGET"
                    _force_market_close_all(to_decimal(f"{close_f:.8f}"), ts_ms)
        else:
            _, eq_flat = _mtm_unrealized_and_equity(close_f)
            if eq_flat > peak_equity:
                peak_equity = eq_flat
            if eq_flat < worst_equity:
                worst_equity = eq_flat
            dd_abs = peak_equity - eq_flat
            if dd_abs > max_dd_abs:
                max_dd_abs = dd_abs
            dd_pct = (dd_abs / peak_equity * 100.0) if peak_equity > 0.0 else 0.0
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

        # Daily MTM equity, drawdown, inventory, utilization & CF snapshot
        day_bucket = ts_ms // ONE_DAY_MS
        if day_bucket > last_day_bucket:
            _, eq_day = _mtm_unrealized_and_equity(close_f)
            dd_day_neg = -((peak_equity - eq_day) / peak_equity * 100.0) if peak_equity > 0.0 and eq_day < peak_equity else 0.0
            util_day = _utilized_capital_usd()
            if util_day > max_util_usd_seen:
                max_util_usd_seen = util_day
            daily_dates.append(_ms_to_date_str(ts_ms))
            daily_equities.append(eq_day)
            daily_eth_closes.append(close_f)
            daily_cf_series.append(float(realized_net))
            daily_dd_series.append(dd_day_neg)
            daily_inv_series.append(open_qty_f)
            daily_cap_series.append(util_day)
            last_day_bucket = day_bucket

    # Final mark-to-market snapshot at last bar close
    last_bar = bars[-1]
    unreal_end, eq_end = _mtm_unrealized_and_equity(last_bar.close)
    last_date_str = _ms_to_date_str(last_bar.open_time_ms)
    dd_end_neg = -((peak_equity - eq_end) / peak_equity * 100.0) if peak_equity > 0.0 and eq_end < peak_equity else 0.0
    util_end = _utilized_capital_usd()
    if util_end > max_util_usd_seen:
        max_util_usd_seen = util_end
    if daily_dates[-1] == last_date_str:
        daily_equities[-1] = eq_end
        daily_eth_closes[-1] = last_bar.close
        daily_cf_series[-1] = float(realized_net)
        daily_dd_series[-1] = dd_end_neg
        daily_inv_series[-1] = open_qty_f
        daily_cap_series[-1] = util_end
    else:
        daily_dates.append(last_date_str)
        daily_equities.append(eq_end)
        daily_eth_closes.append(last_bar.close)
        daily_cf_series.append(float(realized_net))
        daily_dd_series.append(dd_end_neg)
        daily_inv_series.append(open_qty_f)
        daily_cap_series.append(util_end)

    total_mtm_pnl = eq_end - init_cap_f
    total_mtm_ret_pct = (total_mtm_pnl / init_cap_f * 100.0) if init_cap_f > 0.0 else 0.0

    # Daily simple returns (strategy & ETH benchmark) for Sharpe, Sortino, Beta & Correlation
    daily_rets: list[float] = []
    eth_daily_rets: list[float] = []
    for k in range(1, len(daily_equities)):
        prev_eq = daily_equities[k - 1]
        prev_eth = daily_eth_closes[k - 1]
        daily_rets.append(((daily_equities[k] - prev_eq) / prev_eq) if prev_eq > 0.0 else 0.0)
        eth_daily_rets.append(((daily_eth_closes[k] - prev_eth) / prev_eth) if prev_eth > 0.0 else 0.0)

    beta_to_eth, corr_to_eth = compute_beta_and_corr(daily_rets, eth_daily_rets)

    # ISO-week realized cashflow aggregation (consecutive calendar weeks, zero-CF weeks included)
    all_weeks = _consecutive_iso_weeks(daily_dates[0], daily_dates[-1])
    week_cf_map: dict[str, float] = {w: 0.0 for w in all_weeks}
    for day_b, cf_amt in day_realized_cf.items():
        wk = _iso_week_key(_ms_to_date_str(day_b * ONE_DAY_MS))
        if wk in week_cf_map:
            week_cf_map[wk] += cf_amt
    weekly_cf_vals = [round(week_cf_map[w], 4) for w in all_weeks]
    avg_weekly_cf = (sum(weekly_cf_vals) / len(all_weeks)) if all_weeks else 0.0

    sharpe = 0.0
    sortino = 0.0
    if len(daily_rets) >= 2:
        mean_r = sum(daily_rets) / len(daily_rets)
        var_r = sum((r - mean_r) ** 2 for r in daily_rets) / (len(daily_rets) - 1)
        std_r = math.sqrt(var_r)
        if std_r > 1e-12:
            sharpe = (mean_r / std_r) * math.sqrt(365.0)
        down_sq = [r * r for r in daily_rets if r < 0.0]
        if down_sq:
            down_dev = math.sqrt(sum(down_sq) / len(daily_rets))
            if down_dev > 1e-12:
                sortino = (mean_r / down_dev) * math.sqrt(365.0)

    days_covered = max((bars[-1].open_time_ms - bars[0].open_time_ms) / float(ONE_DAY_MS), 1.0 / 1440.0)
    cagr_pct = (
        (((eq_end / init_cap_f) ** (365.0 / days_covered) - 1.0) * 100.0)
        if (eq_end > 0.0 and init_cap_f > 0.0 and days_covered >= 1.0)
        else total_mtm_ret_pct
    )
    calmar = (cagr_pct / max_dd_pct) if max_dd_pct > 1e-9 else 0.0

    n_eval = max(1, len(bars) - 1)
    win_rate = (wins / sell_fills * 100.0) if sell_fills > 0 else 0.0
    avg_net = (float(realized_net) / sell_fills) if sell_fills > 0 else 0.0
    avg_hold = (total_hold_min / sell_fills) if sell_fills > 0 else 0.0
    denom_cap_usd = (init_cap_f * last_bar.close) if is_coinm else init_cap_f
    max_util_pct = (max_util_usd_seen / denom_cap_usd * 100.0) if denom_cap_usd > 0.0 else 0.0

    daily_series_payload: dict[str, Any] = {
        "dates": daily_dates,
        "eth_return": [round((c - first_open_f) / first_open_f * 100.0, 3) for c in daily_eth_closes],
        "equity": [round((e - init_cap_f) / init_cap_f * 100.0, 3) for e in daily_equities],
        "cf": [round(x, 2) for x in daily_cf_series],
        "dd": [round(x, 3) for x in daily_dd_series],
        "inventory": [round(x, 4) for x in daily_inv_series],
        "capital": [round(x, 2) for x in daily_cap_series],
        "weeks": all_weeks,
        "weekly": weekly_cf_vals,
        "daily_returns": [round(r, 6) for r in daily_rets],
        "eth_daily_returns": [round(r, 6) for r in eth_daily_rets],
    }

    return BacktestResult(
        symbol=cfg.symbol,
        product_type=cfg.product_type,
        settlement_unit="ETH" if is_coinm else "USDT",
        signal_name=sig_prov.name,
        fill_mode=opt.fill_mode,
        start_utc=_ms_to_iso(bars[0].open_time_ms),
        end_utc=_ms_to_iso(bars[-1].open_time_ms),
        bar_count=len(bars),
        days_covered=round(days_covered, 2),
        zone_high=zone_high_f,
        zone_low=zone_low_f,
        spacing_pct=float(cfg.spacing_pct),
        grid_levels_count=len(levels),
        initial_capital=init_cap_f,
        ending_equity=round(eq_end, 6),
        total_mtm_pnl=round(total_mtm_pnl, 6),
        total_mtm_return_pct=round(total_mtm_ret_pct, 4),
        realized_net_pnl=round(float(realized_net), 6),
        realized_gross_pnl=round(float(realized_gross), 6),
        unrealized_pnl_end=round(unreal_end, 6),
        total_fees_paid=round(float(total_fees), 6),
        total_funding_pnl=round(float(total_funding), 6),
        max_drawdown_abs=round(max_dd_abs, 6),
        max_drawdown_pct=round(max_dd_pct, 4),
        worst_unrealized_pnl=round(worst_unrealized, 6),
        worst_equity=round(worst_equity, 6),
        would_liquidate=would_liquidate,
        liquidation_bar_utc=_ms_to_iso(liquidation_bar_ms) if liquidation_bar_ms is not None else None,
        sharpe_daily_ann=round(sharpe, 4),
        sortino_daily_ann=round(sortino, 4),
        calmar_ratio=round(calmar, 4),
        buy_fills=buy_fills,
        sell_fills=sell_fills,
        closed_trades_count=sell_fills,
        win_rate_pct=round(win_rate, 2),
        avg_trade_net_pnl=round(avg_net, 6),
        avg_hold_minutes=round(avg_hold, 2),
        max_open_qty=round(max_open_qty_seen, 6),
        max_open_notional=round(max_open_notional_seen, 2),
        ending_open_qty=round(open_qty_f, 6),
        bars_in_zone_pct=round(bars_in_zone / n_eval * 100.0, 2),
        bars_below_low_pct=round(bars_below_low / n_eval * 100.0, 2),
        bars_above_high_pct=round(bars_above_high / n_eval * 100.0, 2),
        emergency_stop_triggered=emergency_triggered,
        funding_events_applied=funding_events,
        historical_funding_hits=hist_funding_hits,
        buy_volume_eth=round(buy_vol_f, 6),
        sell_volume_eth=round(sell_vol_f, 6),
        turnover_usd=round(turnover_usd_f, 2),
        max_utilization_pct=round(max_util_pct, 2),
        avg_weekly_cf_usd=round(avg_weekly_cf, 4),
        weekly_count=len(all_weeks),
        beta_to_eth=round(beta_to_eth, 4),
        corr_to_eth=round(corr_to_eth, 4),
        trades=closed_trades,
        daily_series=daily_series_payload,
    )


def find_worst_crash_window(bars: Sequence[Bar], *, window_days: int = 30) -> tuple[int, int, float]:
    """Find the steepest peak-to-trough drop within any `window_days` rolling span.

    Returns `(start_idx, end_idx, drop_pct)` where `drop_pct` is negative (e.g., `-42.5`).
    Samples 1 bar per hour for O(N/60) speed, then refines exact bar boundaries.
    """
    if len(bars) < 120:
        return 0, len(bars) - 1, 0.0
    step = 60  # hourly stride
    sampled_idx = list(range(0, len(bars), step))
    if sampled_idx[-1] != len(bars) - 1:
        sampled_idx.append(len(bars) - 1)
    max_span_ms = window_days * ONE_DAY_MS

    best_drop = 0.0
    best_s = 0
    best_e = len(bars) - 1

    # Sliding window max high over `window_days`
    for j_pos, j_idx in enumerate(sampled_idx):
        t_j = bars[j_idx].open_time_ms
        low_j = bars[j_idx].low
        # Look back up to window_days
        k_pos = j_pos - 1
        while k_pos >= 0 and (t_j - bars[sampled_idx[k_pos]].open_time_ms) <= max_span_ms:
            k_idx = sampled_idx[k_pos]
            high_k = bars[k_idx].high
            if high_k > 0.0:
                drop = (low_j - high_k) / high_k * 100.0
                if drop < best_drop:
                    best_drop = drop
                    best_s = k_idx
                    best_e = j_idx
            k_pos -= 1

    # Add 48h warmup before peak and 7 days post-trough recovery context where available
    warmup_bars = min(best_s, 200)
    tail_bars = min(len(bars) - 1 - best_e, 7 * 1440)
    return max(0, best_s - warmup_bars), min(len(bars) - 1, best_e + tail_bars), round(best_drop, 2)


def compare_signals(
    bars: Sequence[Bar],
    cfg: Lgb154Config,
    signal_providers: Sequence[SignalProvider],
    *,
    options: BacktestOptions | None = None,
    funding_rates_8h: Mapping[int, float] | None = None,
) -> list[BacktestResult]:
    """Run identical A/B backtests across multiple pluggable SignalProviders."""
    return [
        run_lgb154_backtest(
            bars,
            cfg,
            signal_provider=sp,
            options=options,
            funding_rates_8h=funding_rates_8h,
        )
        for sp in signal_providers
    ]


def render_comparison_markdown(
    results: Sequence[BacktestResult],
    *,
    title: str = "LGB154 V3 Backtest & Signal A/B Comparison",
) -> str:
    """Render concise Markdown summary table highlighting Net Return, MTM Drawdown, and Tail Risk."""
    if not results:
        return f"# {title}\n\nNo backtest results."
    r0 = results[0]
    lines = [
        f"# {title}",
        "",
        f"- **Symbol / Product:** `{r0.symbol}` (`{r0.product_type}`, settlement `{r0.settlement_unit}`)",
        f"- **Window:** `{r0.start_utc}` -> `{r0.end_utc}` ({r0.days_covered:.1f} days, {r0.bar_count:,} bars)",
        f"- **Grid Zone:** `{r0.zone_high:g} -> {r0.zone_low:g}` (spacing `{r0.spacing_pct}%`, `{r0.grid_levels_count}` levels) | **Fill Mode:** `{r0.fill_mode}`",
        f"- **Initial Capital:** `{r0.initial_capital:g} {r0.settlement_unit}` | **Zone Coverage:** in-zone `{r0.bars_in_zone_pct}%`, below-low `{r0.bars_below_low_pct}%`, above-high `{r0.bars_above_high_pct}%`",
        "",
        "| Signal | MTM Return | Realized Net | Unrealized End | Fees | Funding | Max DD (%) | Worst Unrealized | Liquidated? | Sharpe | Trades (Win%) | Avg Hold (m) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|",
    ]
    for r in results:
        liq = f"YES ({r.liquidation_bar_utc})" if r.would_liquidate else "NO"
        lines.append(
            f"| `{r.signal_name}` | {r.total_mtm_return_pct:+.2f}% ({r.total_mtm_pnl:+.2f}) "
            f"| {r.realized_net_pnl:+.2f} | {r.unrealized_pnl_end:+.2f} | -{r.total_fees_paid:.2f} "
            f"| {r.total_funding_pnl:+.2f} | {r.max_drawdown_pct:.2f}% ({r.max_drawdown_abs:.2f}) "
            f"| {r.worst_unrealized_pnl:+.2f} | {liq} | {r.sharpe_daily_ann:.2f} "
            f"| {r.closed_trades_count} ({r.win_rate_pct:.1f}%) | {r.avg_hold_minutes:.1f} |"
        )
    lines.append("")
    return "\n".join(lines)
