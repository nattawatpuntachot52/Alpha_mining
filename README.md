# Alpha_mining

**Alpha_mining** is the central Quant Research, Trading Systems Engineering, and AI Agent Governance Hub built around **Katherine (OVCA Front Door / Conditioner)** and **OVCA v1.0** ([`nattawatpuntachot52/ovca-reference`](https://github.com/nattawatpuntachot52/ovca-reference)).

## Architecture Overview

1. **Katherine Front Door & Conditioner Governance (`AGENTS.md`, `CLAUDE.md` [1:1 mirror], `GEMINI.md`, `roles/`)**
   - Enforces the **Katherine Identity Lock**, `สัมปชัญญะ (P1/P2/P3)`, `Strict Plan Order`, `No Implicit Pass`, `SCAMPER Gate`, `Owner Commit Gate`, and `Closeout Completion Gate`.
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

## Syncing Skills to Codex (GitHub SSOT)

Keep `nattawatpuntachot52/Alpha_mining` on GitHub as the Single Source of Truth. After cloning or running `git pull --ff-only`, sync `skills/` (`conditioner-ovca`, `zoom-out`, and any future skills) into `${CODEX_HOME:-$HOME/.codex}/skills/`:

**macOS / Linux:**

```bash
# Safe copy (stops without overwriting existing skill folders)
./scripts/sync_codex_skills.sh

# Recommended for local dev: symlink so future `git pull` auto-updates Codex skills
./scripts/sync_codex_skills.sh --symlink --force

# Preview without modifying files
./scripts/sync_codex_skills.sh --dry-run
```

**Windows PowerShell:**

```powershell
# Safe copy (stops without overwriting existing skill folders)
.\scripts\sync_codex_skills.ps1

# Recommended for local dev: NTFS directory junction (auto-tracks `git pull`, no admin needed)
.\scripts\sync_codex_skills.ps1 -Junction -Force

# Preview without modifying files
.\scripts\sync_codex_skills.ps1 -DryRun
```

> **Note for Antigravity:** Workspace rules (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`) sync directly from the connected GitHub repository. If you edit `skills/*/SKILL.md`, refresh the installed personal Antigravity skill via `save_skill` as well.

## Scope & Honest Limitations

- `Alpha_mining` enforces workflow conformance, pre-intake conditioning checks, and architectural boundaries.
- Passing `alpha-ovca verify-stream` proves deterministic contract/reducer conformance only — **not** statistical validity or live trading profitability.
- No live trading execution adapters, historical market datasets, or production strategies are included in this initial hub setup.
