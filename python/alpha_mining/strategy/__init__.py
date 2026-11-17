"""Strategy layer boundary: translates validated research signals into target intents.

This layer MUST NOT bypass `risk` checks or submit orders directly to `execution`.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SignalIntent:
    intent_id: str
    strategy_id: str
    instrument: str
    target_exposure: float
    generated_at_utc: str
    research_evidence_ref: str
