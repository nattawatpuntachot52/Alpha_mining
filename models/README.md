# Alpha_mining Model Repository (`beta` / `alpha` / `omega`)

This directory is the **Single Source of Truth (SSOT)** for modular trading models in `Alpha_mining`.
Every model is stored atomically (`spec.json` + `module.mqh`) so it can be:
1. Reviewed, versioned, and assigned an honest per-model **Evidence Status** (`proposed` → `exploratory` → `reproducible` → `robustness_validated` → `independently_replicated`).
2. Assembled deterministically into either a **single-model standalone `.mq5`** or a **multi-model portfolio `.mq5`** via `scripts/build_ea_portfolio.py` without copy-paste drift.
3. Paired with raw backtest/optimization artifacts stored in Google Drive (`00_Katherine_Workspace/01_Alpha_Mining/models/{alpha,beta,omega}`, configured in `config/storage/drive_vault.json`).

## Category Taxonomy

| Category | Directory | Google Drive Folder Key | Current Status |
|---|---|---|---|
| **`alpha`** | `models/alpha/` | `models_alpha` | Active — tactical/directional alpha models |
| **`beta`** | `models/beta/` | `models_beta` | Reserved placeholder (`taxonomy definition TBD by Owner`) |
| **`omega`** | `models/omega/` | `models_omega` | Reserved placeholder (`taxonomy definition TBD by Owner`) |

## Atomic Model Contract

Every registered model under `models/<category>/<model_id>/` MUST provide:
1. `spec.json` — Declarative logic specification, fixed parameters, unique `magic_number`, unique `mql5.prefix`, economic rationale, explicit assumptions, rejection criteria, and current `evidence_status`.
2. `module.mqh` — Self-contained MQL5 module exposing exactly 4 lifecycle hooks using its declared `mql5.prefix`:
   - `void Init_<Prefix>()`
   - `void LogConfig_<Prefix>()`
   - `void EnforceDisabled_<Prefix>(bool enabled, double lots)`
   - `void Process_<Prefix>(bool enabled, double lots)`

## Build & Validation Commands

```bash
# Validate registry, specs, magic number uniqueness, and MQL5 hooks
python3 scripts/build_ea_portfolio.py validate

# List all registered models
python3 scripts/build_ea_portfolio.py list

# Assemble a multi-model portfolio EA (self-contained .mq5 ready for MetaEditor 5)
python3 scripts/build_ea_portfolio.py build \
  --portfolio portfolios/live_bundle_v1.json \
  --out portfolios/assembled/live_bundle_v1.mq5

# Verify zero drift between models/ and portfolios/assembled/live_bundle_v1.mq5
python3 scripts/build_ea_portfolio.py build \
  --portfolio portfolios/live_bundle_v1.json \
  --out portfolios/assembled/live_bundle_v1.mq5 \
  --check

# Build a single model standalone EA for isolated MT5 backtesting
python3 scripts/build_ea_portfolio.py build-single \
  --model impulse_efficiency_s1 \
  --out /tmp/Impulse1_Standalone.mq5
```
