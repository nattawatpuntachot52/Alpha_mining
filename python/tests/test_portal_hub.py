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

from alpha_mining.research.portal_hub import (  # noqa: E402
    collect_unified_portal_payload,
    render_unified_portal_html,
)


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
            proc = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "build_portal.py"),
                    "--out",
                    str(out_html),
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

            # Clear separation of Alpha & Beta tracks and links
            self.assertIn("ALPHA TRACK", text)
            self.assertIn("BETA TRACK", text)
            self.assertIn("alpha/index.html", text)
            self.assertIn("beta/index.html", text)
            self.assertIn(f"alpha/daily/{payload['alpha']['latest_date']}/dashboard.html", text)
            self.assertIn(f"beta/daily/{payload['beta']['latest_date']}/dashboard.html", text)
            self.assertIn("#sym=XAUUSD&amp;tab=ranking", text)
            self.assertIn("#sym=ETHUSDT&amp;tab=ranking", text)
            self.assertIn("#mode=top9", text)

            # Verify inline JS syntax if Node.js is available
            node_bin = shutil.which("node")
            if node_bin:
                m = re.search(r"<script>([\s\S]*?)</script>", text)
                self.assertIsNotNone(m)
                chk = subprocess.run(
                    [node_bin, "-e", f"new Function({m.group(1)!r});"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(chk.returncode, 0, chk.stderr)

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


if __name__ == "__main__":
    unittest.main()
