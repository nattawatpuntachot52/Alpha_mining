# Workflow Run Notes: `wf-brain-memory-cron-001`

## 1. Independent Solution

Implemented **Daily Brain Memory Automated GitHub Actions Cron & Incremental Sync Planner** on feature branch `feat/brain-memory-daily-cron` (branched from `main` @ `d6ba115`, post-PR #7), adhering strictly to PR-only 2-layer `main` Rulesets (`contents: read`, zero direct pushes, zero `secrets.*` in `if:` expressions, `include-hidden-files: true` for hidden paths, and `rclone` + `zstd` installation prior to remote execution):

1. **Incremental Snapshot Sync Planner ([`brain_memory.py`](../../../python/alpha_mining/storage/brain_memory.py), [`storage/__init__.py`](../../../python/alpha_mining/storage/__init__.py), [`scripts/brain_memory.py`](../../../scripts/brain_memory.py))**:
   - Added [`plan_snapshot_sync`](../../../python/alpha_mining/storage/brain_memory.py#L968-L1207) and CLI subcommand `plan-sync` (`--manifest-dir`, `--authoritative-manifest-dir`, `--session-date`, `--force`).
   - Validates all `YYYY-MM-DD.jsonl` logs and computes deterministic canonical SHA-256 digests (`_canonical_jsonl_sha256`, `_canonical_summary_sha256`) so cosmetic trailing blank lines never trigger redundant uploads, while both JSONL changes (`jsonl_sha256_changed`) and deterministic summary drift (`summary_sha256_changed`) fail closed and reschedule packing.
   - Enforces fail-closed authoritative manifest verification and nanosecond cross-directory `last_pushed_utc` conflict detection: stale Git/cache manifests cannot override missing Drive authoritative manifests (`missing_authoritative_manifest`) or newer conflicting pushes (`conflicting_newer_push`), and dry-run/failed uploads without `last_pushed_utc` (`never_pushed`) stay pending.
   - Hardened [`vault.py`](../../../python/alpha_mining/storage/vault.py) (`load_manifest`, `verify_archive_checksum`, `_default_runner`) with strict `isinstance(..., str)` / 64-lowercase-hex SHA-256 validation, non-bool integer bounds checks, `UnicodeDecodeError` conversion, `stdin=subprocess.DEVNULL`, and explicit LF `newline="\n"` manifest serialization.

2. **Automated Daily GitHub Actions Workflow ([`.github/workflows/brain-memory-cron.yml`](../../../.github/workflows/brain-memory-cron.yml), [`workflows/memory/README.md`](../../memory/README.md))**:
   - Runs daily at `18:00 UTC` (`01:00 Asia/Bangkok`) via `schedule` plus manual `workflow_dispatch` (`session_date: auto | YYYY-MM-DD`, `dry_run`, `force_resync`) under `concurrency: alpha-brain-memory-sync` (`cancel-in-progress: false`).
   - Installs `rclone` and `zstd` cleanly on `ubuntu-latest`, validates `workflows/memory/*.jsonl`, restores `.vault_cache` (retaining compact `brain_manifests/` and `brain_summaries/` while keeping `.tar.zst` archives and fetched Drive manifests isolated in `.vault_staging/`), queries Drive read-only when `RCLONE_CONFIG_GDRIVE` is configured (including `dry_run: true`) with `RCLONE_ASK_PASSWORD: "false"`, `</dev/null`, `--max-depth 1`, and `gdrive:` root `Alpha_mining_Vault/` verification before treating `LS_RC=3` as initial `state_snapshots/` bootstrap.
   - Pushes verified archives to `gdrive:Alpha_mining_Vault/state_snapshots/` plus manifest sidecars to `state_snapshots/manifests/`, uploads 90-day workflow artifacts (`include-hidden-files: true`), and skips remote push with `::warning::` when `RCLONE_CONFIG_GDRIVE` is absent instead of failing scheduled validations.

3. **Regression & Workflow Safety Tests ([`test_brain_memory.py`](../../../python/tests/test_brain_memory.py), [`test_github_workflows.py`](../../../python/tests/test_github_workflows.py))**:
   - Expanded `test_plan_snapshot_sync_lifecycle_and_fail_closed_guards` covering empty dirs, missing/invalid dates, `never_pushed` vs `up_to_date`, `force=True`, `resolve_episode_outcome` -> `jsonl_sha256_changed`, `summary_sha256_changed`, `missing_authoritative_manifest`, `conflicting_newer_push`, CLI `--authoritative-manifest-dir`, `bool`-as-`int` `bytes`, non-string `archive_name`, corrupt JSON, zero-episode JSONL, symlinks, and non-UTF-8 CLI error exits.
   - Expanded `test_brain_memory_cron_schedule_rclone_and_secret_hygiene` asserting schedule/concurrency/CLI steps, `--authoritative-manifest-dir`, `.vault_staging/archives`, `RCLONE_ASK_PASSWORD: "false"`, `</dev/null`, `--max-depth 1`, `gdrive:` root verification, `LS_RC=3` guard, `include-hidden-files: true`, no `secrets.*` in `if:`, and `rclone`/`zstd` install ordering.

## 2. Evidence

- **Base Git Commit SHA**: `d6ba115760835b9c2cd1cdf3b96b9e65d58adf7a` (`main`, post-PR #7 merge)
- **Active Branch**: `feat/brain-memory-daily-cron`
- **Tool / Runtime Versions Verified**:
  - `OS / Host`: `Linux 6.12.105+ x86_64` (`sandbox`)
  - `Python 3.11.2`
  - `rustc 1.99.1 (58cf8f9c3 2026-10-13)` / `cargo 1.99.1 (5f94df478 2026-08-27)`
  - `git version 2.39.5`
  - `gh version 2.103.3 (2026-10-26)` (`nattawatpuntachot52`)
  - `rclone`: present in VM (`/usr/bin/rclone`)
- **Live GitHub Configuration Observed via `gh` / `github_ruleset.py`**:
  - `OVCA_REVIEWER_APP_ID`: set (`5800517`); `OVCA_REVIEWER_APP_PRIVATE_KEY`: set; `RCLONE_CONFIG_GDRIVE`: **NOT set** in repository Secrets.
  - Rulesets verified (`27447738` & `27447741`): `main_protected: true`, `required_approving_review_count: 1`, `required_status_checks: ["python", "rust"]`.
- **Independent Adversarial Audits**:
  - Attempt 1 (`research` subagent `c078c8e387c1aa560ce7b8c3c0a6e22a`): returned `Verdict: REPAIR` (`1 High, 3 Medium, 3 Low`).
  - Attempt 2 (`research` subagent `9df1cd76b98b0c4babf7d16f8e72ffc1`): returned **`Verdict: PASS`** (`0 Critical, 0 High, 0 Medium, 0 Low`), confirming closure of all 7 Attempt 1 findings and noting 2 non-blocking informational items.

## 3. Verification

### Executed and Passed After Final Edits
- `cmp -s AGENTS.md CLAUDE.md` -> **passed** (governance files remain 1:1 untouched)
- `git diff --check` + raw CRLF/EOF `\n`/0o644 file-mode hygiene checks -> **passed**
- `cargo fmt --manifest-path rust/Cargo.toml --all -- --check` -> **passed**
- `cargo check --manifest-path rust/Cargo.toml --all-targets --locked` -> **passed**
- `cargo test --manifest-path rust/Cargo.toml --all-targets --locked` -> **passed** (`17/17`)
- `cargo clippy --manifest-path rust/Cargo.toml --all-targets --locked -- -D warnings` -> **passed**
- `python3 scripts/github_ruleset.py validate-configs` & `verify -R nattawatpuntachot52/Alpha_mining` -> **passed**
- `python3 scripts/admission_gate.py validate-policy --verify-rust-parity` -> **passed**
- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s python/tests -v` -> **passed (`55/55`)**
- `python3 scripts/brain_memory.py validate` & `plan-sync --manifest-dir workflows/vault_manifests` -> **passed**
- `yaml.safe_load` check on `.github/workflows/brain-memory-cron.yml` -> **passed (`YAML_OK`)**
- 6-scenario mocked-`rclone` E2E workflow execution of `.github/workflows/brain-memory-cron.yml` -> **passed (`ALL_6_WORKFLOW_E2E_SCENARIOS_PASSED`)**
- `./rust/target/debug/alpha-ovca validate-brief` & `verify-stream` on `workflows/runs/wf-brain-memory-cron-001/` -> **passed (`completed` / `passed`)**

### Explicit Untested / Deferred Paths (`verification not run`)
- **Live remote Google Drive upload via `rclone`**: `verification not run` inside VM and CI until Owner configures `RCLONE_CONFIG_GDRIVE` in GitHub Repository Secrets (`gh secret list` verified it is not currently set). Note: Owner must configure `gdrive:` at Drive root (do not scope `root_folder_id` inside `Alpha_mining_Vault`) so `gdrive:Alpha_mining_Vault/state_snapshots/` resolves consistently.

## 4. Negative Results

- **Attempt 1 Independent Adversarial Code Audit (`c078c8e387c1aa560ce7b8c3c0a6e22a`)** rejected Attempt 1 (`repair_directed`) with **1 High, 3 Medium, 3 Low** findings:
  - *HIGH-1*: `plan_snapshot_sync` exited early on matching manifests without cross-directory conflict checks or an authoritative Drive sidecar source, letting stale Git/cache manifests hide Drive deletions or newer conflicting pushes. Closed by adding `authoritative_manifest_dir`, full-directory scan without early return, nanosecond `last_pushed_utc` conflict ordering, and explicit `missing_authoritative_manifest` / `conflicting_newer_push` failure reasons.
  - *MEDIUM-2*: `rclone` lacked `RCLONE_ASK_PASSWORD=false` and `</dev/null` / `DEVNULL` stdin protections; `LS_RC=3` could mask accidental `root_folder_id` scoping inside `Alpha_mining_Vault`; `dry_run` skipped read-only Drive manifest queries. Closed in `brain-memory-cron.yml` and `vault._default_runner`.
  - *MEDIUM-3*: `vault.load_manifest` lacked strict `isinstance(..., str)` / 64-hex `sha256` / non-bool `int` checks and `UnicodeDecodeError` wrapping; `plan_snapshot_sync` skipped `{s_date}.summary.json` digest checks and allowed inconsistent manifest metadata or CRLF variance. Closed in `vault.py` and `brain_memory.py`.
  - *MEDIUM-4*: Storing cron `.tar.zst` archives in `.vault_cache/` risked unbounded Actions Cache bloat across daily runs. Closed by separating staging archives/Drive downloads into `.vault_staging/`.
  - *LOW-5..7*: Added `--authoritative-manifest-dir` CLI flag + clean `UnicodeDecodeError` handling (`scripts/brain_memory.py`), added `--max-depth 1` on `rclone copy`, and expanded unit/workflow test coverage in `test_brain_memory.py` and `test_github_workflows.py`.
- **Attempt 2 Independent Adversarial Re-Audit (`9df1cd76b98b0c4babf7d16f8e72ffc1`)**: Returned `Verdict: PASS` (`0` blocking defects) with 2 benign informational notes (`brain_memory.py:1170-1172` unreachable fallback branch shadowed by `:1164/:1167`, and `archive_name.startswith` prefix vs exact `.{compression}` check — preserved exact audited code snapshot because `load_manifest` validates `SAFE_FILENAME_RE` and `pack-snapshot` rebuilds fresh archives prior to push).

## 5. Lessons Learned

- Distributed cron state across Git manifests, Actions Cache, and Google Drive must treat Drive (`state_snapshots/manifests/`) as authoritative whenever reachable and order multi-source state by full nanosecond `last_pushed_utc` comparisons rather than "first match wins".
- In Google Drive `rclone` automation, `lsf` exit code `3` can ambiguously signal either a fresh bootstrap folder or a mis-scoped `root_folder_id`; pre-verifying `gdrive:` root for `Alpha_mining_Vault/` cleanly separates valid first-run bootstrap from secret configuration mistakes.
- Keeping GitHub Actions Cache limited to tiny manifests/summaries while placing ephemeral `.tar.zst` archives in `.vault_staging/` avoids unbounded cache churn since Drive stores durable archives.
