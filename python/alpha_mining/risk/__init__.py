"""Risk layer boundary: independent pre-trade and portfolio risk gating.

Risk limits operate independently of Strategy alpha beliefs and approve/clip/reject
`SignalIntent` objects before `Execution` can observe them.
"""

from dataclasses import dataclass, field
from datetime import datetime
import math
import re

_UTC_Z_RE = re.compile(r"^([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(?:\.([0-9]{1,9}))?Z$")


def _validate_risk_utc_z(ts: str) -> None:
    if not isinstance(ts, str):
        raise ValueError("evaluated_at_utc must be a UTC ISO-8601 string ending in 'Z'")
    match = _UTC_Z_RE.fullmatch(ts)
    if not match:
        raise ValueError(f"invalid evaluated_at_utc {ts!r}: expected UTC ISO-8601 ending in 'Z'")
    datetime.fromisoformat(match.group(1) + "+00:00")


@dataclass(frozen=True)
class RiskDecision:
    intent_id: str
    approved: bool
    approved_exposure: float
    rejection_reason: str | None
    evaluated_at_utc: str
    _seal: str = field(default="", repr=False, compare=False, hash=False, kw_only=True)

    def __post_init__(self) -> None:
        if not isinstance(self.intent_id, str) or not self.intent_id.strip():
            raise ValueError("RiskDecision.intent_id must be a non-empty string")
        if not isinstance(self.approved, bool):
            raise ValueError("RiskDecision.approved must be a boolean")
        if isinstance(self.approved_exposure, bool) or not isinstance(self.approved_exposure, (int, float)):
            raise ValueError("RiskDecision.approved_exposure must be numeric")
        exp = float(self.approved_exposure)
        if not math.isfinite(exp):
            raise ValueError("RiskDecision.approved_exposure must be finite")
        object.__setattr__(self, "approved_exposure", exp)
        if not self.approved and exp != 0.0:
            raise ValueError("RiskDecision.approved_exposure must be 0.0 when approved=False")
        if self.approved and exp == 0.0:
            raise ValueError("RiskDecision.approved_exposure must be non-zero when approved=True")
        if self.rejection_reason is not None and (
            not isinstance(self.rejection_reason, str) or not self.rejection_reason.strip()
        ):
            raise ValueError("RiskDecision.rejection_reason must be None or a non-empty string")
        if self.approved and self.rejection_reason is not None:
            raise ValueError("RiskDecision.rejection_reason must be None when approved=True")
        _validate_risk_utc_z(self.evaluated_at_utc)
        if not isinstance(self._seal, str):
            raise ValueError("RiskDecision._seal must be a string")


from .contracts import (  # noqa: E402
    MarketRiskSnapshot,
    RiskLimits,
    evaluate_pre_trade_risk,
    verify_risk_decision_seal,
)

__all__ = [
    "MarketRiskSnapshot",
    "RiskDecision",
    "RiskLimits",
    "evaluate_pre_trade_risk",
    "verify_risk_decision_seal",
]
