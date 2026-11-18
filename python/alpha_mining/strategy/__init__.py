"""Strategy layer boundary: translates validated research signals into target intents.

This layer MUST NOT bypass `risk` checks or submit orders directly to `execution`.
"""

import math
import re
from dataclasses import dataclass
from datetime import datetime

_UTC_Z_RE = re.compile(r"^([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(?:\.([0-9]{1,9}))?Z$")


def _validate_intent_utc_z(ts: str) -> None:
    if not isinstance(ts, str):
        raise ValueError("generated_at_utc must be a UTC ISO-8601 string ending in 'Z'")
    match = _UTC_Z_RE.fullmatch(ts)
    if not match:
        raise ValueError(f"invalid generated_at_utc {ts!r}: expected UTC ISO-8601 ending in 'Z'")
    datetime.fromisoformat(match.group(1) + "+00:00")


@dataclass(frozen=True)
class SignalIntent:
    intent_id: str
    strategy_id: str
    instrument: str
    target_exposure: float
    generated_at_utc: str
    research_evidence_ref: str

    def __post_init__(self) -> None:
        for attr in ("intent_id", "strategy_id", "instrument", "research_evidence_ref"):
            val = getattr(self, attr)
            if not isinstance(val, str) or not val.strip():
                raise ValueError(f"SignalIntent.{attr} must be a non-empty string")
        if isinstance(self.target_exposure, bool) or not isinstance(self.target_exposure, (int, float)):
            raise ValueError("SignalIntent.target_exposure must be numeric")
        exp = float(self.target_exposure)
        if not math.isfinite(exp):
            raise ValueError("SignalIntent.target_exposure must be finite")
        object.__setattr__(self, "target_exposure", exp)
        _validate_intent_utc_z(self.generated_at_utc)


from .contracts import (  # noqa: E402
    MetaLabelScore,
    StrategyDecision,
    evaluate_meta_label_gate,
)

__all__ = [
    "MetaLabelScore",
    "SignalIntent",
    "StrategyDecision",
    "evaluate_meta_label_gate",
]
