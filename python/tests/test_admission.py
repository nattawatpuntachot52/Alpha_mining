"""Tests for Mechanisms 1 (Context != Authority Mandate & Handback) and 2 (Observe Mode Gate)."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python"))

from alpha_mining.control_plane.admission import (  # noqa: E402
    AdmissionError,
    AdmissionTrigger,
    AssessmentUnavailable,
    DirectionDeclaration,
    IgnoredFromCard,
    ProactiveAssessment,
    RuleAssessmentEntry,
    append_decision_ledger,
    build_explicit_mandate,
    compute_policy_version,
    evaluate_gate,
    evaluate_github_observe_snapshot,
    evaluate_proactive_candidate,
    is_path_within_scope,
    load_admission_policy,
    render_observe_report_markdown,
    run_live_github_observe,
    summarize_ledger,
)
from alpha_mining.control_plane.ovca_bridge import OvcaBridge, OvcaBridgeError  # noqa: E402
from alpha_mining.storage.vault import pack_artifact  # noqa: E402

POLICY_PATH = REPO_ROOT / "config" / "governance" / "admission_policy.json"


def _all_rules_assessment(
    policy: dict,
    pver: str,
    *,
    matched: list[str],
    implementation_requested: bool = True,
    target_basis: str = "existing_standard",
    requires_design_decision: bool = False,
    evidence: tuple[str, ...] = ("observed CI log output",),
    proposed_writable_scope: tuple[str, ...] = (),
) -> ProactiveAssessment:
    entries = []
    for rule in policy["proactive_rules"]:
        if not rule["enabled"]:
            continue
        rid = rule["rule_id"]
        is_hit = rid in matched
        entries.append(
            RuleAssessmentEntry(
                rule_id=rid,
                matched=is_hit,
                reason=f"{rid} {'matched' if is_hit else 'did not match'}",
            )
        )
    return ProactiveAssessment(
        policy_version=pver,
        direction=DirectionDeclaration(
            implementation_requested=implementation_requested,
            target_basis=target_basis,
            requires_design_decision=requires_design_decision,
            evidence=evidence,
        ),
        rule_assessments=tuple(entries),
        proposed_writable_scope=proposed_writable_scope,
        summary="test assessment",
    )


class TestAdmissionAndMandate(unittest.TestCase):
    def setUp(self) -> None:
        self.policy, self.pver = load_admission_policy(POLICY_PATH)
        self.bridge = OvcaBridge(repo_root=REPO_ROOT)

    def test_rust_and_python_canonical_policy_version_parity(self) -> None:
        rust_res = self.bridge.policy_version(POLICY_PATH)
        self.assertEqual(rust_res["policy_version"], self.pver)
        self.assertEqual(self.policy["accept_mode"], "observe")

        # Shuffled actors / case must yield identical canonical version
        shuffled = copy.deepcopy(self.policy)
        shuffled["allowed_actors"] = [" NattawatPuntachot52 "]
        shuffled["bot_allowlist"] = list(reversed(shuffled["bot_allowlist"]))
        shuffled["proactive_rules"] = list(reversed(shuffled["proactive_rules"]))
        self.assertEqual(compute_policy_version(shuffled), self.pver)

        # Switching accept_mode rotates policy_version
        auto_pol = copy.deepcopy(self.policy)
        auto_pol["accept_mode"] = "auto"
        self.assertNotEqual(compute_policy_version(auto_pol), self.pver)

    def test_policy_validation_rejects_bots_in_allowed_and_unsafe_scopes(self) -> None:
        bad_bot = copy.deepcopy(self.policy)
        bad_bot["allowed_actors"].append("rogue[bot]")
        with self.assertRaises(AdmissionError):
            compute_policy_version(bad_bot)

        bad_receive_all = copy.deepcopy(self.policy)
        bad_receive_all["admission_table"]["github_comment"]["receive_all"] = False
        with self.assertRaises(AdmissionError):
            compute_policy_version(bad_receive_all)

        bad_ci_row = copy.deepcopy(self.policy)
        bad_ci_row["admission_table"]["github_default_branch_ci"]["listed_addressed"] = "explicit"
        with self.assertRaises(AdmissionError):
            compute_policy_version(bad_ci_row)

        bad_scope = copy.deepcopy(self.policy)
        bad_scope["proactive_rules"][0]["writable_scope"] = ["../outside"]
        with self.assertRaises(AdmissionError):
            compute_policy_version(bad_scope)

    def test_gate_rules_for_explicit_bots_ci_and_modes(self) -> None:
        # 1. Explicit owner mention works even in 'off' mode
        off_policy = copy.deepcopy(self.policy)
        off_policy["accept_mode"] = "off"
        owner_mention = AdmissionTrigger(
            trigger_id="t-owner-1",
            source_kind="github_comment",
            receiving_scope="github_comment",
            thread_id="pr:2",
            actor="NattawatPuntachot52",
            addressed="mention",
        )
        g_owner = evaluate_gate(off_policy, owner_mention)
        self.assertEqual(g_owner.strength, "explicit")

        # 2. Unlisted explicit admission cell takes precedence on thread even in 'off' mode
        custom_off = copy.deepcopy(off_policy)
        custom_off["admission_table"]["github_comment"]["unlisted_addressed"] = "explicit"
        unlisted_mention = AdmissionTrigger(
            trigger_id="t-unlisted-1",
            source_kind="github_comment",
            receiving_scope="github_comment",
            thread_id="pr:2",
            actor="collaborator-x",
            addressed="mention",
            existing_ticket_active=True,
        )
        self.assertEqual(evaluate_gate(custom_off, unlisted_mention).strength, "explicit")

        # 3. Allowlisted bot gets 'inferred' in observe/auto, 'not_admitted' in off, never 'explicit'
        bot_trig = AdmissionTrigger(
            trigger_id="t-bot-1",
            source_kind="bot",
            receiving_scope="github_pr",
            thread_id="pr:5",
            actor="dependabot[bot]",
            actor_is_bot=True,
            addressed="mention",
        )
        self.assertEqual(evaluate_gate(self.policy, bot_trig).strength, "inferred")
        self.assertEqual(evaluate_gate(off_policy, bot_trig).strength, "not_admitted")

        # 4. Unlisted bot or bot mentioning in non-receive-all without mention is rejected
        rogue_bot = AdmissionTrigger(
            trigger_id="t-bot-2",
            source_kind="bot",
            receiving_scope="github_pr",
            thread_id="pr:5",
            actor="evil[bot]",
            actor_is_bot=True,
            addressed="mention",
        )
        self.assertEqual(evaluate_gate(self.policy, rogue_bot).strength, "not_admitted")

        # 5. Direct explicit mandate builder refuses bots and CI
        with self.assertRaises(AdmissionError):
            build_explicit_mandate(
                self.policy,
                bot_trig,
                mandate_id="mnd-bad",
                authority_id="auth-bad",
                writable_scope=["python/"],
            )

    def test_observe_vs_auto_assessment_direction_coverage_and_unavailable(self) -> None:
        ci_trig = AdmissionTrigger(
            trigger_id="t-ci-1",
            source_kind="github_default_branch_ci",
            receiving_scope="github_default_branch_ci",
            thread_id="branch:main",
            actor="github-ci",
        )

        # In observe mode, positive assessment MUST log would_accept=True, decision='ignore', mandate=None
        pos_ass = _all_rules_assessment(
            self.policy,
            self.pver,
            matched=["ci-default-branch-failure"],
            proposed_writable_scope=("rust/crates/alpha-ovca/",),
        )
        rec_obs = evaluate_proactive_candidate(self.policy, ci_trig, pos_ass)
        self.assertEqual(rec_obs.decision, "ignore")
        self.assertTrue(rec_obs.would_accept)
        self.assertIsNone(rec_obs.mandate)
        self.assertEqual(rec_obs.matched_rules, ("ci-default-branch-failure",))

        # Unsettled design decision -> rejected even when rule matches
        unsettled = _all_rules_assessment(
            self.policy,
            self.pver,
            matched=["ci-default-branch-failure"],
            requires_design_decision=True,
        )
        rec_unsettled = evaluate_proactive_candidate(self.policy, ci_trig, unsettled)
        self.assertEqual(rec_unsettled.decision, "ignore")
        self.assertFalse(rec_unsettled.would_accept)

        # Missing enabled rule coverage MUST fail loudly
        incomplete = ProactiveAssessment(
            policy_version=self.pver,
            direction=DirectionDeclaration(True, "existing_standard", False, ("ci failed",)),
            rule_assessments=(RuleAssessmentEntry("ci-default-branch-failure", True, "failed"),),
        )
        with self.assertRaises(AdmissionError):
            evaluate_proactive_candidate(self.policy, ci_trig, incomplete)

        # Stale policy version on assessment records 'unavailable' cleanly
        auto_pol = copy.deepcopy(self.policy)
        auto_pol["accept_mode"] = "auto"
        pver_auto = compute_policy_version(auto_pol)
        rec_stale = evaluate_proactive_candidate(auto_pol, ci_trig, pos_ass)
        self.assertEqual(rec_stale.decision, "unavailable")
        self.assertEqual(rec_stale.error_kind, "stale_policy")

        # Tool/read failure records 'unavailable' (never 'ignore' mismatch)
        rec_err = evaluate_proactive_candidate(
            auto_pol,
            ci_trig,
            AssessmentUnavailable(error_kind="network_error", reason="GitHub API 503"),
        )
        self.assertEqual(rec_err.decision, "unavailable")
        self.assertFalse(rec_err.would_accept)

        # IgnoredFromCard records ignored_from_card=True
        rec_card = evaluate_proactive_candidate(
            auto_pol, ci_trig, IgnoredFromCard("plain chatter unrelated to repo")
        )
        self.assertEqual(rec_card.decision, "ignore")
        self.assertTrue(rec_card.ignored_from_card)

        # Disjoint multi-rule match on shared github_pr receiving_scope refuses auto-widening scope
        pr_trig = AdmissionTrigger(
            trigger_id="t-pr-disjoint",
            source_kind="bot",
            receiving_scope="github_pr",
            thread_id="pr:99",
            actor="github-actions[bot]",
            actor_is_bot=True,
            addressed="none",
        )
        disjoint = _all_rules_assessment(
            auto_pol,
            pver_auto,
            matched=["parallel-pr-semantic-conflict", "quant-manifest-drift-check"],
        )
        rec_disjoint = evaluate_proactive_candidate(auto_pol, pr_trig, disjoint)
        self.assertEqual(rec_disjoint.decision, "ignore")
        self.assertIsNone(rec_disjoint.mandate)
        self.assertIn("disjoint", rec_disjoint.reason)

        # Cross-surface rule escalation (github_comment trigger trying to match CI-only rule) must ignore
        comment_trig = AdmissionTrigger(
            trigger_id="t-comment-xsurf",
            source_kind="bot",
            receiving_scope="github_comment",
            thread_id="pr:99",
            actor="github-actions[bot]",
            actor_is_bot=True,
            addressed="none",
        )
        cross_surf = _all_rules_assessment(
            auto_pol,
            pver_auto,
            matched=["ci-default-branch-failure"],
        )
        rec_xsurf = evaluate_proactive_candidate(auto_pol, comment_trig, cross_surf)
        self.assertEqual(rec_xsurf.decision, "ignore")
        self.assertFalse(rec_xsurf.would_accept)
        self.assertIn("not enabled for receiving_scope", rec_xsurf.reason)

        # Explicitly disabling listed_addressed on github_comment blocks listed actor comment triggers
        disabled_comment_pol = copy.deepcopy(self.policy)
        disabled_comment_pol["admission_table"]["github_comment"]["listed_addressed"] = "ignore"
        owner_comment = AdmissionTrigger(
            trigger_id="t-owner-disabled-surface",
            source_kind="github_comment",
            receiving_scope="github_comment",
            thread_id="pr:2",
            actor="nattawatpuntachot52",
            addressed="mention",
        )
        self.assertEqual(evaluate_gate(disabled_comment_pol, owner_comment).strength, "not_admitted")

        # Passing an explicit owner trigger into proactive evaluator fails loudly
        owner_cli = AdmissionTrigger(
            trigger_id="t-owner-cli-1",
            source_kind="owner_cli",
            receiving_scope="owner_cli",
            thread_id="cli:1",
            actor="nattawatpuntachot52",
            addressed="direct",
        )
        with self.assertRaises(AdmissionError):
            evaluate_proactive_candidate(auto_pol, owner_cli, cross_surf)

        # In auto mode, valid single-rule match mints an immutable Mandate verified by Rust alpha-ovca
        pos_auto = _all_rules_assessment(
            auto_pol,
            pver_auto,
            matched=["ci-default-branch-failure"],
            proposed_writable_scope=("rust/crates/alpha-ovca/",),
        )
        rec_auto = evaluate_proactive_candidate(auto_pol, ci_trig, pos_auto)
        self.assertEqual(rec_auto.decision, "accept")
        self.assertIsNotNone(rec_auto.mandate)
        self.assertEqual(rec_auto.mandate["writable_scope"], ["rust/crates/alpha-ovca/"])

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            auto_pol_path = tmp_dir / "auto_policy.json"
            mandate_path = tmp_dir / "mandate.json"
            followup_path = tmp_dir / "followup.json"
            auto_pol_path.write_text(json.dumps(auto_pol), encoding="utf-8")
            mandate_path.write_text(json.dumps(rec_auto.mandate), encoding="utf-8")

            # Valid under auto_policy via Rust CLI
            v_res = self.bridge.validate_mandate(mandate_path, policy_path=auto_pol_path)
            self.assertTrue(v_res["valid"])
            self.assertTrue(v_res["revalidation"]["valid_to_resume"])

            # Revoked under default observe policy via Rust CLI
            r_obs = self.bridge.revalidate_mandate(mandate_path, POLICY_PATH)
            self.assertFalse(r_obs["valid_to_resume"])
            self.assertEqual(r_obs["resulting_status"], "revoked")

            # Prefix-trap path checked via Rust check-followup emits handback_required
            followup_path.write_text(
                json.dumps(
                    {
                        "trigger_id": "fu-1",
                        "thread_id": "branch:main",
                        "subscription_mode": "owned_work",
                        "actor": "nattawatpuntachot52",
                        "actor_is_bot": False,
                        "is_ci": False,
                        "requested_scope_paths": ["rust/crates/alpha-ovca_evil/pwn.rs"],
                        "requests_stop": False,
                        "requests_scope_expansion": False,
                    }
                ),
                encoding="utf-8",
            )
            fu_res = self.bridge.check_followup(mandate_path, followup_path, auto_pol_path)
            self.assertEqual(fu_res["action"], "handback_required")
            self.assertFalse(fu_res["grant_authority"])

    def test_scope_containment_parity_and_observe_github_snapshot(self) -> None:
        self.assertTrue(is_path_within_scope("python/alpha_mining/a.py", ["python/alpha_mining/"]))
        self.assertFalse(is_path_within_scope("python/alpha_mining_evil/a.py", ["python/alpha_mining/"]))
        self.assertFalse(is_path_within_scope("python/../.env", ["python/"]))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifests_dir = root / "workflows" / "vault_manifests"
            manifests_dir.mkdir(parents=True)
            data_dir = root / "raw_data"
            data_dir.mkdir()
            (data_dir / "sample.bin").write_bytes(b"quant-payload")

            manifest = pack_artifact(
                source_dir=data_dir,
                artifact_id="sample_obs_v1",
                category="dataset",
                manifest_out=manifests_dir / "sample_obs_v1.manifest.json",
                archive_dir=root / ".vault_cache",
                vault_config_path=REPO_ROOT / "config" / "storage" / "drive_vault.json",
                source_commit="deadbeef",
                codec="gz",
            )

            # Corrupt cache archive to trigger quant-manifest-drift-check in observe mode
            (root / ".vault_cache" / manifest["archive_name"]).write_bytes(b"tampered")

            records = evaluate_github_observe_snapshot(
                self.policy,
                repo_root=root,
                ci_runs_main=[
                    {"databaseId": 100, "status": "completed", "conclusion": "failure"},
                    {"databaseId": 99, "status": "completed", "conclusion": "success"},
                ],
                raw_prs=[
                    {
                        "number": 10,
                        "title": "PR A",
                        "author": {"login": "nattawatpuntachot52"},
                        "baseRefName": "main",
                        "headRefName": "feat-a",
                        "baseRefOid": "aaa",
                        "headRefOid": "bbb",
                        "files": [{"path": "python/alpha_mining/control_plane/admission.py"}],
                        "statusCheckRollup": "SUCCESS",
                        "body": "",
                    },
                    {
                        "number": 11,
                        "title": "PR B",
                        "author": {"login": "nattawatpuntachot52"},
                        "baseRefName": "main",
                        "headRefName": "feat-b",
                        "baseRefOid": "aaa",
                        "headRefOid": "ccc",
                        "files": [{"path": "python/alpha_mining/control_plane/admission.py"}],
                        "statusCheckRollup": "SUCCESS",
                        "body": "",
                    },
                ],
            )
            self.assertEqual(len(records), 3)
            self.assertTrue(all(r.decision == "ignore" for r in records))
            self.assertTrue(all(r.would_accept for r in records))
            self.assertTrue(all(r.mandate is None for r in records))

            ledger_file = root / "observe.jsonl"
            for r in records:
                append_decision_ledger(ledger_file, r)
            summary = summarize_ledger(ledger_file)
            self.assertEqual(summary["total_records"], 3)
            self.assertEqual(summary["would_accept_in_observe_count"], 3)
            self.assertEqual(summary["per_rule_would_accept_hits"]["ci-default-branch-failure"], 1)
            self.assertEqual(summary["per_rule_would_accept_hits"]["parallel-pr-semantic-conflict"], 1)
            self.assertEqual(summary["per_rule_would_accept_hits"]["quant-manifest-drift-check"], 1)

            md = render_observe_report_markdown(records, policy=self.policy, policy_version=self.pver)
            self.assertIn("Admission Gate Observe Report", md)
            self.assertIn("quant-manifest-drift-check", md)

            # When latest main CI run passes after earlier failure, ci rule does not falsely fire
            healed = evaluate_github_observe_snapshot(
                self.policy,
                repo_root=REPO_ROOT,
                ci_runs_main=[
                    {"databaseId": 101, "status": "completed", "conclusion": "success"},
                    {"databaseId": 100, "status": "completed", "conclusion": "failure"},
                ],
                raw_prs=[],
            )
            self.assertFalse(healed[0].would_accept)

    def test_live_runner_fetch_error_yields_unavailable_and_cli_works(self) -> None:
        def failing_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="network timeout")

        records = run_live_github_observe(
            self.policy,
            repo="nattawatpuntachot52/Alpha_mining",
            repo_root=REPO_ROOT,
            runner=failing_runner,
        )
        by_id = {r.trigger_id: r for r in records}
        self.assertEqual(by_id["obs-ci-main"].decision, "unavailable")
        self.assertEqual(by_id["obs-pr-audit"].decision, "unavailable")
        self.assertEqual(by_id["obs-vault-drift"].decision, "ignore")
        self.assertFalse(by_id["obs-vault-drift"].would_accept)

        proc = subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "scripts" / "admission_gate.py"),
                "validate-policy",
                "--verify-rust-parity",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        parsed = json.loads(proc.stdout)
        self.assertTrue(parsed["rust_parity_verified"])

    def test_unlisted_ticket_bypass_closed_and_ci_precedence_and_auto_reviewers(self) -> None:
        # BLOCKING #2 regression: unlisted actor on thread with active/ended ticket stays not_admitted
        auto_pol = copy.deepcopy(self.policy)
        auto_pol["accept_mode"] = "auto"
        stranger_on_ticket = AdmissionTrigger(
            trigger_id="t-stranger-ticket",
            source_kind="github_pr",
            receiving_scope="github_pr",
            thread_id="pr:42",
            actor="random-stranger",
            addressed="none",
            existing_ticket_active=True,
            existing_ticket_ended_unstopped=True,
        )
        self.assertEqual(evaluate_gate(auto_pol, stranger_on_ticket).strength, "not_admitted")

        # WARNING #2 regression: github_default_branch_ci cell governs even if actor is an allowlisted bot
        ci_ignore_pol = copy.deepcopy(auto_pol)
        ci_ignore_pol["admission_table"]["github_default_branch_ci"]["unlisted_unaddressed"] = "ignore"
        ci_with_bot = AdmissionTrigger(
            trigger_id="t-ci-bot-spoof",
            source_kind="github_default_branch_ci",
            receiving_scope="github_default_branch_ci",
            thread_id="branch:main",
            actor="github-actions[bot]",
            actor_is_bot=True,
            addressed="none",
        )
        self.assertEqual(evaluate_gate(ci_ignore_pol, ci_with_bot).strength, "not_admitted")

        # Asymmetric CI source_kind/receiving_scope pairing rejected
        mismatched_ci = AdmissionTrigger(
            trigger_id="t-bad-ci-pair",
            source_kind="github_default_branch_ci",
            receiving_scope="github_pr",
            thread_id="pr:1",
            actor="github-ci",
        )
        with self.assertRaises(AdmissionError):
            evaluate_gate(auto_pol, mismatched_ci)

        # Unknown source_kind / empty actor rejected
        bad_src = AdmissionTrigger(
            trigger_id="t-bad-src",
            source_kind="slack_webhook",
            receiving_scope="github_pr",
            thread_id="pr:1",
            actor="nattawatpuntachot52",
        )
        with self.assertRaises(AdmissionError):
            evaluate_gate(auto_pol, bad_src)

        empty_actor = AdmissionTrigger(
            trigger_id="t-empty-actor",
            source_kind="github_pr",
            receiving_scope="github_pr",
            thread_id="pr:1",
            actor="   ",
        )
        with self.assertRaises(AdmissionError):
            evaluate_gate(auto_pol, empty_actor)

        # WARNING #4: automated_reviewers_non_bot overlap rejected and inferred-only enforced
        overlap_pol = copy.deepcopy(auto_pol)
        overlap_pol["automated_reviewers_non_bot"] = ["nattawatpuntachot52"]
        with self.assertRaises(AdmissionError):
            compute_policy_version(overlap_pol)

        rev_pol = copy.deepcopy(auto_pol)
        rev_pol["automated_reviewers_non_bot"] = ["CodexReviewer"]
        rev_trig = AdmissionTrigger(
            trigger_id="t-rev-1",
            source_kind="github_pr",
            receiving_scope="github_pr",
            thread_id="pr:7",
            actor="codexreviewer",
            addressed="mention",
        )
        g_rev = evaluate_gate(rev_pol, rev_trig)
        self.assertEqual(g_rev.strength, "inferred")
        self.assertFalse(g_rev.requester_is_bot)

        # Rust/Python policy_version parity STILL holds when automated_reviewers_non_bot is populated
        with tempfile.TemporaryDirectory() as tmp:
            rev_pol_path = Path(tmp) / "rev_pol.json"
            rev_pol_path.write_text(json.dumps(rev_pol), encoding="utf-8")
            self.assertEqual(
                self.bridge.policy_version(rev_pol_path)["policy_version"],
                compute_policy_version(rev_pol),
            )

        with self.assertRaises(AdmissionError):
            build_explicit_mandate(
                rev_pol,
                rev_trig,
                mandate_id="mnd-rev-bad",
                authority_id="auth-1",
                writable_scope=["python/"],
            )

        # Blank whitespace direction evidence is rejected
        pver_auto = compute_policy_version(auto_pol)
        blank_ev_ass = _all_rules_assessment(
            auto_pol,
            pver_auto,
            matched=["ci-default-branch-failure"],
            evidence=("   ", "\t"),
        )
        ci_valid = AdmissionTrigger(
            trigger_id="t-ci-blank",
            source_kind="github_default_branch_ci",
            receiving_scope="github_default_branch_ci",
            thread_id="branch:main",
            actor="github-ci",
        )
        rec_blank = evaluate_proactive_candidate(auto_pol, ci_valid, blank_ev_ass)
        self.assertEqual(rec_blank.decision, "ignore")
        self.assertFalse(rec_blank.would_accept)

    def test_explicit_mandate_roundtrip_and_auto_stranger_followup_block(self) -> None:
        # Build explicit mandate in 'off' mode and verify end-to-end against Rust alpha-ovca
        off_pol = copy.deepcopy(self.policy)
        off_pol["accept_mode"] = "off"
        owner_trig = AdmissionTrigger(
            trigger_id="t-exp-1",
            source_kind="github_pr",
            receiving_scope="github_pr",
            thread_id="pr:12",
            actor="nattawatpuntachot52",
            addressed="direct",
        )
        rec_exp = build_explicit_mandate(
            off_pol,
            owner_trig,
            mandate_id="mnd-exp-1",
            authority_id="auth-exp-1",
            writable_scope=["python/alpha_mining/"],
        )
        self.assertEqual(rec_exp.decision, "accept")
        self.assertEqual(rec_exp.strength, "explicit")
        self.assertTrue(rec_exp.would_accept)

        auto_pol = copy.deepcopy(self.policy)
        auto_pol["accept_mode"] = "auto"

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            off_path = tmp_dir / "off.json"
            auto_path = tmp_dir / "auto.json"
            mnd_path = tmp_dir / "mandate.json"
            fu_path = tmp_dir / "fu.json"
            off_path.write_text(json.dumps(off_pol), encoding="utf-8")
            auto_path.write_text(json.dumps(auto_pol), encoding="utf-8")
            mnd_path.write_text(json.dumps(rec_exp.mandate), encoding="utf-8")

            # Valid explicit mandate in off mode
            val_res = self.bridge.validate_mandate(mnd_path, policy_path=off_path)
            self.assertTrue(val_res["valid"])
            self.assertTrue(val_res["revalidation"]["valid_to_resume"])

            # Stranger in auto mode on github_pr still blocked (unlisted_* = ignore)
            fu_path.write_text(
                json.dumps(
                    {
                        "trigger_id": "fu-stranger",
                        "thread_id": "pr:12",
                        "subscription_mode": "owned_work",
                        "actor": "outsider",
                        "actor_is_bot": False,
                        "is_ci": False,
                        "addressed": "mention",
                        "requested_scope_paths": ["python/alpha_mining/test.py"],
                        "requests_stop": False,
                        "requests_scope_expansion": False,
                    }
                ),
                encoding="utf-8",
            )
            fu_stranger = self.bridge.check_followup(mnd_path, fu_path, auto_path)
            self.assertEqual(fu_stranger["action"], "context_only_deliver")
            self.assertFalse(fu_stranger["grant_authority"])
            self.assertFalse(fu_stranger["allow_resume"])

            # Empty mandate_id refused
            with self.assertRaises(AdmissionError):
                build_explicit_mandate(
                    off_pol,
                    owner_trig,
                    mandate_id=" ",
                    authority_id="auth-exp-1",
                    writable_scope=["python/alpha_mining/"],
                )

    def test_observe_snapshot_sorting_status_conclusions_and_cli_subcommands(self) -> None:
        # Out-of-order CI runs + null/in-progress status must not false-trigger failure
        records_ok = evaluate_github_observe_snapshot(
            self.policy,
            repo_root=REPO_ROOT,
            ci_runs_main=[
                {
                    "databaseId": 98,
                    "createdAt": "2026-11-17T01:00:00Z",
                    "status": "completed",
                    "conclusion": "failure",
                },
                {
                    "databaseId": 102,
                    "createdAt": "2026-11-17T03:00:00Z",
                    "status": None,
                    "conclusion": "failure",
                },
                {
                    "databaseId": 100,
                    "createdAt": "2026-11-17T02:00:00Z",
                    "status": "completed",
                    "conclusion": "success",
                },
            ],
            raw_prs=[],
        )
        self.assertFalse(records_ok[0].would_accept)

        # Latest completed run concluding with 'stale' or 'error' MUST fire ci-default-branch-failure
        for concl in ("stale", "error"):
            rec_concl = evaluate_github_observe_snapshot(
                self.policy,
                repo_root=REPO_ROOT,
                ci_runs_main=[
                    {
                        "databaseId": 200,
                        "createdAt": "2026-11-17T04:00:00Z",
                        "status": "completed",
                        "conclusion": concl,
                    }
                ],
                raw_prs=[],
            )
            self.assertTrue(rec_concl[0].would_accept, msg=f"expected would_accept for {concl}")

        # CR/LF escaping in markdown renderer
        cr_rec = copy.deepcopy(records_ok[0])
        object.__setattr__(cr_rec, "reason", "line1\r\nline2|pipe")
        md_cr = render_observe_report_markdown([cr_rec], policy=self.policy, policy_version=self.pver)
        self.assertNotIn("\r", md_cr)
        self.assertIn("line1  line2\\|pipe", md_cr)

        # Drive prefix containment parity
        self.assertFalse(is_path_within_scope("C:python/alpha_mining/a.py", ["python/"]))
        self.assertFalse(is_path_within_scope("é:foo", ["python/"]))

        # Full CLI end-to-end subcommands + corrupt/missing ledger errors
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            fixtures_path = tmp_dir / "fixtures.json"
            ledger_path = tmp_dir / "ledger.jsonl"
            json_out = tmp_dir / "report.json"
            trigger_path = tmp_dir / "trigger.json"
            ass_path = tmp_dir / "assessment.json"
            missing_ledger = tmp_dir / "missing.jsonl"

            # Missing ledger fails cleanly on CLI
            miss_proc = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "admission_gate.py"), "summarize-ledger", str(missing_ledger)],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(miss_proc.returncode, 0)

            # Corrupt ledger raises AdmissionError
            bad_ledger = tmp_dir / "corrupt.jsonl"
            bad_ledger.write_text("{bad-json\n", encoding="utf-8")
            with self.assertRaises(AdmissionError):
                summarize_ledger(bad_ledger)

            # observe-github --fixtures-json
            fixtures_path.write_text(
                json.dumps(
                    {
                        "ci_runs_main": [
                            {
                                "databaseId": 300,
                                "createdAt": "2026-11-17T05:00:00Z",
                                "status": "completed",
                                "conclusion": "failure",
                            }
                        ],
                        "raw_prs": [],
                    }
                ),
                encoding="utf-8",
            )
            obs_proc = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "admission_gate.py"),
                    "observe-github",
                    "--fixtures-json",
                    str(fixtures_path),
                    "--format",
                    "json",
                    "--ledger",
                    str(ledger_path),
                    "--json-out",
                    str(json_out),
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(obs_proc.returncode, 0, msg=obs_proc.stderr)
            obs_data = json.loads(json_out.read_text(encoding="utf-8"))
            self.assertEqual(obs_data["accept_mode"], "observe")
            self.assertEqual(obs_data["records"][0]["would_accept"], True)

            # eval-trigger on explicit trigger without --assessment succeeds; with --assessment fails
            trigger_path.write_text(
                json.dumps(
                    {
                        "trigger_id": "cli-exp-1",
                        "source_kind": "github_pr",
                        "receiving_scope": "github_pr",
                        "thread_id": "pr:77",
                        "actor": "nattawatpuntachot52",
                        "addressed": "direct",
                        "requested_scope_paths": ["python/alpha_mining/"],
                    }
                ),
                encoding="utf-8",
            )
            eval_proc = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "admission_gate.py"),
                    "eval-trigger",
                    "--trigger",
                    str(trigger_path),
                    "--ledger",
                    str(ledger_path),
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(eval_proc.returncode, 0, msg=eval_proc.stderr)
            eval_json = json.loads(eval_proc.stdout)
            self.assertEqual(eval_json["strength"], "explicit")
            self.assertEqual(eval_json["decision"], "accept")

            ass_path.write_text(json.dumps({"kind": "ignored_from_card"}), encoding="utf-8")
            bad_eval = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "admission_gate.py"),
                    "eval-trigger",
                    "--trigger",
                    str(trigger_path),
                    "--assessment",
                    str(ass_path),
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(bad_eval.returncode, 0)

            # summarize-ledger reports all appended records accurately
            sum_proc = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "admission_gate.py"), "summarize-ledger", str(ledger_path)],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(sum_proc.returncode, 0, msg=sum_proc.stderr)
            sum_json = json.loads(sum_proc.stdout)
            self.assertEqual(sum_json["total_records"], 4)
            self.assertEqual(sum_json["decision_counts"]["accept"], 1)
            self.assertEqual(sum_json["decision_counts"]["ignore"], 3)
            self.assertEqual(sum_json["would_accept_in_observe_count"], 1)

            # admission_gate.py revalidate-mandate & check-followup CLI subcommands
            cli_mnd_path = tmp_dir / "cli_mandate.json"
            cli_fu_path = tmp_dir / "cli_followup.json"
            cli_mnd_path.write_text(json.dumps(eval_json["mandate"]), encoding="utf-8")
            cli_fu_path.write_text(
                json.dumps(
                    {
                        "trigger_id": "cli-fu-1",
                        "thread_id": "pr:77",
                        "subscription_mode": "owned_work",
                        "actor": "nattawatpuntachot52",
                        "actor_is_bot": False,
                        "is_ci": False,
                        "requested_scope_paths": ["rust/crates/alpha-ovca/"],
                    }
                ),
                encoding="utf-8",
            )
            cli_rev = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "admission_gate.py"),
                    "revalidate-mandate",
                    "--mandate",
                    str(cli_mnd_path),
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(cli_rev.returncode, 0, msg=cli_rev.stderr)
            self.assertTrue(json.loads(cli_rev.stdout)["valid_to_resume"])

            cli_cf = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "admission_gate.py"),
                    "check-followup",
                    "--mandate",
                    str(cli_mnd_path),
                    "--followup",
                    str(cli_fu_path),
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(cli_cf.returncode, 0, msg=cli_cf.stderr)
            self.assertEqual(json.loads(cli_cf.stdout)["action"], "handback_required")

    def test_ovca_bridge_rebuilds_stale_cached_binary_with_locked(self) -> None:
        import os
        import time
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "rust" / "crates" / "alpha-ovca" / "src").mkdir(parents=True)
            (root / "rust" / "target" / "debug").mkdir(parents=True)
            (root / "rust" / "Cargo.toml").write_text("[workspace]\n", encoding="utf-8")
            (root / "rust" / "Cargo.lock").write_text("# lock\n", encoding="utf-8")
            rs_file = root / "rust" / "crates" / "alpha-ovca" / "src" / "lib.rs"
            rs_file.write_text("// updated\n", encoding="utf-8")
            stale_bin = root / "rust" / "target" / "debug" / "alpha-ovca"
            stale_bin.write_text("#!/bin/sh\n", encoding="utf-8")

            now = time.time()
            os.utime(stale_bin, (now - 100, now - 100))
            os.utime(rs_file, (now, now))

            calls: list[list[str]] = []

            def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(cmd)
                stale_bin.write_text("#!/bin/sh\n", encoding="utf-8")
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

            bridge = OvcaBridge(repo_root=root)
            with patch("alpha_mining.control_plane.ovca_bridge.subprocess.run", side_effect=fake_run):
                resolved = bridge.resolve_binary()

            self.assertEqual(resolved, stale_bin)
            self.assertEqual(len(calls), 1)
            self.assertIn("--locked", calls[0])
            self.assertIn("build", calls[0])

            # Missing cargo toolchain raises OvcaBridgeError instead of raw FileNotFoundError
            os.utime(stale_bin, (now - 100, now - 100))
            with patch(
                "alpha_mining.control_plane.ovca_bridge.subprocess.run",
                side_effect=FileNotFoundError("No such file or directory: 'cargo'"),
            ):
                with self.assertRaises(OvcaBridgeError) as ctx:
                    bridge.resolve_binary()
                self.assertIn("cargo executable not found", str(ctx.exception))

            # Non-object trigger JSON & string boolean coercion fail cleanly via CLI
            bad_trg = root / "bad_trig.json"
            bad_trg.write_text("[]\n", encoding="utf-8")
            bad_cli = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "admission_gate.py"), "eval-trigger", "--trigger", str(bad_trg)],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(bad_cli.returncode, 0)
            self.assertNotIn("Traceback", bad_cli.stderr)

            str_bool_trg = root / "str_bool.json"
            str_bool_trg.write_text(
                json.dumps(
                    {
                        "trigger_id": "cli-bad-bool",
                        "source_kind": "github_pr",
                        "receiving_scope": "github_pr",
                        "thread_id": "pr:1",
                        "actor": "nattawatpuntachot52",
                        "actor_is_bot": "false",
                    }
                ),
                encoding="utf-8",
            )
            bad_bool_cli = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "admission_gate.py"), "eval-trigger", "--trigger", str(str_bool_trg)],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(bad_bool_cli.returncode, 0)
            self.assertIn("must be a boolean", bad_bool_cli.stderr)


if __name__ == "__main__":
    unittest.main()
