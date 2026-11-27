"""Unit and invariant tests for the 5 Beta Mining SpacingProvider families and NET Dynamic TP."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
import math
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_SRC = REPO_ROOT / "python"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))

from alpha_mining.research.backtest_lgb154 import (  # noqa: E402
    BacktestOptions,
    run_lgb154_backtest,
)
from alpha_mining.research.beta_store import BetaModelStore  # noqa: E402
from alpha_mining.strategy.lgb154 import (  # noqa: E402
    Bar,
    Lgb154Config,
    RpRange,
    build_grid_levels,
    create_signal_provider,
    create_spacing_provider,
    create_tp_policy,
    parse_beta_model_spec,
)


def _synth_crash_rebound_bars(n: int = 900) -> list[Bar]:
    """Generate deterministic 1m OHLCV bars featuring calm oscillation, steep crash, and recovery."""
    bars: list[Bar] = []
    t0 = 1_760_000_000_000
    price = 3200.0
    for i in range(n):
        if i < 250:
            drift = 18.0 * math.sin(2.0 * math.pi * i / 28.0)
            target = 3200.0 + drift
            wick = 5.0
        elif i < 550:
            # Steep waterfall crash from 3200 -> 2150 with volatile wicks
            prog = (i - 250) / 300.0
            target = 3200.0 - 1050.0 * prog + 35.0 * math.sin(2.0 * math.pi * i / 19.0)
            wick = 18.0
        else:
            # Recovery & range oscillation 2150 -> 2850
            prog = (i - 550) / max(1, n - 550)
            target = 2150.0 + 700.0 * prog + 30.0 * math.sin(2.0 * math.pi * i / 24.0)
            wick = 9.0
        hi = max(price, target) + wick
        lo = max(100.0, min(price, target) - wick)
        bars.append(Bar(open_time_ms=t0 + i * 60_000, open=price, high=hi, low=lo, close=target, volume=100.0))
        price = target
    return bars


def _cfg_2eth() -> Lgb154Config:
    base = Lgb154Config.ethusdt_usdm_default()
    levels = build_grid_levels(Decimal("5000"), Decimal("500"), Decimal("0.20"), base.tick_size)
    return replace(
        base,
        high=Decimal("5000"),
        low=Decimal("500"),
        spacing_pct=Decimal("0.20"),
        order_quantity=Decimal("0.05"),
        max_entry_order_quantity=Decimal("0.05"),
        max_entry_order_notional_usdt=Decimal("500"),
        max_position_quantity=Decimal("2.0"),
        max_notional_usdt=Decimal("10000"),
        rp_ranges=(
            RpRange(
                from_grid=0,
                to_grid=levels[-1][0],
                rp_id="RP001",
                max_quantity=Decimal("2.0"),
                max_notional_usdt=Decimal("10000"),
            ),
        ),
    )


class TestSpacingFamiliesAndDynamicTp(unittest.TestCase):
    def test_all_five_spacing_families_parse_and_respect_bounds(self) -> None:
        specs = [
            ("fixed_0.45", "fixed_pct", False),
            ("atr_60_3.5", "atr_range", True),
            ("parkinson_60_4.0", "atr_range", True),
            ("logret_90_4.2", "log_return_vol", True),
            ("ewma_logret_45_4.0_1.6", "ewma_asymmetric", True),
            ("inv_step_0.20_3.0_2.2", "inventory_hybrid", True),
        ]
        bars = _synth_crash_rebound_bars(200)
        for spec_str, expected_mode, expected_dyn in specs:
            prov = create_spacing_provider(spec_str)
            self.assertEqual(prov.mode, expected_mode)
            self.assertEqual(prov.is_dynamic, expected_dyn)
            for b in bars:
                prov.on_closed_bar(b)
                s0 = prov.current_spacing_pct(0.0)
                s1 = prov.current_spacing_pct(1.0)
                self.assertGreaterEqual(s0, prov.min_spacing_pct - 1e-9)
                self.assertLessEqual(s0, prov.max_spacing_pct + 1e-9)
                self.assertGreaterEqual(s1, prov.min_spacing_pct - 1e-9)
                self.assertLessEqual(s1, prov.max_spacing_pct + 1e-9)
                if expected_mode == "inventory_hybrid":
                    self.assertGreaterEqual(s1, s0)

    def test_zero_lookahead_and_strict_2eth_cap_and_100pct_net_tp_winrate(self) -> None:
        bars = _synth_crash_rebound_bars(900)
        cfg = _cfg_2eth()
        opt = BacktestOptions(
            initial_capital=Decimal("10000"),
            fill_mode="strict_cross",
            default_funding_rate_8h=0.0005,  # Heavy +5 bps per 8h funding penalty on longs!
            use_funding=True,
            record_trades=True,
        )

        five_models = [
            "ha_1m@fixed_0.45",
            "ha_1m@parkinson_60_4.0",
            "ha_1m@logret_90_4.2",
            "ha_1m@ewma_logret_45_4.0_1.6",
            "ha_1m@inv_step_0.20_3.0_2.2",
        ]
        for raw in five_models:
            sig_s, sp_s, tp_s = parse_beta_model_spec(raw)
            res = run_lgb154_backtest(
                bars,
                cfg,
                signal_provider=create_signal_provider(sig_s),
                spacing_provider=create_spacing_provider(sp_s),
                tp_policy=create_tp_policy(tp_s),
                options=opt,
            )
            # 1. Strict 2.0 ETH cap never exceeded
            self.assertLessEqual(res.max_open_qty, 2.0 + 1e-9, f"{raw} exceeded 2.0 ETH cap")
            # 2. Accounting conservation: total MTM PnL == realized_net + unrealized_end + funding_on_open
            # Note: ending_equity = initial_capital + realized_net + open_funding_total + raw_open_mtm
            self.assertAlmostEqual(
                res.ending_equity - res.initial_capital,
                res.total_mtm_pnl,
                places=4,
            )
            # 3. Every closed cycle under NET Dynamic TP is strictly net-positive after fees AND heavy funding!
            self.assertGreater(res.closed_trades_count, 0, f"{raw} should close cycles")
            for tr in res.trades:
                self.assertGreater(tr.net_pnl, 0.0, f"{raw} closed a losing trade under NET Dynamic TP: {tr}")
            self.assertEqual(res.win_rate_pct, 100.0)
            self.assertEqual(res.profit_factor, 999.0)

        # 4. Zero-lookahead causal check: mutating bars[450:] must leave prefix run bars[:450] identical!
        mutated = list(bars)
        for j in range(450, len(mutated)):
            b = mutated[j]
            mutated[j] = Bar(b.open_time_ms, b.open * 0.5, b.high * 0.5, b.low * 0.5, b.close * 0.5, b.volume)

        r_prefix_orig = run_lgb154_backtest(
            bars[:450],
            cfg,
            signal_provider=create_signal_provider("ha_1m"),
            spacing_provider=create_spacing_provider("logret_90_4.2"),
            tp_policy=create_tp_policy("net_dyn"),
            options=opt,
        )
        r_prefix_mut = run_lgb154_backtest(
            mutated[:450],
            cfg,
            signal_provider=create_signal_provider("ha_1m"),
            spacing_provider=create_spacing_provider("logret_90_4.2"),
            tp_policy=create_tp_policy("net_dyn"),
            options=opt,
        )
        self.assertEqual(r_prefix_orig.realized_net_pnl, r_prefix_mut.realized_net_pnl)
        self.assertEqual(r_prefix_orig.buy_fills, r_prefix_mut.buy_fills)

    def test_consistent_profit_ranking_requires_positive_mtm(self) -> None:
        bars = _synth_crash_rebound_bars(400)
        cfg = _cfg_2eth()
        opt = BacktestOptions(initial_capital=Decimal("10000"))
        with tempfile.TemporaryDirectory() as tmp:
            store = BetaModelStore(Path(tmp) / "store")
            r_pos = run_lgb154_backtest(
                bars,
                cfg,
                signal_provider=create_signal_provider("ha_1m"),
                spacing_provider=create_spacing_provider("fixed_0.45"),
                tp_policy=create_tp_policy("net_dyn"),
                options=opt,
            )
            r_neg = replace(r_pos, total_mtm_pnl=-500.0, total_mtm_return_pct=-5.0, realized_net_pnl=4000.0)
            store.record_model_run(model_id="beta_001_neg_mtm", batch_date="2026-11-26", signal_spec="ha_1m", result=r_neg)
            store.record_model_run(
                model_id="beta_002_pos_mtm", batch_date="2026-11-26", signal_spec="ha_1m@fixed_0.45", result=r_pos
            )
            if r_pos.total_mtm_pnl > 0:
                board = store.compute_ranking(rank_by="consistent_profit", write_file=False)
                self.assertEqual([x["model_id"] for x in board["top_ranked"]], ["beta_002_pos_mtm"])
                self.assertIn("NEGATIVE_OR_ZERO_MTM_PNL", board["disqualified"][0]["disqualify_reasons"])


if __name__ == "__main__":
    unittest.main()
