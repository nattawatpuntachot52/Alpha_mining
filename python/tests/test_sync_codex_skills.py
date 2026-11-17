"""Tests for scripts/sync_codex_skills.sh."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNC_SCRIPT = REPO_ROOT / "scripts" / "sync_codex_skills.sh"


class TestSyncCodexSkillsScript(unittest.TestCase):
    def _run_sync(
        self,
        args: list[str],
        codex_home: Path,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CODEX_HOME"] = str(codex_home)
        return subprocess.run(
            ["bash", str(SYNC_SCRIPT), *args],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_copy_conflict_force_and_symlink_preserve_unrelated_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / "codex_home"
            unrelated_dir = codex_home / "skills" / "unrelated-skill"
            unrelated_dir.mkdir(parents=True)
            (unrelated_dir / "SKILL.md").write_text("keep-me", encoding="utf-8")

            # 1. Dry run leaves destination untouched
            dry_res = self._run_sync(["--dry-run"], codex_home)
            self.assertEqual(dry_res.returncode, 0, dry_res.stderr)
            self.assertFalse((codex_home / "skills" / "conditioner-ovca").exists())
            self.assertFalse((codex_home / "skills" / "zoom-out").exists())

            # 2. Default copy syncs both repo skills without touching unrelated-skill
            copy_res = self._run_sync([], codex_home)
            self.assertEqual(copy_res.returncode, 0, copy_res.stderr)
            self.assertTrue((codex_home / "skills" / "conditioner-ovca" / "SKILL.md").is_file())
            self.assertTrue((codex_home / "skills" / "zoom-out" / "SKILL.md").is_file())
            self.assertEqual((unrelated_dir / "SKILL.md").read_text(encoding="utf-8"), "keep-me")

            # 3. Re-running without --force refuses safely
            conflict_res = self._run_sync([], codex_home)
            self.assertNotEqual(conflict_res.returncode, 0)
            self.assertIn("Refusing to overwrite", conflict_res.stderr)

            # 4. --symlink --force converts repo skills to symlinks while preserving unrelated-skill
            link_res = self._run_sync(["--symlink", "--force"], codex_home)
            self.assertEqual(link_res.returncode, 0, link_res.stderr)
            cond_dest = codex_home / "skills" / "conditioner-ovca"
            zoom_dest = codex_home / "skills" / "zoom-out"
            self.assertTrue(cond_dest.is_symlink())
            self.assertTrue(zoom_dest.is_symlink())
            self.assertEqual(cond_dest.resolve(), (REPO_ROOT / "skills" / "conditioner-ovca").resolve())
            self.assertEqual(zoom_dest.resolve(), (REPO_ROOT / "skills" / "zoom-out").resolve())
            self.assertEqual((unrelated_dir / "SKILL.md").read_text(encoding="utf-8"), "keep-me")


if __name__ == "__main__":
    unittest.main()
