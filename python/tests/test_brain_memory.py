"""Unit tests for Daily Brain Memory JSONL storage, anti-leakage checks, and Drive Vault snapshot packing."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python"))

from alpha_mining.accounting import AccountedOutcome
from alpha_mining.storage import (
    BrainEpisode,
    BrainMemoryError,
    DecisionContext,
    EpisodeOutcome,
    TranslationEnvelope,
    append_episode,
    extract_verified_archive,
    load_episodes,
    outcome_from_accounted,
    pack_daily_snapshot,
    render_day_markdown,
    resolve_episode_outcome,
    summarize_day,
)


def _sample_episode(
    *,
    episode_id: str = "ep-20261118-001",
    session_date: str = "2026-11-18",
    observed_at_utc: str = "2026-11-18T05:00:00Z",
    status: str = "pending",
    outcome_at_utc: str | None = None,
    net_return_r: float | None = None,
    cost_r: float | None = None,
    mae_r: float | None = None,
) -> BrainEpisode:
    return BrainEpisode(
        schema_version="1.0",
        episode_id=episode_id,
        session_date=session_date,
        episode_kind="trading_lesson",
        source="owner_teaching",
        natural_language_input="Wait for spread <= 15 bps before taking candidate entry",
        llm_translation=TranslationEnvelope(
            translator_role="nl_to_json_only",
            structured_intent={
                "conditions": [{"feature": "spread_bps", "op": "<=", "value": 15}],
                "horizon_bars": 4,
            },
            parse_status="validated",
            human_confirmed=True,
        ),
        decision_context=DecisionContext(
            observed_at_utc=observed_at_utc,
            features_at_decision={"spread_bps": 12.0, "volatility_z": 0.8},
            available_actions=("skip", "take_half", "take_full"),
            chosen_action="take_half",
            decision_engine="owner_rule_v1",
            risk_gate_passed=True,
        ),
        outcome=EpisodeOutcome(
            status=status,  # type: ignore[arg-type]
            outcome_at_utc=outcome_at_utc,
            net_return_r=net_return_r,
            cost_r=cost_r,
            mae_r=mae_r,
            error_or_lesson_tag="spread_ok" if status == "resolved" else "",
            owner_feedback="clean execution" if status == "resolved" else "",
        ),
    )


class TestBrainMemory(unittest.TestCase):
    def test_append_resolve_summarize_and_immutability(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mem_dir = Path(tmp) / "memory"
            ep1 = _sample_episode(episode_id="ep-001")
            ep2 = _sample_episode(
                episode_id="ep-002",
                observed_at_utc="2026-11-18T06:00:00Z",
                status="resolved",
                outcome_at_utc="2026-11-18T07:00:00Z",
                net_return_r=1.5,
                cost_r=0.1,
            )

            log_path = append_episode(mem_dir, ep1)
            self.assertEqual(stat.S_IMODE(log_path.stat().st_mode), 0o644)
            append_episode(mem_dir, ep2)

            with self.assertRaises(BrainMemoryError):
                append_episode(mem_dir, ep1)

            # Global episode_id uniqueness across different session dates
            ep_other_day_dup = _sample_episode(episode_id="ep-001", session_date="2026-11-19")
            with self.assertRaises(BrainMemoryError):
                append_episode(mem_dir, ep_other_day_dup)

            resolved = resolve_episode_outcome(
                mem_dir,
                "2026-11-18",
                "ep-001",
                outcome_from_accounted(
                    AccountedOutcome(
                        entry_id="rec-1",
                        gross_r=1.0,
                        total_cost_r=0.2,
                        net_r=0.8,
                        realized_at_utc="2026-11-18T05:45:00Z",
                    ),
                    error_or_lesson_tag="discipline_win",
                    owner_feedback="good size control",
                ),
            )
            self.assertEqual(resolved.decision_context, ep1.decision_context)
            self.assertEqual(resolved.llm_translation, ep1.llm_translation)
            self.assertAlmostEqual(resolved.outcome.net_return_r or 0.0, 0.8)

            # Resolving an already finalized episode must be rejected
            with self.assertRaises(BrainMemoryError):
                resolve_episode_outcome(
                    mem_dir,
                    "2026-11-18",
                    "ep-001",
                    EpisodeOutcome(
                        status="resolved",
                        outcome_at_utc="2026-11-18T08:00:00Z",
                        net_return_r=9.9,
                    ),
                )

            missing_dir = Path(tmp) / "does_not_exist"
            with self.assertRaises(BrainMemoryError):
                resolve_episode_outcome(
                    missing_dir,
                    "2026-11-18",
                    "ep-001",
                    EpisodeOutcome(status="void", outcome_at_utc="2026-11-18T08:00:00Z"),
                )
            self.assertFalse(missing_dir.exists())

            # Test nanosecond lookahead rejection in resolve_episode_outcome & pending -> void transition
            ep_void = _sample_episode(
                episode_id="ep-void-ns",
                observed_at_utc="2026-11-18T05:00:00.000000002Z",
            )
            append_episode(mem_dir, ep_void)
            with self.assertRaises(BrainMemoryError):
                resolve_episode_outcome(
                    mem_dir,
                    "2026-11-18",
                    "ep-void-ns",
                    EpisodeOutcome(
                        status="resolved",
                        outcome_at_utc="2026-11-18T05:00:00.000000001Z",
                        net_return_r=0.5,
                    ),
                )
            voided = resolve_episode_outcome(
                mem_dir,
                "2026-11-18",
                "ep-void-ns",
                EpisodeOutcome(
                    status="void",
                    outcome_at_utc="2026-11-18T05:00:00.000000005Z",
                    error_or_lesson_tag="cancelled_before_fill",
                ),
            )
            self.assertEqual(voided.outcome.status, "void")

            loaded = load_episodes(mem_dir, "2026-11-18")
            self.assertEqual(len(loaded), 3)

            summary = summarize_day(mem_dir, "2026-11-18")
            self.assertEqual(summary["total_episodes"], 3)
            self.assertEqual(summary["resolved_with_net_r_count"], 2)
            self.assertAlmostEqual(summary["resolved_net_r_sum"], 2.3)
            self.assertAlmostEqual(summary["resolved_net_r_mean"], 1.15)
            self.assertIn("Daily Brain Memory Summary — 2026-11-18", render_day_markdown(summary))

    def test_rejects_lookahead_secrets_nan_and_role_escalation(self) -> None:
        # Unicode fractional digits must be rejected
        with self.assertRaises(BrainMemoryError):
            _sample_episode(observed_at_utc="2026-11-18T08:00:00.\u0661Z")

        # Sub-microsecond lookahead violation (9th fractional digit) must fail
        with self.assertRaises(BrainMemoryError):
            _sample_episode(
                observed_at_utc="2026-11-18T08:00:00.000000002Z",
                status="resolved",
                outcome_at_utc="2026-11-18T08:00:00.000000001Z",
                net_return_r=1.0,
            )

        # Void outcomes must not carry realized numeric return/cost/mae metrics
        with self.assertRaises(BrainMemoryError):
            _sample_episode(status="void", net_return_r=0.5)
        with self.assertRaises(BrainMemoryError):
            _sample_episode(status="void", mae_r=-0.2)

        with self.assertRaises(BrainMemoryError):
            TranslationEnvelope(
                translator_role="autonomous_trader",  # type: ignore[arg-type]
                structured_intent={},
                parse_status="validated",
                human_confirmed=True,
            )

        with self.assertRaises(BrainMemoryError):
            TranslationEnvelope(
                translator_role="nl_to_json_only",
                structured_intent={"submit_order": {"side": "buy"}},
                parse_status="validated",
                human_confirmed=True,
            )

        with self.assertRaises(BrainMemoryError):
            DecisionContext(
                observed_at_utc="2026-11-18T05:00:00Z",
                features_at_decision={"spread": float("nan")},
                available_actions=("skip",),
                chosen_action="skip",
                decision_engine="rule",
                risk_gate_passed=True,
            )

        with self.assertRaises(BrainMemoryError):
            DecisionContext(
                observed_at_utc="2026-11-18T05:00:00Z",
                features_at_decision={},
                available_actions=("skip",),
                chosen_action="buy_all_in",
                decision_engine="rule",
                risk_gate_passed=True,
            )

        # Nested secret structures, compound/camelCase/hyphenated keys, dict keys, available_actions, and secret formats
        secret_feature_payloads = [
            {"client_secret": {"raw": "secret_value_here"}},
            {"client_secret": ["nested_secret_value"]},
            {"oauth_client_secret": "GOCSPX-supersecret1234"},
            {"gdrive_refresh_token": "1//0supersecret123"},
            {"github_token": "ghp_1234567890abcdef123456"},
            {"oauthClientSecret": "topsecretvalue"},
            {"github-token": "secretval123"},
            {"ghp_1234567890abcdef123456": "sneaky_key_secret"},
        ]
        for bad_features in secret_feature_payloads:
            with self.assertRaises(BrainMemoryError):
                DecisionContext(
                    observed_at_utc="2026-11-18T05:00:00Z",
                    features_at_decision=bad_features,
                    available_actions=("skip",),
                    chosen_action="skip",
                    decision_engine="gate",
                    risk_gate_passed=True,
                )

        with self.assertRaises(BrainMemoryError):
            DecisionContext(
                observed_at_utc="2026-11-18T05:00:00Z",
                features_at_decision={},
                available_actions=("skip", "Bearer eyJhbGciOiJIUzI1NiJ9.payload123.sig12345"),
                chosen_action="skip",
                decision_engine="gate",
                risk_gate_passed=True,
            )

        secret_strings = [
            'token = {"access_token":"ya29.supersecretvalue123"}',
            "authorization: bearer SuperSecretBearerToken123",
            "jwt=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJvd25lciJ9.signature_abcdef",
            "oauth=ya29.a0AfH6SMB_real_looking_token",
            "sec=GOCSPX-1234567890abcdef",
            "ref=1//0gSuperSecretRefreshToken",
            "password=p@ss!1234",
            "API_SECRET: $uper!Secret99",
            "token=mysecretvalue12345",
            "-----begin PGP PRIVATE KEY BLOCK-----\nabc\n-----END PGP PRIVATE KEY BLOCK-----",
            "LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQ==",
            "[gdrive]\ntype = drive\nscope = drive\n",
        ]
        for bad_text in secret_strings:
            with self.assertRaises(BrainMemoryError):
                BrainEpisode(
                    schema_version="1.0",
                    episode_id="ep-secret-str",
                    session_date="2026-11-18",
                    episode_kind="governance_decision",
                    source="control_plane",
                    natural_language_input=bad_text,
                    llm_translation=TranslationEnvelope(
                        translator_role="nl_to_json_only",
                        structured_intent={},
                        parse_status="validated",
                        human_confirmed=True,
                    ),
                    decision_context=DecisionContext(
                        observed_at_utc="2026-11-18T05:00:00Z",
                        features_at_decision={},
                        available_actions=("skip",),
                        chosen_action="skip",
                        decision_engine="gate",
                        risk_gate_passed=True,
                    ),
                    outcome=EpisodeOutcome(status="pending"),
                )

        # Unknown JSON keys (even if containing secrets) must be rejected by from_dict
        base_dict = _sample_episode(episode_id="ep-unknown-key").to_dict()
        with self.assertRaises(BrainMemoryError):
            BrainEpisode.from_dict({**base_dict, "unexpected_secret": "GOCSPX-1234567890abcdef"})
        with self.assertRaises(BrainMemoryError):
            TranslationEnvelope.from_dict({**base_dict["llm_translation"], "extra_field": "x"})
        with self.assertRaises(BrainMemoryError):
            DecisionContext.from_dict({**base_dict["decision_context"], "extra_field": "x"})
        with self.assertRaises(BrainMemoryError):
            EpisodeOutcome.from_dict({**base_dict["outcome"], "extra_field": "x"})

    def test_post_init_deep_freeze_and_symlink_protection(self) -> None:
        caller_intent = {"conditions": [{"feature": "spread_bps", "op": "<=", "value": 15}]}
        caller_features = {"nested": {"spread_bps": 12.0}}
        env = TranslationEnvelope(
            translator_role="nl_to_json_only",
            structured_intent=caller_intent,
            parse_status="validated",
            human_confirmed=True,
        )
        ctx = DecisionContext(
            observed_at_utc="2026-11-18T05:00:00Z",
            features_at_decision=caller_features,
            available_actions=("skip", "take"),
            chosen_action="take",
            decision_engine="rule_v1",
            risk_gate_passed=True,
        )
        # Mutating caller dicts must not pollute frozen snapshot
        caller_intent["conditions"][0]["value"] = float("nan")
        caller_features["nested"]["spread_bps"] = float("nan")
        self.assertEqual(env.structured_intent["conditions"][0]["value"], 15)
        self.assertEqual(ctx.features_at_decision["nested"]["spread_bps"], 12.0)

        with self.assertRaises(TypeError):
            env.structured_intent["extra"] = "bad"  # type: ignore[index]
        with self.assertRaises(TypeError):
            ctx.features_at_decision["nested"]["spread_bps"] = 99.0  # type: ignore[index]

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            mem_dir = tmp_dir / "memory"
            mem_dir.mkdir(parents=True, exist_ok=True)
            outside = tmp_dir / "outside.jsonl"
            outside.write_text(_sample_episode(episode_id="ep-outside").to_json_line() + "\n", encoding="utf-8")

            link_path = mem_dir / "2026-11-18.jsonl"
            os.symlink(outside, link_path)

            with self.assertRaises(BrainMemoryError):
                load_episodes(mem_dir)
            with self.assertRaises(BrainMemoryError):
                load_episodes(mem_dir, "2026-11-18")
            with self.assertRaises(BrainMemoryError):
                append_episode(mem_dir, _sample_episode(episode_id="ep-sym-write"))
            with self.assertRaises(BrainMemoryError):
                pack_daily_snapshot(mem_dir, "2026-11-18", repo_root=REPO_ROOT)

            symlink_dir = tmp_dir / "sym_mem_dir"
            os.symlink(mem_dir, symlink_dir)
            with self.assertRaises(BrainMemoryError):
                load_episodes(symlink_dir)

    def test_concurrent_appends_preserve_all_episodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mem_dir = Path(tmp) / "memory"

            def write_one(idx: int) -> None:
                append_episode(mem_dir, _sample_episode(episode_id=f"ep-conc-{idx:03d}"))

            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(write_one, range(16)))

            loaded = load_episodes(mem_dir, "2026-11-18")
            self.assertEqual(len(loaded), 16)
            self.assertEqual(len({ep.episode_id for ep in loaded}), 16)

    def test_pack_daily_snapshot_and_cli_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            mem_dir = tmp_dir / "memory"
            cache_dir = tmp_dir / "cache"
            manifest_path = tmp_dir / "brain-daily-2026-11-18.manifest.json"
            extract_dir = tmp_dir / "restored"

            ep = _sample_episode(
                episode_id="ep-cli-001",
                status="resolved",
                outcome_at_utc="2026-11-18T05:30:00Z",
                net_return_r=1.2,
                cost_r=0.1,
            )
            ep_json = tmp_dir / "ep.json"
            ep_json.write_text(json.dumps(ep.to_dict()), encoding="utf-8")

            rec = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "brain_memory.py"),
                    "--memory-dir",
                    str(mem_dir),
                    "record",
                    "--input-json",
                    str(ep_json),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(rec.returncode, 0, rec.stderr)

            val = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "brain_memory.py"),
                    "--memory-dir",
                    str(mem_dir),
                    "validate",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(val.returncode, 0, val.stderr)
            self.assertTrue(json.loads(val.stdout)["valid"])

            ep_pending = _sample_episode(episode_id="ep-cli-002")
            ep_pending_json = tmp_dir / "ep_pending.json"
            ep_pending_json.write_text(json.dumps(ep_pending.to_dict()), encoding="utf-8")
            rec2 = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "brain_memory.py"),
                    "--memory-dir",
                    str(mem_dir),
                    "record",
                    "--input-json",
                    str(ep_pending_json),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(rec2.returncode, 0, rec2.stderr)

            outcome_json = tmp_dir / "outcome.json"
            outcome_json.write_text(
                json.dumps(
                    {
                        "status": "resolved",
                        "outcome_at_utc": "2026-11-18T06:15:00Z",
                        "net_return_r": 0.6,
                        "cost_r": 0.1,
                        "error_or_lesson_tag": "cli_resolved",
                        "owner_feedback": "verified via cli",
                    }
                ),
                encoding="utf-8",
            )
            res_cli = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "brain_memory.py"),
                    "--memory-dir",
                    str(mem_dir),
                    "resolve",
                    "--session-date",
                    "2026-11-18",
                    "--episode-id",
                    "ep-cli-002",
                    "--outcome-json",
                    str(outcome_json),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(res_cli.returncode, 0, res_cli.stderr)
            self.assertTrue(json.loads(res_cli.stdout)["resolved"])

            sum_cli = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "brain_memory.py"),
                    "--memory-dir",
                    str(mem_dir),
                    "summarize",
                    "--session-date",
                    "2026-11-18",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(sum_cli.returncode, 0, sum_cli.stderr)
            self.assertEqual(json.loads(sum_cli.stdout)["total_episodes"], 2)

            sum_md_cli = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "brain_memory.py"),
                    "--memory-dir",
                    str(mem_dir),
                    "summarize",
                    "--session-date",
                    "2026-11-18",
                    "--format",
                    "markdown",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(sum_md_cli.returncode, 0, sum_md_cli.stderr)
            self.assertIn("Daily Brain Memory Summary — 2026-11-18", sum_md_cli.stdout)

            manifest = pack_daily_snapshot(
                mem_dir,
                "2026-11-18",
                repo_root=REPO_ROOT,
                manifest_out=manifest_path,
                archive_dir=cache_dir,
                codec="gz",
            )
            self.assertEqual(manifest["category"], "state_snapshot")
            self.assertEqual(manifest["gdrive_folder_id"], "11LgT2EI6OrjeBoF8y91Smz2wEfRwfxbt")
            self.assertEqual(manifest["artifact_id"], "brain-daily-2026-11-18")

            archive_file = cache_dir / manifest["archive_name"]
            verified = extract_verified_archive(archive_file, manifest_path, extract_dir)
            self.assertTrue(verified["verified"])
            self.assertTrue((extract_dir / "2026-11-18.jsonl").is_file())
            self.assertTrue((extract_dir / "2026-11-18.summary.json").is_file())

            push_dry = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "brain_memory.py"),
                    "push-snapshot",
                    "--manifest",
                    str(manifest_path),
                    "--archive",
                    str(archive_file),
                    "--backend",
                    "rclone",
                    "--dry-run",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if "not installed" not in push_dry.stderr:
                self.assertEqual(push_dry.returncode, 0, push_dry.stderr)
                parsed_dry = json.loads(push_dry.stdout)
                self.assertIn("state_snapshots", " ".join(parsed_dry["command"]))

    def test_repo_daily_memory_logs_are_valid_and_secret_free(self) -> None:
        repo_mem = REPO_ROOT / "workflows" / "memory"
        episodes = load_episodes(repo_mem)
        self.assertGreaterEqual(len(episodes), 1)
        for path in repo_mem.glob("*.jsonl"):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o644)
        for ep in episodes:
            summary = summarize_day(repo_mem, ep.session_date)
            self.assertGreaterEqual(summary["total_episodes"], 1)


if __name__ == "__main__":
    unittest.main()
