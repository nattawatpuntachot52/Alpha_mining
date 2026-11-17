## Summary & Workflow Lineage
- **Brief / Workflow Run Path**: `workflows/runs/<workflow_id>/` (or explain why ad-hoc bounded change)
- **OVCA / Katherine Role**: `<coordinator / engineer / reviewer / auditor>`
- **Scope & Touched Interfaces / Schemas**:
  - Modules/files changed:
  - Public schema / template / ruleset changes (if any):

## Pre-Merge Verification (`No Implicit Pass`)
List only commands executed in this branch's current state:
- [ ] `cmp -s AGENTS.md CLAUDE.md` -> `<pass / fail / not run>`
- [ ] `cargo fmt --manifest-path rust/Cargo.toml --all -- --check` -> `<pass / fail / not run>`
- [ ] `cargo check --manifest-path rust/Cargo.toml --all-targets --locked` -> `<pass / fail / not run>`
- [ ] `cargo test --manifest-path rust/Cargo.toml --all-targets --locked` -> `<pass / fail / not run>`
- [ ] `cargo clippy --manifest-path rust/Cargo.toml --all-targets --locked -- -D warnings` -> `<pass / fail / not run>`
- [ ] `python3 -m unittest discover -s python/tests -v` -> `<pass / fail / not run>`
- [ ] `python3 scripts/pr_audit.py --fail-on-critical` -> `<pass / fail / not run>`

## Semantic Conflict Check (Multi-Branch / Stacked PRs)
- **Other open PRs checked**: `<none / PR numbers>`
- **Potential namespace / contract / base-SHA drift**: `<none / reconciled details>`

## AGENT_ACK

```text
AGENT_ACK
mission_id: <mission_id>
task_id: <task_id>
assignment_id: <branch_or_assignment>
phase_id: <phase_id>
agent_id: <agent_id>
ovca_role: <engineer | reviewer | auditor>
actual_provider_runtime: <runtime_and_os>
actual_model_id_version: <exact_model_id_or_UNKNOWN (not exposed by runtime)>
tools_environment: <host / python / rust / gh_account>
mutation_boundary: <branch_and_writable_scope>
verification_summary: <exact_current_slice_verification_results>
```
