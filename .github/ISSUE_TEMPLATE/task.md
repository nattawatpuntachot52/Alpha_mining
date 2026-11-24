---
name: Bounded Task & Quant Experiment Brief (Medium / High-Impact)
about: Canonical work-item brief for medium or high-impact engineering features, workflows, or quant research experiments (not required for trivial fixes).
title: "[TASK] "
labels: []
assignees: []
---

> **Minimum Sufficient Collaboration:** ใช้ template นี้เฉพาะงานขนาดกลาง–ใหญ่ (Feature, Quant Research Experiment, Backtest/Factory change, Governance/Workflow change, หรือ Multi-PR work) **ไม่บังคับกับงานเล็กหรือแก้บั๊กจุดเดียวค่ะ**

## Outcome
- Describe the observable result that must be true when this task is accepted:

## Canonical Source
- **Repository:** `nattawatpuntachot52/Alpha_mining`
- **Relevant Paths / Modules:**
- **Starting Branch / Commit SHA:**

## Ownership
- **Accountable Human Owner:** `@nattawatpuntachot52`
- **Execution Lead:**
- **Independent Reviewer / Auditor:** (`OVCA Reviewer Bot` App ID `5800517` + Owner merge)

## Scope & Permissions
- **Allowed Read Paths / Data Sources:**
- **Allowed Write Paths (`writable_scope`):**
- **Explicitly Excluded Paths / Prohibited Actions:** (e.g., never touch live production `bot.py`, never commit `*.parquet`/`*.tar.zst`/secrets, no direct push to `main`, no unapproved `AGENTS.md`/`roles/` edits)
- **Allowed Tools / Environments:**

## Quant Research Gate *(Fill only for Strategy / Signal / Backtest tasks; omit for pure infra)*
- **Falsifiable Hypothesis:**
- **Economic Rationale:**
- **Alternative Explanations / Risks (Overfitting, Leakage, Fees/Funding, Regime Shift):**
- **Rejection Criteria:** (e.g., Liquidation = true, Max MTM DD > 40%, fails strict_cross fill sensitivity)

## Acceptance Criteria
- [ ] Criterion 1 (observable & testable)
- [ ] Criterion 2 (`cargo test/clippy/fmt` + `python3 -m unittest` + `pr_audit.py` pass on head revision)
- [ ] PR opened with valid `AGENT_ACK` and passes live `required_approving_review_count = 1`

## Risk & Resource Boundary
- **Risk Level:** `Low` | `Medium` | `High`
- **Reason (if Medium/High):**
- **Resource / Time / Retry Limit:**

## Expected Evidence
- Changed paths & commit SHA
- Exact verification commands run and actual results (pass / fail / not run)
- Backtest / dashboard / manifest artifacts (no raw binary commits; Drive Vault manifest if large)
- ADR under `docs/decisions/` if material architectural or quant-gate decision

## Stop Conditions
- Stop and request explicit owner decision if writable scope must expand, governance files require edits, data/credentials are missing, or acceptance criteria conflict.

---

## Agent Acknowledgement (Fill Before Substantive Work)
- **Agent / Assignee:**
- **Actual Execution Environment:**
- **Model & Version (or `UNKNOWN (not exposed by runtime)`):**
- **Starting Revision:**
- **Confirmed Outcome, Acceptance Criteria & Scope:** `Yes` | `Needs clarification`
- **Missing Access / Blockers:**
- **Planned First Action:**
