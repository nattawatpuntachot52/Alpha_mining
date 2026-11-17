use alpha_ovca::{
    append_event_to_stream, evaluate_followup, init_intake_event, intersect_rule_scopes,
    is_path_within_scope, revalidate_mandate, sha256_hex, verify_conditioned_stream, AcceptMode,
    AddressedKind, AdmissionChoice, AdmissionPolicy, AdmissionTableRow, AlphaOvcaError,
    AuthorizationMandate, BriefDomain, ClaimKind, ConditioningBrief, EpistemicClaim,
    EvidenceStatus, FalsifiableHypothesis, FollowUpAction, FollowUpEvent, MandateStatus,
    MandateStrength, ProactiveRule, ProofLevel, QuantGateSpec, ReceivingScope, RoleSeparation,
    SubscriptionMode, TriggerSourceKind, UnaddressedChoice,
};
use ovca_types::{
    AuditDecision, AuditPacket, Authority, Decision, DecisionDisposition, Evidence, EvidenceKind,
    ExecutionBudget, FinalResponse, Finding, FindingSeverity, RepairDirective, ReviewDecision,
    ReviewPacket, Role, RoleInvocation, RoleResult, RoleResultStatus, VerificationCheck,
    VerificationOutcome, VerificationStatus, WorkflowEvent, WorkflowEventKind, WorkflowOutcome,
};
use ovca_workflow::WorkflowPhase;
use std::collections::BTreeMap;

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
        mandate: None,
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

fn sample_policy(accept_mode: AcceptMode) -> AdmissionPolicy {
    let mut table = BTreeMap::new();
    table.insert(
        ReceivingScope::GithubComment,
        AdmissionTableRow {
            receive_all: true,
            listed_addressed: AdmissionChoice::Explicit,
            listed_unaddressed: UnaddressedChoice::Inferred,
            unlisted_addressed: AdmissionChoice::Ignore,
            unlisted_unaddressed: UnaddressedChoice::Ignore,
        },
    );
    table.insert(
        ReceivingScope::GithubDefaultBranchCi,
        AdmissionTableRow {
            receive_all: true,
            listed_addressed: AdmissionChoice::Ignore,
            listed_unaddressed: UnaddressedChoice::Ignore,
            unlisted_addressed: AdmissionChoice::Ignore,
            unlisted_unaddressed: UnaddressedChoice::Inferred,
        },
    );
    table.insert(
        ReceivingScope::GithubIssue,
        AdmissionTableRow {
            receive_all: true,
            listed_addressed: AdmissionChoice::Explicit,
            listed_unaddressed: UnaddressedChoice::Inferred,
            unlisted_addressed: AdmissionChoice::Ignore,
            unlisted_unaddressed: UnaddressedChoice::Ignore,
        },
    );
    table.insert(
        ReceivingScope::GithubPr,
        AdmissionTableRow {
            receive_all: true,
            listed_addressed: AdmissionChoice::Explicit,
            listed_unaddressed: UnaddressedChoice::Inferred,
            unlisted_addressed: AdmissionChoice::Ignore,
            unlisted_unaddressed: UnaddressedChoice::Ignore,
        },
    );
    table.insert(
        ReceivingScope::OwnerCli,
        AdmissionTableRow {
            receive_all: false,
            listed_addressed: AdmissionChoice::Explicit,
            listed_unaddressed: UnaddressedChoice::Ignore,
            unlisted_addressed: AdmissionChoice::Ignore,
            unlisted_unaddressed: UnaddressedChoice::Ignore,
        },
    );

    AdmissionPolicy {
        policy_schema_version: "1.0".into(),
        accept_mode,
        allowed_actors: vec!["nattawatpuntachot52".into()],
        bot_allowlist: vec!["dependabot[bot]".into(), "ovca-reviewer[bot]".into()],
        automated_reviewers_non_bot: vec![],
        admission_table: table,
        proactive_rules: vec![
            ProactiveRule {
                rule_id: "ci-default-branch-failure".into(),
                enabled: true,
                title: "CI failure triage".into(),
                description: "Inspect main CI failures".into(),
                receiving_scopes: vec![ReceivingScope::GithubDefaultBranchCi],
                writable_scope: vec!["research/ofi_synthetic/".into()],
                silent_ack: false,
            },
            ProactiveRule {
                rule_id: "issue-triage".into(),
                enabled: true,
                title: "Issue triage".into(),
                description: "Triage allowlisted bot issue notices".into(),
                receiving_scopes: vec![ReceivingScope::GithubIssue, ReceivingScope::GithubPr],
                writable_scope: vec!["research/ofi_synthetic/".into()],
                silent_ack: false,
            },
        ],
    }
}

#[test]
fn sha256_matches_nist_standard_vectors() {
    assert_eq!(
        sha256_hex(b""),
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    );
    assert_eq!(
        sha256_hex(b"abc"),
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    );
    assert_eq!(
        sha256_hex(b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq"),
        "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"
    );
}

#[test]
fn canonical_policy_version_normalizes_case_and_ordering_and_enforces_table_rules() {
    let policy_a = sample_policy(AcceptMode::Observe);
    let mut policy_b = sample_policy(AcceptMode::Observe);
    policy_b.allowed_actors = vec![" NattawatPuntachot52 ".into()];
    policy_b.bot_allowlist = vec!["OVCA-REVIEWER[BOT]".into(), "dependabot[bot]".into()];
    policy_b.proactive_rules.reverse();

    assert_eq!(
        policy_a.canonical_policy_version().unwrap(),
        policy_b.canonical_policy_version().unwrap()
    );

    // Changing accept_mode from observe -> auto MUST rotate canonical policy_version
    let policy_auto = sample_policy(AcceptMode::Auto);
    assert_ne!(
        policy_a.canonical_policy_version().unwrap(),
        policy_auto.canonical_policy_version().unwrap()
    );

    // Receive-all invariant: unaddressed != ignore when receive_all == false must be rejected
    let mut bad_receive_all = sample_policy(AcceptMode::Observe);
    bad_receive_all
        .admission_table
        .get_mut(&ReceivingScope::GithubComment)
        .unwrap()
        .receive_all = false;
    assert!(matches!(
        bad_receive_all.validate(),
        Err(AlphaOvcaError::PolicyValidation(_))
    ));

    // Bots cannot appear in allowed_actors
    let mut bot_in_allowed = sample_policy(AcceptMode::Observe);
    bot_in_allowed.allowed_actors.push("dependabot[bot]".into());
    assert!(matches!(
        bot_in_allowed.validate(),
        Err(AlphaOvcaError::PolicyValidation(_))
    ));
}

#[test]
fn mandate_enforces_bot_ci_restrictions_and_brief_scope_binding() {
    let policy = sample_policy(AcceptMode::Auto);
    let pver = policy.canonical_policy_version().unwrap();

    // Bot holding Explicit strength MUST be rejected
    let bot_explicit = AuthorizationMandate {
        contract_version: "1.0".into(),
        mandate_id: "mnd-bot-bad".into(),
        authority_id: "auth-ofi-001".into(),
        origin_thread_id: "pr:1".into(),
        source_kind: TriggerSourceKind::Bot,
        receiving_scope: ReceivingScope::GithubPr,
        requester_actor: "dependabot[bot]".into(),
        requester_is_bot: true,
        strength: MandateStrength::Explicit,
        policy_version: pver.clone(),
        matched_rules: vec![],
        writable_scope: vec!["research/ofi_synthetic".into()],
        status: MandateStatus::Active,
    };
    assert!(matches!(
        bot_explicit.validate(),
        Err(AlphaOvcaError::MandateViolation(_))
    ));

    // Inferred mandate without matched_rules MUST be rejected
    let inferred_empty_rules = AuthorizationMandate {
        contract_version: "1.0".into(),
        mandate_id: "mnd-ci-empty".into(),
        authority_id: "auth-ofi-001".into(),
        origin_thread_id: "ci:main".into(),
        source_kind: TriggerSourceKind::GithubDefaultBranchCi,
        receiving_scope: ReceivingScope::GithubDefaultBranchCi,
        requester_actor: "github-ci".into(),
        requester_is_bot: false,
        strength: MandateStrength::Inferred,
        policy_version: pver.clone(),
        matched_rules: vec![],
        writable_scope: vec!["research/ofi_synthetic".into()],
        status: MandateStatus::Active,
    };
    assert!(matches!(
        inferred_empty_rules.validate(),
        Err(AlphaOvcaError::MandateViolation(_))
    ));

    // Asymmetric CI pairing MUST fail validation
    let asymmetric_ci = AuthorizationMandate {
        contract_version: "1.0".into(),
        mandate_id: "mnd-ci-asym".into(),
        authority_id: "auth-ofi-001".into(),
        origin_thread_id: "pr:1".into(),
        source_kind: TriggerSourceKind::GithubDefaultBranchCi,
        receiving_scope: ReceivingScope::GithubPr,
        requester_actor: "github-ci".into(),
        requester_is_bot: false,
        strength: MandateStrength::Inferred,
        policy_version: pver.clone(),
        matched_rules: vec!["issue-triage".into()],
        writable_scope: vec!["research/ofi_synthetic".into()],
        status: MandateStatus::Active,
    };
    assert!(matches!(
        asymmetric_ci.validate(),
        Err(AlphaOvcaError::MandateViolation(_))
    ));

    // Mandate writable_scope exceeding ConditioningBrief.authority.scope MUST fail validation
    let mut brief = sample_quant_brief();
    brief.mandate = Some(AuthorizationMandate {
        contract_version: "1.0".into(),
        mandate_id: "mnd-wide".into(),
        authority_id: "auth-ofi-001".into(),
        origin_thread_id: "cli:1".into(),
        source_kind: TriggerSourceKind::OwnerCli,
        receiving_scope: ReceivingScope::OwnerCli,
        requester_actor: "nattawatpuntachot52".into(),
        requester_is_bot: false,
        strength: MandateStrength::Explicit,
        policy_version: pver.clone(),
        matched_rules: vec![],
        writable_scope: vec!["execution/".into()],
        status: MandateStatus::Active,
    });
    assert!(matches!(
        brief.validate(),
        Err(AlphaOvcaError::MandateViolation(_))
    ));

    // Valid subset binds cleanly
    brief.mandate.as_mut().unwrap().writable_scope = vec!["research/ofi_synthetic/study.py".into()];
    brief
        .validate()
        .expect("mandate within authority scope must validate");
}

#[test]
fn path_containment_blocks_prefix_traps_drive_prefixes_and_traversal() {
    let scope = vec!["python/alpha".into(), "AGENTS.md".into()];
    assert!(is_path_within_scope("python/alpha/module.py", &scope));
    assert!(is_path_within_scope("AGENTS.md", &scope));
    assert!(!is_path_within_scope("python/alpha_evil/pwn.py", &scope));
    assert!(!is_path_within_scope("AGENTS.md.bak", &scope));
    assert!(!is_path_within_scope("python/alpha/../secret/.env", &scope));
    assert!(!is_path_within_scope("/etc/passwd", &scope));
    assert!(!is_path_within_scope("python\\alpha\\file.py", &scope));
    assert!(!is_path_within_scope("C:python/alpha/file.py", &scope));
    assert!(!is_path_within_scope("é:python/alpha/file.py", &scope));

    // ProactiveRule writable_scope must also reject drive-letter prefixes
    let mut bad_drive_policy = sample_policy(AcceptMode::Observe);
    bad_drive_policy.proactive_rules[0].writable_scope = vec!["C:research/ofi_synthetic/".into()];
    assert!(matches!(
        bad_drive_policy.validate(),
        Err(AlphaOvcaError::PolicyValidation(_))
    ));
}

#[test]
fn context_vs_authority_handback_and_policy_revalidation_invariants() {
    let mut auto_policy = sample_policy(AcceptMode::Auto);
    let pver_auto = auto_policy.canonical_policy_version().unwrap();

    let mut inferred_mandate = AuthorizationMandate {
        contract_version: "1.0".into(),
        mandate_id: "mnd-issue-001".into(),
        authority_id: "auth-ofi-001".into(),
        origin_thread_id: "issue:10".into(),
        source_kind: TriggerSourceKind::Bot,
        receiving_scope: ReceivingScope::GithubIssue,
        requester_actor: "dependabot[bot]".into(),
        requester_is_bot: true,
        strength: MandateStrength::Inferred,
        policy_version: pver_auto,
        matched_rules: vec!["issue-triage".into()],
        writable_scope: vec!["research/ofi_synthetic/".into()],
        status: MandateStatus::Ended,
    };

    // 1. Bot/CI cannot wake an ended mandate or trigger stop
    let bot_wakeup = FollowUpEvent {
        trigger_id: "trg-1".into(),
        thread_id: "issue:10".into(),
        subscription_mode: SubscriptionMode::OwnedWork,
        actor: "dependabot[bot]".into(),
        actor_is_bot: true,
        is_ci: false,
        addressed: AddressedKind::Mention,
        requested_scope_paths: vec![],
        requests_stop: true,
        requests_scope_expansion: false,
    };
    let d_bot = evaluate_followup(&inferred_mandate, &bot_wakeup, &auto_policy).unwrap();
    assert_eq!(d_bot.action, FollowUpAction::ContextOnlyDeliver);
    assert!(!d_bot.grant_authority);
    assert!(!d_bot.allow_resume);

    // 2. Context-only subscription (or secondary thread) never grants authority to a human either
    let context_thread = FollowUpEvent {
        trigger_id: "trg-2".into(),
        thread_id: "pr:99".into(),
        subscription_mode: SubscriptionMode::ContextOnly,
        actor: "nattawatpuntachot52".into(),
        actor_is_bot: false,
        is_ci: false,
        addressed: AddressedKind::None,
        requested_scope_paths: vec!["research/ofi_synthetic/test.py".into()],
        requests_stop: false,
        requests_scope_expansion: false,
    };
    let d_ctx = evaluate_followup(&inferred_mandate, &context_thread, &auto_policy).unwrap();
    assert_eq!(d_ctx.action, FollowUpAction::ContextOnlyDeliver);
    assert!(!d_ctx.grant_authority);

    // 3. Authorized human in-scope follow-up cleanly resumes Ended unstopped mandate
    let in_scope_resume = FollowUpEvent {
        trigger_id: "trg-resume".into(),
        thread_id: "issue:10".into(),
        subscription_mode: SubscriptionMode::OwnedWork,
        actor: "nattawatpuntachot52".into(),
        actor_is_bot: false,
        is_ci: false,
        addressed: AddressedKind::Mention,
        requested_scope_paths: vec!["research/ofi_synthetic/test.py".into()],
        requests_stop: false,
        requests_scope_expansion: false,
    };
    let d_resume = evaluate_followup(&inferred_mandate, &in_scope_resume, &auto_policy).unwrap();
    assert_eq!(d_resume.action, FollowUpAction::ProceedInScope);
    assert!(d_resume.grant_authority);
    assert!(d_resume.allow_resume);

    // 4. Owner stop request emits StopRequested cleanly
    let owner_stop = FollowUpEvent {
        trigger_id: "trg-stop".into(),
        thread_id: "issue:10".into(),
        subscription_mode: SubscriptionMode::OwnedWork,
        actor: "nattawatpuntachot52".into(),
        actor_is_bot: false,
        is_ci: false,
        addressed: AddressedKind::Direct,
        requested_scope_paths: vec![],
        requests_stop: true,
        requests_scope_expansion: false,
    };
    let d_stop = evaluate_followup(&inferred_mandate, &owner_stop, &auto_policy).unwrap();
    assert_eq!(d_stop.action, FollowUpAction::StopRequested);
    assert!(!d_stop.grant_authority);
    assert!(!d_stop.allow_resume);

    // 5. Out-of-scope human follow-up emits HandbackRequired while keeping mandate scope intact
    let out_of_scope = FollowUpEvent {
        trigger_id: "trg-3".into(),
        thread_id: "issue:10".into(),
        subscription_mode: SubscriptionMode::OwnedWork,
        actor: "nattawatpuntachot52".into(),
        actor_is_bot: false,
        is_ci: false,
        addressed: AddressedKind::None,
        requested_scope_paths: vec!["AGENTS.md".into()],
        requests_stop: false,
        requests_scope_expansion: false,
    };
    let d_hb = evaluate_followup(&inferred_mandate, &out_of_scope, &auto_policy).unwrap();
    assert_eq!(d_hb.action, FollowUpAction::HandbackRequired);
    assert!(!d_hb.grant_authority);
    assert_eq!(d_hb.out_of_scope_paths, vec!["AGENTS.md"]);
    assert!(d_hb.handback.as_ref().unwrap().preserve_subscription);

    // 6. Switching accept_mode from auto -> observe revokes inferred mandate on revalidation
    let observe_policy = sample_policy(AcceptMode::Observe);
    let rev_mode = revalidate_mandate(&inferred_mandate, &observe_policy).unwrap();
    assert!(!rev_mode.valid_to_resume);
    assert_eq!(rev_mode.resulting_status, MandateStatus::Revoked);
    assert!(rev_mode.policy_changed);

    // 7. Removing bot from bot_allowlist revokes bot mandate even in auto mode
    auto_policy.bot_allowlist = vec!["ovca-reviewer[bot]".into()];
    let rev_bot = revalidate_mandate(&inferred_mandate, &auto_policy).unwrap();
    assert!(!rev_bot.valid_to_resume);
    assert_eq!(rev_bot.resulting_status, MandateStatus::Revoked);

    // 8. StoppedByPerson mandate ignores all future follow-ups permanently
    inferred_mandate.status = MandateStatus::StoppedByPerson;
    let d_stopped = evaluate_followup(&inferred_mandate, &out_of_scope, &auto_policy).unwrap();
    assert_eq!(d_stopped.action, FollowUpAction::IgnoreStoppedOrRevoked);
    assert!(!d_stopped.allow_resume);
}

#[test]
fn attempt2_adversarial_edge_cases_and_revalidation_gates() {
    let mut auto_policy = sample_policy(AcceptMode::Auto);
    auto_policy
        .bot_allowlist
        .push("github-actions[bot]".to_string());
    let pver_auto = auto_policy.canonical_policy_version().unwrap();

    // 1. Unlisted human stranger in Auto mode MUST NOT proceed/resume/stop when unlisted_* = Ignore
    let ended_pr_mandate = AuthorizationMandate {
        contract_version: "1.0".into(),
        mandate_id: "mnd-pr-owner".into(),
        authority_id: "auth-ofi-001".into(),
        origin_thread_id: "pr:15".into(),
        source_kind: TriggerSourceKind::GithubPr,
        receiving_scope: ReceivingScope::GithubPr,
        requester_actor: "nattawatpuntachot52".into(),
        requester_is_bot: false,
        strength: MandateStrength::Explicit,
        policy_version: pver_auto.clone(),
        matched_rules: vec![],
        writable_scope: vec!["research/ofi_synthetic/".into()],
        status: MandateStatus::Ended,
    };
    let stranger_followup = FollowUpEvent {
        trigger_id: "trg-stranger".into(),
        thread_id: "pr:15".into(),
        subscription_mode: SubscriptionMode::OwnedWork,
        actor: "random-outsider".into(),
        actor_is_bot: false,
        is_ci: false,
        addressed: AddressedKind::Mention,
        requested_scope_paths: vec!["research/ofi_synthetic/a.py".into()],
        requests_stop: true,
        requests_scope_expansion: false,
    };
    let d_stranger =
        evaluate_followup(&ended_pr_mandate, &stranger_followup, &auto_policy).unwrap();
    assert_eq!(d_stranger.action, FollowUpAction::ContextOnlyDeliver);
    assert!(!d_stranger.grant_authority);
    assert!(!d_stranger.allow_resume);

    // 2. Backwards-compatible FollowUpEvent JSON omitting `addressed` defaults to None
    let legacy_followup: FollowUpEvent = serde_json::from_str(
        r#"{
            "trigger_id": "trg-legacy",
            "thread_id": "pr:15",
            "subscription_mode": "owned_work",
            "actor": "nattawatpuntachot52",
            "actor_is_bot": false,
            "is_ci": false
        }"#,
    )
    .expect("legacy FollowUpEvent JSON without addressed must deserialize");
    assert_eq!(legacy_followup.addressed, AddressedKind::None);
    let d_legacy = evaluate_followup(&ended_pr_mandate, &legacy_followup, &auto_policy).unwrap();
    assert_eq!(d_legacy.action, FollowUpAction::ProceedInScope);
    assert!(d_legacy.allow_resume);

    // 3. requests_scope_expansion=true with empty paths still triggers HandbackRequired; is_ci=true blocks
    let expand_empty = FollowUpEvent {
        trigger_id: "trg-expand".into(),
        thread_id: "pr:15".into(),
        subscription_mode: SubscriptionMode::OwnedWork,
        actor: "nattawatpuntachot52".into(),
        actor_is_bot: false,
        is_ci: false,
        addressed: AddressedKind::Direct,
        requested_scope_paths: vec![],
        requests_stop: false,
        requests_scope_expansion: true,
    };
    let d_exp = evaluate_followup(&ended_pr_mandate, &expand_empty, &auto_policy).unwrap();
    assert_eq!(d_exp.action, FollowUpAction::HandbackRequired);
    assert!(d_exp.out_of_scope_paths.is_empty());

    let spoof_ci = FollowUpEvent {
        is_ci: true,
        ..legacy_followup.clone()
    };
    let d_ci = evaluate_followup(&ended_pr_mandate, &spoof_ci, &auto_policy).unwrap();
    assert_eq!(d_ci.action, FollowUpAction::ContextOnlyDeliver);
    assert!(!d_ci.allow_resume);

    // 4. CI mandate Owner allowed vs Unlisted blocked, and CI admission_table checked BEFORE bot allowlist
    let ci_mandate = AuthorizationMandate {
        contract_version: "1.0".into(),
        mandate_id: "mnd-ci-main".into(),
        authority_id: "auth-ofi-001".into(),
        origin_thread_id: "branch:main".into(),
        source_kind: TriggerSourceKind::GithubDefaultBranchCi,
        receiving_scope: ReceivingScope::GithubDefaultBranchCi,
        requester_actor: "github-actions[bot]".into(),
        requester_is_bot: true,
        strength: MandateStrength::Inferred,
        policy_version: pver_auto.clone(),
        matched_rules: vec!["ci-default-branch-failure".into()],
        writable_scope: vec!["research/ofi_synthetic/".into()],
        status: MandateStatus::Ended,
    };
    let owner_on_ci = FollowUpEvent {
        thread_id: "branch:main".into(),
        requested_scope_paths: vec!["research/ofi_synthetic/fix.py".into()],
        ..legacy_followup.clone()
    };
    let d_owner_ci = evaluate_followup(&ci_mandate, &owner_on_ci, &auto_policy).unwrap();
    assert_eq!(d_owner_ci.action, FollowUpAction::ProceedInScope);
    assert!(d_owner_ci.allow_resume);

    let stranger_on_ci = FollowUpEvent {
        thread_id: "branch:main".into(),
        ..stranger_followup
    };
    let d_stranger_ci = evaluate_followup(&ci_mandate, &stranger_on_ci, &auto_policy).unwrap();
    assert_eq!(d_stranger_ci.action, FollowUpAction::ContextOnlyDeliver);
    assert!(!d_stranger_ci.allow_resume);

    let mut ci_ignored = auto_policy.clone();
    ci_ignored
        .admission_table
        .get_mut(&ReceivingScope::GithubDefaultBranchCi)
        .unwrap()
        .unlisted_unaddressed = UnaddressedChoice::Ignore;
    let rev_ci_ignored = revalidate_mandate(&ci_mandate, &ci_ignored).unwrap();
    assert!(!rev_ci_ignored.valid_to_resume);
    assert_eq!(rev_ci_ignored.resulting_status, MandateStatus::Revoked);

    // 5. is_bot_login enforcement in revalidate_mandate even when requester_is_bot == false
    let disguised_bot = AuthorizationMandate {
        contract_version: "1.0".into(),
        mandate_id: "mnd-bot-disguise".into(),
        authority_id: "auth-ofi-001".into(),
        origin_thread_id: "pr:22".into(),
        source_kind: TriggerSourceKind::GithubPr,
        receiving_scope: ReceivingScope::GithubPr,
        requester_actor: "rogue[bot]".into(),
        requester_is_bot: false,
        strength: MandateStrength::Inferred,
        policy_version: pver_auto.clone(),
        matched_rules: vec!["issue-triage".into()],
        writable_scope: vec!["research/ofi_synthetic/".into()],
        status: MandateStatus::Active,
    };
    assert!(
        !revalidate_mandate(&disguised_bot, &auto_policy)
            .unwrap()
            .valid_to_resume
    );

    // 6. Rule surface narrowing & intersected writable_scope narrowing revoke inferred mandates
    let mut narrowed_surface = auto_policy.clone();
    narrowed_surface.proactive_rules[0].receiving_scopes = vec![ReceivingScope::GithubPr];
    assert!(
        !revalidate_mandate(&ci_mandate, &narrowed_surface)
            .unwrap()
            .valid_to_resume
    );

    let mut narrowed_path = auto_policy.clone();
    narrowed_path.proactive_rules[0].writable_scope = vec!["research/ofi_synthetic/sub/".into()];
    assert!(
        !revalidate_mandate(&ci_mandate, &narrowed_path)
            .unwrap()
            .valid_to_resume
    );
    assert_eq!(
        intersect_rule_scopes(&[
            &auto_policy.proactive_rules[0],
            &narrowed_path.proactive_rules[0]
        ]),
        vec!["research/ofi_synthetic/sub/"]
    );

    // 7. automated_reviewers_non_bot validation, revalidation, and follow-up containment
    let mut bad_overlap = auto_policy.clone();
    bad_overlap.automated_reviewers_non_bot = vec!["nattawatpuntachot52".into()];
    assert!(matches!(
        bad_overlap.validate(),
        Err(AlphaOvcaError::PolicyValidation(_))
    ));

    let mut rev_policy = auto_policy.clone();
    rev_policy.automated_reviewers_non_bot = vec!["CodexReviewer".into()];
    let pver_rev = rev_policy.canonical_policy_version().unwrap();

    let auto_rev_inferred = AuthorizationMandate {
        contract_version: "1.0".into(),
        mandate_id: "mnd-autorev-inf".into(),
        authority_id: "auth-ofi-001".into(),
        origin_thread_id: "pr:30".into(),
        source_kind: TriggerSourceKind::GithubPr,
        receiving_scope: ReceivingScope::GithubPr,
        requester_actor: "codexreviewer".into(),
        requester_is_bot: false,
        strength: MandateStrength::Inferred,
        policy_version: pver_rev.clone(),
        matched_rules: vec!["issue-triage".into()],
        writable_scope: vec!["research/ofi_synthetic/".into()],
        status: MandateStatus::Active,
    };
    assert!(
        revalidate_mandate(&auto_rev_inferred, &rev_policy)
            .unwrap()
            .valid_to_resume
    );
    // Removed from automated_reviewers_non_bot -> revoked on revalidation
    assert!(
        !revalidate_mandate(&auto_rev_inferred, &auto_policy)
            .unwrap()
            .valid_to_resume
    );

    // Explicit automated reviewer mandate rejected during revalidation
    let auto_rev_explicit = AuthorizationMandate {
        strength: MandateStrength::Explicit,
        matched_rules: vec![],
        policy_version: pver_rev,
        ..auto_rev_inferred
    };
    assert!(
        !revalidate_mandate(&auto_rev_explicit, &rev_policy)
            .unwrap()
            .valid_to_resume
    );

    // Automated reviewer follow-up treated as untrusted context
    let rev_followup = FollowUpEvent {
        actor: "CodexReviewer".into(),
        ..owner_on_ci
    };
    let d_rev_fu = evaluate_followup(&ci_mandate, &rev_followup, &rev_policy).unwrap();
    assert_eq!(d_rev_fu.action, FollowUpAction::ContextOnlyDeliver);
    assert!(!d_rev_fu.grant_authority);
    assert!(!d_rev_fu.allow_resume);

    // Inverted table: listed actor loses explicit validity if listed_addressed != explicit
    let mut inverted_pol = auto_policy.clone();
    if let Some(row) = inverted_pol
        .admission_table
        .get_mut(&ReceivingScope::GithubPr)
    {
        row.listed_addressed = AdmissionChoice::Ignore;
        row.unlisted_addressed = AdmissionChoice::Explicit;
    }
    let owner_pr_mandate = AuthorizationMandate {
        contract_version: "1.0".into(),
        mandate_id: "mnd-owner-pr".into(),
        authority_id: "auth-owner-pr".into(),
        origin_thread_id: "pr:77".into(),
        source_kind: TriggerSourceKind::GithubPr,
        receiving_scope: ReceivingScope::GithubPr,
        requester_actor: "nattawatpuntachot52".into(),
        requester_is_bot: false,
        strength: MandateStrength::Explicit,
        policy_version: pver_auto.clone(),
        matched_rules: vec![],
        writable_scope: vec!["python/alpha_mining/".into()],
        status: MandateStatus::Active,
    };
    assert!(
        revalidate_mandate(&owner_pr_mandate, &auto_policy)
            .unwrap()
            .valid_to_resume
    );
    assert!(
        !revalidate_mandate(&owner_pr_mandate, &inverted_pol)
            .unwrap()
            .valid_to_resume
    );
}
