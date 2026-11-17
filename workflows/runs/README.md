# Workflow Run Ledger (`workflows/runs/`)

Store reproducible OVCA workflow artifacts per task/experiment under `workflows/runs/<workflow_id>/`:

1. `brief.json` — Validated `ConditioningBrief` (inputs, constraints, assumptions, unknowns, falsifiable hypothesis, role separation)
2. `events.json` — Append-only `WorkflowEvent` log validated via `alpha-ovca verify-stream`
3. `notes.md` — Separate record of:
   - `Independent Solution`
   - `Evidence` (with exact inputs, git commit SHA, tool/package versions, seeds, and reproduction commands)
   - `Verification` (including untested areas, uncertainties, limitations)
   - `Negative Results` & `Lessons Learned`
