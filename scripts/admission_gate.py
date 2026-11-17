#!/usr/bin/env python3
"""CLI for Alpha_mining Admission Gate, Observe Mode, and Mandate/Handback Verification."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
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
    evaluate_gate,
    evaluate_github_observe_snapshot,
    evaluate_proactive_candidate,
    load_admission_policy,
    render_observe_report_markdown,
    run_live_github_observe,
    summarize_ledger,
)
from alpha_mining.control_plane.ovca_bridge import OvcaBridge, OvcaBridgeError  # noqa: E402

DEFAULT_POLICY_PATH = REPO_ROOT / "config" / "governance" / "admission_policy.json"


def _require_bool(raw: dict[str, Any], key: str, default: bool) -> bool:
    if key not in raw:
        return default
    val = raw[key]
    if not isinstance(val, bool):
        raise AdmissionError(f"field '{key}' must be a boolean, got {type(val).__name__}")
    return val


def _parse_assessment(raw: Any) -> ProactiveAssessment | IgnoredFromCard | AssessmentUnavailable:
    if not isinstance(raw, dict):
        raise AdmissionError(f"assessment JSON must be an object, got {type(raw).__name__}")
    kind = raw.get("kind", "assessment")
    if not isinstance(kind, str):
        raise AdmissionError("assessment field 'kind' must be a string")
    if kind == "ignored_from_card":
        return IgnoredFromCard(reason=str(raw.get("reason", "ignored from card")))
    if kind == "unavailable":
        return AssessmentUnavailable(
            error_kind=str(raw.get("error_kind", "tool_error")),
            reason=str(raw.get("reason", "assessment unavailable")),
        )
    dir_raw = raw.get("direction") or {}
    if not isinstance(dir_raw, dict):
        raise AdmissionError("assessment field 'direction' must be an object")
    ev_raw = dir_raw.get("evidence") or ()
    if not isinstance(ev_raw, (list, tuple)):
        raise AdmissionError("direction.evidence must be a JSON array")
    direction = DirectionDeclaration(
        implementation_requested=_require_bool(dir_raw, "implementation_requested", False),
        target_basis=str(dir_raw.get("target_basis", "unclear")),
        requires_design_decision=_require_bool(dir_raw, "requires_design_decision", True),
        evidence=tuple(str(x) for x in ev_raw),
    )
    rules_raw = raw.get("rule_assessments") or []
    if not isinstance(rules_raw, list):
        raise AdmissionError("assessment field 'rule_assessments' must be a JSON array")
    entries_list: list[RuleAssessmentEntry] = []
    for item in rules_raw:
        if not isinstance(item, dict):
            raise AdmissionError("each rule_assessments item must be a JSON object")
        if "matched" not in item:
            raise AdmissionError("rule_assessment missing required field 'matched'")
        entries_list.append(
            RuleAssessmentEntry(
                rule_id=str(item["rule_id"]),
                matched=_require_bool(item, "matched", False),
                reason=str(item["reason"]),
            )
        )
    prop_scope = raw.get("proposed_writable_scope") or ()
    if not isinstance(prop_scope, (list, tuple)):
        raise AdmissionError("proposed_writable_scope must be a JSON array")
    return ProactiveAssessment(
        policy_version=str(raw["policy_version"]),
        direction=direction,
        rule_assessments=tuple(entries_list),
        proposed_writable_scope=tuple(str(x) for x in prop_scope),
        summary=str(raw.get("summary", "")),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate AdmissionPolicy, evaluate triggers in off|observe|auto mode, and verify Mandates/Handback"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_val = sub.add_parser("validate-policy", help="Validate admission policy and print canonical SHA-256 policy_version")
    p_val.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    p_val.add_argument("--verify-rust-parity", action="store_true", help="Cross-verify policy_version hash with Rust alpha-ovca")

    p_eval = sub.add_parser("eval-trigger", help="Evaluate an incoming trigger (and optional assessment) against AdmissionPolicy")
    p_eval.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    p_eval.add_argument("--trigger", type=Path, required=True)
    p_eval.add_argument("--assessment", type=Path)
    p_eval.add_argument("--mandate-id", default="mnd-explicit-001")
    p_eval.add_argument("--authority-id", default="auth-explicit-001")
    p_eval.add_argument("--writable-scope", nargs="*", default=[])
    p_eval.add_argument("--ledger", type=Path)
    p_eval.add_argument("--out", type=Path)

    p_sum = sub.add_parser("summarize-ledger", help="Summarize append-only JSONL admission decisions & observe hits")
    p_sum.add_argument("ledger", type=Path)

    p_fu = sub.add_parser("check-followup", help="Delegate follow-up / handback check to Rust alpha-ovca")
    p_fu.add_argument("--mandate", type=Path, required=True)
    p_fu.add_argument("--followup", type=Path, required=True)
    p_fu.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)

    p_rev = sub.add_parser("revalidate-mandate", help="Delegate mandate revalidation to Rust alpha-ovca")
    p_rev.add_argument("--mandate", type=Path, required=True)
    p_rev.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)

    p_obs = sub.add_parser("observe-github", help="Evaluate seeded GitHub proactive rules read-only in observe/off/auto mode")
    p_obs.add_argument("-R", "--repo", default="nattawatpuntachot52/Alpha_mining")
    p_obs.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    p_obs.add_argument("--default-branch", default="main")
    p_obs.add_argument("--fixtures-json", type=Path, help="Offline snapshot fixture JSON ({ci_runs_main, raw_prs})")
    p_obs.add_argument("--format", choices=("markdown", "json"), default="markdown")
    p_obs.add_argument("--ledger", type=Path, help="Optional JSONL ledger path to append observe decisions")
    p_obs.add_argument("--json-out", type=Path, help="Optional file path to save structured JSON records")

    args = parser.parse_args(argv)

    try:
        if args.command == "validate-policy":
            policy, pver = load_admission_policy(args.policy)
            out: dict[str, Any] = {
                "valid": True,
                "accept_mode": policy["accept_mode"],
                "policy_version": pver,
                "enabled_rules": [r["rule_id"] for r in policy["proactive_rules"] if r["enabled"]],
            }
            if args.verify_rust_parity:
                bridge = OvcaBridge(repo_root=REPO_ROOT)
                rust_res = bridge.policy_version(args.policy)
                if rust_res.get("policy_version") != pver:
                    raise AdmissionError(
                        f"Rust/Python policy_version mismatch: rust={rust_res.get('policy_version')} != py={pver}"
                    )
                out["rust_parity_verified"] = True
            print(json.dumps(out, indent=2))
            return 0

        if args.command == "eval-trigger":
            policy, _ = load_admission_policy(args.policy)
            raw_trg = json.loads(args.trigger.read_text(encoding="utf-8"))
            if not isinstance(raw_trg, dict):
                raise AdmissionError(f"trigger JSON must be an object, got {type(raw_trg).__name__}")
            req_paths = raw_trg.get("requested_scope_paths") or ()
            if not isinstance(req_paths, (list, tuple)):
                raise AdmissionError("trigger field 'requested_scope_paths' must be a JSON array")
            trigger = AdmissionTrigger(
                trigger_id=str(raw_trg["trigger_id"]),
                source_kind=str(raw_trg["source_kind"]),
                receiving_scope=str(raw_trg["receiving_scope"]),
                thread_id=str(raw_trg["thread_id"]),
                actor=str(raw_trg["actor"]),
                actor_is_bot=_require_bool(raw_trg, "actor_is_bot", False),
                addressed=str(raw_trg.get("addressed", "none")),
                existing_ticket_active=_require_bool(raw_trg, "existing_ticket_active", False),
                existing_ticket_ended_unstopped=_require_bool(
                    raw_trg, "existing_ticket_ended_unstopped", False
                ),
                summary=str(raw_trg.get("summary", "")),
                requested_scope_paths=tuple(str(x) for x in req_paths),
            )
            gate = evaluate_gate(policy, trigger)
            if gate.strength == "explicit":
                if args.assessment is not None:
                    raise AdmissionError(
                        "explicit trigger grants direct explicit authority and must not consume a proactive assessment"
                    )
                scope = list(args.writable_scope or trigger.requested_scope_paths)
                record = build_explicit_mandate(
                    policy,
                    trigger,
                    mandate_id=args.mandate_id,
                    authority_id=args.authority_id,
                    writable_scope=scope,
                )
            elif args.assessment is not None:
                raw_ass = json.loads(args.assessment.read_text(encoding="utf-8"))
                record = evaluate_proactive_candidate(
                    policy,
                    trigger,
                    _parse_assessment(raw_ass),
                )
            else:
                record = evaluate_proactive_candidate(
                    policy,
                    trigger,
                    IgnoredFromCard(reason=gate.reason),
                )

            if args.ledger is not None:
                append_decision_ledger(args.ledger, record)
            payload_str = json.dumps(record.to_dict(), indent=2, ensure_ascii=False)
            if args.out is not None:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(payload_str + "\n", encoding="utf-8")
            print(payload_str)
            return 0

        if args.command == "summarize-ledger":
            if not args.ledger.is_file():
                raise AdmissionError(f"ledger file not found: {args.ledger}")
            print(json.dumps(summarize_ledger(args.ledger), indent=2))
            return 0

        if args.command == "check-followup":
            bridge = OvcaBridge(repo_root=REPO_ROOT)
            res = bridge.check_followup(args.mandate, args.followup, args.policy)
            print(json.dumps(res, indent=2))
            return 0

        if args.command == "revalidate-mandate":
            bridge = OvcaBridge(repo_root=REPO_ROOT)
            res = bridge.revalidate_mandate(args.mandate, args.policy)
            print(json.dumps(res, indent=2))
            return 0

        if args.command == "observe-github":
            policy, pver = load_admission_policy(args.policy)
            if args.fixtures_json is not None:
                fix = json.loads(args.fixtures_json.read_text(encoding="utf-8"))
                if not isinstance(fix, dict):
                    raise AdmissionError(f"fixtures JSON must be an object, got {type(fix).__name__}")
                records = evaluate_github_observe_snapshot(
                    policy,
                    repo_root=REPO_ROOT,
                    ci_runs_main=fix.get("ci_runs_main"),
                    ci_fetch_error=fix.get("ci_fetch_error"),
                    raw_prs=fix.get("raw_prs"),
                    pr_fetch_error=fix.get("pr_fetch_error"),
                )
            else:
                records = run_live_github_observe(
                    policy,
                    repo=args.repo,
                    repo_root=REPO_ROOT,
                    default_branch=args.default_branch,
                )

            if args.ledger is not None:
                for rec in records:
                    append_decision_ledger(args.ledger, rec)

            json_payload = {
                "accept_mode": policy["accept_mode"],
                "policy_version": pver,
                "records": [rec.to_dict() for rec in records],
            }
            if args.json_out is not None:
                args.json_out.parent.mkdir(parents=True, exist_ok=True)
                args.json_out.write_text(
                    json.dumps(json_payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )

            if args.format == "json":
                print(json.dumps(json_payload, indent=2, ensure_ascii=False))
            else:
                print(
                    render_observe_report_markdown(
                        records,
                        policy=policy,
                        policy_version=pver,
                    )
                )
            return 0

    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError, AdmissionError, OvcaBridgeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
