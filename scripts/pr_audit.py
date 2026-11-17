#!/usr/bin/env python3
"""CLI for multi-PR Semantic Conflict & Pre-Merge Readiness Audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "python"))

from alpha_mining.control_plane.pr_audit import (  # noqa: E402
    PrAuditError,
    audit_pull_requests,
    fetch_open_prs,
    parse_pr_snapshots,
    render_markdown_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit open PRs for semantic collisions and readiness")
    parser.add_argument("-R", "--repo", default="nattawatpuntachot52/Alpha_mining")
    parser.add_argument("--fixtures-json", type=Path, help="Optional offline PR JSON fixture path")
    parser.add_argument("--pr", type=int, help="Focus exit code (--fail-on-critical) on a single PR number")
    parser.add_argument("--no-require-agent-ack", action="store_true")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--fail-on-critical", action="store_true")

    args = parser.parse_args(argv)

    try:
        if args.fixtures_json is not None:
            raw = json.loads(args.fixtures_json.read_text(encoding="utf-8"))
            prs = parse_pr_snapshots(raw)
        else:
            prs = fetch_open_prs(args.repo)
    except (OSError, json.JSONDecodeError, PrAuditError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    results = audit_pull_requests(prs, require_agent_ack=not args.no_require_agent_ack)

    if args.format == "json":
        payload = [
            {
                "number": r.pr.number,
                "title": r.pr.title,
                "author": r.pr.author,
                "base_ref_name": r.pr.base_ref_name,
                "head_ref_name": r.pr.head_ref_name,
                "base_ref_oid": r.pr.base_ref_oid,
                "head_ref_oid": r.pr.head_ref_oid,
                "is_draft": r.pr.is_draft,
                "mergeable": r.pr.mergeable,
                "checks_summary": r.pr.checks_summary,
                "agent_ack_present": r.agent_ack.present,
                "agent_ack_valid": r.agent_ack.valid,
                "verdict": r.verdict,
                "findings": [
                    {
                        "code": f.code,
                        "severity": f.severity,
                        "message": f.message,
                        "related_prs": list(f.related_prs),
                    }
                    for f in r.findings
                ],
            }
            for r in results
        ]
        print(json.dumps(payload, indent=2))
    else:
        print(render_markdown_report(results))

    if args.fail_on_critical:
        checked = [r for r in results if args.pr is None or r.pr.number == args.pr]
        if any(any(f.severity == "critical" for f in r.findings) for r in checked):
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
