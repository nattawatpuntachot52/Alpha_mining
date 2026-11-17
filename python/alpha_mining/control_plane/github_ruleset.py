"""Manage and validate 2-layer GitHub Rulesets and separate Bot/App quorum safely."""

from __future__ import annotations

import copy
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


class RulesetError(RuntimeError):
    """Raised when a GitHub Ruleset configuration or API operation is invalid."""


CommandRunner = Callable[[list[str], str | None], subprocess.CompletedProcess[str]]


def _default_runner(cmd: list[str], stdin_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        input=stdin_text,
        capture_output=True,
        text=True,
        check=False,
    )


def default_ruleset_paths(repo_root: Path) -> tuple[Path, Path]:
    rules_dir = repo_root / "config" / "github" / "rulesets"
    return (
        rules_dir / "standard-main-protection.json",
        rules_dir / "details-main-protection.json",
    )


def load_json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RulesetError(f"failed to read ruleset file '{path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RulesetError(f"invalid JSON in ruleset file '{path}': {exc}") from exc
    if not isinstance(data, dict):
        raise RulesetError(f"ruleset file '{path}' must contain a JSON object")
    return data


def _find_rule(ruleset: dict[str, Any], rule_type: str) -> dict[str, Any] | None:
    rules = ruleset.get("rules")
    if not isinstance(rules, list):
        return None
    for rule in rules:
        if isinstance(rule, dict) and rule.get("type") == rule_type:
            return rule
    return None


def validate_ruleset_configs(
    standard_cfg: dict[str, Any],
    details_cfg: dict[str, Any],
    required_checks: tuple[str, ...] = ("rust", "python"),
) -> dict[str, Any]:
    """Verify 2-layer Ruleset invariants (non-bypassable main PR gate + CI checks)."""
    errors: list[str] = []

    for label, cfg in (("standard", standard_cfg), ("details", details_cfg)):
        if not isinstance(cfg, dict):
            errors.append(f"{label} ruleset must be a JSON object")
            continue
        if not isinstance(cfg.get("name"), str) or not cfg.get("name", "").strip():
            errors.append(f"{label} ruleset must have a non-empty 'name'")
        if cfg.get("target") != "branch":
            errors.append(f"{label} ruleset target must be 'branch'")
        if cfg.get("enforcement") != "active":
            errors.append(f"{label} ruleset enforcement must be 'active'")
        if cfg.get("bypass_actors") != []:
            errors.append(f"{label} ruleset bypass_actors must be []")
        conditions = cfg.get("conditions")
        ref_name = conditions.get("ref_name") if isinstance(conditions, dict) else None
        include_refs = ref_name.get("include") if isinstance(ref_name, dict) else None
        exclude_refs = ref_name.get("exclude") if isinstance(ref_name, dict) else None
        if not isinstance(include_refs, list) or "~DEFAULT_BRANCH" not in include_refs:
            errors.append(f"{label} ruleset must target '~DEFAULT_BRANCH'")
        if not isinstance(exclude_refs, list) or len(exclude_refs) > 0:
            errors.append(f"{label} ruleset conditions.ref_name.exclude must be []")

    if _find_rule(standard_cfg, "deletion") is None:
        errors.append("standard ruleset must enforce 'deletion' protection")
    if _find_rule(standard_cfg, "non_fast_forward") is None:
        errors.append("standard ruleset must enforce 'non_fast_forward' protection")

    pr_rule = _find_rule(standard_cfg, "pull_request")
    if pr_rule is None:
        errors.append("standard ruleset must contain a 'pull_request' rule")
        review_count = -1
        dismiss_stale = False
        thread_resolution = False
    else:
        params = pr_rule.get("parameters")
        if not isinstance(params, dict):
            params = {}
        review_count = params.get("required_approving_review_count")
        if isinstance(review_count, bool) or not isinstance(review_count, int) or review_count < 0:
            errors.append("pull_request.required_approving_review_count must be integer >= 0")
            review_count = -1
        dismiss_stale = params.get("dismiss_stale_reviews_on_push") is True
        thread_resolution = params.get("required_review_thread_resolution") is True
        if not dismiss_stale:
            errors.append("pull_request.dismiss_stale_reviews_on_push must be true")
        if not thread_resolution:
            errors.append("pull_request.required_review_thread_resolution must be true")

    checks_rule = _find_rule(details_cfg, "required_status_checks")
    configured_contexts: list[str] = []
    strict_checks = False
    if checks_rule is None:
        errors.append("details ruleset must contain 'required_status_checks'")
    else:
        params = checks_rule.get("parameters")
        if not isinstance(params, dict):
            params = {}
        strict_checks = params.get("strict_required_status_checks_policy") is True
        if not strict_checks:
            errors.append("strict_required_status_checks_policy must be true")
        raw_checks = params.get("required_status_checks", [])
        if not isinstance(raw_checks, list):
            errors.append("required_status_checks must be a list")
        else:
            configured_contexts = [
                c.get("context", "")
                for c in raw_checks
                if isinstance(c, dict) and isinstance(c.get("context"), str) and c.get("context")
            ]
        for expected in required_checks:
            if expected not in configured_contexts:
                errors.append(
                    f"details ruleset missing required status check context '{expected}'"
                )

    if errors:
        raise RulesetError("; ".join(errors))

    return {
        "valid": True,
        "standard_name": standard_cfg["name"],
        "details_name": details_cfg["name"],
        "required_approving_review_count": review_count,
        "dismiss_stale_reviews_on_push": dismiss_stale,
        "required_review_thread_resolution": thread_resolution,
        "strict_required_status_checks_policy": strict_checks,
        "required_status_checks": sorted(configured_contexts),
    }


def _gh_api_json(
    endpoint: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    runner: CommandRunner = _default_runner,
) -> Any:
    cmd = ["gh", "api"]
    if method != "GET":
        cmd.extend(["-X", method])
    cmd.append(endpoint)
    stdin_text = None
    if payload is not None:
        cmd.extend(["--input", "-"])
        stdin_text = json.dumps(payload)

    proc = runner(cmd, stdin_text)
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip()
        raise RulesetError(f"gh api {method} {endpoint} failed: {detail}")
    if not proc.stdout.strip():
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RulesetError(f"non-JSON response from gh api {endpoint}: {proc.stdout!r}") from exc


@dataclass(frozen=True)
class RulesetSyncResult:
    repo: str
    actions: list[dict[str, Any]]
    main_protected: bool


def apply_rulesets(
    repo: str,
    standard_cfg: dict[str, Any],
    details_cfg: dict[str, Any],
    *,
    dry_run: bool = False,
    runner: CommandRunner = _default_runner,
) -> RulesetSyncResult:
    """Create or update both Layer 1 and Layer 2 Rulesets idempotently by name."""
    validate_ruleset_configs(standard_cfg, details_cfg)
    existing = _gh_api_json(f"repos/{repo}/rulesets", runner=runner) or []
    by_name = {item["name"]: item["id"] for item in existing if isinstance(item, dict) and "name" in item}

    actions: list[dict[str, Any]] = []
    for cfg in (standard_cfg, details_cfg):
        name = cfg["name"]
        existing_id = by_name.get(name)
        method = "PUT" if existing_id is not None else "POST"
        endpoint = (
            f"repos/{repo}/rulesets/{existing_id}"
            if existing_id is not None
            else f"repos/{repo}/rulesets"
        )
        if dry_run:
            actions.append({"name": name, "method": method, "endpoint": endpoint, "dry_run": True})
        else:
            resp = _gh_api_json(endpoint, method=method, payload=cfg, runner=runner)
            actions.append(
                {
                    "name": name,
                    "method": method,
                    "endpoint": endpoint,
                    "id": resp.get("id") if isinstance(resp, dict) else existing_id,
                    "dry_run": False,
                }
            )

    branch_info = _gh_api_json(f"repos/{repo}/branches/main", runner=runner) or {}

    return RulesetSyncResult(
        repo=repo,
        actions=actions,
        main_protected=bool(branch_info.get("protected", False)),
    )


def set_review_quorum(
    repo: str,
    standard_path: Path,
    details_path: Path,
    *,
    count: int,
    confirm_bot_ready: bool = False,
    local_only: bool = False,
    dry_run: bool = False,
    runner: CommandRunner = _default_runner,
) -> dict[str, Any]:
    """Safely adjust required_approving_review_count after verifying non-deadlock readiness."""
    if isinstance(count, bool) or count < 0:
        raise RulesetError("review quorum count must be >= 0")

    standard_cfg = copy.deepcopy(load_json_file(standard_path))
    details_cfg = load_json_file(details_path)
    validate_ruleset_configs(standard_cfg, details_cfg)

    collaborators: list[str] = []
    if count >= 1 and not confirm_bot_ready:
        if local_only:
            raise RulesetError(
                "refusing local-only quorum >= 1 without --confirm-bot-ready "
                "(GitHub Apps do not appear in collaborator checks and self-approval is blocked)"
            )
        raw_collab = _gh_api_json(f"repos/{repo}/collaborators", runner=runner) or []
        collaborators = [
            c.get("login", "")
            for c in raw_collab
            if isinstance(c, dict) and c.get("login")
        ]
        if len(collaborators) < 2:
            raise RulesetError(
                "self-approval deadlock guard: repository has fewer than 2 collaborators "
                f"({collaborators}). Add a separate Bot collaborator OR set up a GitHub App "
                "per docs/bot-account-setup.md and pass --confirm-bot-ready."
            )

    pr_rule = _find_rule(standard_cfg, "pull_request")
    assert pr_rule is not None
    pr_rule["parameters"]["required_approving_review_count"] = count

    # Apply remotely first so local repo config never drifts ahead of live GitHub on API failure.
    sync_result: dict[str, Any] | None = None
    if not local_only:
        res = apply_rulesets(
            repo,
            standard_cfg,
            details_cfg,
            dry_run=dry_run,
            runner=runner,
        )
        sync_result = {
            "actions": res.actions,
            "main_protected": res.main_protected,
        }

    if not dry_run:
        standard_path.write_text(json.dumps(standard_cfg, indent=2) + "\n", encoding="utf-8")

    return {
        "repo": repo,
        "required_approving_review_count": count,
        "confirm_bot_ready": confirm_bot_ready,
        "collaborators_observed": collaborators,
        "dry_run": dry_run,
        "local_only": local_only,
        "sync": sync_result,
    }


def verify_live_rulesets(
    repo: str,
    standard_cfg: dict[str, Any],
    details_cfg: dict[str, Any],
    *,
    runner: CommandRunner = _default_runner,
) -> dict[str, Any]:
    """Read back deployed GitHub Rulesets + main branch protection and check zero drift against local config."""
    local_summary = validate_ruleset_configs(standard_cfg, details_cfg)
    live_list = _gh_api_json(f"repos/{repo}/rulesets", runner=runner) or []
    by_name = {item["name"]: item for item in live_list if isinstance(item, dict) and "name" in item}

    std_summary = by_name.get(standard_cfg["name"])
    det_summary = by_name.get(details_cfg["name"])
    if std_summary is None or det_summary is None:
        raise RulesetError(
            f"missing deployed ruleset(s) on {repo}: found={list(by_name.keys())}"
        )

    std_full = _gh_api_json(f"repos/{repo}/rulesets/{std_summary['id']}", runner=runner)
    det_full = _gh_api_json(f"repos/{repo}/rulesets/{det_summary['id']}", runner=runner)
    live_summary = validate_ruleset_configs(std_full, det_full)

    if live_summary != local_summary:
        raise RulesetError(
            f"live ruleset drift detected on {repo}: local={local_summary}, live={live_summary}"
        )

    branch_info = _gh_api_json(f"repos/{repo}/branches/main", runner=runner) or {}
    if not branch_info.get("protected", False):
        raise RulesetError(f"{repo} branch 'main' reports protected=false")

    return {
        "repo": repo,
        "verified": True,
        "main_protected": True,
        "standard_ruleset_id": std_summary["id"],
        "details_ruleset_id": det_summary["id"],
        "details": live_summary,
    }
