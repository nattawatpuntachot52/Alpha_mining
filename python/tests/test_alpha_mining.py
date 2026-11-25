"""Unit, causality, and 2-round CLI integration tests for the Daily Alpha Mining Factory."""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_SRC = REPO_ROOT / "python"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))

from alpha_mining.research.alpha_backtest import AlphaBacktestOptions, run_alpha_backtest  # noqa: E402
from alpha_mining.research.alpha_data import resample_bars  # noqa: E402
from alpha_mining.research.alpha_signals import FAMILIES, Series, TIMEFRAME_MS, build_positions  # noqa: E402
from alpha_mining.research.alpha_spec import parse_spec  # noqa: E402
from alpha_mining.research.alpha_store import AlphaModelStore  # noqa: E402
from alpha_mining.strategy.lgb154 import Bar  # noqa: E402


def _make_series(n: int = 320, tf: str = "1h", seed_amp: float = 40.0) -> Series:
    tf_ms = TIMEFRAME_MS[tf]
    t0 = 1_704_067_200_000  # 2024-01-01T00:00:00Z
    ts, os_, hs, ls, cs = [], [], [], [], []
    prev = 2000.0
    for i in range(n):
        nxt = 2000.0 + seed_amp * math.sin(i / 7.0) + 18.0 * math.cos(i / 19.0) + 0.35 * i
        hi = max(prev, nxt) + 6.0 + 3.0 * abs(math.sin(i))
        lo = min(prev, nxt) - 6.0 - 3.0 * abs(math.cos(i))
        ts.append(t0 + i * tf_ms)
        os_.append(prev)
        hs.append(hi)
        ls.append(lo)
        cs.append(nxt)
        prev = nxt
    return Series(tuple(ts), tuple(os_), tuple(hs), tuple(ls), tuple(cs), tf_ms)


SAMPLE_PARAMS: dict[str, dict] = {
    "momentum_roc": {"lookback": 14},
    "ma_cross": {"ma": "ema", "fast": 5, "slow": 20},
    "heiken_ma_cross": {"ma": "sma", "fast": 8, "slow": 21, "block_entry_weekdays": [3]},
    "donchian_breakout": {"entry": 20, "exit": 10, "atr_period": 14, "squeeze_ratio": 1.1},
    "session_time": {"start_hour_utc": 20, "end_hour_utc": 4, "mode": "long_inside"},
    "impulse_efficiency": {"k": 3, "w": 20, "z_threshold": 1.2, "er_threshold": 0.6, "hold_bars": 8},
    "ibs_reversion": {"low_threshold": 0.25, "high_threshold": 0.75, "exit_long": 0.65, "trend_sma": 50, "max_hold": 6},
    "rsi_reversion": {"period": 14, "buy_below": 35, "sell_above": 65, "exit_long": 50, "exit_short": 50},
    "rsi_regime": {"period": 14, "upper": 55, "mid": 50, "lower": 45},
    "bollinger_reversion": {"period": 20, "k": 1.8, "exit_z": 0.0},
    "vol_expansion_breakout": {"atr_period": 14, "k_atr": 1.2, "hold_bars": 6},
    "asia_range_breakout": {"range_start_hour_utc": 0, "range_end_hour_utc": 7, "eod_hour_utc": 20},
    "calendar_turn": {"days_of_month": [[1, 10]], "side": "long"},
}


class TestAlphaCausalityAndBacktest(unittest.TestCase):
    def test_every_signal_family_is_strictly_causal(self) -> None:
        self.assertEqual(set(SAMPLE_PARAMS.keys()), set(FAMILIES.keys()))
        full = _make_series(260, tf="1h")
        cut = 170
        prefix = full.truncate(cut)
        for fam, params in SAMPLE_PARAMS.items():
            sig_full = build_positions(full, fam, params, "long_short")
            sig_pref = build_positions(prefix, fam, params, "long_short")
            self.assertEqual(
                sig_full[:cut],
                sig_pref,
                f"lookahead detected in family {fam!r}: truncating future bars altered past signals",
            )

    def test_backtest_sl_priority_no_immediate_reentry_and_cost_drag(self) -> None:
        # Construct 60 bars where bar 10 has both SL and TP hit intrabar after entering long at bar 10 open.
        tf_ms = TIMEFRAME_MS["1h"]
        t0 = 1_704_067_200_000
        ts, os_, hs, ls, cs = [], [], [], [], []
        for i in range(60):
            ts.append(t0 + i * tf_ms)
            if i == 10:
                os_.append(100.0)
                hs.append(105.0)  # +5% would hit 2% TP
                ls.append(95.0)   # -5% would hit 2% SL -> SL must win conservatively
                cs.append(102.0)
            else:
                os_.append(100.0)
                hs.append(100.5)
                ls.append(99.5)
                cs.append(100.0)
        ser = Series(tuple(ts), tuple(os_), tuple(hs), tuple(ls), tuple(cs), tf_ms)
        # Desired stays +1 from bar 9 through bar 20: after SL at bar 10, must NOT re-enter while desired stays +1.
        desired = [1 if 9 <= i <= 20 else 0 for i in range(60)]

        res_sl = run_alpha_backtest(
            ser,
            desired,
            AlphaBacktestOptions(cost_bps_per_side=0.0, sl_pct=2.0, tp_pct=2.0),
            symbol="XAUUSD",
            timeframe="1h",
            direction="long_only",
        )
        self.assertEqual(res_sl.metrics["trades"], 1, "must not re-enter on unchanged signal after SL")
        self.assertAlmostEqual(res_sl.metrics["total_return_pct"], -2.0, places=3)

        # Higher cost must strictly lower ending return when trades occur.
        ser_trend = _make_series(220, tf="1h")
        des_trend = build_positions(ser_trend, "momentum_roc", {"lookback": 10}, "long_short")
        r_low = run_alpha_backtest(ser_trend, des_trend, AlphaBacktestOptions(cost_bps_per_side=1.0))
        r_high = run_alpha_backtest(ser_trend, des_trend, AlphaBacktestOptions(cost_bps_per_side=20.0))
        self.assertGreater(r_low.metrics["total_return_pct"], r_high.metrics["total_return_pct"])

    def test_resample_bars_causal_aggregation(self) -> None:
        t0 = 1_704_067_200_000
        bars_1m = [
            Bar(open_time_ms=t0 + i * 60_000, open=100.0 + i, high=102.0 + i, low=99.0 + i, close=101.0 + i, volume=2.0)
            for i in range(30)
        ]
        bars_15m = resample_bars(bars_1m, TIMEFRAME_MS["15m"])
        self.assertEqual(len(bars_15m), 2)
        self.assertEqual(bars_15m[0].open_time_ms, t0)
        self.assertEqual(bars_15m[0].open, 100.0)
        self.assertEqual(bars_15m[0].high, 102.0 + 14)
        self.assertEqual(bars_15m[0].low, 99.0)
        self.assertEqual(bars_15m[0].close, 101.0 + 14)
        self.assertAlmostEqual(bars_15m[0].volume, 30.0)
        self.assertEqual(bars_15m[1].open_time_ms, t0 + 15 * 60_000)


class TestAlphaQueueAndTwoRoundCLI(unittest.TestCase):
    def test_daily_queue_config_has_140_unique_multi_tf_candidates(self) -> None:
        qpath = REPO_ROOT / "config" / "alpha_mining" / "daily_queue.json"
        self.assertTrue(qpath.is_file())
        q = json.loads(qpath.read_text(encoding="utf-8"))
        self.assertEqual(q["models_per_day"], 20)
        self.assertEqual(q["models_per_symbol_per_day"], 10)
        self.assertEqual(q["models_per_round"], 10)
        self.assertEqual(q["models_per_symbol_per_round"], 5)
        self.assertEqual(q["rounds_per_day"], 2)

        cands = q["candidates"]
        self.assertGreaterEqual(len(cands), 140)
        seen_keys: set[str] = set()
        by_sym: dict[str, int] = {}
        tfs: set[str] = set()
        for raw in cands:
            spec = parse_spec(raw)
            k = spec.key()
            self.assertNotIn(k, seen_keys, f"duplicate spec in alpha daily_queue.json: {raw}")
            seen_keys.add(k)
            by_sym[spec.symbol] = by_sym.get(spec.symbol, 0) + 1
            tfs.add(spec.timeframe)
        self.assertGreaterEqual(by_sym.get("XAUUSD", 0), 70)
        self.assertGreaterEqual(by_sym.get("ETHUSDT", 0), 70)
        self.assertTrue({"5m", "15m", "30m", "1h", "4h", "1d"}.issubset(tfs))

        # next-batch picks exactly 5 XAUUSD + 5 ETHUSDT on an empty store.
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "alpha_mining.py"),
                    "--store-dir",
                    str(Path(tmp) / "alpha_store"),
                    "next-batch",
                    "--queue-file",
                    str(qpath),
                    "--per-symbol",
                    "5",
                    "--json",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            nb = json.loads(proc.stdout)
            self.assertEqual(nb["count"], 10)
            self.assertEqual(nb["by_symbol"], {"XAUUSD": 5, "ETHUSDT": 5})

    def test_two_rounds_accumulate_on_same_date_and_render_offline_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            local_dir = tmp_path / "data"
            local_dir.mkdir()
            t0 = 1_704_067_200_000
            # Write synthetic 1h and 15m CSVs for both XAUUSD and ETHUSDT (300 bars each)
            for sym, base in (("XAUUSD", 2300.0), ("ETHUSDT", 3000.0)):
                for tf in ("15m", "30m", "1h", "4h"):
                    tf_ms = TIMEFRAME_MS[tf]
                    lines = ["open_time_ms,open,high,low,close,volume"]
                    prev = base
                    for i in range(300):
                        nxt = base + 80.0 * math.sin(i / 9.0) + 0.6 * i
                        hi = max(prev, nxt) + 10.0
                        lo = min(prev, nxt) - 10.0
                        lines.append(f"{t0 + i * tf_ms},{prev:.4f},{hi:.4f},{lo:.4f},{nxt:.4f},100.0")
                        prev = nxt
                    (local_dir / f"{sym}_{tf}.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

            mini_queue = tmp_path / "mini_queue.json"
            mini_queue.write_text(
                json.dumps(
                    {
                        "models_per_symbol_per_round": 2,
                        "candidates": [
                            {"symbol": "XAUUSD", "timeframe": "1h", "family": "momentum_roc", "params": {"lookback": 14}, "direction": "long_only", "hypothesis": "x1"},
                            {"symbol": "XAUUSD", "timeframe": "15m", "family": "heiken_ma_cross", "params": {"ma": "sma", "fast": 12, "slow": 26}, "direction": "long_only", "hypothesis": "x2"},
                            {"symbol": "ETHUSDT", "timeframe": "1h", "family": "momentum_roc", "params": {"lookback": 14}, "direction": "long_only", "hypothesis": "e1"},
                            {"symbol": "ETHUSDT", "timeframe": "30m", "family": "donchian_breakout", "params": {"entry": 20, "exit": 10}, "direction": "long_short", "hypothesis": "e2"},
                            {"symbol": "XAUUSD", "timeframe": "4h", "family": "ma_cross", "params": {"ma": "ema", "fast": 5, "slow": 20}, "direction": "long_short", "hypothesis": "x3"},
                            {"symbol": "XAUUSD", "timeframe": "30m", "family": "rsi_regime", "params": {"period": 14, "upper": 55, "mid": 50, "lower": 45}, "direction": "long_only", "hypothesis": "x4"},
                            {"symbol": "ETHUSDT", "timeframe": "4h", "family": "ma_cross", "params": {"ma": "ema", "fast": 5, "slow": 20}, "direction": "long_short", "hypothesis": "e3"},
                            {"symbol": "ETHUSDT", "timeframe": "15m", "family": "ibs_reversion", "params": {"low_threshold": 0.2, "high_threshold": 0.8, "exit_long": 0.7, "max_hold": 5}, "direction": "long_only", "hypothesis": "e4"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            store_dir = tmp_path / "alpha_mining"
            cli = [
                sys.executable,
                str(REPO_ROOT / "scripts" / "alpha_mining.py"),
                "--store-dir",
                str(store_dir),
                "run-daily",
                "--date",
                "2026-11-24",
                "--queue-file",
                str(mini_queue),
                "--per-symbol",
                "2",
                "--local-dir",
                str(local_dir),
                "--min-trades",
                "1",
            ]
            r1 = subprocess.run(cli, capture_output=True, text=True, check=False)
            self.assertEqual(r1.returncode, 0, r1.stderr)
            b1 = json.loads((store_dir / "daily" / "2026-11-24" / "batch.json").read_text(encoding="utf-8"))
            self.assertEqual(b1["model_count"], 4)
            self.assertEqual(b1["rounds"], [1])

            r2 = subprocess.run(cli, capture_output=True, text=True, check=False)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            b2 = json.loads((store_dir / "daily" / "2026-11-24" / "batch.json").read_text(encoding="utf-8"))
            self.assertEqual(b2["model_count"], 8, "Round 2 must accumulate into Round 1")
            self.assertEqual(b2["rounds"], [1, 2])
            syms = [m["symbol"] for m in b2["models"]]
            self.assertEqual(syms.count("XAUUSD"), 4)
            self.assertEqual(syms.count("ETHUSDT"), 4)

            # Offline zero-CDN verification
            dash_html = (store_dir / "daily" / "2026-11-24" / "dashboard.html").read_text(encoding="utf-8")
            hub_html = (store_dir / "index.html").read_text(encoding="utf-8")
            for text in (dash_html, hub_html):
                self.assertNotIn("https://", text)
                self.assertNotIn("http://", text)
            self.assertIn("alpha_001_xauusd", dash_html)
            self.assertIn("alpha_008_ethusdt", dash_html)
            self.assertIn("rank-panels", dash_html)
            self.assertIn("drawRankPanels", dash_html)

            # Ranking board records N_trials=8 and DSR
            store = AlphaModelStore(store_dir)
            ranking = json.loads(store.ranking_path.read_text(encoding="utf-8"))
            self.assertEqual(ranking["total_trials"], 8)
            self.assertIn("top_ranked_by_symbol", ranking)

            # Explicit --max-rounds 2 refuses a 3rd round; default (4 rounds/day) allows rounds 1-4 and skips round 5.
            r3_cap2 = subprocess.run(cli + ["--max-rounds", "2"], capture_output=True, text=True, check=False)
            self.assertEqual(r3_cap2.returncode, 0, r3_cap2.stderr)
            self.assertIn("nothing to mine", r3_cap2.stdout)

            store4 = tmp_path / "alpha_mining_4r"
            cli4 = [
                sys.executable,
                str(REPO_ROOT / "scripts" / "alpha_mining.py"),
                "--store-dir",
                str(store4),
                "run-daily",
                "--date",
                "2026-11-25",
                "--queue-file",
                str(mini_queue),
                "--per-symbol",
                "1",
                "--local-dir",
                str(local_dir),
                "--min-trades",
                "1",
            ]
            for expected_round in (1, 2, 3, 4):
                rx = subprocess.run(cli4, capture_output=True, text=True, check=False)
                self.assertEqual(rx.returncode, 0, rx.stderr)
                bx = json.loads((store4 / "daily" / "2026-11-25" / "batch.json").read_text(encoding="utf-8"))
                self.assertEqual(bx["rounds"], list(range(1, expected_round + 1)))
                self.assertEqual(bx["model_count"], expected_round * 2)

            r5 = subprocess.run(cli4, capture_output=True, text=True, check=False)
            self.assertEqual(r5.returncode, 0, r5.stderr)
            self.assertIn("nothing to mine", r5.stdout)


if __name__ == "__main__":
    unittest.main()
