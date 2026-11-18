"""Research layer boundary: falsifiable hypotheses, trial accounting, and OOS evaluation specs.

This layer MUST remain strictly isolated from order routing (`execution`) and live
capital state (`accounting`). Outputs require explicit EvidenceStatus labeling.
"""

from dataclasses import dataclass
from typing import Literal

EvidenceStatus = Literal[
    "proposed",
    "exploratory",
    "reproducible",
    "robustness_validated",
    "independently_replicated",
]


@dataclass(frozen=True)
class ExperimentRecord:
    experiment_id: str
    hypothesis_ref: str
    trials_tested: int
    evidence_status: EvidenceStatus
    oos_split_description: str
    cost_model_summary: str
    negative_result: bool
    reproduction_command: str

    def __post_init__(self) -> None:
        if self.trials_tested < 1:
            raise ValueError("trials_tested must be at least 1 for multiple-testing accounting")


from .contracts import (  # noqa: E402
    ALLOWED_TRANSLATOR_OPS,
    DIRECTION_BIASES,
    FORBIDDEN_TRANSLATOR_KEYS,
    NLRuleSpec,
    RuleCondition,
    validate_translator_payload,
)

__all__ = [
    "ALLOWED_TRANSLATOR_OPS",
    "DIRECTION_BIASES",
    "EvidenceStatus",
    "ExperimentRecord",
    "FORBIDDEN_TRANSLATOR_KEYS",
    "NLRuleSpec",
    "RuleCondition",
    "validate_translator_payload",
]
