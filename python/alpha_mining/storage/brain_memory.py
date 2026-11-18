"""Structured Daily Brain Memory Ledger with anti-leakage, secret sanitization, and Drive Vault snapshots."""

from __future__ import annotations

import fcntl
import json
import math
import os
import re
import tempfile
from collections import Counter
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from .vault import (
    Codec,
    CommandRunner,
    _default_runner,
    default_vault_config_path,
    pack_artifact,
)

EpisodeKind = Literal["trading_lesson", "governance_decision", "quant_hypothesis", "system_error"]
EpisodeSource = Literal["owner_teaching", "owner_feedback", "control_plane", "backtest_run"]
ParseStatus = Literal["validated", "rejected", "needs_clarification"]
OutcomeStatus = Literal["pending", "resolved", "void"]

EPISODE_KINDS = frozenset({"trading_lesson", "governance_decision", "quant_hypothesis", "system_error"})
EPISODE_SOURCES = frozenset({"owner_teaching", "owner_feedback", "control_plane", "backtest_run"})
PARSE_STATUSES = frozenset({"validated", "rejected", "needs_clarification"})
OUTCOME_STATUSES = frozenset({"pending", "resolved", "void"})

EPISODE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SESSION_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
UTC_Z_RE = re.compile(r"^([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(?:\.([0-9]{1,9}))?Z$")

FORBIDDEN_INTENT_KEYS = frozenset(
    {
        "submit_order",
        "execute_order",
        "place_order",
        "send_order",
        "cancel_order",
        "modify_order",
        "open_position",
        "close_position",
        "override_risk",
        "bypass_risk",
        "broker_api",
        "live_account",
    }
)

_SENSITIVE_KEY_EXACT = frozenset(
    {
        "token",
        "secret",
        "password",
        "passwd",
        "passphrase",
        "private_key",
        "api_key",
        "apikey",
        "secret_key",
        "access_key",
        "signing_key",
        "client_secret",
        "api_secret",
        "refresh_token",
        "access_token",
        "id_token",
        "authorization",
        "credentials",
        "credential",
    }
)

_SENSITIVE_KEY_SUFFIXES = (
    "_token",
    "_secret",
    "_secret_key",
    "_private_key",
    "_api_key",
    "_apikey",
    "_access_key",
    "_signing_key",
    "_password",
    "_passwd",
    "_passphrase",
    "_credential",
    "_credentials",
)

_SENSITIVE_KEY_SUBSTRING_RE = re.compile(
    r"(?:^|[^a-z0-9])(?:client_secret|refresh_token|access_token|id_token|oauth_token|github_token|"
    r"api_secret|secret_key|private_key|api_key|apikey|password|passwd|passphrase)(?:$|[^a-z0-9])"
)

SECRET_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----", re.IGNORECASE),
    re.compile(r"\bLS0tLS1CRUdJTi[A-Za-z0-9+/=]{4,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{16,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z\-_]{20,}\b"),
    re.compile(r"\bya29\.[A-Za-z0-9\-_]{10,}\b"),
    re.compile(r"\bGOCSPX-[A-Za-z0-9\-_]{12,}\b"),
    re.compile(r"(?<![A-Za-z0-9])1//0[A-Za-z0-9\-_]{6,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]{8,}=*", re.IGNORECASE),
    re.compile(r"\beyJ[A-Za-z0-9\-_]{5,}\.[A-Za-z0-9\-_]{5,}\.[A-Za-z0-9\-_]{5,}\b"),
    re.compile(r"\[[A-Za-z0-9._-]+\][\s\S]{0,200}?\btype\s*=\s*drive\b", re.IGNORECASE),
    re.compile(
        r"\b(?:refresh_token|access_token|id_token|client_secret|private_key|api_secret|secret_key|"
        r"api_key|apikey|password|passwd|passphrase|github_token|rclone_config_gdrive|token)"
        r"['\"]?\s*[:=]\s*['\"]?(?!\{)[^\s'\"]{8,}",
        re.IGNORECASE,
    ),
)

_TRANSLATION_KEYS = frozenset({"translator_role", "structured_intent", "parse_status", "human_confirmed"})
_DECISION_CONTEXT_KEYS = frozenset(
    {
        "observed_at_utc",
        "features_at_decision",
        "available_actions",
        "chosen_action",
        "decision_engine",
        "risk_gate_passed",
    }
)
_OUTCOME_ALLOWED_KEYS = frozenset(
    {
        "status",
        "outcome_at_utc",
        "net_return_r",
        "cost_r",
        "mae_r",
        "error_or_lesson_tag",
        "owner_feedback",
    }
)
_OUTCOME_REQUIRED_KEYS = frozenset({"status"})
_EPISODE_KEYS = frozenset(
    {
        "schema_version",
        "episode_id",
        "session_date",
        "episode_kind",
        "source",
        "natural_language_input",
        "llm_translation",
        "decision_context",
        "outcome",
    }
)


class BrainMemoryError(ValueError):
    """Raised on Brain Memory schema, temporal invariance, or secret-hygiene violations."""


def validate_episode_id(episode_id: str) -> str:
    if not isinstance(episode_id, str) or not EPISODE_ID_RE.fullmatch(episode_id):
        raise BrainMemoryError(
            f"invalid episode_id {episode_id!r}: must match ^[A-Za-z0-9][A-Za-z0-9._-]{{0,127}}$"
        )
    _check_string_no_secret(episode_id, "episode_id")
    return episode_id


def parse_session_date(session_date: str) -> date:
    if not isinstance(session_date, str) or not SESSION_DATE_RE.fullmatch(session_date):
        raise BrainMemoryError(f"invalid session_date {session_date!r}: expected YYYY-MM-DD")
    try:
        return date.fromisoformat(session_date)
    except ValueError as exc:
        raise BrainMemoryError(f"invalid calendar session_date {session_date!r}: {exc}") from exc


def parse_utc_z_ns(ts: str, field_name: str = "timestamp") -> tuple[datetime, int]:
    if not isinstance(ts, str):
        raise BrainMemoryError(f"invalid {field_name} {ts!r}: expected UTC ISO-8601 ending in 'Z'")
    match = UTC_Z_RE.fullmatch(ts)
    if not match:
        raise BrainMemoryError(f"invalid {field_name} {ts!r}: expected UTC ISO-8601 ending in 'Z'")
    try:
        sec_dt = datetime.fromisoformat(match.group(1) + "+00:00")
    except ValueError as exc:
        raise BrainMemoryError(f"invalid {field_name} {ts!r}: {exc}") from exc
    ns = int((match.group(2) or "").ljust(9, "0"))
    return sec_dt, ns


def parse_utc_z(ts: str, field_name: str = "timestamp") -> datetime:
    sec_dt, _ = parse_utc_z_ns(ts, field_name)
    return sec_dt


def _check_finite_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BrainMemoryError(f"{field_name} must be a finite number, got {type(value).__name__}")
    num = float(value)
    if not math.isfinite(num):
        raise BrainMemoryError(f"{field_name} must be finite (NaN/Inf rejected)")
    return num


def _check_string_no_secret(text: str, path: str) -> None:
    for pattern in SECRET_VALUE_PATTERNS:
        if pattern.search(text):
            raise BrainMemoryError(f"potential secret detected in {path}; redact credentials before storing")


def _is_sensitive_key(raw_key: str) -> bool:
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", raw_key.strip()).lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    if normalized in _SENSITIVE_KEY_EXACT:
        return True
    if normalized.endswith(_SENSITIVE_KEY_SUFFIXES):
        return True
    return bool(_SENSITIVE_KEY_SUBSTRING_RE.search(normalized))


def _contains_nonempty_payload(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple)):
        return any(_contains_nonempty_payload(item) for item in value)
    if isinstance(value, Mapping):
        for k, v in value.items():
            if isinstance(k, str) and k.strip():
                return True
            if _contains_nonempty_payload(v):
                return True
        return False
    return True


def _validate_json_tree(
    value: Any,
    path: str,
    *,
    forbidden_keys: frozenset[str] = frozenset(),
) -> None:
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise BrainMemoryError(f"non-finite float (NaN/Inf) disallowed in {path}")
        return
    if isinstance(value, str):
        _check_string_no_secret(value, path)
        return
    if isinstance(value, (list, tuple)):
        for idx, item in enumerate(value):
            _validate_json_tree(item, f"{path}[{idx}]", forbidden_keys=forbidden_keys)
        return
    if isinstance(value, Mapping):
        for raw_key, item in value.items():
            if not isinstance(raw_key, str) or not raw_key:
                raise BrainMemoryError(f"all dict keys in {path} must be non-empty strings")
            _check_string_no_secret(raw_key, f"{path}.<key:{raw_key}>")
            key_lower = raw_key.lower()
            if key_lower in forbidden_keys:
                raise BrainMemoryError(
                    f"forbidden execution/bypass key {raw_key!r} disallowed inside {path}"
                )
            if _is_sensitive_key(raw_key) and _contains_nonempty_payload(item):
                raise BrainMemoryError(
                    f"sensitive credential key {raw_key!r} with non-empty value disallowed in {path}"
                )
            _validate_json_tree(item, f"{path}.{raw_key}", forbidden_keys=forbidden_keys)
        return
    raise BrainMemoryError(f"unsupported non-JSON type {type(value).__name__} in {path}")


def _freeze_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json_value(item) for item in value)
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze_json_value(v) for k, v in value.items()})
    raise BrainMemoryError(f"unsupported non-JSON type {type(value).__name__} during freeze")


def _unfreeze_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_unfreeze_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(k): _unfreeze_json_value(v) for k, v in value.items()}
    raise BrainMemoryError(f"unsupported non-JSON type {type(value).__name__} during serialization")


def _validate_dict_keys(
    data: dict[str, Any],
    *,
    object_name: str,
    required: frozenset[str],
    allowed: frozenset[str],
) -> None:
    keys = set(data.keys())
    unknown = keys - allowed
    if unknown:
        raise BrainMemoryError(f"unexpected field(s) in {object_name}: {sorted(unknown)}")
    missing = required - keys
    if missing:
        raise BrainMemoryError(f"missing required field(s) in {object_name}: {sorted(missing)}")


@dataclass(frozen=True)
class TranslationEnvelope:
    """Strictly constrains LLM involvement to NL <-> JSON translation with no execution power."""

    translator_role: Literal["nl_to_json_only"]
    structured_intent: Mapping[str, Any]
    parse_status: ParseStatus
    human_confirmed: bool

    def __post_init__(self) -> None:
        if self.translator_role != "nl_to_json_only":
            raise BrainMemoryError(
                f"translator_role must be 'nl_to_json_only', got {self.translator_role!r}"
            )
        if self.parse_status not in PARSE_STATUSES:
            raise BrainMemoryError(f"invalid parse_status {self.parse_status!r}")
        if not isinstance(self.human_confirmed, bool):
            raise BrainMemoryError("human_confirmed must be a boolean")
        if not isinstance(self.structured_intent, Mapping):
            raise BrainMemoryError("structured_intent must be a JSON object mapping")
        _validate_json_tree(
            self.structured_intent,
            "llm_translation.structured_intent",
            forbidden_keys=FORBIDDEN_INTENT_KEYS,
        )
        object.__setattr__(self, "structured_intent", _freeze_json_value(self.structured_intent))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TranslationEnvelope:
        if not isinstance(data, dict):
            raise BrainMemoryError("llm_translation must be a JSON object")
        _validate_json_tree(data, "llm_translation")
        _validate_dict_keys(
            data,
            object_name="llm_translation",
            required=_TRANSLATION_KEYS,
            allowed=_TRANSLATION_KEYS,
        )
        return cls(
            translator_role=data["translator_role"],
            structured_intent=data["structured_intent"],
            parse_status=data["parse_status"],
            human_confirmed=data["human_confirmed"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "translator_role": self.translator_role,
            "structured_intent": _unfreeze_json_value(self.structured_intent),
            "parse_status": self.parse_status,
            "human_confirmed": self.human_confirmed,
        }


@dataclass(frozen=True)
class DecisionContext:
    """Point-in-time decision snapshot recorded prior to outcome realization."""

    observed_at_utc: str
    features_at_decision: Mapping[str, Any]
    available_actions: tuple[str, ...]
    chosen_action: str
    decision_engine: str
    risk_gate_passed: bool

    def __post_init__(self) -> None:
        parse_utc_z_ns(self.observed_at_utc, "decision_context.observed_at_utc")
        if not isinstance(self.features_at_decision, Mapping):
            raise BrainMemoryError("features_at_decision must be a JSON object mapping")
        _validate_json_tree(self.features_at_decision, "decision_context.features_at_decision")
        object.__setattr__(self, "features_at_decision", _freeze_json_value(self.features_at_decision))

        if isinstance(self.available_actions, list):
            object.__setattr__(self, "available_actions", tuple(self.available_actions))
        if (
            not isinstance(self.available_actions, tuple)
            or not self.available_actions
            or any(not isinstance(a, str) or not a.strip() for a in self.available_actions)
        ):
            raise BrainMemoryError("available_actions must be a non-empty sequence of non-empty strings")
        for idx, action in enumerate(self.available_actions):
            _check_string_no_secret(action, f"decision_context.available_actions[{idx}]")

        if not isinstance(self.chosen_action, str) or not self.chosen_action.strip():
            raise BrainMemoryError("chosen_action must be a non-empty string")
        if self.chosen_action not in self.available_actions:
            raise BrainMemoryError(
                f"chosen_action {self.chosen_action!r} must be one of available_actions {self.available_actions!r}"
            )
        _check_string_no_secret(self.chosen_action, "decision_context.chosen_action")

        if not isinstance(self.decision_engine, str) or not self.decision_engine.strip():
            raise BrainMemoryError("decision_engine must be a non-empty string")
        _check_string_no_secret(self.decision_engine, "decision_context.decision_engine")

        if not isinstance(self.risk_gate_passed, bool):
            raise BrainMemoryError("risk_gate_passed must be a boolean")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DecisionContext:
        if not isinstance(data, dict):
            raise BrainMemoryError("decision_context must be a JSON object")
        _validate_json_tree(data, "decision_context")
        _validate_dict_keys(
            data,
            object_name="decision_context",
            required=_DECISION_CONTEXT_KEYS,
            allowed=_DECISION_CONTEXT_KEYS,
        )
        actions = data["available_actions"]
        if not isinstance(actions, list):
            raise BrainMemoryError("decision_context.available_actions must be a list")
        return cls(
            observed_at_utc=data["observed_at_utc"],
            features_at_decision=data["features_at_decision"],
            available_actions=tuple(actions),
            chosen_action=data["chosen_action"],
            decision_engine=data["decision_engine"],
            risk_gate_passed=data["risk_gate_passed"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "observed_at_utc": self.observed_at_utc,
            "features_at_decision": _unfreeze_json_value(self.features_at_decision),
            "available_actions": list(self.available_actions),
            "chosen_action": self.chosen_action,
            "decision_engine": self.decision_engine,
            "risk_gate_passed": self.risk_gate_passed,
        }


@dataclass(frozen=True)
class EpisodeOutcome:
    """Realized post-decision outcome and Owner lesson label (never backdated prior to observation)."""

    status: OutcomeStatus
    outcome_at_utc: str | None = None
    net_return_r: float | None = None
    cost_r: float | None = None
    mae_r: float | None = None
    error_or_lesson_tag: str = ""
    owner_feedback: str = ""

    def __post_init__(self) -> None:
        if self.status not in OUTCOME_STATUSES:
            raise BrainMemoryError(f"invalid outcome.status {self.status!r}")
        if not isinstance(self.error_or_lesson_tag, str):
            raise BrainMemoryError("outcome.error_or_lesson_tag must be a string")
        if not isinstance(self.owner_feedback, str):
            raise BrainMemoryError("outcome.owner_feedback must be a string")
        _check_string_no_secret(self.error_or_lesson_tag, "outcome.error_or_lesson_tag")
        _check_string_no_secret(self.owner_feedback, "outcome.owner_feedback")

        if self.status in {"pending", "void"}:
            if any(v is not None for v in (self.net_return_r, self.cost_r, self.mae_r)):
                raise BrainMemoryError(
                    f"{self.status} outcome must not carry realized numeric return/cost/mae metrics"
                )
            if self.outcome_at_utc is not None:
                parse_utc_z_ns(self.outcome_at_utc, "outcome.outcome_at_utc")
        else:
            if not self.outcome_at_utc:
                raise BrainMemoryError("resolved outcome requires outcome_at_utc")
            parse_utc_z_ns(self.outcome_at_utc, "outcome.outcome_at_utc")

        if self.net_return_r is not None:
            object.__setattr__(
                self, "net_return_r", _check_finite_number(self.net_return_r, "outcome.net_return_r")
            )
        if self.cost_r is not None:
            cost_val = _check_finite_number(self.cost_r, "outcome.cost_r")
            if cost_val < 0.0:
                raise BrainMemoryError("outcome.cost_r cannot be negative")
            object.__setattr__(self, "cost_r", cost_val)
        if self.mae_r is not None:
            object.__setattr__(self, "mae_r", _check_finite_number(self.mae_r, "outcome.mae_r"))

    def validate_temporal_order(self, observed_at_utc: str) -> None:
        if self.outcome_at_utc is None:
            return
        obs_ts = parse_utc_z_ns(observed_at_utc, "decision_context.observed_at_utc")
        out_ts = parse_utc_z_ns(self.outcome_at_utc, "outcome.outcome_at_utc")
        if out_ts < obs_ts:
            raise BrainMemoryError(
                f"lookahead violation: outcome_at_utc ({self.outcome_at_utc}) precedes observed_at_utc ({observed_at_utc})"
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EpisodeOutcome:
        if not isinstance(data, dict):
            raise BrainMemoryError("outcome must be a JSON object")
        _validate_json_tree(data, "outcome")
        _validate_dict_keys(
            data,
            object_name="outcome",
            required=_OUTCOME_REQUIRED_KEYS,
            allowed=_OUTCOME_ALLOWED_KEYS,
        )
        return cls(
            status=data["status"],
            outcome_at_utc=data.get("outcome_at_utc"),
            net_return_r=data.get("net_return_r"),
            cost_r=data.get("cost_r"),
            mae_r=data.get("mae_r"),
            error_or_lesson_tag=data.get("error_or_lesson_tag", ""),
            owner_feedback=data.get("owner_feedback", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "outcome_at_utc": self.outcome_at_utc,
            "net_return_r": self.net_return_r,
            "cost_r": self.cost_r,
            "mae_r": self.mae_r,
            "error_or_lesson_tag": self.error_or_lesson_tag,
            "owner_feedback": self.owner_feedback,
        }


@dataclass(frozen=True)
class BrainEpisode:
    """Single structured episode stored one-per-line inside workflows/memory/YYYY-MM-DD.jsonl."""

    schema_version: Literal["1.0"]
    episode_id: str
    session_date: str
    episode_kind: EpisodeKind
    source: EpisodeSource
    natural_language_input: str
    llm_translation: TranslationEnvelope
    decision_context: DecisionContext
    outcome: EpisodeOutcome

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if self.schema_version != "1.0":
            raise BrainMemoryError(f"unsupported schema_version {self.schema_version!r}")
        validate_episode_id(self.episode_id)
        parse_session_date(self.session_date)
        if self.episode_kind not in EPISODE_KINDS:
            raise BrainMemoryError(f"invalid episode_kind {self.episode_kind!r}")
        if self.source not in EPISODE_SOURCES:
            raise BrainMemoryError(f"invalid source {self.source!r}")
        if not isinstance(self.natural_language_input, str) or not self.natural_language_input.strip():
            raise BrainMemoryError("natural_language_input must be a non-empty string")
        _check_string_no_secret(self.natural_language_input, "natural_language_input")
        if not isinstance(self.llm_translation, TranslationEnvelope):
            raise BrainMemoryError("llm_translation must be a TranslationEnvelope")
        if not isinstance(self.decision_context, DecisionContext):
            raise BrainMemoryError("decision_context must be a DecisionContext")
        if not isinstance(self.outcome, EpisodeOutcome):
            raise BrainMemoryError("outcome must be an EpisodeOutcome")

        _validate_json_tree(
            self.llm_translation.structured_intent,
            "llm_translation.structured_intent",
            forbidden_keys=FORBIDDEN_INTENT_KEYS,
        )
        _validate_json_tree(self.decision_context.features_at_decision, "decision_context.features_at_decision")
        self.outcome.validate_temporal_order(self.decision_context.observed_at_utc)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrainEpisode:
        if not isinstance(data, dict):
            raise BrainMemoryError("BrainEpisode must be a JSON object")
        _validate_json_tree(data, "BrainEpisode")
        _validate_dict_keys(
            data,
            object_name="BrainEpisode",
            required=_EPISODE_KEYS,
            allowed=_EPISODE_KEYS,
        )
        return cls(
            schema_version=data["schema_version"],
            episode_id=data["episode_id"],
            session_date=data["session_date"],
            episode_kind=data["episode_kind"],
            source=data["source"],
            natural_language_input=data["natural_language_input"],
            llm_translation=TranslationEnvelope.from_dict(data["llm_translation"]),
            decision_context=DecisionContext.from_dict(data["decision_context"]),
            outcome=EpisodeOutcome.from_dict(data["outcome"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "session_date": self.session_date,
            "episode_kind": self.episode_kind,
            "source": self.source,
            "natural_language_input": self.natural_language_input,
            "llm_translation": self.llm_translation.to_dict(),
            "decision_context": self.decision_context.to_dict(),
            "outcome": self.outcome.to_dict(),
        }

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _assert_safe_memory_dir(memory_dir: Path, *, allow_missing: bool) -> Path | None:
    if memory_dir.is_symlink():
        raise BrainMemoryError(f"symlink disallowed for memory_dir: {memory_dir}")
    if not memory_dir.exists():
        if allow_missing:
            return None
        raise BrainMemoryError(f"memory directory not found: {memory_dir}")
    if not memory_dir.is_dir():
        raise BrainMemoryError(f"memory_dir is not a directory: {memory_dir}")
    return memory_dir.resolve()


def _assert_safe_log_file(path: Path, resolved_memory_dir: Path, *, allow_missing: bool) -> bool:
    if path.is_symlink():
        raise BrainMemoryError(f"symlink disallowed in daily memory directory: {path}")
    if not path.exists():
        if allow_missing:
            return False
        raise BrainMemoryError(f"daily memory file not found: {path}")
    if not path.is_file():
        raise BrainMemoryError(f"non-regular file disallowed in daily memory directory: {path}")
    resolved_target = path.resolve()
    if not resolved_target.is_relative_to(resolved_memory_dir):
        raise BrainMemoryError(f"daily memory log escapes memory_dir: {path}")
    return True


@contextmanager
def _memory_lock(memory_dir: Path, *, shared: bool = False, create_dir: bool = True) -> Iterator[None]:
    if memory_dir.is_symlink():
        raise BrainMemoryError(f"symlink disallowed for memory_dir: {memory_dir}")
    if create_dir:
        memory_dir.mkdir(parents=True, exist_ok=True)
    elif not memory_dir.exists():
        yield
        return
    if not memory_dir.is_dir():
        raise BrainMemoryError(f"memory_dir is not a directory: {memory_dir}")

    lock_path = memory_dir / ".brain_memory.lock"
    if lock_path.is_symlink():
        raise BrainMemoryError(f"symlink disallowed for lock file: {lock_path}")
    if not create_dir and not lock_path.exists():
        yield
        return

    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        lock_fh = os.fdopen(fd, "r+", encoding="utf-8")
    except BaseException:
        os.close(fd)
        raise
    mode = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
    with lock_fh:
        fcntl.flock(lock_fh.fileno(), mode)
        try:
            yield
        finally:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)


def daily_log_path(memory_dir: Path, session_date: str) -> Path:
    parse_session_date(session_date)
    return memory_dir / f"{session_date}.jsonl"


def _write_lines_atomic(target: Path, lines: list[str]) -> None:
    if target.parent.is_symlink():
        raise BrainMemoryError(f"symlink disallowed for memory_dir: {target.parent}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise BrainMemoryError(f"symlink disallowed for daily log target: {target}")
    payload = "\n".join(lines) + ("\n" if lines else "")
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.chmod(tmp_path, 0o644)
        os.replace(tmp_path, target)
    except BaseException:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def _read_episodes_unlocked(memory_dir: Path, session_date: str | None = None) -> list[BrainEpisode]:
    resolved_mem_dir = _assert_safe_memory_dir(memory_dir, allow_missing=True)
    if resolved_mem_dir is None:
        return []

    if session_date is not None:
        candidate = daily_log_path(memory_dir, session_date)
        if not _assert_safe_log_file(candidate, resolved_mem_dir, allow_missing=True):
            return []
        paths = [candidate]
    else:
        paths = sorted(memory_dir.glob("*.jsonl"))

    episodes: list[BrainEpisode] = []
    seen_ids: set[str] = set()
    for path in paths:
        _assert_safe_log_file(path, resolved_mem_dir, allow_missing=False)
        if SESSION_DATE_RE.fullmatch(path.stem):
            parse_session_date(path.stem)
        else:
            raise BrainMemoryError(f"unexpected daily log filename {path.name!r}: expected YYYY-MM-DD.jsonl")
        for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = raw.strip()
            if not stripped:
                continue
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise BrainMemoryError(f"{path.name}:{line_no}: invalid JSON: {exc}") from exc
            ep = BrainEpisode.from_dict(parsed)
            if ep.session_date != path.stem:
                raise BrainMemoryError(
                    f"{path.name}:{line_no}: episode session_date {ep.session_date!r} does not match file {path.name!r}"
                )
            if ep.episode_id in seen_ids:
                raise BrainMemoryError(f"{path.name}:{line_no}: duplicate episode_id {ep.episode_id!r}")
            seen_ids.add(ep.episode_id)
            episodes.append(ep)
    return episodes


def load_episodes(memory_dir: Path, session_date: str | None = None) -> list[BrainEpisode]:
    with _memory_lock(memory_dir, shared=True, create_dir=False):
        return _read_episodes_unlocked(memory_dir, session_date)


def append_episode(memory_dir: Path, episode: BrainEpisode) -> Path:
    if not isinstance(episode, BrainEpisode):
        raise BrainMemoryError("episode must be a BrainEpisode instance")
    episode.validate()

    with _memory_lock(memory_dir, shared=False, create_dir=True):
        target = daily_log_path(memory_dir, episode.session_date)
        resolved_mem_dir = _assert_safe_memory_dir(memory_dir, allow_missing=False)
        assert resolved_mem_dir is not None
        _assert_safe_log_file(target, resolved_mem_dir, allow_missing=True)

        all_episodes = _read_episodes_unlocked(memory_dir, session_date=None)
        if any(ep.episode_id == episode.episode_id for ep in all_episodes):
            raise BrainMemoryError(f"duplicate episode_id {episode.episode_id!r} across daily memory logs")
        day_existing = [ep for ep in all_episodes if ep.session_date == episode.session_date]
        updated_lines = [ep.to_json_line() for ep in day_existing] + [episode.to_json_line()]
        _write_lines_atomic(target, updated_lines)
        return target


def resolve_episode_outcome(
    memory_dir: Path,
    session_date: str,
    episode_id: str,
    outcome: EpisodeOutcome,
) -> BrainEpisode:
    validate_episode_id(episode_id)
    parse_session_date(session_date)
    if not isinstance(outcome, EpisodeOutcome):
        raise BrainMemoryError("outcome must be an EpisodeOutcome instance")
    if outcome.status == "pending":
        raise BrainMemoryError("resolve_episode_outcome requires target status 'resolved' or 'void'")

    resolved_mem_dir_pre = _assert_safe_memory_dir(memory_dir, allow_missing=False)
    assert resolved_mem_dir_pre is not None
    pre_target = daily_log_path(memory_dir, session_date)
    _assert_safe_log_file(pre_target, resolved_mem_dir_pre, allow_missing=False)

    with _memory_lock(memory_dir, shared=False, create_dir=False):
        resolved_mem_dir = _assert_safe_memory_dir(memory_dir, allow_missing=False)
        assert resolved_mem_dir is not None
        target = daily_log_path(memory_dir, session_date)
        _assert_safe_log_file(target, resolved_mem_dir, allow_missing=False)

        episodes = _read_episodes_unlocked(memory_dir, session_date)
        updated_list: list[BrainEpisode] = []
        resolved_ep: BrainEpisode | None = None
        for ep in episodes:
            if ep.episode_id != episode_id:
                updated_list.append(ep)
                continue
            if ep.outcome.status != "pending":
                raise BrainMemoryError(
                    f"episode {episode_id!r} is already {ep.outcome.status!r}; cannot overwrite finalized outcome"
                )
            outcome.validate_temporal_order(ep.decision_context.observed_at_utc)
            resolved_ep = BrainEpisode(
                schema_version=ep.schema_version,
                episode_id=ep.episode_id,
                session_date=ep.session_date,
                episode_kind=ep.episode_kind,
                source=ep.source,
                natural_language_input=ep.natural_language_input,
                llm_translation=ep.llm_translation,
                decision_context=ep.decision_context,
                outcome=outcome,
            )
            updated_list.append(resolved_ep)

        if resolved_ep is None:
            raise BrainMemoryError(f"episode {episode_id!r} not found in {target.name}")

        _write_lines_atomic(target, [ep.to_json_line() for ep in updated_list])
        return resolved_ep


def _summarize_episodes(session_date: str, episodes: list[BrainEpisode]) -> dict[str, Any]:
    by_kind = Counter(ep.episode_kind for ep in episodes)
    by_status = Counter(ep.outcome.status for ep in episodes)
    lesson_tags = Counter(
        ep.outcome.error_or_lesson_tag.strip()
        for ep in episodes
        if ep.outcome.error_or_lesson_tag.strip()
    )
    resolved_returns = [
        ep.outcome.net_return_r
        for ep in episodes
        if ep.outcome.status == "resolved" and ep.outcome.net_return_r is not None
    ]

    return {
        "schema_version": "1.0",
        "session_date": session_date,
        "total_episodes": len(episodes),
        "by_kind": dict(sorted(by_kind.items())),
        "by_outcome_status": dict(sorted(by_status.items())),
        "human_confirmed_count": sum(1 for ep in episodes if ep.llm_translation.human_confirmed),
        "risk_gate_passed_count": sum(1 for ep in episodes if ep.decision_context.risk_gate_passed),
        "resolved_with_net_r_count": len(resolved_returns),
        "resolved_net_r_sum": round(sum(resolved_returns), 6),
        "resolved_net_r_mean": (
            round(sum(resolved_returns) / len(resolved_returns), 6) if resolved_returns else None
        ),
        "lesson_tags": dict(sorted(lesson_tags.items())),
        "episode_ids": [ep.episode_id for ep in episodes],
    }


def summarize_day(memory_dir: Path, session_date: str) -> dict[str, Any]:
    parse_session_date(session_date)
    episodes = load_episodes(memory_dir, session_date)
    return _summarize_episodes(session_date, episodes)


def render_day_markdown(summary: dict[str, Any]) -> str:
    lines = [
        f"# Daily Brain Memory Summary — {summary['session_date']}",
        "",
        f"- **Total Episodes**: {summary['total_episodes']}",
        f"- **Human Confirmed Translations**: {summary['human_confirmed_count']}",
        f"- **Risk Gate Passed**: {summary['risk_gate_passed_count']}",
        f"- **By Kind**: {json.dumps(summary['by_kind'], sort_keys=True)}",
        f"- **By Outcome Status**: {json.dumps(summary['by_outcome_status'], sort_keys=True)}",
        f"- **Resolved Net R Count / Sum / Mean**: {summary['resolved_with_net_r_count']} / {summary['resolved_net_r_sum']} / {summary['resolved_net_r_mean']}",
        f"- **Lesson / Error Tags**: {json.dumps(summary['lesson_tags'], sort_keys=True, ensure_ascii=False)}",
    ]
    return "\n".join(lines) + "\n"


def pack_daily_snapshot(
    memory_dir: Path,
    session_date: str,
    *,
    repo_root: Path,
    manifest_out: Path | None = None,
    archive_dir: Path | None = None,
    vault_config_path: Path | None = None,
    source_commit: str = "UNKNOWN",
    codec: Codec = "auto",
    runner: CommandRunner = _default_runner,
) -> dict[str, Any]:
    """Validate one day's JSONL log, bundle with deterministic summary, and pack into state_snapshot Vault."""
    parse_session_date(session_date)

    with _memory_lock(memory_dir, shared=True, create_dir=False):
        resolved_mem_dir = _assert_safe_memory_dir(memory_dir, allow_missing=False)
        assert resolved_mem_dir is not None
        src_jsonl = daily_log_path(memory_dir, session_date)
        _assert_safe_log_file(src_jsonl, resolved_mem_dir, allow_missing=False)

        episodes = _read_episodes_unlocked(memory_dir, session_date)
        if not episodes:
            raise BrainMemoryError(f"cannot pack snapshot: daily log {src_jsonl.name} contains zero episodes")
        summary = _summarize_episodes(session_date, episodes)
        serialized_lines = [ep.to_json_line() for ep in episodes]

    artifact_id = f"brain-daily-{session_date}"
    target_manifest = manifest_out or (
        repo_root / "workflows" / "vault_manifests" / f"{artifact_id}.manifest.json"
    )
    target_archive_dir = archive_dir or (repo_root / ".vault_cache")
    target_vault_cfg = vault_config_path or default_vault_config_path(repo_root)

    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / artifact_id
        stage.mkdir(parents=True, exist_ok=True)
        (stage / f"{session_date}.jsonl").write_text(
            "\n".join(serialized_lines) + "\n",
            encoding="utf-8",
        )
        (stage / f"{session_date}.summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        return pack_artifact(
            stage,
            artifact_id=artifact_id,
            category="state_snapshot",
            manifest_out=target_manifest,
            archive_dir=target_archive_dir,
            vault_config_path=target_vault_cfg,
            source_commit=source_commit,
            codec=codec,
            runner=runner,
        )


def outcome_from_accounted(
    accounted: Any,
    *,
    error_or_lesson_tag: str = "",
    owner_feedback: str = "",
    mae_r: float | None = None,
) -> EpisodeOutcome:
    """Convert an Accounting AccountedOutcome object into a validated resolved EpisodeOutcome."""
    return EpisodeOutcome(
        status="resolved",
        outcome_at_utc=accounted.realized_at_utc,
        net_return_r=accounted.net_r,
        cost_r=accounted.total_cost_r,
        mae_r=mae_r,
        error_or_lesson_tag=error_or_lesson_tag,
        owner_feedback=owner_feedback,
    )
