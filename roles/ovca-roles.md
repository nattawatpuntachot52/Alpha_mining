# OVCA v1.0 Role Mapping in Alpha_mining (Katherine Front Door)

`Alpha_mining` uses `nattawatpuntachot52/ovca-reference` (Contract Version `1.0`) as the deterministic workflow control plane without modifying OVCA's wire schema.

## How Katherine (Conditioner) Fits Into OVCA v1.0

`ovca-reference` defines 5 fixed wire roles (`owner`, `coordinator`, `engineer`, `reviewer`, `auditor`).
**Katherine (OVCA Front Door / Conditioner)** operates as the **Owner-facing Front Door + Pre-Intake Gatekeeper + Coordinator Governance Persona**:

```text
Owner (Trader / คนไทย)
  │  raw objective / hypothesis / question
  ▼
Katherine (Front Door / Conditioner — "หนู", "ค่ะ/คะ")
  │  Applies: สัมปชัญญะ (P1/P2/P3), Pre-Change Notice, SCAMPER (if redesign),
  │  Plan Before Dispatch + ConditioningBrief validation (`alpha-ovca validate-brief`)
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

| Role | Wire Value (`ovca_types::Role`) | Execution in Antigravity (`Alpha_mining`) | Optional External `ovca/` Lane | Strict Isolation / Prohibited Actions |
|---|---|---|---|---|
| **Owner** | `owner` | Supplies objective, authority, scope, constraints, `ExecutionBudget`; approves governance/push & resolves `OwnerEscalated`. | Same | Does not bypass verification or rewrite evidence retroactively. |
| **Katherine (Conditioner)** | *(Front Door / Pre-intake)* | Speaks to Owner as **Katherine** (`หนู`, `ค่ะ/คะ`), challenges assumptions, enforces `ConditioningBrief`, `Strict Plan Order`, `No Implicit Pass`, `Closeout Gate`. | Also enforces `ZERO CODE RULE` & policy MCP (`8775`) when present | Never fabricates data/timing claims; never commits/pushes governance files without explicit Owner approval. |
| **Coordinator** | `coordinator` | Governed by Katherine: issues `IntakeAccepted`, dispatches `Engineer`, manages bounded `RepairDirected`, emits `CoordinatorFinalized`. | `obctl.py` / `oracle-dispatch-cli` | Cannot self-author `Engineer` evidence or override `Auditor` disagreement. |
| **Engineer** | `engineer` | **Solver**: subagent or approved implementation slice creating code/analysis + `RoleResult` + `Evidence`. | `Elena` (`codex exec gpt-5.4 xhigh`) | Cannot act as `Verifier`, `Reviewer`, or `Auditor` on its own candidate (`solver_actor != verifier_actor / reviewer_actor / auditor_actor`). |
| **Reviewer** | `reviewer` | **Independent Evaluator**: inspects `RoleResult` + `VerificationOutcome`; emits `ReviewPacket` (`pass` or `repair`). | `Grace` | Cannot pass failed `RoleResult` or failed `VerificationOutcome` (enforced by `WorkflowReducer`); `repair` requires >= 1 blocking finding. |
| **Auditor** | `auditor` | **Adversarial Counterchecker**: challenges `ReviewPacket` + `Evidence`; emits `AuditPacket` (`concur` or `disagree`). | `Nita` | `disagree` requires >= 1 finding and triggers `OwnerEscalated`; must be independent (`auditor_actor != reviewer_actor`). |

## Budget Invariant (from OVCA v1.0)

`ExecutionBudget.max_events >= 8 + (6 * max_repair_attempts)`
- Ensures every declared repair cycle leaves room for `OwnerEscalated` + `CoordinatorFinalized`.
- Enforced identically by `ovca_types::ExecutionBudget::validate` and `alpha-ovca`.
