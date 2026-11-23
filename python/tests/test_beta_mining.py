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

from alpha_mining.research.backtest_lgb154 import BacktestResult  # noqa: E402
from alpha_mining.research.beta_dashboard import (  # noqa: E402
    render_daily_summary_markdown,
    render_dashboard_html,
)
from alpha_mining.research.beta_store import (  # noqa: E402
    BetaModelStore,
    compute_return_correlation_matrix,
    validate_model_id,
)
from alpha_mining.strategy.lgb154 import Bar  # noqa: E402


def _fake_result(
    *,
    signal_name: str,
    cashflow: float,
    max_dd_pct: float,
    mtm_pct: float = 0.0,
    liquidated: bool = False,
) -> BacktestResult:
    init = 10000.0
    mtm_usd = init * mtm_pct / 100.0
    return BacktestResult(
        symbol="ETHUSDT",
        product_type="USD_M",
        settlement_unit="USDT",
        signal_name=signal_name,
        fill_mode="strict_cross",
        start_utc="2024-02-27T00:00:00Z",
        end_utc="2026-11-21T23:59:00Z",
        bar_count=1000,
        days_covered=999.0,
        zone_high=5000.0,
        zone_low=500.0,
        spacing_pct=0.2,
        grid_levels_count=1151,
        initial_capital=init,
        ending_equity=init + mtm_usd,
        total_mtm_pnl=mtm_usd,
        total_mtm_return_pct=mtm_pct,
        realized_net_pnl=cashflow,
        realized_gross_pnl=cashflow + 100.0,
        unrealized_pnl_end=mtm_usd - cashflow,
        total_fees_paid=50.0,
        total_funding_pnl=-50.0,
        max_drawdown_abs=init * max_dd_pct / 100.0,
        max_drawdown_pct=max_dd_pct,
        worst_unrealized_pnl=-init * max_dd_pct / 100.0,
        worst_equity=init * (1.0 - max_dd_pct / 100.0),
        would_liquidate=liquidated,
        liquidation_bar_utc="2026-02-01T00:00:00Z" if liquidated else None,
        sharpe_daily_ann=0.5,
        sortino_daily_ann=0.7,
        calmar_ratio=0.3,
        buy_fills=500,
        sell_fills=490,
        closed_trades_count=490,
        win_rate_pct=98.0,
        avg_trade_net_pnl=cashflow / 490.0,
        avg_hold_minutes=1200.0,
        max_open_qty=2.0,
        max_open_notional=5000.0,
        ending_open_qty=1.0,
        bars_in_zone_pct=100.0,
        bars_below_low_pct=0.0,
        bars_above_high_pct=0.0,
        emergency_stop_triggered=None,
        funding_events_applied=100,
        historical_funding_hits=100,
    )


class TestBetaMiningStoreAndDashboard(unittest.TestCase):
    def test_isolated_storage_ranking_cashflow_dd_tiebreak_and_hard_gates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = BetaModelStore(Path(tmp) / "beta_mining")

            # Reject unsafe model IDs
            with self.assertRaises(ValueError):
                validate_model_id("../escape")
            with self.assertRaises(ValueError):
                validate_model_id("UpperCaseBad")

            # Create 12 models: 10 qualified, 1 DD > 40% disqualified, 1 liquidated disqualified
            # Include exact Cashflow tie ($3000) to verify secondary DD ASC tie-breaker!
            specs = [
                ("beta_001_tie_high_dd", "ha_1m", 3000.0, 28.0, False),
                ("beta_002_tie_low_dd", "ema_9_21", 3000.0, 18.0, False),
                ("beta_003_top_cf", "rsi_reversion", 3500.0, 35.0, False),
                ("beta_004_dd_fail", "supertrend_10_3", 4500.0, 41.5, False),  # > 40% DD gate -> disqualified
                ("beta_005_liq_fail", "ema_12_26", 5000.0, 20.0, True),       # liquidated -> disqualified
            ]
            for i in range(6, 13):
                specs.append((f"beta_{i:03d}_cand", "ha_1m", 2000.0 + i * 50.0, 15.0 + i, False))

            for mid, sig, cf, dd, liq in specs:
                store.record_model_run(
                    model_id=mid,
                    batch_date="2026-11-23",
                    signal_spec=sig,
                    result=_fake_result(signal_name=sig, cashflow=cf, max_dd_pct=dd, liquidated=liq),
                )

            # Verify isolated folder structure for one model
            loaded = store.load_model("beta_002_tie_low_dd")
            self.assertTrue((loaded.model_dir / "spec.json").is_file())
            self.assertTrue((loaded.model_dir / "latest_metrics.json").is_file())
            self.assertEqual(len(loaded.run_files), 1)
            self.assertEqual(loaded.spec["trial_number"], 2)

            # Compute Top-9 Ranking Board with Cashflow DESC -> DD ASC & Hard Gate (No Liq + DD <= 40%)
            board = store.compute_ranking(top_n=9, max_dd_pct=40.0, rank_by="cashflow_dd", write_file=True)
            self.assertTrue(store.ranking_path.is_file())
            self.assertEqual(board["total_trials"], 12)
            self.assertEqual(board["qualified_count"], 10)
            self.assertEqual(board["disqualified_count"], 2)
            self.assertEqual(len(board["top_ranked"]), 9)

            ranked_ids = [r["model_id"] for r in board["top_ranked"]]
            # #1 must be beta_003_top_cf ($3500), #2 must be beta_002_tie_low_dd ($3000, 18% DD) BEFORE beta_001_tie_high_dd ($3000, 28% DD)!
            self.assertEqual(ranked_ids[0], "beta_003_top_cf")
            self.assertEqual(ranked_ids[1], "beta_002_tie_low_dd")
            self.assertEqual(ranked_ids[2], "beta_001_tie_high_dd")
            self.assertNotIn("beta_004_dd_fail", ranked_ids)
            self.assertNotIn("beta_005_liq_fail", ranked_ids)

            disq_map = {d["model_id"]: d["disqualify_reasons"] for d in board["disqualified"]}
            self.assertIn("MAX_DD_EXCEEDS_40PCT", disq_map["beta_004_dd_fail"])
            self.assertIn("LIQUIDATED", disq_map["beta_005_liq_fail"])

            # Verify custom isolated signal.py drop-in loading
            custom_py = loaded.model_dir / "signal.py"
            custom_py.write_text(
                "from alpha_mining.strategy.lgb154 import CallableSignal\n"
                "def build_signal(spec):\n"
                "    return CallableSignal('custom_plugin_test', lambda b: 1 if b.close >= b.open else -1)\n",
                encoding="utf-8",
            )
            sp = store.load_signal_provider("beta_002_tie_low_dd")
            self.assertEqual(sp.name, "custom_plugin_test")
            self.assertEqual(sp.on_closed_bar(Bar(0, 100.0, 102.0, 99.0, 101.0)), 1)

            # Verify offline self-contained dashboard HTML (no external CDN links)
            all_m = [m.latest_metrics for m in store.load_all_models()]
            md = render_daily_summary_markdown(batch_date="2026-11-23", batch_metrics=all_m[:5], ranking_board=board)
            html_out = render_dashboard_html(
                batch_date="2026-11-23",
                batch_metrics=all_m[:5],
                all_models_metrics=all_m,
                ranking_board=board,
            )
            self.assertIn("beta_003_top_cf", md)
            self.assertIn("beta_003_top_cf", html_out)
            self.assertNotIn("https://", html_out)
            self.assertNotIn("http://", html_out)

    def test_cli_run_daily_rank_show_compare_and_rebuild_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            csv_path = tmp_path / "sample_1m.csv"
            start_ms = 1_760_000_000_000
            lines = ["open_time_ms,open,high,low,close,volume"]
            prev = 2500.0
            for i in range(240):
                nxt = 2500.0 + 50.0 * math.sin(2.0 * math.pi * i / 36.0)
                hi = max(prev, nxt) + 4.0
                lo = min(prev, nxt) - 4.0
                lines.append(f"{start_ms + i * 60_000},{prev:.4f},{hi:.4f},{lo:.4f},{nxt:.4f},100.0")
                prev = nxt
            csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            store_dir = tmp_path / "beta_mining"
            cli = [sys.executable, str(REPO_ROOT / "scripts" / "beta_mining.py"), "--store-dir", str(store_dir)]

            r1 = subprocess.run(
                cli
                + [
                    "run-daily",
                    "--date",
                    "2026-11-23",
                    "--source",
                    "local",
                    "--local-path",
                    str(csv_path),
                    "--signals",
                    "ha_1m,ema_9_21,ema_12_26,supertrend_10_3,rsi_reversion_14_40_60",
                    "--stress-crash-days",
                    "0",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(r1.returncode, 0, r1.stderr)
            self.assertTrue((store_dir / "catalog.json").is_file())
            self.assertTrue((store_dir / "ranking_top9.json").is_file())
            dash_path = store_dir / "daily" / "2026-11-23" / "dashboard.html"
            self.assertTrue(dash_path.is_file())
            self.assertTrue((store_dir / "daily" / "2026-11-23" / "daily_summary.md").is_file())

            # Verify every model persisted latest_series.json and dashboard embeds all 9 panels with zero CDN links
            store = BetaModelStore(store_dir)
            mids = store.list_model_ids()
            self.assertEqual(len(mids), 5)
            batch_series = store.load_batch_series(mids)
            self.assertEqual(len(batch_series), 5)
            for mid in mids:
                self.assertTrue((store_dir / "models" / mid / "latest_series.json").is_file())

            dash_text = dash_path.read_text(encoding="utf-8")
            self.assertNotIn("https://", dash_text)
            self.assertNotIn("http://", dash_text)
            for cid in (
                "chart-weekly",
                "chart-cumulative",
                "chart-equity",
                "chart-drawdown",
                "chart-inventory",
                "chart-utilization",
                "chart-volume",
                "chart-betacorr",
                "chart-heatmap",
                "daily-perf-table",
                "daily-legend-pills",
            ):
                self.assertIn(f'id="{cid}"', dash_text)

            r_rank = subprocess.run(cli + ["rank", "--top", "9", "--max-dd", "40", "--json"], capture_output=True, text=True, check=False)
            self.assertEqual(r_rank.returncode, 0, r_rank.stderr)
            board = json.loads(r_rank.stdout)
            self.assertEqual(board["total_models"], 5)

            first_id = board["top_ranked"][0]["model_id"]
            r_show = subprocess.run(cli + ["show", first_id], capture_output=True, text=True, check=False)
            self.assertEqual(r_show.returncode, 0, r_show.stderr)
            self.assertEqual(json.loads(r_show.stdout)["model_id"], first_id)

            r_cmp = subprocess.run(cli + ["compare"], capture_output=True, text=True, check=False)
            self.assertEqual(r_cmp.returncode, 0, r_cmp.stderr)
            self.assertIn(first_id, r_cmp.stdout)

            r_reb = subprocess.run(cli + ["rebuild-dashboard", "--date", "2026-11-23"], capture_output=True, text=True, check=False)
            self.assertEqual(r_reb.returncode, 0, r_reb.stderr)

    def test_correlation_matrix_symmetry_diagonal_and_eth_benchmark(self) -> None:
        series_by_id = {
            "beta_001_a": {
                "daily_returns": [0.01, -0.02, 0.03, 0.01, -0.01],
                "eth_daily_returns": [0.02, -0.04, 0.05, 0.02, -0.02],
            },
            "beta_002_b": {
                "daily_returns": [-0.01, 0.02, -0.03, -0.01, 0.01],
                "eth_daily_returns": [0.02, -0.04, 0.05, 0.02, -0.02],
            },
        }
        cm = compute_return_correlation_matrix(["beta_001_a", "beta_002_b"], series_by_id)
        self.assertEqual(cm["labels"], ["beta_001_a", "beta_002_b", "ETH"])
        mat = cm["matrix"]
        self.assertEqual(len(mat), 3)
        for i in range(3):
            self.assertEqual(mat[i][i], 1.0)
            for j in range(3):
                self.assertEqual(mat[i][j], mat[j][i])
        self.assertAlmostEqual(mat[0][1], -1.0, places=3)
        self.assertGreater(mat[0][2], 0.99)

    def test_daily_queue_config_all_specs_parse_and_select_next_unmined_batch(self) -> None:
        from alpha_mining.strategy.lgb154 import create_signal_provider

        queue_path = REPO_ROOT / "config" / "beta_mining" / "daily_queue.json"
        self.assertTrue(queue_path.is_file())
        qdata = json.loads(queue_path.read_text(encoding="utf-8"))
        candidates = qdata["candidates"]
        self.assertGreaterEqual(len(candidates), 35)
        seen_specs: set[str] = set()
        for entry in candidates:
            spec = entry["signal_spec"]
            self.assertNotIn(spec, seen_specs, f"duplicate signal_spec in daily_queue.json: {spec}")
            seen_specs.add(spec)
            sp = create_signal_provider(spec)
            self.assertTrue(sp.name)

        # Against repo store (which has Day-1's 5 baseline models), next-batch must pick Day-2's 5 models
        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "beta_mining.py"),
                "--store-dir",
                str(REPO_ROOT / "beta_mining"),
                "next-batch",
                "--queue-file",
                str(queue_path),
                "--batch-size",
                "5",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        nb = json.loads(proc.stdout)
        self.assertEqual(nb["selection_mode"], "queue_unmined")
        self.assertEqual(
            [m["signal_spec"] for m in nb["models"]],
            ["ema_5_15", "ema_8_21", "ema_13_34", "ema_20_50", "ema_30_90"],
        )

        # Exhausted queue gracefully switches to top_leaders_refresh
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            mini_q = tmp_path / "mini_q.json"
            mini_q.write_text(
                json.dumps({"models_per_day": 2, "candidates": [{"signal_spec": "ha_1m"}, {"signal_spec": "ema_9_21"}]}),
                encoding="utf-8",
            )
            st = BetaModelStore(tmp_path / "store")
            st.record_model_run(
                model_id="beta_001_ha_1m",
                batch_date="2026-11-23",
                signal_spec="ha_1m",
                result=_fake_result(signal_name="ha_1m", cashflow=3000.0, max_dd_pct=25.0),
            )
            st.record_model_run(
                model_id="beta_002_ema_9_21",
                batch_date="2026-11-23",
                signal_spec="ema_9_21",
                result=_fake_result(signal_name="ema_9_21", cashflow=2700.0, max_dd_pct=20.0),
            )
            proc2 = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "beta_mining.py"),
                    "--store-dir",
                    str(tmp_path / "store"),
                    "next-batch",
                    "--queue-file",
                    str(mini_q),
                    "--batch-size",
                    "2",
                    "--json",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc2.returncode, 0, proc2.stderr)
            nb2 = json.loads(proc2.stdout)
            self.assertEqual(nb2["selection_mode"], "top_leaders_refresh")
            self.assertEqual([m["model_id"] for m in nb2["models"]], ["beta_001_ha_1m", "beta_002_ema_9_21"])


if __name__ == "__main__":
    unittest.main()
