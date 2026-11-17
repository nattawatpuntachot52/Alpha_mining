//! Conditioner pre-intake conditioning gates and OVCA v1.0 control-plane runner
//! for `Alpha_mining`.
//!
//! This crate preserves `ovca-reference` v1.0 wire contracts without altering
//! `ovca-types` or `ovca-workflow`. It adds pre-intake validation (`ConditioningBrief`),
//! epistemic claim tagging, Solver-vs-Verifier actor separation checks, and
//! transactional stream management around `WorkflowReducer`.

use ovca_types::{
    Authority, ExecutionBudget, Validate, ValidationError, WorkflowEvent, WorkflowEventKind,
    CONTRACT_VERSION,
};
use ovca_workflow::{
    recover_public, PublicWorkflowSnapshot, WorkflowError, WorkflowPhase, WorkflowReducer,
};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use thiserror::Error;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BriefDomain {
    QuantResearch,
    TradingSystem,
    Infrastructure,
    Learning,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EvidenceStatus {
    Proposed,
    Exploratory,
    Reproducible,
    RobustnessValidated,
    IndependentlyReplicated,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ClaimKind {
    Fact,
    Assumption,
    Hypothesis,
    Inference,
    ComputedResult,
    IndependentlyVerifiedResult,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProofLevel {
    ValidCandidate,
    Correctness,
    Completeness,
    Optimality,
    Uniqueness,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct EpistemicClaim {
    pub kind: ClaimKind,
    pub statement: String,
    pub evidence_status: EvidenceStatus,
    pub source_ref: String,
}

impl EpistemicClaim {
    pub fn validate(&self) -> Result<(), AlphaOvcaError> {
        require_text("claim.statement", &self.statement)?;
        require_text("claim.source_ref", &self.source_ref)?;
        if matches!(
            self.evidence_status,
            EvidenceStatus::RobustnessValidated | EvidenceStatus::IndependentlyReplicated
        ) && !matches!(
            self.kind,
            ClaimKind::Fact | ClaimKind::IndependentlyVerifiedResult
        ) {
            return Err(AlphaOvcaError::BriefValidation(
                "robustness_validated or independently_replicated claims require fact or independently_verified_result kind".into(),
            ));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FalsifiableHypothesis {
    pub statement: String,
    pub economic_rationale: String,
    pub alternative_explanations: Vec<String>,
    pub falsification_criteria: Vec<String>,
}

impl FalsifiableHypothesis {
    pub fn validate(&self) -> Result<(), AlphaOvcaError> {
        require_text("hypothesis.statement", &self.statement)?;
        require_text("hypothesis.economic_rationale", &self.economic_rationale)?;
        require_non_empty_unique(
            "hypothesis.alternative_explanations",
            &self.alternative_explanations,
        )?;
        require_non_empty_unique(
            "hypothesis.falsification_criteria",
            &self.falsification_criteria,
        )?;
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct QuantGateSpec {
    pub cost_model_assumptions: Vec<String>,
    pub leakage_controls: Vec<String>,
    pub multiple_testing_plan: String,
    pub oos_validation_plan: String,
    pub target_proof_level: ProofLevel,
}

impl QuantGateSpec {
    pub fn validate(&self) -> Result<(), AlphaOvcaError> {
        require_non_empty_unique(
            "quant_checks.cost_model_assumptions",
            &self.cost_model_assumptions,
        )?;
        require_non_empty_unique("quant_checks.leakage_controls", &self.leakage_controls)?;
        require_text(
            "quant_checks.multiple_testing_plan",
            &self.multiple_testing_plan,
        )?;
        require_text(
            "quant_checks.oos_validation_plan",
            &self.oos_validation_plan,
        )?;
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RoleSeparation {
    pub solver_actor: String,
    pub verifier_actor: String,
    pub reviewer_actor: String,
    pub auditor_actor: String,
}

impl RoleSeparation {
    pub fn validate(&self) -> Result<(), AlphaOvcaError> {
        require_text("governance.solver_actor", &self.solver_actor)?;
        require_text("governance.verifier_actor", &self.verifier_actor)?;
        require_text("governance.reviewer_actor", &self.reviewer_actor)?;
        require_text("governance.auditor_actor", &self.auditor_actor)?;

        let solver = normalize_actor(&self.solver_actor);
        let verifier = normalize_actor(&self.verifier_actor);
        let reviewer = normalize_actor(&self.reviewer_actor);
        let auditor = normalize_actor(&self.auditor_actor);

        if solver == verifier {
            return Err(AlphaOvcaError::RoleSeparationViolation(
                "solver_actor and verifier_actor must be distinct".into(),
            ));
        }
        if solver == reviewer {
            return Err(AlphaOvcaError::RoleSeparationViolation(
                "solver_actor and reviewer_actor must be distinct".into(),
            ));
        }
        if solver == auditor {
            return Err(AlphaOvcaError::RoleSeparationViolation(
                "solver_actor and auditor_actor must be distinct".into(),
            ));
        }
        if reviewer == auditor {
            return Err(AlphaOvcaError::RoleSeparationViolation(
                "reviewer_actor and auditor_actor must be distinct for independent countercheck"
                    .into(),
            ));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ConditioningBrief {
    pub contract_version: String,
    pub brief_id: String,
    pub title: String,
    pub public_summary: String,
    pub domain: BriefDomain,
    pub target_evidence_status: EvidenceStatus,
    pub inputs: Vec<String>,
    pub outputs: Vec<String>,
    pub variables: Vec<String>,
    pub constraints: Vec<String>,
    pub assumptions: Vec<String>,
    pub unknowns: Vec<String>,
    pub block_on_unresolved_unknowns: bool,
    pub acceptance_criteria: Vec<String>,
    #[serde(default)]
    pub hypothesis: Option<FalsifiableHypothesis>,
    #[serde(default)]
    pub quant_checks: Option<QuantGateSpec>,
    pub governance: RoleSeparation,
    pub authority: Authority,
    pub budget: ExecutionBudget,
    pub created_at: String,
}

impl ConditioningBrief {
    pub fn validate(&self) -> Result<(), AlphaOvcaError> {
        if self.contract_version != CONTRACT_VERSION {
            return Err(AlphaOvcaError::BriefValidation(format!(
                "contract_version must be {CONTRACT_VERSION}"
            )));
        }
        require_text("brief_id", &self.brief_id)?;
        require_text("title", &self.title)?;
        require_text("public_summary", &self.public_summary)?;
        require_non_empty_unique("inputs", &self.inputs)?;
        require_non_empty_unique("outputs", &self.outputs)?;
        require_unique_non_empty("variables", &self.variables)?;
        require_unique_non_empty("constraints", &self.constraints)?;
        require_unique_non_empty("assumptions", &self.assumptions)?;
        require_unique_non_empty("unknowns", &self.unknowns)?;
        if self.block_on_unresolved_unknowns && !self.unknowns.is_empty() {
            return Err(AlphaOvcaError::UnresolvedUnknowns(self.unknowns.join("; ")));
        }
        require_non_empty_unique("acceptance_criteria", &self.acceptance_criteria)?;

        match self.domain {
            BriefDomain::QuantResearch => {
                let hypothesis = self.hypothesis.as_ref().ok_or_else(|| {
                    AlphaOvcaError::BriefValidation(
                        "quant_research brief requires a falsifiable hypothesis with economic_rationale"
                            .into(),
                    )
                })?;
                hypothesis.validate()?;
                let quant_checks = self.quant_checks.as_ref().ok_or_else(|| {
                    AlphaOvcaError::BriefValidation(
                        "quant_research brief requires quant_checks (cost model, leakage, multiple testing, oos plan)"
                            .into(),
                    )
                })?;
                quant_checks.validate()?;
            }
            BriefDomain::TradingSystem => {
                if let Some(hypothesis) = &self.hypothesis {
                    hypothesis.validate()?;
                }
                let quant_checks = self.quant_checks.as_ref().ok_or_else(|| {
                    AlphaOvcaError::BriefValidation(
                        "trading_system brief requires quant_checks for reconciliation and validation gates"
                            .into(),
                    )
                })?;
                quant_checks.validate()?;
            }
            BriefDomain::Infrastructure | BriefDomain::Learning => {
                if let Some(hypothesis) = &self.hypothesis {
                    hypothesis.validate()?;
                }
                if let Some(quant_checks) = &self.quant_checks {
                    quant_checks.validate()?;
                }
            }
        }

        self.governance.validate()?;
        self.authority.validate()?;
        self.budget.validate()?;
        require_timestamp("created_at", &self.created_at)?;
        Ok(())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ConditionedVerificationReport {
    pub brief_id: Option<String>,
    pub workflow_id: Option<String>,
    pub domain: Option<BriefDomain>,
    pub snapshot: PublicWorkflowSnapshot,
    pub next_allowed_events: Vec<String>,
    pub honest_status_note: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Error)]
pub enum AlphaOvcaError {
    #[error("conditioning brief error: {0}")]
    BriefValidation(String),
    #[error("unresolved unknowns block intake: {0}")]
    UnresolvedUnknowns(String),
    #[error("role separation violation: {0}")]
    RoleSeparationViolation(String),
    #[error("ovca contract validation error: {0}")]
    ContractValidation(#[from] ValidationError),
    #[error("ovca workflow error: {0}")]
    Workflow(#[from] WorkflowError),
    #[error("brief/stream binding mismatch: {0}")]
    BriefMismatch(String),
}

pub fn init_intake_event(
    brief: &ConditioningBrief,
    workflow_id: &str,
    event_id: &str,
    occurred_at: &str,
) -> Result<WorkflowEvent, AlphaOvcaError> {
    brief.validate()?;
    require_text("workflow_id", workflow_id)?;
    require_text("event_id", event_id)?;
    require_timestamp("occurred_at", occurred_at)?;

    let event = WorkflowEvent {
        contract_version: CONTRACT_VERSION.to_string(),
        workflow_id: workflow_id.to_string(),
        event_id: event_id.to_string(),
        sequence: 0,
        previous_event_id: None,
        occurred_at: occurred_at.to_string(),
        kind: WorkflowEventKind::IntakeAccepted {
            request_ref: brief.brief_id.clone(),
            public_summary: brief.public_summary.clone(),
            authority: brief.authority.clone(),
            budget: brief.budget.clone(),
        },
    };

    let mut reducer = WorkflowReducer::new();
    reducer.apply(&event)?;
    Ok(event)
}

pub fn verify_conditioned_stream(
    events: &[WorkflowEvent],
    brief: Option<&ConditioningBrief>,
) -> Result<ConditionedVerificationReport, AlphaOvcaError> {
    if let Some(b) = brief {
        b.validate()?;
    }

    let mut reducer = WorkflowReducer::new();
    for event in events {
        reducer.apply(event)?;
    }

    let snapshot = recover_public(events)?;

    if let Some(b) = brief {
        let first = events.first().ok_or_else(|| {
            AlphaOvcaError::BriefMismatch(
                "event stream is empty; expected IntakeAccepted bound to brief".into(),
            )
        })?;
        match &first.kind {
            WorkflowEventKind::IntakeAccepted {
                request_ref,
                authority,
                budget,
                ..
            } => {
                if request_ref != &b.brief_id {
                    return Err(AlphaOvcaError::BriefMismatch(format!(
                        "intake request_ref '{}' does not match brief_id '{}'",
                        request_ref, b.brief_id
                    )));
                }
                if authority != &b.authority {
                    return Err(AlphaOvcaError::BriefMismatch(
                        "intake authority does not match conditioning brief authority".into(),
                    ));
                }
                if budget != &b.budget {
                    return Err(AlphaOvcaError::BriefMismatch(
                        "intake budget does not match conditioning brief budget".into(),
                    ));
                }
            }
            _ => {
                return Err(AlphaOvcaError::BriefMismatch(
                    "first event must be intake_accepted".into(),
                ));
            }
        }
    }

    let workflow_id = events.first().map(|e| e.workflow_id.clone());
    let next_allowed_events = next_allowed_events(snapshot.phase)
        .into_iter()
        .map(str::to_string)
        .collect();

    Ok(ConditionedVerificationReport {
        brief_id: brief.map(|b| b.brief_id.clone()),
        workflow_id,
        domain: brief.map(|b| b.domain),
        snapshot,
        next_allowed_events,
        honest_status_note: "OVCA reduction verifies deterministic event/reference/role conformance only; it does not prove empirical market edge or truth of external evidence.".into(),
    })
}

pub fn append_event_to_stream(
    events: &mut Vec<WorkflowEvent>,
    new_event: WorkflowEvent,
    brief: Option<&ConditioningBrief>,
) -> Result<ConditionedVerificationReport, AlphaOvcaError> {
    let mut candidate = events.clone();
    candidate.push(new_event);
    let report = verify_conditioned_stream(&candidate, brief)?;
    *events = candidate;
    Ok(report)
}

pub fn next_allowed_events(phase: WorkflowPhase) -> Vec<&'static str> {
    match phase {
        WorkflowPhase::AwaitingIntake => vec!["intake_accepted"],
        WorkflowPhase::AwaitingCoordinatorDispatch => vec!["coordinator_dispatched"],
        WorkflowPhase::AwaitingEngineerResult => vec!["engineer_returned"],
        WorkflowPhase::AwaitingVerification => vec!["verification_recorded"],
        WorkflowPhase::AwaitingReview => vec!["reviewer_decided"],
        WorkflowPhase::AwaitingAudit => vec!["auditor_counterchecked"],
        WorkflowPhase::AwaitingRepairDirective => vec!["repair_directed"],
        WorkflowPhase::AwaitingOwnerEscalation => vec!["owner_escalated"],
        WorkflowPhase::AwaitingCoordinatorFinalResponse => vec!["coordinator_finalized"],
        WorkflowPhase::Completed => vec![],
    }
}

fn normalize_actor(actor: &str) -> String {
    actor.trim().to_ascii_lowercase()
}

fn require_text(field: &str, value: &str) -> Result<(), AlphaOvcaError> {
    if value.trim().is_empty() {
        Err(AlphaOvcaError::BriefValidation(format!(
            "{field} must not be empty"
        )))
    } else {
        Ok(())
    }
}

fn require_timestamp(field: &str, value: &str) -> Result<(), AlphaOvcaError> {
    require_text(field, value)?;
    if value.contains('T') && value.ends_with('Z') {
        Ok(())
    } else {
        Err(AlphaOvcaError::BriefValidation(format!(
            "{field} must be a caller-supplied UTC timestamp containing 'T' and ending in 'Z'"
        )))
    }
}

fn require_non_empty_unique(field: &str, values: &[String]) -> Result<(), AlphaOvcaError> {
    if values.is_empty() {
        return Err(AlphaOvcaError::BriefValidation(format!(
            "{field} must contain at least one item"
        )));
    }
    require_unique_non_empty(field, values)
}

fn require_unique_non_empty(field: &str, values: &[String]) -> Result<(), AlphaOvcaError> {
    let mut seen = BTreeSet::new();
    for item in values {
        require_text(field, item)?;
        if !seen.insert(item.trim()) {
            return Err(AlphaOvcaError::BriefValidation(format!(
                "{field} must not contain duplicate entries"
            )));
        }
    }
    Ok(())
}
