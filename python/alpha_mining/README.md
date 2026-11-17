# Quant & Systems Domain Separation (`alpha_mining`)

`Alpha_mining` enforces strict separation across the five trading/engineering layers:

```text
research ──▶ strategy ──▶ risk ──▶ execution ──▶ accounting
   │                                                  │
   └────────────── governed by control_plane (OVCA) ──┘
```

- `control_plane`: Bridges Python workflows to the Rust `alpha-ovca` CLI (which uses `ovca-types` and `ovca-workflow` from `ovca-reference`).
- `research`: Falsifiable hypotheses, trial count (`trials_tested`) for multiple-testing tracking, leakage & cost assumptions, negative results.
- `strategy`: Converts validated research rules into `SignalIntent` only.
- `risk`: Independent pre-trade & portfolio risk gating (`RiskDecision`).
- `execution`: Order-routing adapters (e.g., MQL5/API/Rust adapters) consuming only risk-approved orders.
- `accounting`: Independent PnL, fee, slippage, and broker/ledger reconciliation.
