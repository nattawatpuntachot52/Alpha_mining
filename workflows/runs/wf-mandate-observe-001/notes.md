# Workflow Run Notes: `wf-mandate-observe-001`

## 1. Independent Solution

Implemented DeepSeek Super-Agent Mechanisms **1 (`Context ≠ Authority`: Immutable `AuthorizationMandate` + Policy Versioning + Revalidation + Handback)** and **2 (`Observe Mode`: `off | observe | auto` Proactive Admission Gate)** for `Alpha_mining` on branch `feat/mandate-observe-admission`, without altering any pinned `ovca-reference` v1.0 wire contracts (`ovca-types`, `ovca-workflow`, `rust/Cargo.lock`):

1. **Canonical Versioned Admission Policy (`config/governance/admission_policy.json`)**:
   - Starts safely in `accept_mode: "observe"` with `allowed_actors: ["nattawatpuntachot52"]`, `bot_allowlist`, `automated_reviewers_non_bot`, explicit `admission_table` (`github_comment`, `github_issue`, `github_pr`, `github_default_branch_ci`, `owner_cli`), and 3 seeded enabled proactive rules:
     - `ci-default-branch-failure` (`github_default_branch_ci`)
     - `parallel-pr-semantic-conflict` (`github_pr`, `github_comment`)
     - `quant-manifest-drift-check` (`github_pr`, `github_default_branch_ci`)
2. **Rust Control Plane Enforcement ([`rust/crates/alpha-ovca/src/admission.rs`](../../../rust/crates/alpha-ovca/src/admission.rs), [`main.rs`](../../../rust/crates/alpha-ovca/src/main.rs), [`lib.rs`](../../../rust/crates/alpha-ovca/src/lib.rs))**:
   - Deterministic `CanonJson` (`BTreeMap`-backed, immune to `serde_json/preserve_order`) SHA-256 canonical `policy_version` computation (`sha256:1c8847163051455592f4db0714c5a352cb099d57e3c2698421d8a28289dfe78d` for default policy).
   - `AuthorizationMandate` binding to `ConditioningBrief.authority.scope` via segment-safe path containment (rejecting prefix traps, traversal `..`, UNC/Windows drive prefixes like `C:`/`é:`, and control characters).
   - `revalidate_mandate` validating `AcceptMode::Auto`, matched rule existence/enabled status, `receiving_scopes` containment, `intersect_rule_scopes` narrowing, CI-before-bot precedence, `is_bot_login` checks, `automated_reviewers_non_bot` disjointness/inferred-only, and listed-vs-unlisted explicit symmetry.
   - `evaluate_followup` enforcing `Context ≠ Authority`: context-only/unlisted/bot/CI/non-bot-reviewer follow-ups stay `ContextOnlyDeliver` (even under `accept_mode: "auto"` and across `Active`/`Ended` threads), bots/CI/strangers cannot invoke `stop` or widen `writable_scope`, and out-of-scope owner follow-ups emit structured `HandbackRecord` (`handback_required`).
   - New `alpha-ovca` subcommands: `policy-version`, `validate-mandate`, `revalidate-mandate`, and `check-followup`.
3. **Python Admission Gate, Bridge Freshness & Observe Workflow ([`admission.py`](../../../python/alpha_mining/control_plane/admission.py), [`ovca_bridge.py`](../../../python/alpha_mining/control_plane/ovca_bridge.py), [`admission_gate.py`](../../../scripts/admission_gate.py), [`admission-observe.yml`](../../../.github/workflows/admission-observe.yml))**:
   - Exact Rust/Python `policy_version` SHA-256 parity and `off | observe | auto` gating with strict `unavailable` vs `ignore` separation.
   - Proactive `DecisionRecord` append-only JSONL logging under [`workflows/admission_ledger/`](../../admission_ledger/README.md) with deferred `would_accept_in_observe_count` calibration summaries.
   - Read-only `admission-observe.yml` workflow triggered after `CI` completion on trusted `main`, evaluating the 3 seeded rules via `gh` + `pr_audit` + `vault_manifests` and uploading Markdown/JSON/JSONL artifacts without mutating the repository.
   - Updated [`ci.yml`](../../../.github/workflows/ci.yml) so the `python` job rebuilds `alpha-ovca --locked` before parity checks, and updated `OvcaBridge.resolve_binary()` to verify source/Cargo mtimes and build with `--locked`.
4. **Governance & Skill Synchronization**:
   - Added `Context ≠ Authority` & `Proactive Admission & Observe Mode` sections to [`AGENTS.md`](../../../AGENTS.md), [`CLAUDE.md`](../../../CLAUDE.md) (1:1 identical), [`GEMINI.md`](../../../GEMINI.md), [`roles/ovca-roles.md`](../../../roles/ovca-roles.md), [`docs/architecture.md`](../../../docs/architecture.md), [`README.md`](../../../README.md), and [`skills/conditioner-ovca/SKILL.md`](../../../skills/conditioner-ovca/SKILL.md).

## 2. Evidence

- **Base Git Commit SHA**: `398bd39cc3580ebb9b3ec73ecb51969a46fef3e2` (`main`, post-PR #1 merge)
- **Active Branch**: `feat/mandate-observe-admission`
- **Canonical Policy Digest**: `sha256:1c8847163051455592f4db0714c5a352cb099d57e3c2698421d8a28289dfe78d`
- **Tool / Runtime Versions Verified**:
  - `OS / Host`: `Linux 6.12.105+ x86_64` (`sandbox`)
  - `Python 3.11.2`
  - `rustc 1.99.1 (58cf8f9c3 2026-10-13)` / `cargo 1.99.1 (5f94df478 2026-08-27)`
  - `git version 2.39.5`
  - `gh version 2.103.3 (2026-10-26)` (`nattawatpuntachot52`)

## 3. Verification

### Executed and Passed in Current Slice
- `cmp -s AGENTS.md CLAUDE.md` → **passed**
- `git diff --check` → **passed**
- PyYAML validation across `.github/workflows/*.yml` (`admission-observe.yml`, `ci.yml`, `ovca-reviewer-bot.yml`, `vault-sync.yml`) → **passed**
- Relative Markdown link check across all `.md` files → **passed** (`0` broken links)
- `cargo fmt --manifest-path rust/Cargo.toml --all -- --check` → **passed**
- `cargo check --manifest-path rust/Cargo.toml --all-targets --locked` → **passed**
- `cargo test --manifest-path rust/Cargo.toml --all-targets --locked` → **passed** (`3/3` CLI tests + `14/14` integration tests = `17/17`)
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets --locked -- -D warnings` → **passed**
- `cargo build --manifest-path rust/Cargo.toml --bin alpha-ovca --locked` → **passed**
- `python3 scripts/github_ruleset.py validate-configs` & `verify -R nattawatpuntachot52/Alpha_mining` → **passed** (Rulesets `27447738` & `27447741`, `main_protected: true`)
- `python3 scripts/admission_gate.py validate-policy --verify-rust-parity` → **passed** (`rust_parity_verified: true`)
- `python3 -m unittest discover -s python/tests -v` → **passed (`34/34`)** under both normal `PATH` and stripped `PATH=/usr/local/bin:/usr/bin:/bin`
- `python3 scripts/admission_gate.py observe-github -R nattawatpuntachot52/Alpha_mining --format markdown` → **passed** (read-only live inspection)
- `python3 scripts/pr_audit.py --fail-on-critical` → **passed** (`0` open PRs)
- `alpha-ovca validate-brief` / `verify-stream` on synthetic quant example + `workflows/runs/wf-mandate-observe-001/` → **passed** (`completed` / `passed`)

### Explicit Untested / Deferred Paths (`verification not run`)
- **Live GitHub Actions runner execution of `.github/workflows/admission-observe.yml`**: `verification not run` in GitHub Actions until branch/PR #2 is pushed and merged/dispatched (YAML syntax, fixture snapshot paths, and read-only live `gh` snapshot execution passed locally).
- **Automated mutation dispatching (`accept_mode: "auto"`)**: Intentionally disabled (`config/governance/admission_policy.json` remains `accept_mode: "observe"`); auto-minting paths were verified strictly via deterministic Rust/Python unit & integration tests rather than live unattended repo mutations.

## 4. Negative Results

- **Attempt 1 Independent Adversarial Code Audit (`research` subagent `42f0200586b7dca24656397a19edb550`)** flagged **3 BLOCKING**, **6 WARNING**, and **4 actionable NOTE** findings:
  - *BLOCKING #1*: `.github/workflows/ci.yml` `python` job restored stale `target/debug/alpha-ovca` Cargo cache without rebuilding on unchanged `rust/Cargo.lock`, and `OvcaBridge.resolve_binary()` lacked source/Cargo `mtime` freshness checks and `--locked`.
  - *BLOCKING #2*: Python `evaluate_gate` contained an unconditional `elif has_ticket:` branch granting `inferred` to unlisted actors on active/ended threads despite `unlisted_* = ignore`.
  - *BLOCKING #3*: Rust `evaluate_followup` omitted `AddressedKind` and allowed unlisted actors to resume/proceed under `accept_mode: "auto"`.
  - *WARNINGs & NOTEs*: `revalidate_mandate` omitted `is_bot_login`, rule surface (`receiving_scopes`), and `intersect_rule_scopes` checks; CI check ran after bot allowlist; `VALID_SOURCE_KINDS`, symmetric CI pairing, empty ID/evidence checks, `C:` drive prefixes in `normalized_segments`, Unicode `.to_lowercase()` parity, `automated_reviewers_non_bot` enforcement, CI run `completed` status sorting & `stale`/`error` conclusions, `preserve_order`-immune `CanonJson` hashing, `summarize-ledger` missing/corrupt ledger checks, `.observe_out/` `.gitignore`, `if-no-files-found: ignore`, `\r` Markdown escaping, and CLI/followup test coverage.
- **Observe-Mode Summary Overcount Bug Caught During Attempt 2 Verification**: Initial Attempt 2 test run caught `would_accept_in_observe_count == 2 != 1` in `test_observe_snapshot_sorting_status_conclusions_and_cli_subcommands` because `summarize_ledger` counted an already-accepted explicit mandate (`decision: "accept"`, `strength: "explicit"`) that ran while `policy.accept_mode == "observe"`. Tightened `summarize_ledger` to count only deferred proactive candidates (`accept_mode == "observe" and decision == "ignore" and strength == "inferred" and would_accept`) and re-verified `34/34`.
- **Attempt 2 Independent Adversarial Re-Audit (`42f0200586b7dca24656397a19edb550`)**: Passed cleanly (**0 BLOCKING, 0 WARNING, 4 NOTE**). Followed up by polishing 3 of those 4 NOTEs (`revalidate_mandate` listed-vs-unlisted explicit symmetry, strict dict/bool JSON parsing in `scripts/admission_gate.py`, and `OvcaBridgeError` on missing `cargo` + clean `git diff --check`), while preserving NOTE #2's design intentionally (addressed bot/reviewer triggers remain bounded by `proactive_rules[*].receiving_scopes`), and re-ran the full Rust + Python verification suite cleanly.

## 5. Lessons Learned

- Caching `rust/target/` keyed only on `rust/Cargo.lock` silently tests stale compiled binaries whenever `.rs` files change without dependency bumps; CI cross-language jobs and language bridges must check source/manifest `mtime` freshness and pass `--locked`.
- Follow-up admission paths (`evaluate_followup`) and proactive trigger gates (`evaluate_gate`) must share identical fail-closed admission table & actor-class invariants; checking `has_ticket` globally or assuming `accept_mode == "auto"` opens threads to arbitrary unlisted actors opens authority leaks.
- Counting `would_accept_in_observe_count` for Observe-to-Auto calibration must filter strictly on deferred `inferred` candidates (`decision == "ignore"`), otherwise routine explicit Owner commands executed while the policy is in `observe` mode distort historical rule precision metrics.
