"""Independent pre-trade Risk gating contracts enforcing hard exposure, drawdown, spread, and freshness bounds."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import secrets
from dataclasses import dataclass, replace
from datetime import datetime

from ..strategy import StrategyDecision
from . import RiskDecision

_UTC_Z_RE = re.compile(r"^([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(?:\.([0-9]{1,9}))?Z$")


def _make_risk_seal_ops():
    secret = secrets.token_bytes(32)

    def canonical_payload(decision: RiskDecision) -> bytes:
        return json.dumps(
            {
                "intent_id": decision.intent_id,
                "approved": decision.approved,
                "approved_exposure": float(decision.approved_exposure),
                "rejection_reason": decision.rejection_reason,
                "evaluated_at_utc": decision.evaluated_at_utc,
            },
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")

    def sign(decision: RiskDecision) -> str:
        return hmac.new(secret, canonical_payload(decision), hashlib.sha256).hexdigest()

    def verify(decision: RiskDecision) -> bool:
        if not isinstance(decision._seal, str) or not decision._seal:
            return False
        return hmac.compare_digest(decision._seal, sign(decision))

    return sign, verify


_sign_risk_decision, _verify_risk_seal_hmac = _make_risk_seal_ops()
del _make_risk_seal_ops


def _seal_decision(decision: RiskDecision) -> RiskDecision:
    return replace(decision, _seal=_sign_risk_decision(decision))


def _parse_utc_z_ns(ts: str, field_name: str) -> tuple[datetime, int]:
    if not isinstance(ts, str):
        raise ValueError(f"invalid {field_name} {ts!r}: expected UTC ISO-8601 ending in 'Z'")
    match = _UTC_Z_RE.fullmatch(ts)
    if not match:
        raise ValueError(f"invalid {field_name} {ts!r}: expected UTC ISO-8601 ending in 'Z'")
    sec_dt = datetime.fromisoformat(match.group(1) + "+00:00")
    ns = int((match.group(2) or "").ljust(9, "0"))
    return sec_dt, ns


def _positive_finite(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    f = float(value)
    if not math.isfinite(f) or f <= 0.0:
        raise ValueError(f"{field_name} must be positive finite, got {value!r}")
    return f


def _nonneg_finite(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    f = float(value)
    if not math.isfinite(f) or f < 0.0:
        raise ValueError(f"{field_name} must be non-negative finite, got {value!r}")
    return f


@dataclass(frozen=True)
class RiskLimits:
    """Hard deterministic risk limits immune to Strategy or LLM overrides."""

    max_abs_exposure: float
    max_daily_loss_r: float
    max_spread_bps: float
    max_data_age_sec: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_abs_exposure", _positive_finite(self.max_abs_exposure, "max_abs_exposure"))
        object.__setattr__(self, "max_daily_loss_r", _positive_finite(self.max_daily_loss_r, "max_daily_loss_r"))
        object.__setattr__(self, "max_spread_bps", _positive_finite(self.max_spread_bps, "max_spread_bps"))
        object.__setattr__(self, "max_data_age_sec", _positive_finite(self.max_data_age_sec, "max_data_age_sec"))


@dataclass(frozen=True)
class MarketRiskSnapshot:
    """Point-in-time market and portfolio state checked at pre-trade Risk evaluation."""

    observed_at_utc: str
    evaluated_at_utc: str
    current_daily_loss_r: float
    spread_bps: float

    def __post_init__(self) -> None:
        obs_ts = _parse_utc_z_ns(self.observed_at_utc, "observed_at_utc")
        eval_ts = _parse_utc_z_ns(self.evaluated_at_utc, "evaluated_at_utc")
        if eval_ts < obs_ts:
            raise ValueError("evaluated_at_utc cannot precede observed_at_utc")
        object.__setattr__(
            self, "current_daily_loss_r", _nonneg_finite(self.current_daily_loss_r, "current_daily_loss_r")
        )
        object.__setattr__(self, "spread_bps", _nonneg_finite(self.spread_bps, "spread_bps"))


def verify_risk_decision_seal(decision: RiskDecision) -> None:
    """Verify that a RiskDecision was genuinely sealed by evaluate_pre_trade_risk() and never altered."""
    if not isinstance(decision, RiskDecision):
        raise TypeError("decision must be a RiskDecision instance; raw SignalIntent is forbidden")
    _parse_utc_z_ns(decision.evaluated_at_utc, "RiskDecision.evaluated_at_utc")
    if isinstance(decision.approved_exposure, bool) or not isinstance(
        decision.approved_exposure, (int, float)
    ):
        raise ValueError("RiskDecision.approved_exposure must be numeric")
    if not math.isfinite(float(decision.approved_exposure)):
        raise ValueError("RiskDecision.approved_exposure must be finite")
    if not _verify_risk_seal_hmac(decision):
        raise PermissionError(
            "RiskDecision lacks a valid evaluate_pre_trade_risk() capability seal; forged or tampered decisions cannot authorize execution"
        )


def evaluate_pre_trade_risk(
    decision: StrategyDecision,
    limits: RiskLimits,
    snapshot: MarketRiskSnapshot,
) -> RiskDecision:
    """Independently reject or clip StrategyDecision before Execution can observe it."""
    if not isinstance(decision, StrategyDecision):
        raise TypeError("decision must be a StrategyDecision")
    if not isinstance(limits, RiskLimits):
        raise TypeError("limits must be a RiskLimits")
    if not isinstance(snapshot, MarketRiskSnapshot):
        raise TypeError("snapshot must be a MarketRiskSnapshot")

    if not isinstance(decision.intent_id, str) or not decision.intent_id.strip():
        raise ValueError("StrategyDecision.intent_id must be a non-empty string")
    if not isinstance(decision.execute, bool):
        raise ValueError("StrategyDecision.execute must be a boolean")
    if isinstance(decision.target_exposure, bool) or not isinstance(decision.target_exposure, (int, float)):
        raise ValueError("StrategyDecision.target_exposure must be numeric")
    target_exp = float(decision.target_exposure)
    if not math.isfinite(target_exp):
        raise ValueError("StrategyDecision.target_exposure must be finite")

    if not decision.execute or target_exp == 0.0:
        return _seal_decision(
            RiskDecision(
                intent_id=decision.intent_id,
                approved=False,
                approved_exposure=0.0,
                rejection_reason="strategy_did_not_request_execution",
                evaluated_at_utc=snapshot.evaluated_at_utc,
            )
        )

    obs_dt, obs_ns = _parse_utc_z_ns(snapshot.observed_at_utc, "observed_at_utc")
    eval_dt, eval_ns = _parse_utc_z_ns(snapshot.evaluated_at_utc, "evaluated_at_utc")
    delta = eval_dt - obs_dt
    age_ns = (delta.days * 86400 + delta.seconds) * 1_000_000_000 + (eval_ns - obs_ns)
    if age_ns < 0:
        raise ValueError("evaluated_at_utc cannot precede observed_at_utc")
    if age_ns > limits.max_data_age_sec * 1_000_000_000.0:
        return _seal_decision(
            RiskDecision(
                intent_id=decision.intent_id,
                approved=False,
                approved_exposure=0.0,
                rejection_reason="stale_observation",
                evaluated_at_utc=snapshot.evaluated_at_utc,
            )
        )

    if snapshot.current_daily_loss_r >= limits.max_daily_loss_r:
        return _seal_decision(
            RiskDecision(
                intent_id=decision.intent_id,
                approved=False,
                approved_exposure=0.0,
                rejection_reason="daily_loss_limit_reached",
                evaluated_at_utc=snapshot.evaluated_at_utc,
            )
        )

    if snapshot.spread_bps > limits.max_spread_bps:
        return _seal_decision(
            RiskDecision(
                intent_id=decision.intent_id,
                approved=False,
                approved_exposure=0.0,
                rejection_reason="spread_limit_exceeded",
                evaluated_at_utc=snapshot.evaluated_at_utc,
            )
        )

    clipped = max(-limits.max_abs_exposure, min(limits.max_abs_exposure, target_exp))
    return _seal_decision(
        RiskDecision(
            intent_id=decision.intent_id,
            approved=True,
            approved_exposure=clipped,
            rejection_reason=None,
            evaluated_at_utc=snapshot.evaluated_at_utc,
        )
    )
