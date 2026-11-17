#!/usr/bin/env python3
"""CLI for validating, inspecting, applying, and upgrading Alpha_mining GitHub Rulesets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "python"))

from alpha_mining.control_plane.github_ruleset import (  # noqa: E402
    RulesetError,
    apply_rulesets,
    default_ruleset_paths,
    load_json_file,
    set_review_quorum,
    validate_ruleset_configs,
    verify_live_rulesets,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage Alpha_mining 2-layer GitHub Rulesets")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("validate-configs", help="Validate local Standard + Details ruleset JSON files")

    apply_p = sub.add_parser("apply", help="Idempotently apply Rulesets to GitHub")
    apply_p.add_argument("-R", "--repo", default="nattawatpuntachot52/Alpha_mining")
    apply_p.add_argument("--dry-run", action="store_true")

    verify_p = sub.add_parser("verify", help="Verify live GitHub Rulesets against local config")
    verify_p.add_argument("-R", "--repo", default="nattawatpuntachot52/Alpha_mining")

    quorum_p = sub.add_parser("set-review-quorum", help="Safely change required_approving_review_count")
    quorum_p.add_argument("-R", "--repo", default="nattawatpuntachot52/Alpha_mining")
    quorum_p.add_argument("--count", type=int, required=True)
    quorum_p.add_argument("--confirm-bot-ready", action="store_true")
    quorum_p.add_argument("--local-only", action="store_true")
    quorum_p.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    std_path, det_path = default_ruleset_paths(REPO_ROOT)

    try:
        if args.cmd == "validate-configs":
            out = validate_ruleset_configs(load_json_file(std_path), load_json_file(det_path))
        elif args.cmd == "apply":
            res = apply_rulesets(
                args.repo,
                load_json_file(std_path),
                load_json_file(det_path),
                dry_run=args.dry_run,
            )
            out = {"repo": res.repo, "actions": res.actions, "main_protected": res.main_protected}
        elif args.cmd == "verify":
            out = verify_live_rulesets(args.repo, load_json_file(std_path), load_json_file(det_path))
        elif args.cmd == "set-review-quorum":
            out = set_review_quorum(
                args.repo,
                std_path,
                det_path,
                count=args.count,
                confirm_bot_ready=args.confirm_bot_ready,
                local_only=args.local_only,
                dry_run=args.dry_run,
            )
        else:
            parser.error(f"unknown subcommand: {args.cmd}")
            return 2
    except RulesetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
