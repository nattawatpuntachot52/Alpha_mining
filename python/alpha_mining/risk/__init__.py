"""Risk layer boundary: independent pre-trade and portfolio risk gating.

Risk limits operate independently of Strategy alpha beliefs and approve/clip/reject
`SignalIntent` objects before `Execution` can observe them.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskDecision:
    intent_id: str
    approved: bool
    approved_exposure: float
    rejection_reason: str | None
    evaluated_at_utc: str
