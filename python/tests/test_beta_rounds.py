"""Beta Mining 2-round/day accumulation tests (Round 2 merges into Round 1, never overwrites)."""

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

from alpha_mining.research.beta_store import merge_batch_models  # noqa: E402


class TestMergeBatchModels(unittest.TestCase):
    def test_merge_preserves_order_replaces_same_id_and_appends_new(self) -> None:
        existing = [{"model_id": "a", "v": 1}, {"model_id": "b", "v": 1}]
        new = [{"model_id": "b", "v": 2}, {"model_id": "c", "v": 2}]
        merged = merge_batch_models(existing, new)
        self.assertEqual([m["model_id"] for m in merged], ["a", "b", "c"])
        self.assertEqual([m["v"] for m in merged], [1, 2, 2])
        self.assertEqual(existing[1]["v"], 1, "inputs must not be mutated")


class TestBetaTwoRoundsPerDay(unittest.TestCase):
    def test_round2_accumulates_into_same_day_batch_and_auto_skips_third_round(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            csv_path = tmp_path / "sample_1m.csv"
            start_ms = 1_760_000_000_000
            lines = ["open_time_ms,open,high,low,close,volume"]
            prev = 2500.0
            for i in range(180):
                nxt = 2500.0 + 40.0 * math.sin(2.0 * math.pi * i / 30.0)
                hi = max(prev, nxt) + 3.0
                lo = min(prev, nxt) - 3.0
                lines.append(f"{start_ms + i * 60_000},{prev:.4f},{hi:.4f},{lo:.4f},{nxt:.4f},50.0")
                prev = nxt
            csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            store_dir = tmp_path / "beta_mining"
            cli = [sys.executable, str(REPO_ROOT / "scripts" / "beta_mining.py"), "--store-dir", str(store_dir)]

            def run_round(signals: str, *extra: str) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    cli
                    + [
                        "run-daily",
                        "--date",
                        "2026-11-24",
                        "--source",
                        "local",
                        "--local-path",
                        str(csv_path),
                        "--signals",
                        signals,
                        "--stress-crash-days",
                        "0",
                        *extra,
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )

            r1 = run_round("ha_1m,ema_9_21")
            self.assertEqual(r1.returncode, 0, r1.stderr)
            batch1 = json.loads((store_dir / "daily" / "2026-11-24" / "batch.json").read_text(encoding="utf-8"))
            self.assertEqual(batch1["model_count"], 2)
            self.assertEqual(batch1["rounds"], [1])

            r2 = run_round("ema_12_26,supertrend_10_3")
            self.assertEqual(r2.returncode, 0, r2.stderr)
            batch2 = json.loads((store_dir / "daily" / "2026-11-24" / "batch.json").read_text(encoding="utf-8"))
            self.assertEqual(batch2["model_count"], 4, "Round 2 must accumulate, not overwrite Round 1")
            self.assertEqual(batch2["rounds"], [1, 2])
            self.assertEqual(
                [m["model_id"] for m in batch2["models"]],
                [
                    "beta_001_ha_1m",
                    "beta_002_ema_9_21",
                    "beta_003_ema_12_26",
                    "beta_004_supertrend_10_3",
                ],
            )
            self.assertEqual([m["round_no"] for m in batch2["models"]], [1, 1, 2, 2])

            # Dashboard + summary reflect all 4 models of the day.
            dash = (store_dir / "daily" / "2026-11-24" / "dashboard.html").read_text(encoding="utf-8")
            self.assertIn("beta_003_ema_12_26", dash)
            self.assertIn("beta_001_ha_1m", dash)

            # Auto mode refuses a 3rd round (max 2/day) without touching the store.
            before = (store_dir / "daily" / "2026-11-24" / "batch.json").read_text(encoding="utf-8")
            r3 = run_round("rsi_trend_14_45_55")
            self.assertEqual(r3.returncode, 0, r3.stderr)
            self.assertIn("nothing to mine", r3.stdout)
            after = (store_dir / "daily" / "2026-11-24" / "batch.json").read_text(encoding="utf-8")
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
