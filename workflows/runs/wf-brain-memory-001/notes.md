# Workflow Run Notes: `wf-brain-memory-001`

## 1. Independent Solution

Implemented Phase 1 (**Daily Brain Memory JSONL Ledger + Drive Vault Snapshot CLI + 5-Layer Domain-Neutral Contract Skeletons**) on feature branch `feat/brain-memory-and-skeleton` (branched from `main` @ `d899d4c`), isolating LLM usage strictly to `nl_to_json_only` translation with zero trade-execution or risk-override authority and intentionally deferring market instrument, timeframe, and trading strategy rules (`Unknowns` deferred to Phase 2 Owner teaching sessions):

1. **Daily Brain Memory Storage & Snapshot CLI ([`brain_memory.py`](../../../python/alpha_mining/storage/brain_memory.py), [`storage/__init__.py`](../../../python/alpha_mining/storage/__init__.py), [`scripts/brain_memory.py`](../../../scripts/brain_memory.py), [`workflows/memory/`](../../memory/README.md))**:
   - Enforces structured `BrainEpisode` (`v1.0`) JSONL logs (`workflows/memory/YYYY-MM-DD.jsonl`) separating:
     - `TranslationEnvelope` (`translator_role == "nl_to_json_only"`, `FORBIDDEN_INTENT_KEYS`, immutable `MappingProxyType`/`tuple` freeze)
     - `DecisionContext` (`observed_at_utc`, immutable `features_at_decision`, non-empty `available_actions`, validated `chosen_action`, `decision_engine`, `risk_gate_passed`)
     - `EpisodeOutcome` (`pending | resolved | void`, strict nanosecond lookahead invariance `outcome_at_utc >= observed_at_utc`, ban on realized numeric metrics for `pending` and `void`)
   - Enforces secret sanitization across all fields, dict keys, nested structures, unknown keys, `available_actions`, compound/camelCase/hyphenated credential keys, PEM/PGP/base64 keys, JWTs, Bearer tokens, OAuth/refresh tokens (`ya29.`, `GOCSPX-`, `1//0`), GitHub/AWS/Google keys, and rclone Drive INI sections.
   - Enforces symlink + directory-containment checks (`_assert_safe_memory_dir`, `_assert_safe_log_file`), `fcntl.flock` concurrency locking via `.brain_memory.lock` (gitignored cleanly in [`.gitignore`](../../../.gitignore)), global cross-day `episode_id` uniqueness in `append_episode`, atomic `0o644` file writes, and single-pass `state_snapshot` Vault packing via [`vault.py`](../../../python/alpha_mining/storage/vault.py).
   - Seeded initial sanitized governance episode `ep-20261118-brain-init` (`outcome.status: "pending"`) in [`workflows/memory/2026-11-18.jsonl`](../../memory/2026-11-18.jsonl).
2. **5-Layer Domain-Neutral Contract Skeletons**:
   - **Research** ([`research/contracts.py`](../../../python/alpha_mining/research/contracts.py), [`research/__init__.py`](../../../python/alpha_mining/research/__init__.py)): `RuleCondition`, `NLRuleSpec`, and `validate_translator_payload` enforcing allowed predicate operators, execution-command bans, finite numbers, strict JSON whitelists, ASCII UTC-Z validation, and safe `notes=None -> ""` normalization.
   - **Strategy** ([`strategy/contracts.py`](../../../python/alpha_mining/strategy/contracts.py), [`strategy/__init__.py`](../../../python/alpha_mining/strategy/__init__.py)): `SignalIntent.__post_init__`, `MetaLabelScore`, `StrategyDecision.__post_init__`, and deterministic `evaluate_meta_label_gate` requiring out-of-sample calibration and enforcing nanosecond lookahead checks (`meta_score.evaluated_at_utc >= intent.generated_at_utc`).
   - **Risk** ([`risk/contracts.py`](../../../python/alpha_mining/risk/contracts.py), [`risk/__init__.py`](../../../python/alpha_mining/risk/__init__.py)): `RiskLimits`, `MarketRiskSnapshot`, `RiskDecision` (backward-compatible 5-arg construction preserved for existing bridge tests while adding closure-scoped HMAC-SHA256 `_seal`), `verify_risk_decision_seal`, defensive finite/type validation against `__post_init__` bypasses, and nanosecond data freshness gating inside `evaluate_pre_trade_risk`.
   - **Execution** ([`execution/contracts.py`](../../../python/alpha_mining/execution/contracts.py), [`execution/__init__.py`](../../../python/alpha_mining/execution/__init__.py)): `ExecutionOrderRequest` gated by closure-scoped HMAC-SHA256 seal in `__post_init__` (blocking direct instantiation, forged seals, and `dataclasses.replace` tampering with `PermissionError`), constructed solely via `build_order_from_risk_decision` after `verify_risk_decision_seal`.
   - **Accounting** ([`accounting/contracts.py`](../../../python/alpha_mining/accounting/contracts.py), [`accounting/__init__.py`](../../../python/alpha_mining/accounting/__init__.py)): `CostAssumptions`, `AccountedOutcome.__post_init__`, `compute_net_r`, and `account_for_reconciliation` with ID/UTC-Z validation and post-division finiteness checks.
3. **Adversarial & Contract Tests**:
   - Added [`test_brain_memory.py`](../../../python/tests/test_brain_memory.py) and [`test_domain_contracts.py`](../../../python/tests/test_domain_contracts.py) while keeping [`test_ovca_bridge.py`](../../../python/tests/test_ovca_bridge.py) unmodified and green.

## 2. Evidence

- **Base Git Commit SHA**: `d899d4c201e3edd2bd13827211c4eccd7a9a9e49` (`main`, post-PR #6 merge)
- **Active Branch**: `feat/brain-memory-and-skeleton`
- **Tool / Runtime Versions Verified**:
  - `OS / Host`: `Linux 6.12.105+ x86_64` (`sandbox`)
  - `Python 3.11.2`
  - `rustc 1.99.1 (58cf8f9c3 2026-10-13)` / `cargo 1.99.1 (5f94df478 2026-08-27)`
  - `git version 2.39.5`
  - `gh version 2.103.3 (2026-10-26)` (`nattawatpuntachot52`)
- **Independent Adversarial Re-Audit Subagent (`602cbb1750161a45faa5fbb7ac31a366`)**: Returned `PASS` (`0 Critical, 0 High, 0 Medium`), followed by targeted closure of all 3 residual `Low` notes (strict ASCII `[0-9]` UTC-Z regexes, special-character password / bare `token=` detection in free text, missing-dir side-effect guard in `resolve_episode_outcome`, and expanded CLI `resolve`/`summarize` tests) and full final re-verification.

## 3. Verification

### Executed and Passed in Current Final Slice
- `cmp -s AGENTS.md CLAUDE.md` → **passed** (governance files remain 1:1 untouched)
- `git diff --check` + raw line-ending / EOF `\n` / trailing-whitespace / file-mode check → **passed** (`0` issues, `0o644` permissions)
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s python/tests -v` → **passed (`53/53`)**
- `python3 scripts/brain_memory.py validate` → **passed** (`valid: true, episode_count: 1`)
- `python3 scripts/brain_memory.py summarize --session-date 2026-11-18` (JSON + Markdown) → **passed**
- `python3 scripts/github_ruleset.py validate-configs` → **passed** (`valid: true`)
- `python3 scripts/admission_gate.py validate-policy --verify-rust-parity` → **passed** (`rust_parity_verified: true`)
- `cargo fmt --manifest-path rust/Cargo.toml --all -- --check` → **passed**
- `cargo check --manifest-path rust/Cargo.toml --all-targets --locked` → **passed**
- `cargo test --manifest-path rust/Cargo.toml --all-targets --locked` → **passed** (`3/3` CLI + `14/14` integration = `17/17`)
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets --locked -- -D warnings` → **passed**
- `./rust/target/debug/alpha-ovca validate-brief workflows/runs/wf-brain-memory-001/brief.json` & `verify-stream workflows/runs/wf-brain-memory-001/events.json --brief workflows/runs/wf-brain-memory-001/brief.json` → **passed** (`completed` / `passed`)

### Explicit Untested / Deferred Paths (`verification not run`)
- **Live Google Drive `rclone` push execution**: `verification not run` inside sandbox because Owner's repository Secret `RCLONE_CONFIG_GDRIVE` is outside the VM (`push-snapshot --dry-run` and local `pack-snapshot`/`extract_verified_archive` checksum round-trips passed).
- **Phase 2 Market/Strategy ML training & `RCLONE_CONFIG_GDRIVE` Vault upload**: Explicitly deferred until Owner configures `RCLONE_CONFIG_GDRIVE` and begins market/rule teaching sessions.

## 4. Negative Results

- **Attempt 1 Independent Adversarial Code Audit (`research` subagent `602cbb1750161a45faa5fbb7ac31a366`)** rejected Attempt 1 (`repair_directed`) with **3 High, 4 Medium, 3 Low** findings:
  - *HIGH-1*: Direct `ExecutionOrderRequest(...)` instantiation and unsealed/`replace()`-mutated `RiskDecision` objects were accepted by `build_order_from_risk_decision`; missing UTC-Z check on `risk_evaluated_at_utc`. Fixed with dual closure-scoped ephemeral HMAC-SHA256 capability seals preserving 5-arg `RiskDecision` bridge compatibility.
  - *HIGH-2*: `StrategyDecision` lacked `__post_init__` and `evaluate_pre_trade_risk` passed `NaN`/`Inf`/`bool`/`str` `target_exposure` through `min/max` (`min(1.0, NaN)` approved `max_abs_exposure`). Fixed in both `StrategyDecision.__post_init__` and defensively in `evaluate_pre_trade_risk`.
  - *HIGH-3*: Secret sanitizer bypassed via nested structures under sensitive keys, compound keys, case variations, Bearer/JWT/`ya29.`/`GOCSPX-`/`1//0`/PGP/base64 PEM/rclone INI blocks, `available_actions`, dict keys, and unknown `from_dict` keys. Fixed across `_is_sensitive_key`, `_contains_nonempty_payload`, `SECRET_VALUE_PATTERNS`, and strict `from_dict` tree/key validation.
  - *MEDIUM-1..4*: Fixed mutable dict post-init poisoning & missing `allow_nan=False` (`MappingProxyType`/`tuple` recursive freeze), symlink escapes in `memory_dir`, sub-microsecond truncation + `SignalIntent` lookahead + `void` numeric leak + `op="in"` smuggling, race conditions without `fcntl.flock`, per-day vs global `episode_id` mismatch, and double-read during `pack_daily_snapshot`.
  - *LOW-1..3*: Fixed `0o600` file permissions from `tempfile.mkstemp` (`os.chmod(..., 0o644)`), added `AccountedOutcome.__post_init__` + division finiteness + `notes=None` safe coercion, and expanded regression tests.
- **Attempt 2 Independent Adversarial Re-Audit (`602cbb1750161a45faa5fbb7ac31a366`)**: Returned `PASS` (`0 Critical/High/Medium`) and surfaced 3 residual `Low` notes (Unicode `\d` in fractional seconds, special-char password / bare `token=` patterns, and `resolve_episode_outcome` missing-dir lock creation), all resolved and re-verified on disk prior to stream finalization.

## 5. Lessons Learned

- Python `@dataclass(frozen=True)` only protects attribute rebinding, not nested `dict`/`list` mutation (`features_at_decision`, `structured_intent`); point-in-time training snapshots must recursively freeze nested containers into `MappingProxyType`/`tuple` and unfreeze exclusively for `allow_nan=False` serialization.
- Builtin `min(cap, float("nan"))` in Python returns `cap` instead of propagating `NaN`; every financial boundary gate must check `not isinstance(x, bool) and isinstance(x, (int, float)) and math.isfinite(x)` before numeric comparisons or clamping.
- Python 3.11 `datetime.fromisoformat()` silently truncates 7–9 fractional second digits to microseconds; temporal lookahead guards must parse nanosecond digits separately into `(datetime_sec, ns_int)` using ASCII `[0-9]` regexes.
