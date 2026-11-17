"""Tests for 2-layer GitHub Ruleset validation and anti-deadlock quorum upgrades."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python"))

from alpha_mining.control_plane.github_ruleset import (  # noqa: E402
    RulesetError,
    default_ruleset_paths,
    load_json_file,
    set_review_quorum,
    validate_ruleset_configs,
    verify_live_rulesets,
)


class TestGitHubRuleset(unittest.TestCase):
    def setUp(self) -> None:
        std_path, det_path = default_ruleset_paths(REPO_ROOT)
        self.std_cfg = load_json_file(std_path)
        self.det_cfg = load_json_file(det_path)

    def test_repo_ruleset_configs_are_valid(self) -> None:
        summary = validate_ruleset_configs(self.std_cfg, self.det_cfg)
        self.assertTrue(summary["valid"])
        self.assertEqual(summary["required_approving_review_count"], 0)
        self.assertEqual(summary["required_status_checks"], ["python", "rust"])

    def test_rejects_bypass_actor_or_missing_check(self) -> None:
        bad_std = copy.deepcopy(self.std_cfg)
        bad_std["bypass_actors"] = [{"actor_id": 1, "actor_type": "RepositoryRole"}]
        with self.assertRaises(RulesetError):
            validate_ruleset_configs(bad_std, self.det_cfg)

        bad_det = copy.deepcopy(self.det_cfg)
        bad_det["rules"][0]["parameters"]["required_status_checks"] = [
            {"context": "rust", "integration_id": 15368}
        ]
        with self.assertRaises(RulesetError):
            validate_ruleset_configs(self.std_cfg, bad_det)

    def test_quorum_deadlock_guard_and_confirmed_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            std_path = tmp_dir / "std.json"
            det_path = tmp_dir / "det.json"
            std_path.write_text(json.dumps(self.std_cfg), encoding="utf-8")
            det_path.write_text(json.dumps(self.det_cfg), encoding="utf-8")

            calls: list[tuple[list[str], str | None]] = []

            def fake_runner(cmd: list[str], stdin_text: str | None) -> subprocess.CompletedProcess[str]:
                calls.append((cmd, stdin_text))
                endpoint = [arg for arg in cmd if arg.startswith("repos/")][0]
                if endpoint.endswith("/collaborators"):
                    return subprocess.CompletedProcess(cmd, 0, json.dumps([{"login": "nattawatpuntachot52"}]), "")
                if endpoint.endswith("/rulesets") and "-X" not in cmd:
                    return subprocess.CompletedProcess(
                        cmd,
                        0,
                        json.dumps([
                            {"id": 101, "name": "standard-main-protection"},
                            {"id": 102, "name": "alpha-mining-details-main-protection"},
                        ]),
                        "",
                    )
                if endpoint.endswith("/branches/main"):
                    return subprocess.CompletedProcess(cmd, 0, json.dumps({"protected": True}), "")
                return subprocess.CompletedProcess(cmd, 0, json.dumps({"id": 101}), "")

            # Must refuse quorum >= 1 when only 1 collaborator exists and --confirm-bot-ready is omitted
            with self.assertRaises(RulesetError):
                set_review_quorum(
                    "nattawatpuntachot52/Alpha_mining",
                    std_path,
                    det_path,
                    count=1,
                    confirm_bot_ready=False,
                    runner=fake_runner,
                )

            # With --confirm-bot-ready (e.g. GitHub App installed), updates config and issues PUTs
            res = set_review_quorum(
                "nattawatpuntachot52/Alpha_mining",
                std_path,
                det_path,
                count=1,
                confirm_bot_ready=True,
                runner=fake_runner,
            )
            self.assertEqual(res["required_approving_review_count"], 1)
            updated_std: dict[str, Any] = json.loads(std_path.read_text(encoding="utf-8"))
            self.assertEqual(
                updated_std["rules"][2]["parameters"]["required_approving_review_count"],
                1,
            )
            self.assertTrue(res["sync"]["main_protected"])

    def test_verify_live_rulesets_detects_unprotected_branch(self) -> None:
        def unprotected_runner(cmd: list[str], stdin_text: str | None) -> subprocess.CompletedProcess[str]:
            endpoint = [arg for arg in cmd if arg.startswith("repos/")][0]
            if endpoint.endswith("/rulesets"):
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    json.dumps([
                        {"id": 10, "name": "standard-main-protection"},
                        {"id": 11, "name": "alpha-mining-details-main-protection"},
                    ]),
                    "",
                )
            if endpoint.endswith("/rulesets/10"):
                return subprocess.CompletedProcess(cmd, 0, json.dumps(self.std_cfg), "")
            if endpoint.endswith("/rulesets/11"):
                return subprocess.CompletedProcess(cmd, 0, json.dumps(self.det_cfg), "")
            if endpoint.endswith("/branches/main"):
                return subprocess.CompletedProcess(cmd, 0, json.dumps({"protected": False}), "")
            return subprocess.CompletedProcess(cmd, 1, "", "unexpected call")

        with self.assertRaises(RulesetError):
            verify_live_rulesets(
                "nattawatpuntachot52/Alpha_mining",
                self.std_cfg,
                self.det_cfg,
                runner=unprotected_runner,
            )

    def test_verify_live_rulesets_detects_drift_from_local(self) -> None:
        drifted_std = copy.deepcopy(self.std_cfg)
        drifted_std["rules"][2]["parameters"]["required_approving_review_count"] = 2

        def drifted_runner(cmd: list[str], stdin_text: str | None) -> subprocess.CompletedProcess[str]:
            endpoint = [arg for arg in cmd if arg.startswith("repos/")][0]
            if endpoint.endswith("/rulesets"):
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    json.dumps([
                        {"id": 10, "name": "standard-main-protection"},
                        {"id": 11, "name": "alpha-mining-details-main-protection"},
                    ]),
                    "",
                )
            if endpoint.endswith("/rulesets/10"):
                return subprocess.CompletedProcess(cmd, 0, json.dumps(drifted_std), "")
            if endpoint.endswith("/rulesets/11"):
                return subprocess.CompletedProcess(cmd, 0, json.dumps(self.det_cfg), "")
            if endpoint.endswith("/branches/main"):
                return subprocess.CompletedProcess(cmd, 0, json.dumps({"protected": True}), "")
            return subprocess.CompletedProcess(cmd, 1, "", "unexpected call")

        with self.assertRaises(RulesetError) as ctx:
            verify_live_rulesets(
                "nattawatpuntachot52/Alpha_mining",
                self.std_cfg,
                self.det_cfg,
                runner=drifted_runner,
            )
        self.assertIn("drift", str(ctx.exception).lower())

    def test_rejects_bool_quorum_non_empty_exclude_and_preserves_disk_on_api_failure(self) -> None:
        bad_bool_std = copy.deepcopy(self.std_cfg)
        bad_bool_std["rules"][2]["parameters"]["required_approving_review_count"] = True
        with self.assertRaises(RulesetError):
            validate_ruleset_configs(bad_bool_std, self.det_cfg)

        bad_excl_std = copy.deepcopy(self.std_cfg)
        bad_excl_std["conditions"]["ref_name"]["exclude"] = ["refs/heads/hotfix"]
        with self.assertRaises(RulesetError):
            validate_ruleset_configs(bad_excl_std, self.det_cfg)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            std_path = tmp_dir / "std.json"
            det_path = tmp_dir / "det.json"
            std_path.write_text(json.dumps(self.std_cfg, indent=2) + "\n", encoding="utf-8")
            det_path.write_text(json.dumps(self.det_cfg, indent=2) + "\n", encoding="utf-8")
            original_text = std_path.read_text(encoding="utf-8")

            with self.assertRaises(RulesetError):
                set_review_quorum(
                    "nattawatpuntachot52/Alpha_mining",
                    std_path,
                    det_path,
                    count=True,  # type: ignore[arg-type]
                    confirm_bot_ready=True,
                )

            def failing_put_runner(cmd: list[str], stdin_text: str | None) -> subprocess.CompletedProcess[str]:
                if "-X" in cmd:
                    return subprocess.CompletedProcess(cmd, 1, "", "HTTP 500 internal error")
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    json.dumps([
                        {"id": 10, "name": "standard-main-protection"},
                        {"id": 11, "name": "alpha-mining-details-main-protection"},
                    ]),
                    "",
                )

            with self.assertRaises(RulesetError):
                set_review_quorum(
                    "nattawatpuntachot52/Alpha_mining",
                    std_path,
                    det_path,
                    count=1,
                    confirm_bot_ready=True,
                    runner=failing_put_runner,
                )
            # Remote API failed before disk write -> local file stays intact at original 0 quorum
            self.assertEqual(std_path.read_text(encoding="utf-8"), original_text)

    def test_cli_validate_configs_and_dash_r_parsing(self) -> None:
        script = REPO_ROOT / "scripts" / "github_ruleset.py"
        res = subprocess.run(
            [sys.executable, str(script), "validate-configs"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        payload = json.loads(res.stdout)
        self.assertTrue(payload["valid"])

        # Verify -R flag is accepted cleanly by subcommands (validation error on local-only without confirm returns exit 1, not exit 2 argparse error)
        res_r = subprocess.run(
            [
                sys.executable,
                str(script),
                "set-review-quorum",
                "-R",
                "owner/repo",
                "--count",
                "1",
                "--local-only",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(res_r.returncode, 1)
        self.assertIn("refusing local-only quorum >= 1", res_r.stderr)


if __name__ == "__main__":
    unittest.main()
