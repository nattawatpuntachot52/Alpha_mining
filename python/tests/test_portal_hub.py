"""Tests for the Unified Central Research Portal (Alpha + Beta split hub)."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PYTHON_SRC = REPO_ROOT / "python"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))

from alpha_mining.research.model_library import (  # noqa: E402
    collect_model_library_payload,
    render_model_library_html,
)
from alpha_mining.research.portal_hub import (  # noqa: E402
    collect_unified_portal_payload,
    render_unified_portal_html,
)
from alpha_mining.research.stability import compute_stability_metrics  # noqa: E402


class TestUnifiedPortalHub(unittest.TestCase):
    def test_build_unified_portal_separates_alpha_and_beta_offline_and_valid_js(self) -> None:
        payload = collect_unified_portal_payload(
            alpha_dir=REPO_ROOT / "alpha_mining",
            beta_dir=REPO_ROOT / "beta_mining",
        )
        self.assertGreaterEqual(payload["alpha"]["total_models"], 20)
        self.assertGreaterEqual(payload["beta"]["total_models"], 10)
        self.assertTrue(payload["alpha"]["latest_date"])
        self.assertTrue(payload["beta"]["latest_date"])

        with tempfile.TemporaryDirectory() as tmp:
            out_html = Path(tmp) / "index.html"
            lib_html = Path(tmp) / "library.html"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "build_portal.py"),
                    "--out",
                    str(out_html),
                    "--library-out",
                    str(lib_html),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            text = out_html.read_text(encoding="utf-8")

            # Must be 100% zero-CDN / offline-ready
            self.assertNotIn("https://", text)
            self.assertNotIn("http://", text)

            # Clear separation of Alpha & Beta tracks and links (including Model Library)
            self.assertIn("ALPHA TRACK", text)
            self.assertIn("BETA TRACK", text)
            self.assertIn("library.html", text)
            self.assertIn("alpha/index.html", text)
            self.assertIn("beta/index.html", text)
            self.assertIn(f"alpha/daily/{payload['alpha']['latest_date']}/dashboard.html", text)
            self.assertIn(f"beta/daily/{payload['beta']['latest_date']}/dashboard.html", text)
            self.assertIn("#sym=XAUUSD&amp;tab=ranking", text)
            self.assertIn("#sym=ETHUSDT&amp;tab=ranking", text)
            self.assertIn("#mode=top9", text)

            # Model Library page must exist, be 100% zero-CDN, and contain Alpha + Beta models & conditions
            self.assertTrue(lib_html.is_file())
            lib_text = lib_html.read_text(encoding="utf-8")
            self.assertNotIn("https://", lib_text)
            self.assertNotIn("http://", lib_text)
            self.assertIn("ห้องสมุดโมเดล", lib_text)
            self.assertIn("alpha_001", lib_text)
            self.assertIn("beta_001", lib_text)
            self.assertIn("ann_vol_pct", lib_text)
            self.assertIn("equity_r2", lib_text)

            # Verify inline JS syntax if Node.js is available
            node_bin = shutil.which("node")
            if node_bin:
                for label, doc in (("portal", text), ("library", lib_text)):
                    m = re.search(r"<script>([\s\S]*?)</script>", doc)
                    self.assertIsNotNone(m, f"Missing <script> in {label}")
                    js_file = Path(tmp) / f"{label}.js"
                    js_file.write_text(m.group(1), encoding="utf-8")
                    chk = subprocess.run(
                        [node_bin, "--check", str(js_file)],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(chk.returncode, 0, f"{label} JS error: {chk.stderr}")

    def test_stability_metrics_distinguish_smooth_vs_choppy_returns(self) -> None:
        # Smooth upward equity curve (constant small positive daily return + tiny noise)
        smooth = [0.002 + (0.0001 if i % 2 == 0 else -0.0001) for i in range(250)]
        smooth_m = compute_stability_metrics(smooth)
        self.assertGreater(smooth_m["equity_r2"], 0.98)
        self.assertLess(smooth_m["ann_vol_pct"], 5.0)
        self.assertLess(smooth_m["ulcer_index_pct"], 1.0)

        # Wild choppy / downward returns
        choppy = [0.04 if i % 2 == 0 else -0.045 for i in range(250)]
        choppy_m = compute_stability_metrics(choppy)
        self.assertEqual(choppy_m["equity_r2"], 0.0)
        self.assertGreater(choppy_m["ann_vol_pct"], 50.0)
        self.assertGreater(choppy_m["ulcer_index_pct"], 5.0)

    def test_render_handles_empty_stores_gracefully(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = collect_unified_portal_payload(
                alpha_dir=root / "missing_alpha",
                beta_dir=root / "missing_beta",
            )
            html_out = render_unified_portal_html(payload)
            self.assertIn("ALPHA TRACK", html_out)
            self.assertIn("BETA TRACK", html_out)
            lib_payload = collect_model_library_payload(
                alpha_dir=root / "missing_alpha",
                beta_dir=root / "missing_beta",
            )
            lib_html = render_model_library_html(lib_payload)
            self.assertIn("ห้องสมุดโมเดล", lib_html)
            self.assertNotIn("https://", lib_html)
            self.assertNotIn("http://", lib_html)


if __name__ == "__main__":
    unittest.main()
