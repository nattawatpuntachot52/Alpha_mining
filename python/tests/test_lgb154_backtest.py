from __future__ import annotations

import io
import json
import math
import subprocess
import sys
import tempfile
import unittest
import zipfile
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_SRC = REPO_ROOT / "python"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))

from alpha_mining.research.backtest_lgb154 import (  # noqa: E402
    BacktestOptions,
    compare_signals,
    find_worst_crash_window,
    render_comparison_markdown,
    run_lgb154_backtest,
)
from alpha_mining.research.kline_loader import (  # noqa: E402
    fetch_data_api_spot_klines,
    load_funding_from_zip_bytes,
    load_klines_from_zip_bytes,
    load_local_klines,
    parse_kline_csv_stream,
)
from alpha_mining.strategy.lgb154 import (  # noqa: E402
    Bar,
    CallableSignal,
    EmaCrossSignal,
    HeikinAshiSignal,
    Lgb154Config,
    RsiRegimeSignal,
    SupertrendSignal,
    ZERO,
    build_grid_levels,
    compute_net_tp_price,
    create_signal_provider,
    ha_closed_decimal_window,
    missing_qty,
    within_spacing,
)


def _make_oscillating_bars(
    count: int = 360,
    *,
    base_price: float = 2250.0,
    amp: float = 35.0,
    period_bars: int = 40,
    wick: float = 2.5,
    start_ms: int = 1_760_000_000_000,
) -> list[Bar]:
    bars: list[Bar] = []
    prev_close = base_price
    for i in range(count):
        wave = math.sin(2.0 * math.pi * i / period_bars)
        nxt = base_price + amp * wave
        o = prev_close
        c = nxt
        hi = max(o, c) + wick
        lo = min(o, c) - wick
        bars.append(Bar(open_time_ms=start_ms + i * 60_000, open=o, high=hi, low=lo, close=c, volume=100.0))
        prev_close = c
    return bars


class TestLgb154StrategyAndBacktest(unittest.TestCase):
    def test_grid_levels_exact_parity_usdm_and_coinm(self) -> None:
        # USD-M ETHUSDT 2500 -> 2000 @ 0.20% => exactly 112 levels (Index 0..111) per README_TH.md
        usdm_levels = build_grid_levels("2500", "2000", "0.20", "0.01")
        self.assertEqual(len(usdm_levels), 112)
        self.assertEqual(usdm_levels[0], (0, Decimal("2500.00")))
        self.assertEqual(usdm_levels[-1][0], 111)
        self.assertGreaterEqual(usdm_levels[-1][1], Decimal("2000.00"))

        # COIN-M ETHUSD_PERP 2000 -> 1500 @ 1% => exactly 29 levels (Index 0..28, last=1509.43)
        coinm_levels = build_grid_levels("2000", "1500", "1", "0.01")
        self.assertEqual(len(coinm_levels), 29)
        self.assertEqual(coinm_levels[0], (0, Decimal("2000.00")))
        self.assertEqual(coinm_levels[-1], (28, Decimal("1509.43")))

        # Spacing & partial-fill recovery math parity
        self.assertTrue(within_spacing("2500", "2496", "0.20", "0.01"))
        self.assertFalse(within_spacing("2500", "2495", "0.20", "0.01"))
        self.assertEqual(missing_qty("0.01", "0.004", "0.002", "0.001"), Decimal("0.004"))

    def test_streaming_ha_matches_exact_decimal_window_parity(self) -> None:
        bars = _make_oscillating_bars(count=260, base_price=2250.0, amp=45.0, period_bars=32)
        candles = [{"open": f"{b.open:.4f}", "high": f"{b.high:.4f}", "low": f"{b.low:.4f}", "close": f"{b.close:.4f}"} for b in bars]

        ha = HeikinAshiSignal()
        matches = 0
        evaluated = 0
        for i in range(1, len(bars)):
            stream_sig = ha.on_closed_bar(bars[i - 1])
            ref_sig = ha_closed_decimal_window(candles[: i + 1], lookback=200)
            evaluated += 1
            if stream_sig == ref_sig:
                matches += 1
        self.assertEqual(matches, evaluated, "streaming O(1) HA must match exact 199-bar Decimal HA 100%")

    def test_net_tp_price_exact_parity_usdm_markup_net_and_coinm(self) -> None:
        # 1. USD-M PROFIT_PLUS_COMMISSION: 2500 * 1.0045 = 2511.25
        cfg_markup = Lgb154Config.ethusdt_usdm_default()
        self.assertIsNone(
            compute_net_tp_price(
                open_qty=Decimal("0.01"),
                cost_basis=Decimal("25.00"),
                entry_fee_open=Decimal("0.005"),
                funding_open=ZERO,
                bid=Decimal("2511.24"),
                cfg=cfg_markup,
            )
        )
        tp = compute_net_tp_price(
            open_qty=Decimal("0.01"),
            cost_basis=Decimal("25.00"),
            entry_fee_open=Decimal("0.005"),
            funding_open=ZERO,
            bid=Decimal("2511.25"),
            cfg=cfg_markup,
        )
        self.assertEqual(tp, Decimal("2511.27"))  # max(2511.25, bid + 2*0.01)

        # 2. COIN-M Inverse NET ETH 1%
        cfg_cm = Lgb154Config.ethusd_coinm_default()
        eth_basis = Decimal("10") / Decimal("2000")  # 0.005 ETH for 1 contract @ 2000
        entry_fee_eth = eth_basis * Decimal("0.0002")
        tp_cm_low = compute_net_tp_price(
            open_qty=Decimal("1"),
            cost_basis=eth_basis,
            entry_fee_open=entry_fee_eth,
            funding_open=ZERO,
            bid=Decimal("2020.00"),  # +1% gross is NOT enough after 0.10% exit + entry fee!
            cfg=cfg_cm,
        )
        self.assertIsNone(tp_cm_low)
        tp_cm_ok = compute_net_tp_price(
            open_qty=Decimal("1"),
            cost_basis=eth_basis,
            entry_fee_open=entry_fee_eth,
            funding_open=ZERO,
            bid=Decimal("2025.00"),
            cfg=cfg_cm,
        )
        self.assertIsNotNone(tp_cm_ok)
        self.assertEqual(tp_cm_ok, Decimal("2025.02"))

    def test_backtest_accounting_conservation_zero_lookahead_and_fill_sensitivity(self) -> None:
        bars = _make_oscillating_bars(count=600, base_price=2250.0, amp=60.0, period_bars=48)
        cfg = Lgb154Config.ethusdt_usdm_default()

        res_strict = run_lgb154_backtest(
            bars,
            cfg,
            signal_provider=HeikinAshiSignal(),
            options=BacktestOptions(initial_capital=Decimal("1000"), fill_mode="strict_cross"),
        )
        res_touch = run_lgb154_backtest(
            bars,
            cfg,
            signal_provider=HeikinAshiSignal(),
            options=BacktestOptions(initial_capital=Decimal("1000"), fill_mode="touch"),
        )
        self.assertGreater(res_strict.buy_fills, 0)
        self.assertGreater(res_strict.closed_trades_count, 0)
        self.assertGreaterEqual(res_touch.buy_fills, res_strict.buy_fills)

        # Accounting conservation identity:
        # ending_equity - initial_capital == realized_gross + unrealized_end - total_fees + total_funding
        expected_mtm = (
            res_strict.realized_gross_pnl
            + res_strict.unrealized_pnl_end
            - res_strict.total_fees_paid
            + res_strict.total_funding_pnl
        )
        self.assertAlmostEqual(res_strict.total_mtm_pnl, expected_mtm, places=4)
        self.assertAlmostEqual(res_strict.ending_equity, res_strict.initial_capital + res_strict.total_mtm_pnl, places=4)

        # Zero-lookahead check: mutating the LAST bar's close cannot change decisions/fills on earlier bars
        mutated = list(bars)
        last = mutated[-1]
        mutated[-1] = Bar(last.open_time_ms, last.open, last.high + 500.0, last.low, last.close + 500.0)
        res_mut = run_lgb154_backtest(
            mutated,
            cfg,
            signal_provider=HeikinAshiSignal(),
            options=BacktestOptions(initial_capital=Decimal("1000"), fill_mode="strict_cross"),
        )
        early_orig = [t for t in res_strict.trades if t.exit_time_ms < last.open_time_ms]
        early_mut = [t for t in res_mut.trades if t.exit_time_ms < last.open_time_ms]
        self.assertEqual(early_orig, early_mut)

    def test_coinm_inverse_backtest_and_crash_liquidation_detection(self) -> None:
        # Synthetic stair-step crash with dead-cat bounces (2450 -> 1100) so LGB154 accumulates inventory
        start_ms = 1_760_000_000_000
        bars: list[Bar] = []
        price = 2460.0
        for i in range(420):
            if i < 240:
                # 15-bar cycles: 5 bars bounce up (triggers GREEN batch), 10 bars drop down (fills BUYs)
                phase = i % 15
                nxt = price + 4.0 if phase < 5 else price - 4.0
            else:
                # Final capitulation drop below zone low (2000 -> 1100)
                nxt = max(1100.0, price - 6.0)
            wick = 12.0 if i < 240 else 1.0
            bars.append(
                Bar(
                    open_time_ms=start_ms + i * 60_000,
                    open=price,
                    high=max(price, nxt) + 1.0,
                    low=min(price, nxt) - wick,
                    close=nxt,
                )
            )
            price = nxt

        cfg_usdm = Lgb154Config.ethusdt_usdm_default()
        res_liq = run_lgb154_backtest(
            bars,
            cfg_usdm,
            options=BacktestOptions(initial_capital=Decimal("120"), fill_mode="strict_cross"),
        )
        self.assertGreater(res_liq.buy_fills, 10)
        self.assertLess(res_liq.worst_unrealized_pnl, -120.0)
        self.assertTrue(res_liq.would_liquidate)
        self.assertIsNotNone(res_liq.liquidation_bar_utc)

        # COIN-M Inverse profile runs cleanly and maintains ETH conservation
        bars_cm = _make_oscillating_bars(count=500, base_price=1750.0, amp=80.0, period_bars=40, wick=20.0)
        res_cm = run_lgb154_backtest(
            bars_cm,
            Lgb154Config.ethusd_coinm_default(),
            options=BacktestOptions(initial_capital=Decimal("1.0"), fill_mode="strict_cross"),
        )
        self.assertEqual(res_cm.settlement_unit, "ETH")
        self.assertGreater(res_cm.buy_fills, 0)
        self.assertGreater(res_cm.closed_trades_count, 0)
        expected_cm = (
            res_cm.realized_gross_pnl
            + res_cm.unrealized_pnl_end
            - res_cm.total_fees_paid
            + res_cm.total_funding_pnl
        )
        self.assertAlmostEqual(res_cm.total_mtm_pnl, expected_cm, places=5)

    def test_pluggable_signals_and_ab_comparison_and_crash_finder(self) -> None:
        bars = _make_oscillating_bars(count=500, base_price=2250.0, amp=55.0, period_bars=44)
        cfg = Lgb154Config.ethusdt_usdm_default()
        custom = CallableSignal("custom_bar_dir", lambda b: 1 if b.close > b.open else (-1 if b.close < b.open else 0))
        providers = [
            create_signal_provider("ha_1m"),
            create_signal_provider("ema_9_21"),
            create_signal_provider("rsi_reversion"),
            create_signal_provider("supertrend_10_3"),
            custom,
        ]
        results = compare_signals(bars, cfg, providers, options=BacktestOptions(initial_capital=Decimal("1000")))
        self.assertEqual(len(results), 5)
        md = render_comparison_markdown(results)
        for sp in providers:
            self.assertIn(sp.name, md)

        s_idx, e_idx, drop = find_worst_crash_window(bars, window_days=1)
        self.assertGreaterEqual(e_idx, s_idx)
        self.assertLessEqual(drop, 0.0)

    def test_kline_loader_csv_zip_funding_rest_and_cli_local(self) -> None:
        # 1. Microsecond Spot CSV + headered CSV + ZIP round-trip
        csv_text = (
            "1760000000000000,2250.0,2255.0,2248.0,2252.0,10.0,1760000059999999,0,0,0,0,0\n"
            "1760000060000000,2252.0,2260.0,2250.0,2258.0,12.0,1760000119999999,0,0,0,0,0\n"
        )
        parsed = parse_kline_csv_stream(io.StringIO(csv_text))
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0].open_time_ms, 1_760_000_000_000)

        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, "w") as zf:
            zf.writestr("ETHUSDT-1m-test.csv", csv_text)
        zbars = load_klines_from_zip_bytes(zbuf.getvalue())
        self.assertEqual(len(zbars), 2)

        fbuf = io.BytesIO()
        with zipfile.ZipFile(fbuf, "w") as zf:
            zf.writestr("ETHUSDT-fundingRate.csv", "calc_time,funding_interval_hours,last_funding_rate\n1760025600002,8,0.00015\n")
        frates = load_funding_from_zip_bytes(fbuf.getvalue())
        self.assertEqual(frates[1_760_025_600_000], 0.00015)

        # 2. Mock data-api.binance.vision REST transport
        def fake_rest(_url: str, _timeout: float) -> tuple[int, bytes]:
            payload = [
                [1760000000000, "2250", "2255", "2245", "2252", "10", 1760000059999],
                [1760000060000, "2252", "2260", "2251", "2258", "12", 1760000119999],
            ]
            return 200, json.dumps(payload).encode("utf-8")

        rest_bars = fetch_data_api_spot_klines(
            symbol="ETHUSDT",
            start_ms=1760000000000,
            end_ms=1760000120000,
            transport=fake_rest,
        )
        self.assertEqual(len(rest_bars), 2)

        # 3. End-to-end CLI local CSV run
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "eth_sample.csv"
            bars = _make_oscillating_bars(count=180, base_price=2250.0, amp=45.0, period_bars=30)
            lines = ["open_time_ms,open,high,low,close,volume"]
            for b in bars:
                lines.append(f"{b.open_time_ms},{b.open:.4f},{b.high:.4f},{b.low:.4f},{b.close:.4f},{b.volume:.2f}")
            csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            self.assertEqual(len(load_local_klines(csv_path)), 180)

            out_json = Path(tmp) / "report.json"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "backtest_lgb154.py"),
                    "--source",
                    "local",
                    "--local-path",
                    str(csv_path),
                    "--signals",
                    "ha_1m,ema_9_21",
                    "--json-out",
                    str(out_json),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            rep = json.loads(out_json.read_text(encoding="utf-8"))
            self.assertEqual(len(rep["main_results"]), 2)
            self.assertEqual(rep["main_results"][0]["signal_name"], "ha_1m")
            self.assertEqual(rep["main_results"][1]["signal_name"], "ema_9_21")

    def test_recovery_mode_partial_only_avoids_zero_fill_zombie_starvation(self) -> None:
        # Phase 1: price visits ~2080, triggers GREEN batch below 2080 that cancels unfilled (0 fills).
        # Phase 2: price jumps to ~2450 and oscillates there.
        # Under legacy_v3, the 5 unfilled zombie groups near ~2075 consume all 5 batch slots and starve ~2445!
        # Under partial_only, zero-fill cancelled groups are discarded so ~2445 fills normally.
        start_ms = 1_760_000_000_000
        bars: list[Bar] = []
        # 20 bars rising gently around 2080 -> GREEN batch placed near 2075..2055 (no dip fills), then 10 RED bars cancel them
        p = 2070.0
        for i in range(30):
            nxt = p + (1.0 if i < 15 else -1.0)
            bars.append(Bar(start_ms + i * 60_000, p, max(p, nxt) + 0.5, min(p, nxt) - 0.5, nxt))
            p = nxt
        # Jump up to 2450 and oscillate with enough lower wick to fill levels near 2445
        p = 2450.0
        for i in range(30, 210):
            phase = (i - 30) % 20
            nxt = p + (2.0 if phase < 10 else -2.0)
            bars.append(Bar(start_ms + i * 60_000, p, max(p, nxt) + 2.0, min(p, nxt) - 10.0, nxt))
            p = nxt

        cfg = Lgb154Config.ethusdt_usdm_default()
        res_clean = run_lgb154_backtest(
            bars, cfg, options=BacktestOptions(initial_capital=Decimal("1000"), recovery_mode="partial_only")
        )
        res_legacy = run_lgb154_backtest(
            bars, cfg, options=BacktestOptions(initial_capital=Decimal("1000"), recovery_mode="legacy_v3")
        )
        self.assertGreater(res_clean.buy_fills, 0)
        self.assertEqual(res_legacy.buy_fills, 0)


if __name__ == "__main__":
    unittest.main()
