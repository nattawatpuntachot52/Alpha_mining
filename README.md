# Alpha_mining

**Alpha_mining** is the central Quant Research, Trading Systems Engineering, and AI Agent Governance Hub built around the **Conditioner** operating charter and **OVCA v1.0** ([`nattawatpuntachot52/ovca-reference`](https://github.com/nattawatpuntachot52/ovca-reference)).

## Architecture Overview

1. **Conditioner Governance (`AGENTS.md`, `GEMINI.md`, `roles/`)**
   - Defines the **Conditioner** persona: Critical Thinking Partner, Quant Researcher, Systems Architect, and Adaptive Tutor.
   - Enforces Pre-Intake framing (`Inputs`, `Outputs`, `Variables`, `Constraints`, `Assumptions`, `Acceptance Criteria`, `Unknowns`), falsifiable hypotheses, epistemic claim classification, and Solver-vs-Verifier separation.
2. **OVCA v1.0 Control Plane (`rust/crates/alpha-ovca`)**
   - Links directly to `ovca-types` and `ovca-workflow` from `ovca-reference` via pinned Cargo git dependency (`rev = "5b0726ceddc5c92ccf334e6ef94ba9875ce0c5f4"`), keeping OVCA v1.0 wire contracts unchanged.
   - Validates `ConditioningBrief` pre-intake specs, initializes deterministic `IntakeAccepted` events, transactionally appends events, and replays streams through `WorkflowReducer` and `recover_public`.
3. **Python Hub & Domain Boundaries (`python/alpha_mining/`)**
   - `control_plane/`: Bridges Python research scripts to `alpha-ovca`.
   - Strict 5-layer separation: `research/` | `strategy/` | `risk/` | `execution/` | `accounting/`.
4. **Workflow Ledger & Templates (`workflows/`)**
   - Pre-intake JSON templates, research gate checklists, synthetic OVCA reference fixtures, and reproducible run logs (`workflows/runs/`).
5. **Installable Skills (`skills/`)**
   - `skills/conditioner-ovca/SKILL.md`: Portable skill encapsulating the Conditioner role + OVCA workflow rules.
   - `skills/zoom-out/SKILL.md`: Evidence-grounded codebase overview skill synced from `ovca-reference` (`5b0726c`).

## Quick Verification

Run the Rust checks (formatting, compilation, unit/integration/CLI tests, clippy):

```bash
cargo fmt --manifest-path rust/Cargo.toml --all -- --check
cargo check --manifest-path rust/Cargo.toml --all-targets --locked
cargo test --manifest-path rust/Cargo.toml --all-targets --locked
cargo clippy --manifest-path rust/Cargo.toml --all-targets --locked -- -D warnings
```

Run the CLI directly against the synthetic example fixture:

```bash
cargo run --manifest-path rust/Cargo.toml --bin alpha-ovca -- \
  validate-brief workflows/examples/quant_alpha_brief.example.json

cargo run --manifest-path rust/Cargo.toml --bin alpha-ovca -- \
  verify-stream workflows/examples/quant_alpha_pass_stream.json \
  --brief workflows/examples/quant_alpha_brief.example.json
```

Run the Python bridge and domain boundary tests:

```bash
python3 -m unittest discover -s python/tests -v
```

## Scope & Honest Limitations

- `Alpha_mining` enforces workflow conformance, pre-intake conditioning checks, and architectural boundaries.
- Passing `alpha-ovca verify-stream` proves deterministic contract/reducer conformance only — **not** statistical validity or live trading profitability.
- No live trading execution adapters, historical market datasets, or production strategies are included in this initial hub setup.
