"""Tests for AGENT_ACK parsing/validation and Multi-PR Semantic Conflict Audit."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python"))

from alpha_mining.control_plane.agent_ack import validate_agent_ack  # noqa: E402
from alpha_mining.control_plane.pr_audit import (  # noqa: E402
    audit_pull_requests,
    parse_pr_snapshots,
    render_markdown_report,
)

VALID_ACK_BODY = """
Summary here.

```text
AGENT_ACK
mission_id: ALPHA-M1
task_id: TASK-001
assignment_id: ASG-001
phase_id: CPO-1
agent_id: katherine
ovca_role: coordinator
actual_provider_runtime: Antigravity Agentic Runtime (Debian 12 Linux)
actual_model_id_version: UNKNOWN (not exposed by runtime)
tools_environment:
  host: vm-antigravity
  secondary_nodes: UNKNOWN / NOT_CONNECTED
  python: 3.11.2
mutation_boundary: branch feat/test scoped to control_plane/
verification_summary: cargo test passed (10/10); unittest passed
```
"""


class TestAgentAckAndPrAudit(unittest.TestCase):
    def test_valid_and_invalid_agent_ack(self) -> None:
        ok = validate_agent_ack(VALID_ACK_BODY)
        self.assertTrue(ok.present)
        self.assertTrue(ok.valid, ok.errors)
        self.assertEqual(ok.fields["actual_model_id_version"], "UNKNOWN (not exposed by runtime)")

        placeholder_bad = validate_agent_ack(VALID_ACK_BODY.replace("TASK-001", "<task_id>"))
        self.assertFalse(placeholder_bad.valid)

        guess_bad = validate_agent_ack(
            VALID_ACK_BODY.replace("cargo test passed (10/10); unittest passed", "probably passed")
        )
        self.assertFalse(guess_bad.valid)

        missing = validate_agent_ack("No acknowledgement section here.")
        self.assertFalse(missing.present)
        self.assertFalse(missing.valid)

    def test_catches_mergeable_parallel_sibling_collision_and_stale_stack(self) -> None:
        raw_prs = [
            {
                "number": 43,
                "title": "Docs: Engineering Guardrails",
                "author": {"login": "katherine"},
                "baseRefName": "main",
                "headRefName": "docs/guardrails",
                "baseRefOid": "main0001",
                "headRefOid": "d3de513d",
                "isDraft": False,
                "state": "OPEN",
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "body": VALID_ACK_BODY,
                "comments": [],
                "files": [{"path": "docs/guardrails.md"}],
                "statusCheckRollup": [
                    {"name": "rust", "conclusion": "SUCCESS"},
                    {"name": "python", "conclusion": "SUCCESS"},
                ],
                "reviews": [],
            },
            {
                "number": 46,
                "title": "Slice C: ExecutionRun -> ACK Lineage",
                "author": {"login": "elena"},
                "baseRefName": "main",
                "headRefName": "feat/slice-c",
                "baseRefOid": "main0001",
                "headRefOid": "c97c9c26",
                "isDraft": True,
                "state": "OPEN",
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "body": VALID_ACK_BODY,
                "comments": [],
                "files": [{"path": "python/alpha_mining/research/__init__.py"}],
                "statusCheckRollup": [{"name": "rust", "conclusion": "SUCCESS"}],
                "reviews": [],
            },
            # Parallel #47 and #48 branched off same #46 head SHA, both MERGEABLE & CI=SUCCESS,
            # touching distinct filenames with sibling semantic/naming & contract collision!
            {
                "number": 47,
                "title": "Slice D (Variant A): Single mission manifest",
                "author": {"login": "elena"},
                "baseRefName": "feat/slice-c",
                "headRefName": "feat/slice-d-a",
                "baseRefOid": "c97c9c26",
                "headRefOid": "005e5d2d",
                "isDraft": True,
                "state": "OPEN",
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "body": VALID_ACK_BODY,
                "comments": [],
                "files": [
                    {"path": "control/mission.json"},
                    {"path": "control/context_manifests/item.json"},
                ],
                "statusCheckRollup": [{"name": "rust", "conclusion": "SUCCESS"}],
                "reviews": [],
            },
            {
                "number": 48,
                "title": "Slice D (Variant B): Plural missions & schema edit",
                "author": {"login": "grace"},
                "baseRefName": "feat/slice-c",
                "headRefName": "feat/slice-d-b",
                "baseRefOid": "c97c9c26",
                "headRefOid": "5e03c62e",
                "isDraft": True,
                "state": "OPEN",
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "body": VALID_ACK_BODY,
                "comments": [],
                "files": [
                    {"path": "control/missions/m1.json"},
                    {"path": "control/context-manifests/item.json"},
                    {"path": "workflows/templates/assignment.schema.json"},
                ],
                "statusCheckRollup": [{"name": "rust", "conclusion": "SUCCESS"}],
                "reviews": [],
            },
            # Stacked PR #49 with stale base commit behind #47 head SHA
            {
                "number": 49,
                "title": "Slice E: Stacked on outdated #47",
                "author": {"login": "nita"},
                "baseRefName": "feat/slice-d-a",
                "headRefName": "feat/slice-e",
                "baseRefOid": "stale999",
                "headRefOid": "eeee0001",
                "isDraft": False,
                "state": "OPEN",
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "body": VALID_ACK_BODY,
                "comments": [],
                "files": [{"path": "python/alpha_mining/accounting/__init__.py"}],
                "statusCheckRollup": [{"name": "rust", "conclusion": "SUCCESS"}],
                "reviews": [],
            },
        ]

        prs = parse_pr_snapshots(raw_prs)
        results = {res.pr.number: res for res in audit_pull_requests(prs)}

        self.assertEqual(results[43].verdict, "MERGE_WITH_CAUTION")  # shares base SHA main0001 with #46
        self.assertEqual(results[46].verdict, "MERGE_WITH_CAUTION")
        self.assertEqual(results[47].verdict, "RECONCILE_REQUIRED")
        self.assertEqual(results[48].verdict, "RECONCILE_REQUIRED")
        self.assertEqual(results[49].verdict, "BLOCKED")

        codes_47 = {f.code for f in results[47].findings}
        self.assertIn("SIBLING_NAMESPACE_COLLISION", codes_47)
        self.assertIn("PARALLEL_SAME_BASE_CONTRACT_DIVERGENCE", codes_47)

        codes_49 = {f.code for f in results[49].findings}
        self.assertIn("STALE_STACKED_BASE", codes_49)
        self.assertIn("STACKED_PARENT_NOT_READY", codes_49)

        md = render_markdown_report(list(results.values()))
        self.assertIn("RECONCILE_REQUIRED", md)
        self.assertIn("SIBLING_NAMESPACE_COLLISION", md)

    def test_fetch_open_prs_enriches_unresolved_threads_and_unknown_mergeable(self) -> None:
        import json
        import subprocess
        from alpha_mining.control_plane.pr_audit import fetch_open_prs

        def fake_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
            if cmd[:2] == ["gh", "pr"]:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    json.dumps([
                        {
                            "number": 7,
                            "title": "Test thread enrichment",
                            "author": {"login": "katherine"},
                            "baseRefName": "main",
                            "headRefName": "feat/x",
                            "baseRefOid": "aaa",
                            "headRefOid": "bbb",
                            "isDraft": False,
                            "state": "OPEN",
                            "mergeable": "UNKNOWN",
                            "mergeStateStatus": "UNKNOWN",
                            "body": VALID_ACK_BODY,
                            "files": [{"path": "README.md"}],
                            "comments": [],
                            "reviews": [],
                            "statusCheckRollup": [{"name": "rust", "conclusion": "SUCCESS"}],
                        }
                    ]),
                    "",
                )
            return subprocess.CompletedProcess(
                cmd,
                0,
                json.dumps(
                    {
                        "data": {
                            "repository": {
                                "pullRequests": {
                                    "nodes": [
                                        {
                                            "number": 7,
                                            "reviewThreads": {
                                                "nodes": [
                                                    {"isResolved": False},
                                                    {"isResolved": True},
                                                ]
                                            },
                                        }
                                    ]
                                }
                            }
                        }
                    }
                ),
                "",
            )

        prs = fetch_open_prs("nattawatpuntachot52/Alpha_mining", runner=fake_runner)
        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0].unresolved_threads, 1)
        res = audit_pull_requests(prs)[0]
        self.assertEqual(res.verdict, "BLOCKED")
        codes = {f.code for f in res.findings}
        self.assertIn("UNRESOLVED_THREADS", codes)
        self.assertIn("MERGEABLE_UNKNOWN", codes)

    def test_indented_ack_embedded_placeholder_and_role_validation(self) -> None:
        indented_fenced = """
        - Handover note:
          ```md
          AGENT_ACK
            mission_id: M-INDENT
            task_id: T-INDENT
            assignment_id: A-INDENT
            phase_id: P-1
            agent_id: elena
            ovca_role: engineer
            actual_provider_runtime: Linux VM
            actual_model_id_version: UNKNOWN (not exposed)
            tools_environment:
              host: vm-1
            mutation_boundary: feat/indented
            verification_summary: python unittest passed
          ```
        """
        rep_ok = validate_agent_ack(indented_fenced)
        self.assertTrue(rep_ok.valid, rep_ok.errors)
        self.assertEqual(rep_ok.fields["mission_id"], "M-INDENT")
        self.assertEqual(rep_ok.fields["tools_environment"], "host: vm-1")

        indented_raw = "\n    AGENT_ACK\n    mission_id: M2\n    task_id: T2\n    agent_id: grace\n    actual_provider_runtime: Linux\n    actual_model_id_version: gpt-test\n    mutation_boundary: feat/raw\n    verification_summary: checks passed\n"
        rep_raw = validate_agent_ack(indented_raw)
        self.assertTrue(rep_raw.valid, rep_raw.errors)
        self.assertEqual(rep_raw.fields["agent_id"], "grace")

        embedded_placeholder = validate_agent_ack(VALID_ACK_BODY.replace("feat/test", "feat/<branch_name>"))
        self.assertFalse(embedded_placeholder.valid)
        self.assertTrue(any("placeholder" in err for err in embedded_placeholder.errors))

        bad_role = validate_agent_ack(VALID_ACK_BODY.replace("ovca_role: coordinator", "ovca_role: wizard"))
        self.assertFalse(bad_role.valid)
        self.assertTrue(any("ovca_role" in err for err in bad_role.errors))

    def test_three_hop_stack_propagation_fork_isolation_legacy_checks_and_comment_trust(self) -> None:
        raw_prs = [
            # PR #10 (root of 3-hop stack, fails CI via STARTUP_FAILURE & legacy ERROR StatusContext)
            {
                "number": 10,
                "title": "Stack Root | Escape <check>",
                "author": {"login": "alice"},
                "baseRefName": "main",
                "headRefName": "feat/hop-1",
                "baseRefOid": "mainsha",
                "headRefOid": "sha10",
                "isDraft": False,
                "state": "OPEN",
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "UNSTABLE",
                "body": VALID_ACK_BODY,
                "comments": [],
                "files": [{"path": "python/alpha_mining/research/a.py"}],
                "statusCheckRollup": [
                    {"state": "SUCCESS"},
                    {"name": "rust", "conclusion": "STARTUP_FAILURE"},
                ],
                "reviews": [],
            },
            # PR #11 (hop 2, cleanly stacked on #10, touches same file cleanly)
            {
                "number": 11,
                "title": "Hop 2\nMultiline",
                "author": {"login": "alice"},
                "baseRefName": "feat/hop-1",
                "headRefName": "feat/hop-2",
                "baseRefOid": "sha10",
                "headRefOid": "sha11",
                "isDraft": False,
                "state": "OPEN",
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "body": VALID_ACK_BODY,
                "comments": [],
                "files": [{"path": "python/alpha_mining/research/a.py"}],
                "statusCheckRollup": [{"state": "SUCCESS"}],
                "reviews": [],
            },
            # PR #12 (hop 3, cleanly stacked on #11, touches same file as #10 cleanly)
            {
                "number": 12,
                "title": "Hop 3",
                "author": {"login": "alice"},
                "baseRefName": "feat/hop-2",
                "headRefName": "feat/hop-3",
                "baseRefOid": "sha11",
                "headRefOid": "sha12",
                "isDraft": False,
                "state": "OPEN",
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "body": "Body without ack",
                "comments": [
                    # Author comment supplies valid ACK
                    {"author": {"login": "alice"}, "body": VALID_ACK_BODY}
                ],
                "files": [{"path": "python/alpha_mining/research/a.py"}],
                "statusCheckRollup": [{"state": "PENDING"}],
                "reviews": [],
            },
            # PR #13: Fork PR whose headRefName happens to be "main" must NOT make PR #10 count as stacked on it!
            # Also has a spoofed AGENT_ACK from an untrusted third-party user "mallory".
            {
                "number": 13,
                "title": "External fork main",
                "author": {"login": "bob"},
                "baseRefName": "main",
                "headRefName": "main",
                "baseRefOid": "otherbase",
                "headRefOid": "sha13",
                "isCrossRepository": True,
                "isDraft": False,
                "state": "OPEN",
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "body": "No ack in body",
                "comments": [
                    {"author": {"login": "mallory"}, "body": VALID_ACK_BODY},
                ],
                "files": [{"path": "docs/fork_note.md"}],
                "statusCheckRollup": [{"state": "SUCCESS"}],
                "reviews": [],
            },
        ]

        results = {res.pr.number: res for res in audit_pull_requests(parse_pr_snapshots(raw_prs))}

        # Multi-hop propagation: #10 CI_FAILED -> #11 BLOCKED -> #12 BLOCKED (without false DIRECT_FILE_OVERLAP!)
        self.assertEqual(results[10].verdict, "BLOCKED")
        self.assertIn("CI_FAILED", {f.code for f in results[10].findings})
        self.assertEqual(results[11].verdict, "BLOCKED")
        self.assertIn("STACKED_PARENT_NOT_READY", {f.code for f in results[11].findings})
        self.assertNotIn("DIRECT_FILE_OVERLAP", {f.code for f in results[11].findings})

        self.assertEqual(results[12].verdict, "BLOCKED")
        codes_12 = {f.code for f in results[12].findings}
        self.assertIn("STACKED_PARENT_NOT_READY", codes_12)
        self.assertIn("CI_NOT_GREEN", codes_12)  # from legacy PENDING StatusContext
        self.assertNotIn("DIRECT_FILE_OVERLAP", codes_12)
        self.assertTrue(results[12].agent_ack.valid)  # author comment trusted

        # PR #13 ignored mallory's spoofed ACK -> BLOCKED for missing AGENT_ACK; fork head "main" did not trap #10
        self.assertFalse(results[13].agent_ack.valid)
        self.assertIn("AGENT_ACK_INVALID", {f.code for f in results[13].findings})
        self.assertNotIn("STALE_STACKED_BASE", {f.code for f in results[10].findings})

        md = render_markdown_report(list(results.values()))
        self.assertIn(r"Stack Root \| Escape <check>", md)
        self.assertIn("Hop 2 Multiline", md)

    def test_graphql_pagination_and_cli_execution(self) -> None:
        import json
        import subprocess
        import tempfile
        from alpha_mining.control_plane.pr_audit import fetch_open_prs

        cursors_seen: list[str | None] = []

        def paged_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
            if cmd[:2] == ["gh", "pr"]:
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    json.dumps([
                        {
                            "number": 1,
                            "title": "One",
                            "author": {"login": "a"},
                            "baseRefName": "main",
                            "headRefName": "feat/one",
                            "baseRefOid": "b1",
                            "headRefOid": "h1",
                            "state": "OPEN",
                            "mergeable": "MERGEABLE",
                            "mergeStateStatus": "CLEAN",
                            "body": VALID_ACK_BODY,
                            "files": [],
                            "comments": [],
                            "reviews": [],
                            "statusCheckRollup": [{"name": "rust", "conclusion": "SUCCESS"}],
                        },
                        {
                            "number": 2,
                            "title": "Two",
                            "author": {"login": "b"},
                            "baseRefName": "main",
                            "headRefName": "feat/two",
                            "baseRefOid": "b2",
                            "headRefOid": "h2",
                            "state": "OPEN",
                            "mergeable": "MERGEABLE",
                            "mergeStateStatus": "CLEAN",
                            "body": VALID_ACK_BODY,
                            "files": [],
                            "comments": [],
                            "reviews": [],
                            "statusCheckRollup": [{"name": "rust", "conclusion": "SUCCESS"}],
                        },
                    ]),
                    "",
                )
            cursor_arg = [arg for arg in cmd if arg.startswith("cursor=")]
            cursor_val = cursor_arg[0].split("=", 1)[1] if cursor_arg else None
            cursors_seen.append(cursor_val)
            if cursor_val is None:
                page = {
                    "pageInfo": {"hasNextPage": True, "endCursor": "CUR1"},
                    "nodes": [{"number": 1, "reviewThreads": {"nodes": []}}],
                }
            else:
                page = {
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                    "nodes": [{"number": 2, "reviewThreads": {"nodes": [{"isResolved": False}]}}],
                }
            return subprocess.CompletedProcess(
                cmd,
                0,
                json.dumps({"data": {"repository": {"pullRequests": page}}}),
                "",
            )

        prs = fetch_open_prs("nattawatpuntachot52/Alpha_mining", runner=paged_runner)
        self.assertEqual(cursors_seen, [None, "CUR1"])
        self.assertEqual([p.unresolved_threads for p in prs], [0, 1])

        with tempfile.TemporaryDirectory() as tmp:
            fixture_path = Path(tmp) / "prs.json"
            fixture_path.write_text(
                json.dumps([
                    {
                        "number": 5,
                        "title": "Missing ACK PR",
                        "author": {"login": "a"},
                        "baseRefName": "main",
                        "headRefName": "feat/bad",
                        "baseRefOid": "b1",
                        "headRefOid": "h5",
                        "state": "OPEN",
                        "mergeable": "MERGEABLE",
                        "mergeStateStatus": "CLEAN",
                        "body": "No ack",
                        "files": [{"path": "README.md"}],
                        "comments": [],
                        "reviews": [],
                        "statusCheckRollup": [{"name": "rust", "conclusion": "SUCCESS"}],
                    }
                ]),
                encoding="utf-8",
            )
            script = REPO_ROOT / "scripts" / "pr_audit.py"
            proc = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "-R",
                    "owner/repo",
                    "--fixtures-json",
                    str(fixture_path),
                    "--format",
                    "json",
                    "--fail-on-critical",
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 2, proc.stderr)
            parsed = json.loads(proc.stdout)
            self.assertEqual(parsed[0]["verdict"], "BLOCKED")

    def test_disjoint_alpha_and_beta_factory_prs_stay_ready_to_merge(self) -> None:
        raw_prs = [
            {
                "number": 27,
                "title": "chore(alpha-mining): daily 10-model XAUUSD+ETH batch (r1)",
                "author": {"login": "app/github-actions"},
                "baseRefName": "main",
                "headRefName": "bot/daily-alpha-mining-2026-11-25",
                "baseRefOid": "1d1eb3a",
                "headRefOid": "6b62f2c",
                "isDraft": False,
                "state": "OPEN",
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "BLOCKED",
                "body": VALID_ACK_BODY,
                "comments": [],
                "files": [
                    {"path": "alpha_mining/daily/2026-11-25/batch.json"},
                    {"path": "alpha_mining/index.html"},
                ],
                "statusCheckRollup": [
                    {"name": "rust", "conclusion": "SUCCESS"},
                    {"name": "python", "conclusion": "SUCCESS"},
                ],
                "reviews": [],
            },
            {
                "number": 28,
                "title": "chore(beta-mining): daily 5-model batch (r1)",
                "author": {"login": "app/github-actions"},
                "baseRefName": "main",
                "headRefName": "bot/daily-beta-mining-2026-11-25",
                "baseRefOid": "1d1eb3a",
                "headRefOid": "c872959",
                "isDraft": False,
                "state": "OPEN",
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "BLOCKED",
                "body": VALID_ACK_BODY,
                "comments": [],
                "files": [
                    {"path": "beta_mining/daily/2026-11-25/batch.json"},
                    {"path": "beta_mining/index.html"},
                ],
                "statusCheckRollup": [
                    {"name": "rust", "conclusion": "SUCCESS"},
                    {"name": "python", "conclusion": "SUCCESS"},
                ],
                "reviews": [],
            },
        ]
        results = {res.pr.number: res for res in audit_pull_requests(parse_pr_snapshots(raw_prs))}
        self.assertEqual(results[27].verdict, "READY_TO_MERGE")
        self.assertEqual(results[28].verdict, "READY_TO_MERGE")
        self.assertEqual([f.code for f in results[27].findings], ["PARALLEL_DISJOINT_FACTORY_DATA"])
        self.assertEqual([f.severity for f in results[27].findings], ["info"])
        self.assertEqual([f.code for f in results[28].findings], ["PARALLEL_DISJOINT_FACTORY_DATA"])

        # Adding even one non-factory file must fall back to PARALLEL_SAME_BASE warning (MERGE_WITH_CAUTION).
        raw_prs[1]["files"].append({"path": "README.md"})
        mixed = {res.pr.number: res for res in audit_pull_requests(parse_pr_snapshots(raw_prs))}
        self.assertEqual(mixed[27].verdict, "MERGE_WITH_CAUTION")
        self.assertEqual(mixed[28].verdict, "MERGE_WITH_CAUTION")
        self.assertIn("PARALLEL_SAME_BASE", {f.code for f in mixed[27].findings})
        self.assertIn("PARALLEL_SAME_BASE", {f.code for f in mixed[28].findings})


if __name__ == "__main__":
    unittest.main()
