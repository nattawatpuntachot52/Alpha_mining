"""Research translation contract enforcing NL -> JSON isolation with zero execution privileges."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

ALLOWED_TRANSLATOR_OPS = frozenset({">", ">=", "<", "<=", "==", "!=", "in"})
DIRECTION_BIASES = frozenset({"long", "short", "flat", "neutral"})
FORBIDDEN_TRANSLATOR_KEYS = frozenset(
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
FORBIDDEN_TRANSLATOR_STRINGS = frozenset(
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
    }
)
ALLOWED_PAYLOAD_KEYS = frozenset(
    {
        "spec_id",
        "natural_language_rule",
        "translator_role",
        "conditions",
        "horizon_bars",
        "direction_bias",
        "human_confirmed",
        "created_at_utc",
        "notes",
    }
)
_SPEC_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_UTC_Z_RE = re.compile(r"^([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(?:\.([0-9]{1,9}))?Z$")


def _validate_utc_z(ts: str, field_name: str) -> tuple[datetime, int]:
    if not isinstance(ts, str):
        raise ValueError(f"invalid {field_name} {ts!r}: expected UTC ISO-8601 ending in 'Z'")
    match = _UTC_Z_RE.fullmatch(ts)
    if not match:
        raise ValueError(f"invalid {field_name} {ts!r}: expected UTC ISO-8601 ending in 'Z'")
    sec_dt = datetime.fromisoformat(match.group(1) + "+00:00")
    ns = int((match.group(2) or "").ljust(9, "0"))
    return sec_dt, ns


def _validate_condition_value(obj: Any, path: str, *, allow_nested: bool = True) -> Any:
    if obj is None or isinstance(obj, (bool, int)):
        return obj
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ValueError(f"non-finite float (NaN/Inf) disallowed in {path}")
        return obj
    if isinstance(obj, str):
        if obj.strip().lower() in FORBIDDEN_TRANSLATOR_STRINGS:
            raise ValueError(f"forbidden execution string {obj!r} disallowed in {path}")
        return obj
    if isinstance(obj, (list, tuple)) and allow_nested:
        return tuple(_validate_condition_value(item, f"{path}[{i}]", allow_nested=False) for i, item in enumerate(obj))
    raise ValueError(f"unsupported or nested complex value {type(obj).__name__} inside {path}")


def _walk_forbidden_payload(obj: Any, path: str = "payload", *, check_strings: bool = True) -> None:
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ValueError(f"non-finite float (NaN/Inf) disallowed in {path}")
        return
    if isinstance(obj, str):
        if check_strings and obj.strip().lower() in FORBIDDEN_TRANSLATOR_STRINGS:
            raise ValueError(f"forbidden execution string {obj!r} disallowed in {path}")
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str) or not k:
                raise ValueError(f"non-string or empty key inside {path}")
            if k.lower() in FORBIDDEN_TRANSLATOR_KEYS:
                raise ValueError(f"forbidden execution/bypass key {k!r} disallowed in translator output")
            sub_check = False if path == "payload" and k in {"natural_language_rule", "notes"} else check_strings
            _walk_forbidden_payload(v, f"{path}.{k}", check_strings=sub_check)
        return
    if isinstance(obj, (list, tuple)):
        for idx, item in enumerate(obj):
            _walk_forbidden_payload(item, f"{path}[{idx}]", check_strings=check_strings)


@dataclass(frozen=True)
class RuleCondition:
    """Single deterministic feature predicate translated from Owner natural language."""

    feature: str
    op: str
    value: Any

    def __post_init__(self) -> None:
        if not isinstance(self.feature, str) or not self.feature.strip():
            raise ValueError("condition.feature must be a non-empty string")
        if self.feature.strip().lower() in FORBIDDEN_TRANSLATOR_KEYS:
            raise ValueError(f"forbidden execution feature {self.feature!r} disallowed")
        if self.op not in ALLOWED_TRANSLATOR_OPS:
            raise ValueError(f"unsupported condition.op {self.op!r}; allowed: {sorted(ALLOWED_TRANSLATOR_OPS)}")
        if self.op in {">", ">=", "<", "<="}:
            if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
                raise ValueError(f"numeric operator {self.op!r} requires a finite number value")
            if not math.isfinite(float(self.value)):
                raise ValueError("condition.value must be finite")
        elif self.op == "in":
            if not isinstance(self.value, (list, tuple)) or not self.value:
                raise ValueError("operator 'in' requires a non-empty list/tuple")
            frozen = _validate_condition_value(self.value, "condition.value", allow_nested=True)
            object.__setattr__(self, "value", frozen)
        else:
            _validate_condition_value(self.value, "condition.value", allow_nested=False)


@dataclass(frozen=True)
class NLRuleSpec:
    """Validated JSON specification translated by an LLM without execution authority."""

    spec_id: str
    natural_language_rule: str
    translator_role: Literal["nl_to_json_only"]
    conditions: tuple[RuleCondition, ...]
    horizon_bars: int
    direction_bias: Literal["long", "short", "flat", "neutral"]
    human_confirmed: bool
    created_at_utc: str
    notes: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.spec_id, str) or not _SPEC_ID_RE.fullmatch(self.spec_id):
            raise ValueError(f"invalid spec_id {self.spec_id!r}")
        if not isinstance(self.natural_language_rule, str) or not self.natural_language_rule.strip():
            raise ValueError("natural_language_rule must be non-empty")
        if self.translator_role != "nl_to_json_only":
            raise ValueError(f"translator_role must be 'nl_to_json_only', got {self.translator_role!r}")
        if isinstance(self.conditions, list):
            object.__setattr__(self, "conditions", tuple(self.conditions))
        if not self.conditions or not all(isinstance(c, RuleCondition) for c in self.conditions):
            raise ValueError("conditions must be a non-empty sequence of RuleCondition")
        if isinstance(self.horizon_bars, bool) or not isinstance(self.horizon_bars, int) or self.horizon_bars < 1:
            raise ValueError("horizon_bars must be a positive integer")
        if self.direction_bias not in DIRECTION_BIASES:
            raise ValueError(f"invalid direction_bias {self.direction_bias!r}")
        if not isinstance(self.human_confirmed, bool):
            raise ValueError("human_confirmed must be a boolean")
        _validate_utc_z(self.created_at_utc, "created_at_utc")
        if not isinstance(self.notes, str):
            raise ValueError("notes must be a string")


def validate_translator_payload(payload: dict[str, Any]) -> NLRuleSpec:
    """Parse and strictly validate raw LLM JSON translation output before Research/Strategy sees it."""
    if not isinstance(payload, dict):
        raise ValueError("translator payload must be a JSON object")
    _walk_forbidden_payload(payload)

    extra_keys = set(payload.keys()) - ALLOWED_PAYLOAD_KEYS
    if extra_keys:
        raise ValueError(f"unexpected field(s) in translator payload: {sorted(extra_keys)}")

    raw_conditions = payload.get("conditions")
    if not isinstance(raw_conditions, list) or not raw_conditions:
        raise ValueError("translator payload requires non-empty 'conditions' list")
    allowed_cond_keys = frozenset({"feature", "op", "value"})
    conditions: list[RuleCondition] = []
    for idx, item in enumerate(raw_conditions):
        if not isinstance(item, dict):
            raise ValueError(f"conditions[{idx}] must be an object")
        extra_cond = set(item.keys()) - allowed_cond_keys
        if extra_cond:
            raise ValueError(f"unexpected field(s) in conditions[{idx}]: {sorted(extra_cond)}")
        missing_cond = allowed_cond_keys - set(item.keys())
        if missing_cond:
            raise ValueError(f"missing required field(s) in conditions[{idx}]: {sorted(missing_cond)}")
        conditions.append(
            RuleCondition(
                feature=item["feature"],
                op=item["op"],
                value=item["value"],
            )
        )

    raw_notes = payload.get("notes", "")
    if raw_notes is None:
        raw_notes = ""
    if not isinstance(raw_notes, str):
        raise ValueError("notes must be a string")

    return NLRuleSpec(
        spec_id=payload.get("spec_id", ""),
        natural_language_rule=payload.get("natural_language_rule", ""),
        translator_role=payload.get("translator_role", ""),
        conditions=tuple(conditions),
        horizon_bars=payload.get("horizon_bars"),  # type: ignore[arg-type]
        direction_bias=payload.get("direction_bias", ""),
        human_confirmed=payload.get("human_confirmed"),  # type: ignore[arg-type]
        created_at_utc=payload.get("created_at_utc", ""),
        notes=raw_notes,
    )
