# Admission & Observe Decision Ledger (`workflows/admission_ledger/`)

Append-only local or CI-exported JSONL records created when running proactive rule evaluations in `off | observe | auto` mode via `scripts/admission_gate.py`.

## Schema Highlights (`DecisionRecord`)

- `accept_mode`: `"off" | "observe" | "auto"`
- `policy_version`: canonical `sha256:<64 hex>` hash of [`config/governance/admission_policy.json`](../../config/governance/admission_policy.json)
- `decision`: `"accept" | "stop" | "ignore" | "unavailable"`
- `would_accept`: `true` whenever a trigger/candidate passed every rule and direction gate (logged without mutating files or minting a Mandate when `accept_mode == "observe"`, or paired with `decision == "accept"` in `explicit`/`auto` decisions)
- `matched_rules`: enabled rule IDs matched (empty when `decision == "unavailable"` or rejected)
- `rule_assessments`: full 1:1 judgment covering every enabled rule

## Typical Calibration Loop (`Observe -> Auto`)

1. Run `python3 scripts/admission_gate.py observe-github --ledger workflows/admission_ledger/observe.jsonl` (or inspect uploaded `admission-observe` workflow artifacts in GitHub Actions).
2. Summarize recorded `would_accept` hits and false positives:
   ```bash
   python3 scripts/admission_gate.py summarize-ledger workflows/admission_ledger/observe.jsonl
   ```
3. Only switch `accept_mode` in `config/governance/admission_policy.json` from `"observe"` to `"auto"` after inspecting historical `would_accept` precision across target rules.
