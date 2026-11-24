# ADR-0001: OVCA Control Plane, 2-Layer Main Protection & Live Separate Reviewer Bot (`Quorum = 1`)

- **Status:** `Accepted`
- **Date:** `2026-11-24`
- **Owner:** `@nattawatpuntachot52`
- **Scope:** `Alpha_mining` (`rust/crates/alpha-ovca/`, `config/github/rulesets/`, `.github/workflows/ovca-reviewer-bot.yml`, `.github/CODEOWNERS`, `scripts/pr_audit.py`)

## Context
Running AI coding agents and scheduled automation on a trading research repository creates two failure modes: (1) self-approval deadlock on solo-owner repositories when `required_approving_review_count >= 1`, and (2) false merge confidence when GitHub reports `MERGEABLE` despite parallel semantic conflicts or stale stacked PRs.

## Decision
1. **2-Layer GitHub Rulesets on `main`** (`standard-main-protection` ID `27447738` + `alpha-mining-details-main-protection` ID `27447741`):
   - PR-only merges, `dismiss_stale_reviews_on_push: true`, `required_review_thread_resolution: true`, `strict_required_status_checks_policy: true`, required CI checks `rust` and `python`.
2. **Separate Reviewer Identity (`OVCA_REVIEWER_APP_ID = 5800517` + `OVCA_REVIEWER_APP_PRIVATE_KEY`):**
   - Deployed `.github/workflows/ovca-reviewer-bot.yml` checking out only trusted `main`, executing `scripts/pr_audit.py` (validating `AGENT_ACK`, CI status, unresolved threads, file/sibling collisions, and stacked base freshness), and approving only same-repo non-draft PRs with `READY_TO_MERGE`.
   - Flipped live `required_approving_review_count` from `0` to **`1`** once the GitHub App was proven live.
3. **GitHub-Native Hygiene Additions:** Added `.github/ISSUE_TEMPLATE/task.md` (for medium/high-impact work), `.github/CODEOWNERS`, `docs/decisions/`, and `docs/operations/agent-inventory.md` alongside our existing Rust `alpha-ovca` mandates.

## Alternatives Considered
1. **Keep `required_approving_review_count = 0` indefinitely:** Rejected because it leaves human merge as the sole merge gate without an independent automated audit approval.
2. **Use a Personal Access Token (PAT) from a secondary account:** Rejected in favor of a scoped GitHub App emitting short-lived per-job installation tokens.

## Consequences & Guardrails
- **Benefits:** Eliminates solo-owner self-approval deadlock while enforcing real `required_approving_review_count = 1` + deterministic semantic audit before every merge to `main`.
- **Trade-offs / Risks:** Rotating the `.pem` key requires updating `OVCA_REVIEWER_APP_PRIVATE_KEY` in repo secrets; bot approvals validate automated checks/audit and do not replace human owner judgment on strategy logic.
- **Rollback Path:** Revert `required_approving_review_count` via `python3 scripts/github_ruleset.py set-review-quorum --count 0` if App installation experiences an outage.

## Verification / Evidence
- Verified live on `2026-11-24` via `python3 scripts/github_ruleset.py verify` (`verified: true`, `main_protected: true`, `standard_ruleset_id: 27447738`, `details_ruleset_id: 27447741`, `required_approving_review_count: 1`).
- Verified live bot approvals on PR #15 (`619285d`), PR #18 (`5c3a863`, workflow run `45318298071`), and a full `CHANGES_REQUESTED` → fix (`fe65cac`) → `APPROVED` cycle on PR #19 (`1ddd667`).
