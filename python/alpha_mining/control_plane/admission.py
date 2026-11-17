"""Mechanism 1 (Context != Authority Mandate & Handback) and Mechanism 2 (Observe Mode Gate)."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from .pr_audit import audit_pull_requests, fetch_open_prs, parse_pr_snapshots

AcceptMode = Literal["off", "observe", "auto"]
MandateStrength = Literal["explicit", "inferred", "not_admitted"]
DecisionKind = Literal["accept", "stop", "ignore", "unavailable"]
CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]

VALID_ACCEPT_MODES = frozenset({"off", "observe", "auto"})
VALID_ADMISSION_CHOICES = frozenset({"explicit", "inferred", "ignore"})
VALID_UNADDRESSED_CHOICES = frozenset({"inferred", "ignore"})
VALID_SCOPES = frozenset(
    {
        "owner_cli",
        "github_issue",
        "github_pr",
        "github_comment",
        "github_default_branch_ci",
    }
)
VALID_SOURCE_KINDS = frozenset(
    {
        "owner_cli",
        "github_issue",
        "github_pr",
        "github_comment",
        "github_default_branch_ci",
        "bot",
    }
)
VALID_TARGET_BASES = frozenset({"specified", "existing_standard", "unclear", "not_applicable"})
_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


class AdmissionError(ValueError):
    """Raised when an admission policy, assessment, or mandate contract is invalid."""


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalize_actor(actor: str) -> str:
    return actor.strip().lower()


def _is_bot_login(actor: str) -> bool:
    return _normalize_actor(actor).endswith("[bot]")


def _normalized_segments(raw: str) -> list[str] | None:
    clean = raw.strip().rstrip("/")
    if not clean or clean.startswith("/") or "\\" in clean or "\x00" in clean:
        return None
    if len(clean) >= 2 and clean[1] == ":":
        return None
    parts: list[str] = []
    for seg in clean.split("/"):
        if not seg or seg in (".", ".."):
            return None
        parts.append(seg)
    return parts


def is_path_within_scope(candidate: str, allowed_scopes: list[str] | tuple[str, ...]) -> bool:
    """Segment-boundary containment check matching Rust alpha-ovca `is_path_within_scope`."""
    trimmed = candidate.strip()
    if (
        not trimmed
        or trimmed.startswith("/")
        or trimmed.startswith("\\")
        or "\\" in trimmed
        or "\x00" in trimmed
        or (len(trimmed) >= 2 and trimmed[1] == ":")
    ):
        return False

    cand_parts = _normalized_segments(trimmed)
    if not cand_parts:
        return False

    for raw_scope in allowed_scopes:
        scope_parts = _normalized_segments(raw_scope)
        if not scope_parts:
            continue
        if len(cand_parts) >= len(scope_parts) and cand_parts[: len(scope_parts)] == scope_parts:
            return True
    return False


def _validate_safe_scope_pattern(raw: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise AdmissionError("writable_scope entries must be non-empty strings")
    trimmed = raw.strip()
    if trimmed.startswith("/") or "\\" in trimmed or "\x00" in trimmed:
        raise AdmissionError(f"writable_scope '{raw}' must be repository-relative with '/'")
    if _normalized_segments(trimmed) is None:
        raise AdmissionError(f"writable_scope '{raw}' contains invalid '.' or '..' segments")
    return trimmed


def _normalize_actor_list(field_name: str, values: Any, *, require_non_empty: bool) -> list[str]:
    if not isinstance(values, list):
        raise AdmissionError(f"{field_name} must be a list")
    if require_non_empty and not values:
        raise AdmissionError(f"{field_name} must contain at least one actor")
    seen: set[str] = set()
    out: list[str] = []
    for item in values:
        if not isinstance(item, str):
            raise AdmissionError(f"{field_name} entries must be strings")
        norm = _normalize_actor(item)
        if not norm:
            raise AdmissionError(f"{field_name} must not contain empty actor entries")
        if norm in seen:
            raise AdmissionError(f"{field_name} must not contain duplicate actor '{norm}'")
        seen.add(norm)
        out.append(norm)
    return sorted(out)


def canonicalize_policy(raw_policy: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize an AdmissionPolicy dict cleanly for canonical SHA-256 hashing."""
    if not isinstance(raw_policy, dict):
        raise AdmissionError("policy document must be a JSON object")

    expected_keys = {
        "policy_schema_version",
        "accept_mode",
        "allowed_actors",
        "bot_allowlist",
        "automated_reviewers_non_bot",
        "admission_table",
        "proactive_rules",
    }
    unknown = set(raw_policy.keys()) - expected_keys
    if unknown:
        raise AdmissionError(f"unknown policy field(s): {sorted(unknown)}")

    schema_ver = raw_policy.get("policy_schema_version")
    if schema_ver != "1.0":
        raise AdmissionError(f"policy_schema_version must be '1.0', got {schema_ver!r}")

    accept_mode = raw_policy.get("accept_mode")
    if accept_mode not in VALID_ACCEPT_MODES:
        raise AdmissionError(f"accept_mode must be one of {sorted(VALID_ACCEPT_MODES)}")

    allowed_actors = _normalize_actor_list(
        "allowed_actors", raw_policy.get("allowed_actors"), require_non_empty=True
    )
    for actor in allowed_actors:
        if _is_bot_login(actor):
            raise AdmissionError(
                f"bot identity '{actor}' cannot appear in allowed_actors; place bots in bot_allowlist"
            )

    bot_allowlist = _normalize_actor_list(
        "bot_allowlist", raw_policy.get("bot_allowlist"), require_non_empty=False
    )
    overlap = set(allowed_actors).intersection(bot_allowlist)
    if overlap:
        raise AdmissionError(f"actors cannot appear in both allowed_actors and bot_allowlist: {sorted(overlap)}")

    auto_rev = _normalize_actor_list(
        "automated_reviewers_non_bot",
        raw_policy.get("automated_reviewers_non_bot", []),
        require_non_empty=False,
    )
    for actor in auto_rev:
        if _is_bot_login(actor):
            raise AdmissionError(
                f"bot identity '{actor}' cannot appear in automated_reviewers_non_bot; place bots in bot_allowlist"
            )
    rev_allowed_overlap = set(allowed_actors).intersection(auto_rev)
    if rev_allowed_overlap:
        raise AdmissionError(
            f"actors cannot appear in both allowed_actors and automated_reviewers_non_bot: {sorted(rev_allowed_overlap)}"
        )
    rev_bot_overlap = set(bot_allowlist).intersection(auto_rev)
    if rev_bot_overlap:
        raise AdmissionError(
            f"actors cannot appear in both bot_allowlist and automated_reviewers_non_bot: {sorted(rev_bot_overlap)}"
        )

    raw_table = raw_policy.get("admission_table")
    if not isinstance(raw_table, dict) or not raw_table:
        raise AdmissionError("admission_table must be a non-empty object")

    canon_table: dict[str, dict[str, Any]] = {}
    for scope in sorted(raw_table.keys()):
        if scope not in VALID_SCOPES:
            raise AdmissionError(f"unsupported admission_table scope '{scope}'")
        row = raw_table[scope]
        if not isinstance(row, dict):
            raise AdmissionError(f"admission_table['{scope}'] must be an object")
        row_keys = {
            "receive_all",
            "listed_addressed",
            "listed_unaddressed",
            "unlisted_addressed",
            "unlisted_unaddressed",
        }
        if set(row.keys()) != row_keys:
            raise AdmissionError(f"admission_table['{scope}'] keys must equal {sorted(row_keys)}")
        receive_all = row["receive_all"]
        if not isinstance(receive_all, bool):
            raise AdmissionError(f"admission_table['{scope}'].receive_all must be bool")
        for k in ("listed_addressed", "unlisted_addressed"):
            if row[k] not in VALID_ADMISSION_CHOICES:
                raise AdmissionError(f"admission_table['{scope}'].{k} invalid: {row[k]!r}")
        for k in ("listed_unaddressed", "unlisted_unaddressed"):
            if row[k] not in VALID_UNADDRESSED_CHOICES:
                raise AdmissionError(f"admission_table['{scope}'].{k} invalid: {row[k]!r}")

        if scope == "github_default_branch_ci":
            if (
                row["listed_addressed"] != "ignore"
                or row["listed_unaddressed"] != "ignore"
                or row["unlisted_addressed"] != "ignore"
            ):
                raise AdmissionError(
                    "github_default_branch_ci has no sender; only unlisted_unaddressed may be configured"
                )
        elif not receive_all and (
            row["listed_unaddressed"] != "ignore" or row["unlisted_unaddressed"] != "ignore"
        ):
            raise AdmissionError(
                f"receiving scope '{scope}' has receive_all=false, so unaddressed cells must be 'ignore'"
            )

        canon_table[scope] = {
            "listed_addressed": row["listed_addressed"],
            "listed_unaddressed": row["listed_unaddressed"],
            "receive_all": receive_all,
            "unlisted_addressed": row["unlisted_addressed"],
            "unlisted_unaddressed": row["unlisted_unaddressed"],
        }

    raw_rules = raw_policy.get("proactive_rules")
    if not isinstance(raw_rules, list):
        raise AdmissionError("proactive_rules must be a list")

    seen_rule_ids: set[str] = set()
    canon_rules: list[dict[str, Any]] = []
    rule_expected_keys = {
        "rule_id",
        "enabled",
        "title",
        "description",
        "receiving_scopes",
        "writable_scope",
        "silent_ack",
    }
    for rule in raw_rules:
        if not isinstance(rule, dict) or set(rule.keys()) != rule_expected_keys:
            raise AdmissionError("each proactive_rule must contain exact required fields")
        rule_id = rule["rule_id"].strip() if isinstance(rule["rule_id"], str) else ""
        if not rule_id or rule_id in seen_rule_ids:
            raise AdmissionError(f"proactive rule_id must be non-empty and unique, got {rule.get('rule_id')!r}")
        seen_rule_ids.add(rule_id)
        if not isinstance(rule["enabled"], bool) or not isinstance(rule["silent_ack"], bool):
            raise AdmissionError(f"rule '{rule_id}' enabled and silent_ack must be booleans")
        title = rule["title"].strip() if isinstance(rule["title"], str) else ""
        desc = rule["description"].strip() if isinstance(rule["description"], str) else ""
        if not title or not desc:
            raise AdmissionError(f"rule '{rule_id}' title and description must not be empty")
        scopes = rule["receiving_scopes"]
        if not isinstance(scopes, list) or not scopes:
            raise AdmissionError(f"rule '{rule_id}' must declare non-empty receiving_scopes")
        for sc in scopes:
            if sc not in VALID_SCOPES:
                raise AdmissionError(f"rule '{rule_id}' has invalid receiving_scope '{sc}'")
        wscopes = rule["writable_scope"]
        if not isinstance(wscopes, list) or not wscopes:
            raise AdmissionError(f"rule '{rule_id}' must declare non-empty writable_scope")
        seen_w: set[str] = set()
        norm_w: list[str] = []
        for ws in wscopes:
            cleaned = _validate_safe_scope_pattern(ws)
            if cleaned in seen_w:
                raise AdmissionError(f"rule '{rule_id}' has duplicate writable_scope '{cleaned}'")
            seen_w.add(cleaned)
            norm_w.append(cleaned)

        canon_rules.append(
            {
                "description": desc,
                "enabled": rule["enabled"],
                "receiving_scopes": sorted(set(scopes)),
                "rule_id": rule_id,
                "silent_ack": rule["silent_ack"],
                "title": title,
                "writable_scope": sorted(norm_w),
            }
        )

    canon_rules.sort(key=lambda r: r["rule_id"])
    return {
        "accept_mode": accept_mode,
        "admission_table": canon_table,
        "allowed_actors": allowed_actors,
        "automated_reviewers_non_bot": auto_rev,
        "bot_allowlist": bot_allowlist,
        "policy_schema_version": "1.0",
        "proactive_rules": canon_rules,
    }


def validate_admission_policy(raw_policy: dict[str, Any]) -> dict[str, Any]:
    """Validate and return the normalized canonical policy dictionary."""
    return canonicalize_policy(raw_policy)


def compute_policy_version(raw_policy: dict[str, Any]) -> str:
    """Compute canonical SHA-256 `policy_version` matching Rust alpha-ovca byte-for-byte."""
    canon = canonicalize_policy(raw_policy)
    payload = json.dumps(canon, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def load_admission_policy(path: Path | str) -> tuple[dict[str, Any], str]:
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    canon = canonicalize_policy(raw)
    return canon, compute_policy_version(canon)


@dataclass(frozen=True)
class AdmissionTrigger:
    trigger_id: str
    source_kind: str
    receiving_scope: str
    thread_id: str
    actor: str
    actor_is_bot: bool = False
    addressed: str = "none"  # "mention" | "direct" | "none"
    existing_ticket_active: bool = False
    existing_ticket_ended_unstopped: bool = False
    summary: str = ""
    requested_scope_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class GateResult:
    trigger_id: str
    strength: MandateStrength
    policy_version: str
    accept_mode: AcceptMode
    reason: str
    requester_is_bot: bool


@dataclass(frozen=True)
class DirectionDeclaration:
    implementation_requested: bool
    target_basis: str  # "specified" | "existing_standard" | "unclear" | "not_applicable"
    requires_design_decision: bool
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuleAssessmentEntry:
    rule_id: str
    matched: bool
    reason: str


@dataclass(frozen=True)
class ProactiveAssessment:
    policy_version: str
    direction: DirectionDeclaration
    rule_assessments: tuple[RuleAssessmentEntry, ...]
    proposed_writable_scope: tuple[str, ...] = ()
    summary: str = ""


@dataclass(frozen=True)
class IgnoredFromCard:
    reason: str


@dataclass(frozen=True)
class AssessmentUnavailable:
    error_kind: str
    reason: str


@dataclass(frozen=True)
class DecisionRecord:
    trigger_id: str
    thread_id: str
    decision: DecisionKind
    strength: MandateStrength
    accept_mode: AcceptMode
    policy_version: str
    would_accept: bool
    ignored_from_card: bool
    matched_rules: tuple[str, ...]
    reason: str
    recorded_at: str
    mandate: dict[str, Any] | None = None
    rule_assessments: tuple[dict[str, Any], ...] = ()
    error_kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_gate(raw_policy: dict[str, Any], trigger: AdmissionTrigger) -> GateResult:
    """Deterministic admission gate deciding explicit vs inferred vs not_admitted."""
    policy = canonicalize_policy(raw_policy)
    pver = compute_policy_version(policy)
    accept_mode: AcceptMode = policy["accept_mode"]

    if not trigger.trigger_id.strip():
        raise AdmissionError("trigger.trigger_id must not be empty")
    if not trigger.thread_id.strip():
        raise AdmissionError("trigger.thread_id must not be empty")
    if not trigger.actor.strip():
        raise AdmissionError("trigger.actor must not be empty")
    if trigger.source_kind not in VALID_SOURCE_KINDS:
        raise AdmissionError(f"invalid trigger.source_kind: {trigger.source_kind!r}")
    if trigger.receiving_scope not in VALID_SCOPES:
        raise AdmissionError(f"invalid trigger.receiving_scope: {trigger.receiving_scope!r}")
    if (trigger.source_kind == "github_default_branch_ci") != (
        trigger.receiving_scope == "github_default_branch_ci"
    ):
        raise AdmissionError(
            "github_default_branch_ci source_kind and receiving_scope must be paired symmetrically"
        )
    if trigger.addressed not in ("mention", "direct", "none"):
        raise AdmissionError(f"invalid trigger.addressed: {trigger.addressed!r}")

    actor = _normalize_actor(trigger.actor)
    is_bot = trigger.actor_is_bot or trigger.source_kind == "bot" or _is_bot_login(actor)
    row = policy["admission_table"].get(trigger.receiving_scope)
    if row is None:
        return GateResult(
            trigger_id=trigger.trigger_id,
            strength="not_admitted",
            policy_version=pver,
            accept_mode=accept_mode,
            reason=f"no admission_table row configured for scope '{trigger.receiving_scope}'",
            requester_is_bot=is_bot,
        )

    # 1. Default-branch CI BEFORE bot allowlist: github_default_branch_ci cell always controls CI gating
    if trigger.source_kind == "github_default_branch_ci":
        if row["unlisted_unaddressed"] != "inferred":
            return GateResult(
                trigger_id=trigger.trigger_id,
                strength="not_admitted",
                policy_version=pver,
                accept_mode=accept_mode,
                reason="github_default_branch_ci cell configured as ignore",
                requester_is_bot=is_bot,
            )
        if accept_mode == "off":
            return GateResult(
                trigger_id=trigger.trigger_id,
                strength="not_admitted",
                policy_version=pver,
                accept_mode=accept_mode,
                reason="accept_mode='off' blocks inferred CI candidates",
                requester_is_bot=is_bot,
            )
        return GateResult(
            trigger_id=trigger.trigger_id,
            strength="inferred",
            policy_version=pver,
            accept_mode=accept_mode,
            reason="default-branch CI trigger admitted as inferred candidate",
            requester_is_bot=is_bot,
        )

    # 2. Bots: never explicit, never stop, inferred only when allowlisted & observable
    if is_bot:
        if actor not in policy["bot_allowlist"]:
            return GateResult(
                trigger_id=trigger.trigger_id,
                strength="not_admitted",
                policy_version=pver,
                accept_mode=accept_mode,
                reason=f"bot '{actor}' is not in bot_allowlist",
                requester_is_bot=True,
            )
        if trigger.addressed == "none" and not row["receive_all"]:
            return GateResult(
                trigger_id=trigger.trigger_id,
                strength="not_admitted",
                policy_version=pver,
                accept_mode=accept_mode,
                reason="allowlisted bot did not address agent and scope lacks receive_all",
                requester_is_bot=True,
            )
        if accept_mode == "off":
            return GateResult(
                trigger_id=trigger.trigger_id,
                strength="not_admitted",
                policy_version=pver,
                accept_mode=accept_mode,
                reason="accept_mode='off' blocks all inferred bot candidates",
                requester_is_bot=True,
            )
        return GateResult(
            trigger_id=trigger.trigger_id,
            strength="inferred",
            policy_version=pver,
            accept_mode=accept_mode,
            reason="allowlisted bot admitted as inferred candidate (explicit prohibited for bots)",
            requester_is_bot=True,
        )

    # 3. Non-bot automated reviewers: inferred-only when observable & accept_mode != 'off'
    if actor in policy["automated_reviewers_non_bot"]:
        if trigger.addressed == "none" and not row["receive_all"]:
            return GateResult(
                trigger_id=trigger.trigger_id,
                strength="not_admitted",
                policy_version=pver,
                accept_mode=accept_mode,
                reason="automated reviewer did not address agent and scope lacks receive_all",
                requester_is_bot=False,
            )
        if accept_mode == "off":
            return GateResult(
                trigger_id=trigger.trigger_id,
                strength="not_admitted",
                policy_version=pver,
                accept_mode=accept_mode,
                reason="accept_mode='off' blocks inferred automated reviewer candidates",
                requester_is_bot=False,
            )
        return GateResult(
            trigger_id=trigger.trigger_id,
            strength="inferred",
            policy_version=pver,
            accept_mode=accept_mode,
            reason="non-bot automated reviewer admitted as inferred candidate (explicit prohibited)",
            requester_is_bot=False,
        )

    # 4. Human triggers
    is_listed = actor in policy["allowed_actors"]
    is_addressed = trigger.addressed in ("mention", "direct")
    has_ticket = trigger.existing_ticket_active or trigger.existing_ticket_ended_unstopped

    if not is_listed and is_addressed and row["unlisted_addressed"] == "explicit":
        return GateResult(
            trigger_id=trigger.trigger_id,
            strength="explicit",
            policy_version=pver,
            accept_mode=accept_mode,
            reason="unlisted_addressed='explicit' grants explicit strength in every mode",
            requester_is_bot=False,
        )

    if is_listed and (is_addressed or has_ticket):
        cell = row["listed_addressed"]
        if cell == "explicit":
            return GateResult(
                trigger_id=trigger.trigger_id,
                strength="explicit",
                policy_version=pver,
                accept_mode=accept_mode,
                reason="allowed actor addressed agent or followed up on ticket thread (listed_addressed='explicit')",
                requester_is_bot=False,
            )
        if cell == "inferred":
            strength = "not_admitted" if accept_mode == "off" else "inferred"
            return GateResult(
                trigger_id=trigger.trigger_id,
                strength=strength,
                policy_version=pver,
                accept_mode=accept_mode,
                reason=f"listed_addressed='inferred' under accept_mode='{accept_mode}'",
                requester_is_bot=False,
            )
        if not is_addressed and has_ticket and row["listed_unaddressed"] == "inferred":
            strength = "not_admitted" if accept_mode == "off" else "inferred"
            return GateResult(
                trigger_id=trigger.trigger_id,
                strength=strength,
                policy_version=pver,
                accept_mode=accept_mode,
                reason=f"listed_addressed='ignore'; unaddressed ticket fallback resolved under accept_mode='{accept_mode}'",
                requester_is_bot=False,
            )
        return GateResult(
            trigger_id=trigger.trigger_id,
            strength="not_admitted",
            policy_version=pver,
            accept_mode=accept_mode,
            reason="listed_addressed cell resolved to 'ignore'",
            requester_is_bot=False,
        )

    if is_listed:
        cell = row["listed_unaddressed"]
        strength: MandateStrength = "inferred" if cell == "inferred" else "not_admitted"
        reason = f"listed_unaddressed cell resolved to '{cell}'"
    elif is_addressed:
        cell = row["unlisted_addressed"]
        strength = "inferred" if cell == "inferred" else "not_admitted"
        reason = f"unlisted_addressed cell resolved to '{cell}'"
    else:
        cell = row["unlisted_unaddressed"]
        strength = "inferred" if cell == "inferred" else "not_admitted"
        reason = f"unlisted_unaddressed cell resolved to '{cell}'"

    if strength == "inferred" and accept_mode == "off":
        return GateResult(
            trigger_id=trigger.trigger_id,
            strength="not_admitted",
            policy_version=pver,
            accept_mode=accept_mode,
            reason=f"accept_mode='off' blocks inferred candidate ({reason})",
            requester_is_bot=False,
        )

    return GateResult(
        trigger_id=trigger.trigger_id,
        strength=strength,
        policy_version=pver,
        accept_mode=accept_mode,
        reason=reason,
        requester_is_bot=False,
    )


def _intersect_rule_scopes(rules: list[dict[str, Any]]) -> list[str]:
    """Compute conservative intersection of writable scopes across matched rules."""
    if not rules:
        return []
    if len(rules) == 1:
        return list(rules[0]["writable_scope"])

    first_scopes = list(rules[0]["writable_scope"])
    other_scope_lists = [list(r["writable_scope"]) for r in rules[1:]]
    common: list[str] = []
    for cand in first_scopes:
        if all(is_path_within_scope(cand, other) for other in other_scope_lists):
            common.append(cand)
    # Also retain narrower child paths from subsequent rules when covered by all others
    for r in rules[1:]:
        all_others = [list(x["writable_scope"]) for x in rules if x["rule_id"] != r["rule_id"]]
        for cand in r["writable_scope"]:
            if cand not in common and all(is_path_within_scope(cand, o) for o in all_others):
                common.append(cand)
    return sorted(set(common))


def build_explicit_mandate(
    raw_policy: dict[str, Any],
    trigger: AdmissionTrigger,
    *,
    mandate_id: str,
    authority_id: str,
    writable_scope: list[str],
    recorded_at: str | None = None,
) -> DecisionRecord:
    """Create an explicit Mandate directly after Gate admits explicit strength."""
    if not isinstance(mandate_id, str) or not mandate_id.strip():
        raise AdmissionError("explicit mandate requires non-empty mandate_id")
    if not isinstance(authority_id, str) or not authority_id.strip():
        raise AdmissionError("explicit mandate requires non-empty authority_id")
    policy = canonicalize_policy(raw_policy)
    gate = evaluate_gate(policy, trigger)
    if gate.strength != "explicit":
        raise AdmissionError(
            f"direct explicit accept refused: gate yielded '{gate.strength}' ({gate.reason})"
        )
    if (
        gate.requester_is_bot
        or trigger.source_kind == "github_default_branch_ci"
        or _normalize_actor(trigger.actor) in policy["automated_reviewers_non_bot"]
    ):
        raise AdmissionError("bots, CI, and automated reviewers cannot hold explicit mandates")
    if not writable_scope:
        raise AdmissionError("explicit mandate requires non-empty writable_scope")
    clean_scope = sorted({_validate_safe_scope_pattern(s) for s in writable_scope})

    mandate = {
        "contract_version": "1.0",
        "mandate_id": mandate_id.strip(),
        "authority_id": authority_id.strip(),
        "origin_thread_id": trigger.thread_id,
        "source_kind": trigger.source_kind,
        "receiving_scope": trigger.receiving_scope,
        "requester_actor": _normalize_actor(trigger.actor),
        "requester_is_bot": False,
        "strength": "explicit",
        "policy_version": gate.policy_version,
        "matched_rules": [],
        "writable_scope": clean_scope,
        "status": "active",
    }
    return DecisionRecord(
        trigger_id=trigger.trigger_id,
        thread_id=trigger.thread_id,
        decision="accept",
        strength="explicit",
        accept_mode=gate.accept_mode,
        policy_version=gate.policy_version,
        would_accept=True,
        ignored_from_card=False,
        matched_rules=(),
        reason=gate.reason,
        recorded_at=recorded_at or _utc_now_z(),
        mandate=mandate,
    )


def evaluate_proactive_candidate(
    raw_policy: dict[str, Any],
    trigger: AdmissionTrigger,
    assessment: ProactiveAssessment | IgnoredFromCard | AssessmentUnavailable,
    *,
    mandate_id_prefix: str = "mnd-auto",
    authority_id: str = "auth-proactive-auto",
    recorded_at: str | None = None,
) -> DecisionRecord:
    """Evaluate an inferred/proactive candidate under `off | observe | auto` rules cleanly."""
    policy = canonicalize_policy(raw_policy)
    gate = evaluate_gate(policy, trigger)
    ts = recorded_at or _utc_now_z()

    if gate.strength == "explicit":
        raise AdmissionError(
            "explicit trigger grants direct explicit authority; use build_explicit_mandate instead of evaluate_proactive_candidate"
        )

    if gate.strength == "not_admitted":
        return DecisionRecord(
            trigger_id=trigger.trigger_id,
            thread_id=trigger.thread_id,
            decision="ignore",
            strength="not_admitted",
            accept_mode=gate.accept_mode,
            policy_version=gate.policy_version,
            would_accept=False,
            ignored_from_card=False,
            matched_rules=(),
            reason=gate.reason,
            recorded_at=ts,
        )

    if isinstance(assessment, AssessmentUnavailable):
        return DecisionRecord(
            trigger_id=trigger.trigger_id,
            thread_id=trigger.thread_id,
            decision="unavailable",
            strength=gate.strength,
            accept_mode=gate.accept_mode,
            policy_version=gate.policy_version,
            would_accept=False,
            ignored_from_card=False,
            matched_rules=(),
            reason=assessment.reason,
            recorded_at=ts,
            error_kind=assessment.error_kind,
        )

    if isinstance(assessment, IgnoredFromCard):
        return DecisionRecord(
            trigger_id=trigger.trigger_id,
            thread_id=trigger.thread_id,
            decision="ignore",
            strength=gate.strength,
            accept_mode=gate.accept_mode,
            policy_version=gate.policy_version,
            would_accept=False,
            ignored_from_card=True,
            matched_rules=(),
            reason=assessment.reason,
            recorded_at=ts,
        )

    # ProactiveAssessment contract checks
    if assessment.policy_version != gate.policy_version:
        return DecisionRecord(
            trigger_id=trigger.trigger_id,
            thread_id=trigger.thread_id,
            decision="unavailable",
            strength=gate.strength,
            accept_mode=gate.accept_mode,
            policy_version=gate.policy_version,
            would_accept=False,
            ignored_from_card=False,
            matched_rules=(),
            reason=(
                f"stale assessment policy_version '{assessment.policy_version}' != current "
                f"'{gate.policy_version}'; requeue under current version"
            ),
            recorded_at=ts,
            error_kind="stale_policy",
        )

    enabled_rules = {r["rule_id"]: r for r in policy["proactive_rules"] if r["enabled"]}
    assessed_ids = [entry.rule_id for entry in assessment.rule_assessments]
    if len(assessed_ids) != len(set(assessed_ids)):
        raise AdmissionError("rule_assessments must not contain duplicate rule_id entries")
    assessed_set = set(assessed_ids)
    enabled_set = set(enabled_rules.keys())
    if assessed_set != enabled_set:
        missing = sorted(enabled_set - assessed_set)
        extra = sorted(assessed_set - enabled_set)
        raise AdmissionError(
            f"rule_assessments must match all enabled rules exactly once (missing={missing}, extra={extra})"
        )

    if assessment.direction.target_basis not in VALID_TARGET_BASES:
        raise AdmissionError(f"invalid direction.target_basis: {assessment.direction.target_basis!r}")

    for entry in assessment.rule_assessments:
        if not entry.reason.strip():
            raise AdmissionError(f"rule_assessment for '{entry.rule_id}' must provide a factual reason")

    matched_entries = [entry for entry in assessment.rule_assessments if entry.matched]
    matched_ids = tuple(entry.rule_id for entry in matched_entries)
    serialized_assessments = tuple(asdict(entry) for entry in assessment.rule_assessments)

    if not matched_entries:
        return DecisionRecord(
            trigger_id=trigger.trigger_id,
            thread_id=trigger.thread_id,
            decision="ignore",
            strength=gate.strength,
            accept_mode=gate.accept_mode,
            policy_version=gate.policy_version,
            would_accept=False,
            ignored_from_card=False,
            matched_rules=(),
            reason="assessment evaluated all enabled rules with zero matches",
            recorded_at=ts,
            rule_assessments=serialized_assessments,
        )

    direction = assessment.direction
    has_valid_evidence = bool(direction.evidence) and all(
        isinstance(ev, str) and bool(ev.strip()) for ev in direction.evidence
    )
    if (
        not direction.implementation_requested
        or direction.target_basis not in ("specified", "existing_standard")
        or direction.requires_design_decision
        or not has_valid_evidence
    ):
        return DecisionRecord(
            trigger_id=trigger.trigger_id,
            thread_id=trigger.thread_id,
            decision="ignore",
            strength=gate.strength,
            accept_mode=gate.accept_mode,
            policy_version=gate.policy_version,
            would_accept=False,
            ignored_from_card=False,
            matched_rules=(),
            reason=(
                "matched rules rejected by direction contract "
                "(requires settled target, implementation_requested=true, non-empty evidence, and no design decision)"
            ),
            recorded_at=ts,
            rule_assessments=serialized_assessments,
        )

    matched_rule_objs = [enabled_rules[rid] for rid in matched_ids]
    out_of_surface = [
        r["rule_id"] for r in matched_rule_objs if trigger.receiving_scope not in r["receiving_scopes"]
    ]
    if out_of_surface:
        return DecisionRecord(
            trigger_id=trigger.trigger_id,
            thread_id=trigger.thread_id,
            decision="ignore",
            strength=gate.strength,
            accept_mode=gate.accept_mode,
            policy_version=gate.policy_version,
            would_accept=False,
            ignored_from_card=False,
            matched_rules=(),
            reason=(
                f"matched rule(s) {out_of_surface} are not enabled for receiving_scope "
                f"'{trigger.receiving_scope}'"
            ),
            recorded_at=ts,
            rule_assessments=serialized_assessments,
        )
    bounded_scope = _intersect_rule_scopes(matched_rule_objs)
    if not bounded_scope:
        return DecisionRecord(
            trigger_id=trigger.trigger_id,
            thread_id=trigger.thread_id,
            decision="ignore",
            strength=gate.strength,
            accept_mode=gate.accept_mode,
            policy_version=gate.policy_version,
            would_accept=False,
            ignored_from_card=False,
            matched_rules=(),
            reason=(
                f"conflicting or disjoint rule scopes across {list(matched_ids)}; ignored to avoid scope expansion"
            ),
            recorded_at=ts,
            rule_assessments=serialized_assessments,
        )

    if assessment.proposed_writable_scope:
        for req_path in assessment.proposed_writable_scope:
            if not is_path_within_scope(req_path, bounded_scope):
                return DecisionRecord(
                    trigger_id=trigger.trigger_id,
                    thread_id=trigger.thread_id,
                    decision="ignore",
                    strength=gate.strength,
                    accept_mode=gate.accept_mode,
                    policy_version=gate.policy_version,
                    would_accept=False,
                    ignored_from_card=False,
                    matched_rules=(),
                    reason=f"proposed scope '{req_path}' exceeds matched rule writable_scope {bounded_scope}",
                    recorded_at=ts,
                    rule_assessments=serialized_assessments,
                )
        final_scope = sorted({_validate_safe_scope_pattern(s) for s in assessment.proposed_writable_scope})
    else:
        final_scope = bounded_scope

    # Core Observe Mode Gate (Mechanism 2): never mutate or mint a Mandate in observe mode!
    if gate.accept_mode == "observe":
        return DecisionRecord(
            trigger_id=trigger.trigger_id,
            thread_id=trigger.thread_id,
            decision="ignore",
            strength=gate.strength,
            accept_mode="observe",
            policy_version=gate.policy_version,
            would_accept=True,
            ignored_from_card=False,
            matched_rules=matched_ids,
            reason=f"observe mode: would accept under rules {list(matched_ids)} (no mutation dispatched)",
            recorded_at=ts,
            mandate=None,
            rule_assessments=serialized_assessments,
        )

    if not isinstance(mandate_id_prefix, str) or not mandate_id_prefix.strip():
        raise AdmissionError("evaluate_proactive_candidate requires non-empty mandate_id_prefix")
    if not isinstance(authority_id, str) or not authority_id.strip():
        raise AdmissionError("evaluate_proactive_candidate requires non-empty authority_id")

    # accept_mode == "auto": mint immutable inferred Mandate bounded to rule writable_scope
    mandate = {
        "contract_version": "1.0",
        "mandate_id": f"{mandate_id_prefix.strip()}-{trigger.trigger_id}",
        "authority_id": authority_id.strip(),
        "origin_thread_id": trigger.thread_id,
        "source_kind": trigger.source_kind,
        "receiving_scope": trigger.receiving_scope,
        "requester_actor": _normalize_actor(trigger.actor) or "github-ci",
        "requester_is_bot": gate.requester_is_bot,
        "strength": "inferred",
        "policy_version": gate.policy_version,
        "matched_rules": list(matched_ids),
        "writable_scope": final_scope,
        "status": "active",
    }
    return DecisionRecord(
        trigger_id=trigger.trigger_id,
        thread_id=trigger.thread_id,
        decision="accept",
        strength="inferred",
        accept_mode="auto",
        policy_version=gate.policy_version,
        would_accept=True,
        ignored_from_card=False,
        matched_rules=matched_ids,
        reason=f"auto mode accepted rules {list(matched_ids)} with immutable inferred mandate",
        recorded_at=ts,
        mandate=mandate,
        rule_assessments=serialized_assessments,
    )


def append_decision_ledger(ledger_path: Path | str, record: DecisionRecord) -> None:
    p = Path(ledger_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), sort_keys=True, ensure_ascii=False) + "\n")


def load_decision_ledger(ledger_path: Path | str) -> list[dict[str, Any]]:
    p = Path(ledger_path)
    if not p.is_file():
        return []
    entries: list[dict[str, Any]] = []
    for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise AdmissionError(f"corrupt JSONL in {p} line {lineno}: {exc}") from exc
        if not isinstance(obj, dict):
            raise AdmissionError(f"ledger entry line {lineno} must be a JSON object")
        entries.append(obj)
    return entries


def summarize_ledger(ledger_path: Path | str) -> dict[str, Any]:
    entries = load_decision_ledger(ledger_path)
    counts = {"accept": 0, "stop": 0, "ignore": 0, "unavailable": 0}
    would_accept_observe = 0
    per_rule_hits: dict[str, int] = {}
    policy_versions: list[str] = []

    for item in entries:
        dec = item.get("decision", "ignore")
        if dec in counts:
            counts[dec] += 1
        if (
            item.get("accept_mode") == "observe"
            and item.get("decision") == "ignore"
            and item.get("strength") == "inferred"
            and item.get("would_accept")
        ):
            would_accept_observe += 1
        if item.get("would_accept"):
            for rid in item.get("matched_rules") or []:
                per_rule_hits[rid] = per_rule_hits.get(rid, 0) + 1
        pver = item.get("policy_version")
        if pver and pver not in policy_versions:
            policy_versions.append(pver)

    return {
        "total_records": len(entries),
        "decision_counts": counts,
        "would_accept_in_observe_count": would_accept_observe,
        "per_rule_would_accept_hits": per_rule_hits,
        "policy_versions": policy_versions,
    }


def _build_all_rule_assessment(
    policy: dict[str, Any],
    pver: str,
    *,
    matched_rule_id: str | None,
    match_reason: str,
    evidence: tuple[str, ...],
    proposed_writable_scope: tuple[str, ...] = (),
) -> ProactiveAssessment:
    enabled = [r for r in policy["proactive_rules"] if r["enabled"]]
    entries = []
    for rule in enabled:
        rid = rule["rule_id"]
        if rid == matched_rule_id:
            entries.append(RuleAssessmentEntry(rule_id=rid, matched=True, reason=match_reason))
        else:
            entries.append(
                RuleAssessmentEntry(
                    rule_id=rid,
                    matched=False,
                    reason=f"Rule '{rid}' does not match this evaluated signal",
                )
            )

    direction = DirectionDeclaration(
        implementation_requested=matched_rule_id is not None,
        target_basis="existing_standard" if matched_rule_id is not None else "not_applicable",
        requires_design_decision=False,
        evidence=evidence,
    )
    return ProactiveAssessment(
        policy_version=pver,
        direction=direction,
        rule_assessments=tuple(entries),
        proposed_writable_scope=proposed_writable_scope,
        summary=match_reason,
    )


def _check_vault_manifests(repo_root: Path) -> tuple[bool, str, list[str]]:
    """Read-only verification of workflows/vault_manifests/*.manifest.json via storage.vault."""
    from ..storage.vault import VaultError, load_manifest, verify_archive_checksum

    manifests_dir = repo_root / "workflows" / "vault_manifests"
    if not manifests_dir.is_dir():
        return False, "workflows/vault_manifests directory does not exist", []

    manifest_files = sorted(manifests_dir.glob("*.manifest.json"))
    problems: list[str] = []

    for mf in manifest_files:
        rel = mf.relative_to(repo_root).as_posix()
        try:
            data = load_manifest(mf)
        except VaultError as exc:
            problems.append(f"{rel}: {exc}")
            continue
        archive_sha = str(data.get("archive_sha256", ""))
        if not _SAFE_HEX64_RE.match(archive_sha):
            problems.append(f"{rel}: invalid archive_sha256 format")
            continue
        cache_archive = repo_root / ".vault_cache" / str(data["archive_name"])
        if cache_archive.is_file():
            try:
                verify_archive_checksum(cache_archive, data)
            except VaultError as exc:
                problems.append(f"{rel}: {exc}")

    if problems:
        return True, f"Detected {len(problems)} vault manifest drift/integrity issue(s)", problems
    return False, f"Verified {len(manifest_files)} vault manifest(s) cleanly with zero drift", []


def _safe_int(val: Any) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return -1


def evaluate_github_observe_snapshot(
    raw_policy: dict[str, Any],
    *,
    repo_root: Path,
    ci_runs_main: list[dict[str, Any]] | None = None,
    ci_fetch_error: str | None = None,
    raw_prs: list[dict[str, Any]] | None = None,
    pr_fetch_error: str | None = None,
    recorded_at: str | None = None,
) -> list[DecisionRecord]:
    """Evaluate the 3 seeded Alpha_mining proactive rules purely in read-only mode."""
    policy = canonicalize_policy(raw_policy)
    pver = compute_policy_version(policy)
    ts = recorded_at or _utc_now_z()
    enabled_ids = {r["rule_id"] for r in policy["proactive_rules"] if r["enabled"]}
    records: list[DecisionRecord] = []

    # 1. ci-default-branch-failure (evaluates latest completed CI run on main)
    if "ci-default-branch-failure" in enabled_ids:
        ci_trigger = AdmissionTrigger(
            trigger_id="obs-ci-main",
            source_kind="github_default_branch_ci",
            receiving_scope="github_default_branch_ci",
            thread_id="branch:main",
            actor="github-ci",
            actor_is_bot=False,
            addressed="none",
        )
        if ci_fetch_error:
            records.append(
                evaluate_proactive_candidate(
                    policy,
                    ci_trigger,
                    AssessmentUnavailable(error_kind="tool_error", reason=ci_fetch_error),
                    recorded_at=ts,
                )
            )
        else:
            runs = ci_runs_main or []
            completed_runs_indexed = [
                (idx, r)
                for idx, r in enumerate(runs)
                if str(r.get("status") or "").lower() == "completed"
            ]
            completed_runs_indexed.sort(
                key=lambda pair: (
                    str(pair[1].get("createdAt") or ""),
                    _safe_int(
                        pair[1].get("databaseId")
                        if pair[1].get("databaseId") is not None
                        else pair[1].get("id")
                    ),
                    -pair[0],
                ),
                reverse=True,
            )
            completed_runs = [pair[1] for pair in completed_runs_indexed]
            latest = completed_runs[0] if completed_runs else None
            latest_concl = str(latest.get("conclusion") or "").lower() if latest else ""
            if latest and latest_concl in {
                "failure",
                "timed_out",
                "cancelled",
                "action_required",
                "startup_failure",
                "stale",
                "error",
            }:
                run_id = latest.get("databaseId") or latest.get("id") or "unknown"
                assessment = _build_all_rule_assessment(
                    policy,
                    pver,
                    matched_rule_id="ci-default-branch-failure",
                    match_reason=f"Latest completed main CI run {run_id} ended with conclusion={latest_concl}",
                    evidence=(f"main workflow run {run_id} conclusion={latest_concl}",),
                    proposed_writable_scope=("workflows/runs/",),
                )
            else:
                assessment = _build_all_rule_assessment(
                    policy,
                    pver,
                    matched_rule_id=None,
                    match_reason=f"Checked {len(completed_runs)} completed main CI run(s); latest is non-failing",
                    evidence=(f"checked {len(completed_runs)} completed workflow runs on main",),
                )
            records.append(evaluate_proactive_candidate(policy, ci_trigger, assessment, recorded_at=ts))

    # 2. parallel-pr-semantic-conflict
    if "parallel-pr-semantic-conflict" in enabled_ids:
        pr_trigger = AdmissionTrigger(
            trigger_id="obs-pr-audit",
            source_kind="github_pr",
            receiving_scope="github_pr",
            thread_id="repo:open-prs",
            actor="github-actions[bot]",
            actor_is_bot=True,
            addressed="none",
        )
        if pr_fetch_error:
            records.append(
                evaluate_proactive_candidate(
                    policy,
                    pr_trigger,
                    AssessmentUnavailable(error_kind="tool_error", reason=pr_fetch_error),
                    recorded_at=ts,
                )
            )
        else:
            snapshots = parse_pr_snapshots(raw_prs or [])
            audit_results = audit_pull_requests(snapshots, require_agent_ack=True)
            semantic_codes = {
                "DIRECT_FILE_OVERLAP",
                "SIBLING_NAMESPACE_COLLISION",
                "PARALLEL_SAME_BASE_CONTRACT_DIVERGENCE",
                "STALE_STACKED_BASE",
                "PARALLEL_SAME_BASE",
            }
            flagged = [
                f"PR #{r.pr.number}:{f.code}"
                for r in audit_results
                for f in r.findings
                if f.code in semantic_codes
            ]
            if flagged:
                assessment = _build_all_rule_assessment(
                    policy,
                    pver,
                    matched_rule_id="parallel-pr-semantic-conflict",
                    match_reason=f"Detected semantic/base conflict across open PRs: {', '.join(flagged[:4])}",
                    evidence=tuple(flagged[:4]),
                    proposed_writable_scope=("workflows/runs/",),
                )
            else:
                assessment = _build_all_rule_assessment(
                    policy,
                    pver,
                    matched_rule_id=None,
                    match_reason=f"Audited {len(audit_results)} open PR(s); zero semantic collisions detected",
                    evidence=(f"pr_audit clean across {len(audit_results)} open PRs",),
                )
            records.append(evaluate_proactive_candidate(policy, pr_trigger, assessment, recorded_at=ts))

    # 3. quant-manifest-drift-check
    if "quant-manifest-drift-check" in enabled_ids:
        vault_trigger = AdmissionTrigger(
            trigger_id="obs-vault-drift",
            source_kind="github_default_branch_ci",
            receiving_scope="github_default_branch_ci",
            thread_id="vault:manifests",
            actor="github-ci",
            actor_is_bot=False,
            addressed="none",
        )
        has_drift, summary_msg, problems = _check_vault_manifests(repo_root)
        if has_drift:
            assessment = _build_all_rule_assessment(
                policy,
                pver,
                matched_rule_id="quant-manifest-drift-check",
                match_reason=summary_msg,
                evidence=tuple(problems[:4]),
                proposed_writable_scope=("workflows/vault_manifests/",),
            )
        else:
            assessment = _build_all_rule_assessment(
                policy,
                pver,
                matched_rule_id=None,
                match_reason=summary_msg,
                evidence=(summary_msg,),
            )
        records.append(evaluate_proactive_candidate(policy, vault_trigger, assessment, recorded_at=ts))

    return records


def _default_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def run_live_github_observe(
    raw_policy: dict[str, Any],
    *,
    repo: str,
    repo_root: Path,
    default_branch: str = "main",
    runner: CommandRunner = _default_runner,
) -> list[DecisionRecord]:
    """Fetch read-only main CI status + open PR audit inputs via gh and run observe evaluation."""
    ci_runs: list[dict[str, Any]] | None = None
    ci_err: str | None = None
    ci_proc = runner(
        [
            "gh",
            "run",
            "list",
            "-R",
            repo,
            "--branch",
            default_branch,
            "--workflow",
            "CI",
            "--limit",
            "5",
            "--json",
            "databaseId,conclusion,status,headSha,createdAt",
        ]
    )
    if ci_proc.returncode != 0:
        ci_err = f"gh run list failed: {ci_proc.stderr.strip() or ci_proc.stdout.strip()}"
    else:
        try:
            parsed = json.loads(ci_proc.stdout)
            if not isinstance(parsed, list):
                ci_err = "gh run list returned non-list JSON"
            else:
                ci_runs = parsed
        except json.JSONDecodeError as exc:
            ci_err = f"gh run list invalid JSON: {exc}"

    raw_prs: list[dict[str, Any]] | None = None
    pr_err: str | None = None
    try:
        snaps = fetch_open_prs(repo, runner=runner)
        # Re-encode parsed snapshots cleanly back to raw dict view for evaluate_github_observe_snapshot
        raw_prs = [
            {
                "number": s.number,
                "title": s.title,
                "author": {"login": s.author},
                "baseRefName": s.base_ref_name,
                "headRefName": s.head_ref_name,
                "baseRefOid": s.base_ref_oid,
                "headRefOid": s.head_ref_oid,
                "isDraft": s.is_draft,
                "state": s.state,
                "mergeable": s.mergeable,
                "mergeStateStatus": s.merge_state_status,
                "body": s.body,
                "comments": [{"author": {"login": c.author}, "body": c.body} for c in s.comments],
                "files": [{"path": f} for f in s.files],
                "statusCheckRollup": s.checks_summary,
                "review_count": s.review_count,
                "unresolved_threads": s.unresolved_threads,
                "isCrossRepository": s.is_cross_repository,
                "url": s.url,
            }
            for s in snaps
        ]
    except Exception as exc:  # noqa: BLE001
        pr_err = str(exc)

    return evaluate_github_observe_snapshot(
        raw_policy,
        repo_root=repo_root,
        ci_runs_main=ci_runs,
        ci_fetch_error=ci_err,
        raw_prs=raw_prs,
        pr_fetch_error=pr_err,
    )


def render_observe_report_markdown(
    records: list[DecisionRecord],
    *,
    policy: dict[str, Any],
    policy_version: str,
) -> str:
    mode = policy.get("accept_mode", "observe")
    lines = [
        "## Admission Gate Observe Report",
        "",
        f"- **accept_mode**: `{mode}`",
        f"- **policy_version**: `{policy_version}`",
        "",
        "| Trigger | Thread | Decision | would_accept | Matched Rules | Summary / Reason |",
        "|---|---|---|---|---|---|",
    ]
    for rec in records:
        rules_str = ", ".join(rec.matched_rules) if rec.matched_rules else "-"
        reason = rec.reason.replace("|", "\\|").replace("\r", " ").replace("\n", " ").strip()
        lines.append(
            f"| `{rec.trigger_id}` | `{rec.thread_id}` | **{rec.decision}** | `{str(rec.would_accept).lower()}` | `{rules_str}` | {reason} |"
        )
    lines.append("")
    return "\n".join(lines)
