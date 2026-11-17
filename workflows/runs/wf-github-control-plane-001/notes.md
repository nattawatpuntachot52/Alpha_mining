# Workflow Run Notes: `wf-github-control-plane-001`

## 1. Independent Solution

Implemented the 4-part GitHub-centered Multi-Agent Control Plane for `Alpha_mining` on branch `feat/github-control-plane`:

1. **2-Layer GitHub Rulesets on `main`** (`config/github/rulesets/standard-main-protection.json`, `config/github/rulesets/details-main-protection.json`, `python/alpha_mining/control_plane/github_ruleset.py`, `scripts/github_ruleset.py`):
   - Active non-bypassable Rulesets (`bypass_actors: []`) deployed live on `nattawatpuntachot52/Alpha_mining`: ID `27447738` (`standard-main-protection`) & ID `27447741` (`alpha-mining-details-main-protection`).
   - Enforces PR-only merges, deletion/non-fast-forward blocks, stale review dismissal, thread resolution, and `strict_required_status_checks_policy: true` requiring `rust` and `python` Actions checks (`integration_id: 15368`). Keeps `required_approving_review_count: 0` temporarily to prevent single-collaborator self-approval deadlock.
2. **Separate Bot/App Quorum Readiness** (`.github/workflows/ovca-reviewer-bot.yml`, `docs/bot-account-setup.md`, `set-review-quorum`):
   - Checks out trusted `main` only (never PR head code), runs `scripts/pr_audit.py`, posts the Markdown Semantic Audit report, and auto-approves only internal-repo, non-draft, `CI=SUCCESS`, `READY_TO_MERGE` PRs after confirming matching `head_sha` (TOCTOU guard).
   - Safe `0 -> 1` upgrade via `python3 scripts/github_ruleset.py set-review-quorum --count 1 --confirm-bot-ready`.
3. **`AGENT_ACK` Disclosure + Multi-PR Semantic Audit** (`workflows/templates/agent_ack.template.md`, `.github/pull_request_template.md`, `python/alpha_mining/control_plane/agent_ack.py`, `python/alpha_mining/control_plane/pr_audit.py`, `scripts/pr_audit.py`):
   - Enforces explicit `UNKNOWN (not exposed by runtime)` disclosure and rejects placeholders / guess words.
   - Detects non-textual collisions across GitHub `MERGEABLE` PRs: direct file overlaps, singular/plural and kebab/snake sibling collisions, parallel same-base schema/contract divergence, stale stacked bases, multi-hop `STACKED_PARENT_NOT_READY` propagation, fork head collisions, legacy `StatusContext` failures, and untrusted third-party comments.
4. **Google Drive + Actions Cache 3-Tier Quant Vault** (`config/storage/drive_vault.json`, `python/alpha_mining/storage/vault.py`, `scripts/vault_sync.py`, `.github/workflows/vault-sync.yml`, `.gitignore`):
   - Tier 1 (Git SSOT): SHA-256 manifests under `workflows/vault_manifests/`.
   - Tier 2 (Hot Cache): `.vault_cache/` + `actions/cache@v4`.
   - Tier 3 (Master Durable Vault): Google Drive `Alpha_mining_Vault` (`1uB0PU8GvrCx5payhEufdkxFXuWf4RGFp` → `datasets/`, `backtests/`, `state_snapshots/`).

## 2. Evidence

- **Base Git Commit SHA**: `f0ac2eb79b131c6503303fd175a4696cff199fe1` (`main`)
- **Tool / Runtime Versions Verified**:
  - `Python 3.11.2`
  - `rustc 1.99.1 (58cf8f9c3 2026-10-13)` / `cargo 1.99.1 (5f94df478 2026-08-27)`
  - `git version 2.39.5`
  - `gh version 2.103.3 (2026-10-26)` (`nattawatpuntachot52`)
- **External Resources Verified**:
  - GitHub Rulesets live IDs: `27447738` (`standard-main-protection`), `27447741` (`alpha-mining-details-main-protection`), `branches/main` `protected: true`
  - Google Drive `Alpha_mining_Vault` ID `1uB0PU8GvrCx5payhEufdkxFXuWf4RGFp`, subfolders `datasets` (`12q4OVX65a0R1fubWJuey5kqkXUNoDXsX`), `backtests` (`1mSUfgnR4yNhSi3ggM_DYHMjP9ynB5Yxr`), `state_snapshots` (`11LgT2EI6OrjeBoF8y91Smz2wEfRwfxbt`)

## 3. Verification

### Executed and Passed in Current Slice
- `cmp -s AGENTS.md CLAUDE.md` → **passed**
- YAML validation (`ci.yml`, `ovca-reviewer-bot.yml`, `vault-sync.yml`) → **passed**
- Relative Markdown link checker across all `.md` files → **passed**
- `cargo fmt --manifest-path rust/Cargo.toml --all -- --check` → **passed**
- `cargo check --manifest-path rust/Cargo.toml --all-targets --locked` → **passed**
- `cargo test --manifest-path rust/Cargo.toml --all-targets --locked` → **passed** (`2` CLI + `8` integration)
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets --locked -- -D warnings` → **passed**
- `cargo run --manifest-path rust/Cargo.toml --locked --bin alpha-ovca -- validate-brief workflows/runs/wf-github-control-plane-001/brief.json` → **valid**
- `cargo run --manifest-path rust/Cargo.toml --locked --bin alpha-ovca -- verify-stream workflows/examples/quant_alpha_pass_stream.json --brief workflows/examples/quant_alpha_brief.example.json` → **passed**
- `python3 scripts/github_ruleset.py validate-configs` → **passed**
- `python3 scripts/github_ruleset.py verify` → **passed** (zero drift between local configs and live Rulesets `27447738` & `27447741`)
- `python3 scripts/pr_audit.py --format markdown` → **passed**
- `python3 -m unittest discover -s python/tests -v` → **passed (`24/24`)**
- `bash -n scripts/sync_codex_skills.sh && shellcheck scripts/sync_codex_skills.sh` → **passed**

### Explicit Untested / Deferred Paths (`verification not run`)
- **`zstd` compression/decompression path** (`_resolve_codec("zstd")`): `verification not run` in local Linux VM (`zstd` binary not installed).
- **`scripts/sync_codex_skills.ps1`**: `verification not run` in local Linux VM (`pwsh` not installed).
- **Live execution of `ovca-reviewer-bot.yml` & `vault-sync.yml`**: deferred until Owner creates GitHub App + configures `OVCA_REVIEWER_APP_ID`, `OVCA_REVIEWER_APP_PRIVATE_KEY`, and optionally `RCLONE_CONFIG_GDRIVE`.

## 4. Negative Results

- **Attempt 1 Independent Adversarial Review (`research` subagent `cd1b9ac2ba3cc5bbed208b8f227874ee`)** uncovered critical integration/security issues:
  - `ovca-reviewer-bot.yml` originally passed `-R` to `scripts/pr_audit.py` (which only supported `--repo`, guaranteed exit code 2 failure in Actions), and lacked TOCTOU/CI-bypass/private-key guards.
  - `vault.py` originally lacked `archive_name` traversal validation, unmanifested archive member checks, symlink-directory checks, and `rclone` fallback when `gdrive_file_id` is absent.
  - `pr_audit.py` originally propagated stacked blocks only 1 hop and risked `headRefName == "main"` fork collisions.
- **Hardlink Truncation Defect Caught During Test Expansion**: Adding `test_hardlinks_xz_roundtrip_symlink_dir_and_unmanifested_member_rejection` caught that `_add_deterministic_regular_file()` in `vault.py` switched `tarfile` `LNKTYPE` to `REGTYPE` without resetting `info.size = abs_path.stat().st_size`, silently extracting hardlinked files as 0 bytes (`e3b0c44...`). Fixed and re-verified (`24/24`).
- **Sorted Check Order Assertion Mismatch**: `validate_ruleset_configs` returned sorted `["python", "rust"]`, breaking older unsorted assertion `["rust", "python"]` in `test_github_ruleset.py`. Fixed cleanly.

## 5. Lessons Learned

- Writing adversarial failure/edge-case tests (hardlinks, 3-hop stacks, fork `main`, unmanifested tar members, remote API failures) directly catches silent data-truncation and CLI contract bugs that happy-path tests miss.
- Keeping GitHub Ruleset `required_approving_review_count` at `0` until separate GitHub App credentials are populated prevents accidental repository self-lockout while still enforcing PR-only merges and required `rust`/`python` CI checks.
