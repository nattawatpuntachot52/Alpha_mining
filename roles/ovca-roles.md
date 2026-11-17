# OVCA v1.0 Role Mapping in Alpha_mining

`Alpha_mining` uses `nattawatpuntachot52/ovca-reference` (Contract Version `1.0`) as the deterministic workflow control plane without modifying OVCA's wire schema.

## How Conditioner Fits Into OVCA v1.0

`ovca-reference` defines 5 fixed wire roles (`owner`, `coordinator`, `engineer`, `reviewer`, `auditor`).
**Conditioner** operates as the **Pre-Intake Gatekeeper + Coordinator Governance Persona**:

```text
Owner (User / Trader)
  │  raw objective / hypothesis / question
  ▼
Conditioner (Pre-Intake Gate + Critical Thinking Partner)
  │  validates ConditioningBrief (Inputs, Outputs, Constraints, Unknowns,
  │  Falsifiable Hypothesis, Economic Rationale, Solver≠Verifier isolation)
  ▼
OVCA v1.0 Workflow Stream (enforced by ovca-workflow::WorkflowReducer)
  ├─ 0. IntakeAccepted (Owner Authority + ExecutionBudget)
  ├─ 1. CoordinatorDispatched (Coordinator → Engineer, exact input_ref)
  ├─ 2. EngineerReturned (Engineer / Solver → Result + Evidence)
  ├─ 3. VerificationRecorded (Independent Verifier → Checks + Evidence)
  ├─ 4. ReviewerDecided (Reviewer → pass | repair with blocking findings)
  ├─ 5. AuditorCounterchecked (Auditor → concur | disagree)
  └─ 6. Branch:
       ├─ pass + concur      → CoordinatorFinalized(passed)
       ├─ repair + concur    → RepairDirected (if budget remains) → loop to step 1
       └─ disagree / budget  → OwnerEscalated → CoordinatorFinalized(escalated)
```

## Role Responsibilities & Isolation Rules

| Role | Wire Value (`ovca_types::Role`) | Primary Responsibility | Strict Isolation / Prohibited Actions |
|---|---|---|---|
| **Owner** | `owner` | Sets objective, authority, scope, constraints, and `ExecutionBudget`. Resolves `OwnerEscalated`. | Does not bypass verification or edit evidence retroactively. |
| **Conditioner** | *(Pre-intake / Meta-governance)* | Challenges assumptions, exposes Unknowns, checks Research/Quant Gates via `ConditioningBrief`, supervises Coordinator & Thai concise communication. | Never fabricates data/results or passes unverified claims. |
| **Coordinator** | `coordinator` | Accepts conditioned intake (`IntakeAccepted`), dispatches `Engineer` (`CoordinatorDispatched`), manages bounded `RepairDirected`, emits `CoordinatorFinalized`. | Cannot self-author `Engineer` evidence or override `Auditor` disagreement. |
| **Engineer** | `engineer` | **Solver / Implementer**: builds artifact/analysis/backtest/code, emits `RoleResult` + implementation `Evidence`. | Cannot act as `Verifier`, `Reviewer`, or `Auditor` on its own candidate (`solver_actor != verifier_actor / reviewer_actor / auditor_actor`). |
| **Reviewer** | `reviewer` | **Independent Evaluator**: inspects `RoleResult` + `VerificationOutcome`; outputs `ReviewPacket` (`pass` or `repair`). | Cannot pass a failed `RoleResult` or failed `VerificationOutcome` (enforced by `WorkflowReducer`); `repair` requires >= 1 blocking finding. |
| **Auditor** | `auditor` | **Adversarial Counterchecker**: challenges `ReviewPacket` and cited `Evidence`; outputs `AuditPacket` (`concur` or `disagree`). | `disagree` requires >= 1 finding and forces `OwnerEscalated`; must be independent from `Engineer` and `Reviewer` (`auditor_actor != reviewer_actor`). |

## Budget Invariant (from OVCA v1.0)

`ExecutionBudget.max_events >= 8 + (6 * max_repair_attempts)`
- Ensures every declared repair cycle leaves room for `OwnerEscalated` + `CoordinatorFinalized`.
- Enforced identically by `ovca_types::ExecutionBudget::validate` and `alpha-ovca`.
