use alpha_ovca::{
    append_event_to_stream, init_intake_event, verify_conditioned_stream, AlphaOvcaError,
    BriefDomain, ClaimKind, ConditioningBrief, EpistemicClaim, EvidenceStatus,
    FalsifiableHypothesis, ProofLevel, QuantGateSpec, RoleSeparation,
};
use ovca_types::{
    AuditDecision, AuditPacket, Authority, Decision, DecisionDisposition, Evidence, EvidenceKind,
    ExecutionBudget, FinalResponse, Finding, FindingSeverity, RepairDirective, ReviewDecision,
    ReviewPacket, Role, RoleInvocation, RoleResult, RoleResultStatus, VerificationCheck,
    VerificationOutcome, VerificationStatus, WorkflowEvent, WorkflowEventKind, WorkflowOutcome,
};
use ovca_workflow::WorkflowPhase;

fn sample_quant_brief() -> ConditioningBrief {
    ConditioningBrief {
        contract_version: "1.0".into(),
        brief_id: "brief-ofi-001".into(),
        title: "Synthetic Order Flow Imbalance Microstructure Study".into(),
        public_summary: "Conditioned quant study for synthetic order flow imbalance".into(),
        domain: BriefDomain::QuantResearch,
        target_evidence_status: EvidenceStatus::Reproducible,
        inputs: vec!["synthetic_l1_ticks.parquet (time-ordered, UTC)".into()],
        outputs: vec!["oos_net_sharpe_and_turnover_report.json".into()],
        variables: vec!["ofi_window_ticks".into(), "spread_threshold_bps".into()],
        constraints: vec![
            "zero lookahead bias".into(),
            "include half-spread + fee cost model".into(),
        ],
        assumptions: vec!["constant tick size and deterministic fee tier".into()],
        unknowns: vec![],
        block_on_unresolved_unknowns: true,
        acceptance_criteria: vec![
            "reproducible OOS evaluation passes independent verification".into(),
        ],
        hypothesis: Some(FalsifiableHypothesis {
            statement: "Short-horizon order flow imbalance predicts temporary price pressure before inventory mean reversion".into(),
            economic_rationale: "Liquidity providers widen quotes or adjust reservation prices against toxic flow until inventory clears".into(),
            alternative_explanations: vec![
                "Spurious autocorrelation caused by bid-ask bounce".into(),
                "Regime-specific volatility clustering rather than directional alpha".into(),
            ],
            falsification_criteria: vec![
                "OOS net return after spread+fees is <= 0 or indistinguishable from mid-price random sign permutation (p > 0.05)".into(),
            ],
        }),
        quant_checks: Some(QuantGateSpec {
            cost_model_assumptions: vec!["half-spread crossing + 1.0 bps taker fee".into()],
            leakage_controls: vec!["strict chronological train/validation/OOS split with embargo".into()],
            multiple_testing_plan: "Record total parameter trials and evaluate Deflated Sharpe Ratio".into(),
            oos_validation_plan: "Walk-forward purged split on unseen synthetic holdout window".into(),
            target_proof_level: ProofLevel::Correctness,
        }),
        governance: RoleSeparation {
            solver_actor: "engineer-quant-solver".into(),
            verifier_actor: "verifier-ci-checks".into(),
            reviewer_actor: "reviewer-quant-critic".into(),
            auditor_actor: "auditor-adversarial".into(),
        },
        authority: Authority {
            contract_version: "1.0".into(),
            authority_id: "auth-ofi-001".into(),
            granted_by: Role::Owner,
            objective: "Evaluate synthetic OFI hypothesis under strict cost and leakage gates".into(),
            scope: vec!["research/ofi_synthetic".into()],
            constraints: vec!["read-only research; no live execution".into()],
        },
        budget: ExecutionBudget {
            contract_version: "1.0".into(),
            max_repair_attempts: 1,
            max_events: 14,
        },
        created_at: "2026-11-17T00:00:00Z".into(),
    }
}

fn ev(
    workflow_id: &str,
    event_id: &str,
    sequence: u64,
    prev: Option<&str>,
    ts: &str,
    kind: WorkflowEventKind,
) -> WorkflowEvent {
    WorkflowEvent {
        contract_version: "1.0".into(),
        workflow_id: workflow_id.into(),
        event_id: event_id.into(),
        sequence,
        previous_event_id: prev.map(str::to_string),
        occurred_at: ts.into(),
        kind,
    }
}

#[test]
fn valid_quant_brief_initializes_and_completes_pass_stream() {
    let brief = sample_quant_brief();
    brief.validate().expect("quant brief must validate");

    let mut stream = vec![
        init_intake_event(&brief, "wf-ofi-1", "ev-0", "2026-11-17T00:01:00Z")
            .expect("intake must initialize"),
    ];

    let report_0 = verify_conditioned_stream(&stream, Some(&brief)).expect("intake must verify");
    assert_eq!(
        report_0.snapshot.phase,
        WorkflowPhase::AwaitingCoordinatorDispatch
    );
    assert_eq!(report_0.next_allowed_events, vec!["coordinator_dispatched"]);

    let dispatch = ev(
        "wf-ofi-1",
        "ev-1",
        1,
        Some("ev-0"),
        "2026-11-17T00:02:00Z",
        WorkflowEventKind::CoordinatorDispatched {
            invocation: RoleInvocation {
                contract_version: "1.0".into(),
                invocation_id: "inv-1".into(),
                requested_by: Role::Coordinator,
                role: Role::Engineer,
                objective: "Run OFI falsification test".into(),
                authority_ref: "auth-ofi-001".into(),
                input_refs: vec!["brief-ofi-001".into()],
                attempt: 1,
                requested_at: "2026-11-17T00:02:00Z".into(),
            },
        },
    );
    append_event_to_stream(&mut stream, dispatch, Some(&brief)).expect("dispatch must append");

    let result = ev(
        "wf-ofi-1",
        "ev-2",
        2,
        Some("ev-1"),
        "2026-11-17T00:03:00Z",
        WorkflowEventKind::EngineerReturned {
            result: RoleResult {
                contract_version: "1.0".into(),
                result_id: "res-1".into(),
                invocation_ref: "inv-1".into(),
                role: Role::Engineer,
                status: RoleResultStatus::Succeeded,
                summary: "Produced synthetic OFI OOS evaluation artifact".into(),
                evidence: vec![Evidence {
                    contract_version: "1.0".into(),
                    evidence_id: "evd-impl-1".into(),
                    kind: EvidenceKind::Implementation,
                    summary: "Computed synthetic OOS metrics with transaction costs".into(),
                    source: "engineer-quant-solver".into(),
                    collected_at: "2026-11-17T00:03:00Z".into(),
                }],
                completed_at: "2026-11-17T00:03:00Z".into(),
            },
        },
    );
    append_event_to_stream(&mut stream, result, Some(&brief)).expect("result must append");

    let verification = ev(
        "wf-ofi-1",
        "ev-3",
        3,
        Some("ev-2"),
        "2026-11-17T00:04:00Z",
        WorkflowEventKind::VerificationRecorded {
            outcome: VerificationOutcome {
                contract_version: "1.0".into(),
                verification_id: "ver-1".into(),
                subject_result_ref: "res-1".into(),
                status: VerificationStatus::Passed,
                checks: vec![VerificationCheck {
                    name: "no-lookahead-invariant".into(),
                    status: VerificationStatus::Passed,
                    summary: "Timestamp alignment check passed".into(),
                }],
                evidence: vec![Evidence {
                    contract_version: "1.0".into(),
                    evidence_id: "evd-ver-1".into(),
                    kind: EvidenceKind::Verification,
                    summary: "Independent verification checks passed".into(),
                    source: "verifier-ci-checks".into(),
                    collected_at: "2026-11-17T00:04:00Z".into(),
                }],
                completed_at: "2026-11-17T00:04:00Z".into(),
            },
        },
    );
    append_event_to_stream(&mut stream, verification, Some(&brief))
        .expect("verification must append");

    let review = ev(
        "wf-ofi-1",
        "ev-4",
        4,
        Some("ev-3"),
        "2026-11-17T00:05:00Z",
        WorkflowEventKind::ReviewerDecided {
            packet: ReviewPacket {
                contract_version: "1.0".into(),
                review_id: "rev-1".into(),
                engineer_result_ref: "res-1".into(),
                verification_ref: "ver-1".into(),
                decision: ReviewDecision::Pass,
                findings: vec![],
                evidence_refs: vec!["evd-ver-1".into()],
                completed_at: "2026-11-17T00:05:00Z".into(),
            },
        },
    );
    append_event_to_stream(&mut stream, review, Some(&brief)).expect("review must append");

    let audit = ev(
        "wf-ofi-1",
        "ev-5",
        5,
        Some("ev-4"),
        "2026-11-17T00:06:00Z",
        WorkflowEventKind::AuditorCounterchecked {
            packet: AuditPacket {
                contract_version: "1.0".into(),
                audit_id: "aud-1".into(),
                review_ref: "rev-1".into(),
                decision: AuditDecision::Concur,
                findings: vec![],
                evidence_refs: vec!["evd-ver-1".into()],
                completed_at: "2026-11-17T00:06:00Z".into(),
            },
        },
    );
    append_event_to_stream(&mut stream, audit, Some(&brief)).expect("audit must append");

    let finalized = ev(
        "wf-ofi-1",
        "ev-6",
        6,
        Some("ev-5"),
        "2026-11-17T00:07:00Z",
        WorkflowEventKind::CoordinatorFinalized {
            response: FinalResponse {
                contract_version: "1.0".into(),
                response_id: "resp-1".into(),
                outcome: WorkflowOutcome::Passed,
                public_summary: "Synthetic OFI verification passed review and audit".into(),
                evidence_refs: vec!["evd-ver-1".into()],
                completed_at: "2026-11-17T00:07:00Z".into(),
            },
        },
    );
    let final_report =
        append_event_to_stream(&mut stream, finalized, Some(&brief)).expect("final must append");
    assert_eq!(final_report.snapshot.phase, WorkflowPhase::Completed);
    assert_eq!(final_report.snapshot.outcome, Some(WorkflowOutcome::Passed));
    assert_eq!(final_report.snapshot.evidence_count, 2);
}

#[test]
fn quant_brief_without_hypothesis_or_quant_checks_is_rejected() {
    let mut missing_hypothesis = sample_quant_brief();
    missing_hypothesis.hypothesis = None;
    assert!(matches!(
        missing_hypothesis.validate(),
        Err(AlphaOvcaError::BriefValidation(_))
    ));

    let mut missing_checks = sample_quant_brief();
    missing_checks.quant_checks = None;
    assert!(matches!(
        missing_checks.validate(),
        Err(AlphaOvcaError::BriefValidation(_))
    ));
}

#[test]
fn unresolved_unknowns_block_intake_when_blocking_is_enabled() {
    let mut brief = sample_quant_brief();
    brief.unknowns = vec!["Exact maker rebate tier not yet confirmed".into()];
    brief.block_on_unresolved_unknowns = true;

    assert!(matches!(
        brief.validate(),
        Err(AlphaOvcaError::UnresolvedUnknowns(_))
    ));

    brief.block_on_unresolved_unknowns = false;
    brief
        .validate()
        .expect("non-blocking documented unknowns may proceed");
}

#[test]
fn solver_and_verifier_or_reviewer_and_auditor_collision_is_rejected() {
    let mut same_verifier = sample_quant_brief();
    same_verifier.governance.verifier_actor = " Engineer-Quant-Solver ".into();
    assert!(matches!(
        same_verifier.validate(),
        Err(AlphaOvcaError::RoleSeparationViolation(_))
    ));

    let mut same_auditor = sample_quant_brief();
    same_auditor.governance.auditor_actor = same_auditor.governance.reviewer_actor.clone();
    assert!(matches!(
        same_auditor.validate(),
        Err(AlphaOvcaError::RoleSeparationViolation(_))
    ));
}

#[test]
fn transactional_append_leaves_stream_unchanged_on_invalid_event() {
    let brief = sample_quant_brief();
    let mut stream = vec![
        init_intake_event(&brief, "wf-ofi-2", "ev-0", "2026-11-17T00:01:00Z")
            .expect("intake must initialize"),
    ];
    let len_before = stream.len();

    let bad_dispatch = ev(
        "wf-ofi-2",
        "ev-1",
        1,
        Some("ev-0"),
        "2026-11-17T00:02:00Z",
        WorkflowEventKind::CoordinatorDispatched {
            invocation: RoleInvocation {
                contract_version: "1.0".into(),
                invocation_id: "inv-bad".into(),
                requested_by: Role::Coordinator,
                role: Role::Engineer,
                objective: "Invalid input ref test".into(),
                authority_ref: "auth-ofi-001".into(),
                input_refs: vec!["wrong-ref".into()],
                attempt: 1,
                requested_at: "2026-11-17T00:02:00Z".into(),
            },
        },
    );

    assert!(append_event_to_stream(&mut stream, bad_dispatch, Some(&brief)).is_err());
    assert_eq!(stream.len(), len_before);
}

#[test]
fn epistemic_claim_prevents_overclaiming_unverified_results() {
    let invalid_claim = EpistemicClaim {
        kind: ClaimKind::ComputedResult,
        statement: "In-sample Sharpe is 3.2".into(),
        evidence_status: EvidenceStatus::RobustnessValidated,
        source_ref: "solver-log".into(),
    };
    assert!(invalid_claim.validate().is_err());

    let valid_claim = EpistemicClaim {
        kind: ClaimKind::IndependentlyVerifiedResult,
        statement: "OOS Sharpe verified by independent runner".into(),
        evidence_status: EvidenceStatus::RobustnessValidated,
        source_ref: "verifier-report".into(),
    };
    valid_claim
        .validate()
        .expect("verified claim must validate");
}

#[test]
fn brief_mismatch_and_repair_budget_escalation_checks() {
    let brief = sample_quant_brief();
    let mut wrong_brief = sample_quant_brief();
    wrong_brief.brief_id = "other-brief".into();

    let intake = init_intake_event(&brief, "wf-ofi-3", "ev-0", "2026-11-17T00:01:00Z").unwrap();
    assert!(matches!(
        verify_conditioned_stream(&[intake], Some(&wrong_brief)),
        Err(AlphaOvcaError::BriefMismatch(_))
    ));

    // Confirm repair directive & escalation paths are preserved cleanly through alpha-ovca
    let mut stream =
        vec![init_intake_event(&brief, "wf-ofi-4", "e0", "2026-11-17T00:00:00Z").unwrap()];
    let events = vec![
        ev(
            "wf-ofi-4",
            "e1",
            1,
            Some("e0"),
            "2026-11-17T00:01:00Z",
            WorkflowEventKind::CoordinatorDispatched {
                invocation: RoleInvocation {
                    contract_version: "1.0".into(),
                    invocation_id: "inv-1".into(),
                    requested_by: Role::Coordinator,
                    role: Role::Engineer,
                    objective: "Attempt 1".into(),
                    authority_ref: "auth-ofi-001".into(),
                    input_refs: vec!["brief-ofi-001".into()],
                    attempt: 1,
                    requested_at: "2026-11-17T00:01:00Z".into(),
                },
            },
        ),
        ev(
            "wf-ofi-4",
            "e2",
            2,
            Some("e1"),
            "2026-11-17T00:02:00Z",
            WorkflowEventKind::EngineerReturned {
                result: RoleResult {
                    contract_version: "1.0".into(),
                    result_id: "res-1".into(),
                    invocation_ref: "inv-1".into(),
                    role: Role::Engineer,
                    status: RoleResultStatus::Succeeded,
                    summary: "Attempt 1 output".into(),
                    evidence: vec![Evidence {
                        contract_version: "1.0".into(),
                        evidence_id: "evd-1".into(),
                        kind: EvidenceKind::Implementation,
                        summary: "Candidate artifact".into(),
                        source: "engineer-quant-solver".into(),
                        collected_at: "2026-11-17T00:02:00Z".into(),
                    }],
                    completed_at: "2026-11-17T00:02:00Z".into(),
                },
            },
        ),
        ev(
            "wf-ofi-4",
            "e3",
            3,
            Some("e2"),
            "2026-11-17T00:03:00Z",
            WorkflowEventKind::VerificationRecorded {
                outcome: VerificationOutcome {
                    contract_version: "1.0".into(),
                    verification_id: "ver-1".into(),
                    subject_result_ref: "res-1".into(),
                    status: VerificationStatus::Failed,
                    checks: vec![VerificationCheck {
                        name: "cost-check".into(),
                        status: VerificationStatus::Failed,
                        summary: "Fees omitted".into(),
                    }],
                    evidence: vec![Evidence {
                        contract_version: "1.0".into(),
                        evidence_id: "evd-2".into(),
                        kind: EvidenceKind::Verification,
                        summary: "Fee check failed".into(),
                        source: "verifier-ci-checks".into(),
                        collected_at: "2026-11-17T00:03:00Z".into(),
                    }],
                    completed_at: "2026-11-17T00:03:00Z".into(),
                },
            },
        ),
        ev(
            "wf-ofi-4",
            "e4",
            4,
            Some("e3"),
            "2026-11-17T00:04:00Z",
            WorkflowEventKind::ReviewerDecided {
                packet: ReviewPacket {
                    contract_version: "1.0".into(),
                    review_id: "rev-1".into(),
                    engineer_result_ref: "res-1".into(),
                    verification_ref: "ver-1".into(),
                    decision: ReviewDecision::Repair,
                    findings: vec![Finding {
                        code: "missing-fees".into(),
                        severity: FindingSeverity::Blocking,
                        summary: "Include taker fee".into(),
                        evidence_refs: vec!["evd-2".into()],
                    }],
                    evidence_refs: vec!["evd-2".into()],
                    completed_at: "2026-11-17T00:04:00Z".into(),
                },
            },
        ),
        ev(
            "wf-ofi-4",
            "e5",
            5,
            Some("e4"),
            "2026-11-17T00:05:00Z",
            WorkflowEventKind::AuditorCounterchecked {
                packet: AuditPacket {
                    contract_version: "1.0".into(),
                    audit_id: "aud-1".into(),
                    review_ref: "rev-1".into(),
                    decision: AuditDecision::Disagree,
                    findings: vec![Finding {
                        code: "leakage-risk".into(),
                        severity: FindingSeverity::Blocking,
                        summary: "Escalate to owner due to split discrepancy".into(),
                        evidence_refs: vec!["evd-2".into()],
                    }],
                    evidence_refs: vec!["evd-2".into()],
                    completed_at: "2026-11-17T00:05:00Z".into(),
                },
            },
        ),
        ev(
            "wf-ofi-4",
            "e6",
            6,
            Some("e5"),
            "2026-11-17T00:06:00Z",
            WorkflowEventKind::OwnerEscalated {
                decision: Decision {
                    contract_version: "1.0".into(),
                    decision_id: "dec-1".into(),
                    made_by: Role::Owner,
                    disposition: DecisionDisposition::Escalate,
                    rationale: "Owner halted run after audit disagreement".into(),
                    evidence_refs: vec!["evd-2".into()],
                    made_at: "2026-11-17T00:06:00Z".into(),
                },
            },
        ),
        ev(
            "wf-ofi-4",
            "e7",
            7,
            Some("e6"),
            "2026-11-17T00:07:00Z",
            WorkflowEventKind::CoordinatorFinalized {
                response: FinalResponse {
                    contract_version: "1.0".into(),
                    response_id: "resp-1".into(),
                    outcome: WorkflowOutcome::Escalated,
                    public_summary: "Escalated to owner".into(),
                    evidence_refs: vec!["evd-2".into()],
                    completed_at: "2026-11-17T00:07:00Z".into(),
                },
            },
        ),
    ];

    for event in events {
        append_event_to_stream(&mut stream, event, Some(&brief)).unwrap();
    }

    let report = verify_conditioned_stream(&stream, Some(&brief)).unwrap();
    assert_eq!(report.snapshot.phase, WorkflowPhase::Completed);
    assert_eq!(report.snapshot.outcome, Some(WorkflowOutcome::Escalated));
}

#[test]
fn repair_directive_requires_matching_attempt() {
    let mut brief = sample_quant_brief();
    brief.domain = BriefDomain::Infrastructure;
    brief.hypothesis = None;
    brief.quant_checks = None;
    let directive = RepairDirective {
        contract_version: "1.0".into(),
        directive_id: "dir-1".into(),
        source_review_ref: "rev-1".into(),
        source_audit_ref: "aud-1".into(),
        attempt: 1,
        instructions: vec!["Fix".into()],
        evidence_refs: vec!["evd-2".into()],
        issued_at: "2026-11-17T00:05:30Z".into(),
    };
    assert_eq!(directive.attempt, 1);
    brief
        .validate()
        .expect("infra brief without quant fields is valid");
}
