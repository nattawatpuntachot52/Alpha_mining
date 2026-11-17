# GEMINI.md — Antigravity Workspace Instructions

When working in `Alpha_mining`, read and follow [AGENTS.md](AGENTS.md) as the primary workspace charter.

Key operational entrypoints:
1. **Role Charter & Owner Profile**: [roles/conditioner.md](roles/conditioner.md)
2. **OVCA v1.0 Agent Role Mapping**: [roles/ovca-roles.md](roles/ovca-roles.md)
3. **Control Plane CLI**: `cargo run --manifest-path rust/Cargo.toml --bin alpha-ovca -- --help`
4. **Python Bridge & Domain Layout**: `python/alpha_mining/` (`research/`, `strategy/`, `execution/`, `risk/`, `accounting/`, `control_plane/`)

Core non-negotiables:
- Never fabricate data, references, test results, or confidence beyond observed evidence.
- Never claim compilation, tests, or backtests passed without running them in the current environment.
- Keep `ovca-reference` v1.0 wire contracts untouched; enforce Conditioner gates at pre-intake (`ConditioningBrief`) and review/audit stages.
- Respond in concise Thai (conclusion first), using English technical terms where precise.
