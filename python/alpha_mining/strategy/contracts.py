"""Deterministic Strategy contracts separating primary rules from learned Meta-Label sizing."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from . import SignalIntent

_UTC_Z_RE = re.compile(r"^([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(?:\.([0-9]{1,9}))?Z$")
_DECISION_MODES = frozenset({"primary_rule_only", "meta_label_filtered"})


def _check_unit_float(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    f = float(value)
    if not math.isfinite(f) or f < 0.0 or f > 1.0:
        raise ValueError(f"{field_name} must be finite and within [0.0, 1.0], got {value!r}")
    return f


def _parse_utc_z_ns(ts: str, field_name: str) -> tuple[datetime, int]:
    if not isinstance(ts, str):
        raise ValueError(f"invalid {field_name} {ts!r}: expected UTC ISO-8601 ending in 'Z'")
    match = _UTC_Z_RE.fullmatch(ts)
    if not match:
        raise ValueError(f"invalid {field_name} {ts!r}: expected UTC ISO-8601 ending in 'Z'")
    sec_dt = datetime.fromisoformat(match.group(1) + "+00:00")
    ns = int((match.group(2) or "").ljust(9, "0"))
    return sec_dt, ns


@dataclass(frozen=True)
class MetaLabelScore:
    """Calibrated secondary ML output predicting P(net_return > 0) and bet-size multiplier."""

    intent_id: str
    model_id: str
    prob_net_positive: float
    suggested_size_multiplier: float
    out_of_sample_calibrated: bool
    evaluated_at_utc: str

    def __post_init__(self) -> None:
        if not isinstance(self.intent_id, str) or not self.intent_id.strip():
            raise ValueError("intent_id must be non-empty")
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("model_id must be non-empty")
        object.__setattr__(
            self, "prob_net_positive", _check_unit_float(self.prob_net_positive, "prob_net_positive")
        )
        object.__setattr__(
            self,
            "suggested_size_multiplier",
            _check_unit_float(self.suggested_size_multiplier, "suggested_size_multiplier"),
        )
        if not isinstance(self.out_of_sample_calibrated, bool):
            raise ValueError("out_of_sample_calibrated must be a boolean")
        _parse_utc_z_ns(self.evaluated_at_utc, "evaluated_at_utc")


@dataclass(frozen=True)
class StrategyDecision:
    """Deterministic strategy output passed to independent Risk gating."""

    intent_id: str
    execute: bool
    target_exposure: float
    decision_mode: Literal["primary_rule_only", "meta_label_filtered"]
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.intent_id, str) or not self.intent_id.strip():
            raise ValueError("StrategyDecision.intent_id must be a non-empty string")
        if not isinstance(self.execute, bool):
            raise ValueError("StrategyDecision.execute must be a boolean")
        if isinstance(self.target_exposure, bool) or not isinstance(self.target_exposure, (int, float)):
            raise ValueError("StrategyDecision.target_exposure must be numeric")
        exp = float(self.target_exposure)
        if not math.isfinite(exp):
            raise ValueError("StrategyDecision.target_exposure must be finite")
        object.__setattr__(self, "target_exposure", exp)
        if not self.execute and exp != 0.0:
            raise ValueError("StrategyDecision.target_exposure must be 0.0 when execute=False")
        if self.execute and exp == 0.0:
            raise ValueError("StrategyDecision.target_exposure must be non-zero when execute=True")
        if self.decision_mode not in _DECISION_MODES:
            raise ValueError(f"invalid decision_mode {self.decision_mode!r}")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("StrategyDecision.reason must be a non-empty string")


def evaluate_meta_label_gate(
    intent: SignalIntent,
    meta_score: MetaLabelScore | None,
    *,
    min_prob_net_positive: float = 0.55,
    require_oos_calibration: bool = True,
) -> StrategyDecision:
    """Deterministically combine primary rule intent with optional secondary Meta-Label score."""
    if not isinstance(intent, SignalIntent):
        raise TypeError("intent must be a SignalIntent")
    intent_ts = _parse_utc_z_ns(intent.generated_at_utc, "intent.generated_at_utc")
    threshold = _check_unit_float(min_prob_net_positive, "min_prob_net_positive")
    if isinstance(intent.target_exposure, bool) or not isinstance(intent.target_exposure, (int, float)):
        raise ValueError("intent.target_exposure must be numeric")
    raw_exposure = float(intent.target_exposure)
    if not math.isfinite(raw_exposure):
        raise ValueError("intent.target_exposure must be finite")

    if meta_score is None:
        if raw_exposure == 0.0:
            return StrategyDecision(
                intent_id=intent.intent_id,
                execute=False,
                target_exposure=0.0,
                decision_mode="primary_rule_only",
                reason="zero_primary_exposure",
            )
        return StrategyDecision(
            intent_id=intent.intent_id,
            execute=True,
            target_exposure=raw_exposure,
            decision_mode="primary_rule_only",
            reason="primary_rule_approved",
        )

    if not isinstance(meta_score, MetaLabelScore):
        raise TypeError("meta_score must be a MetaLabelScore or None")
    if meta_score.intent_id != intent.intent_id:
        raise ValueError(
            f"meta_score.intent_id {meta_score.intent_id!r} does not match intent.intent_id {intent.intent_id!r}"
        )
    meta_ts = _parse_utc_z_ns(meta_score.evaluated_at_utc, "meta_score.evaluated_at_utc")
    if meta_ts < intent_ts:
        raise ValueError(
            f"lookahead violation: meta_score.evaluated_at_utc ({meta_score.evaluated_at_utc}) precedes intent.generated_at_utc ({intent.generated_at_utc})"
        )

    if raw_exposure == 0.0:
        return StrategyDecision(
            intent_id=intent.intent_id,
            execute=False,
            target_exposure=0.0,
            decision_mode="meta_label_filtered",
            reason="zero_primary_exposure",
        )
    if require_oos_calibration and not meta_score.out_of_sample_calibrated:
        return StrategyDecision(
            intent_id=intent.intent_id,
            execute=False,
            target_exposure=0.0,
            decision_mode="meta_label_filtered",
            reason="uncalibrated_meta_label_model",
        )
    if meta_score.prob_net_positive < threshold:
        return StrategyDecision(
            intent_id=intent.intent_id,
            execute=False,
            target_exposure=0.0,
            decision_mode="meta_label_filtered",
            reason="below_meta_label_threshold",
        )

    scaled_exposure = raw_exposure * meta_score.suggested_size_multiplier
    if scaled_exposure == 0.0:
        return StrategyDecision(
            intent_id=intent.intent_id,
            execute=False,
            target_exposure=0.0,
            decision_mode="meta_label_filtered",
            reason="zero_meta_multiplier",
        )
    return StrategyDecision(
        intent_id=intent.intent_id,
        execute=True,
        target_exposure=scaled_exposure,
        decision_mode="meta_label_filtered",
        reason="meta_label_approved",
    )
