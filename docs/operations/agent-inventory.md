# Agent & Execution Environment Inventory + Capability Evidence Ledger (`Alpha_mining`)

> เอกสารนี้จัดทำตามแนวทาง **Provider-Neutral Operations (Section 7.1 & 11)** เพื่อบันทึกข้อเท็จจริงของ Agent / Execution Environment และ **Capability Evidence แยกตามประเภทงาน** ในโปรเจกต์ `01_Alpha_Mining` (เชื่อมโยงกับศูนย์กลาง `Katherine-HQ/docs/operations/agent-inventory.md`)
>
> **กฎความซื่อสัตย์ (Anti-Guess Policy):** ห้ามอนุมานรุ่นโมเดลจากชื่อเล่น หาก runtime ไม่เปิดเผย exact model identifier/version ให้บันทึกเป็น `UNKNOWN (not exposed by runtime)` เสมอ และเก็บขนาดตัวอย่าง (`sample_size`) กับเงื่อนไขการทดสอบกำกับทุกหลักฐาน

---

## 1. Active Agent & Execution Environment Inventory (`Alpha_mining`)

| Agent / Service | Platform / Account | Provider & Model ID/Version | Execution Environment / Harness | Permitted Tools & Boundary | Status / Known Limitations |
|---|---|---|---|---|---|
| **Katherine (Front Door / Conditioner)** | `nattawatpuntachot52` (via Antigravity proxy) | `UNKNOWN (not exposed by runtime)` | Antigravity Remote Linux VM (Debian 12) | Local repo R/W on feature branches, `git`, `gh`, `cargo`, `python3`, `gdrive`, `gsheets`, `gcalendar`; **PR-only** (no direct `main` push, Owner Commit Gate) | Connected; no access to GitHub App `.pem` keys or live Binance/MT5 production trading credentials |
| **OVCA Reviewer Bot (`alpha-mining-ovca-reviewer`)** | GitHub App `OVCA_REVIEWER_APP_ID = 5800517` | Deterministic Python script (`scripts/pr_audit.py`, no LLM) | GitHub Actions `ubuntu-latest` (`.github/workflows/ovca-reviewer-bot.yml`) | `contents: read`, `pull-requests: read/write` via short-lived App token; checks out trusted `main` only | **LIVE (`required_approving_review_count = 1`)** via Ruleset `27447738`; proven `CHANGES_REQUESTED -> APPROVED` loop on PR #19 (`1ddd667`) |
| **Daily Beta Mining Factory** | `github-actions[bot]` | Deterministic Python backtest (`scripts/beta_mining.py`, no LLM) | GitHub Actions `ubuntu-latest` (`.github/workflows/daily-beta-mining.yml`, `07:30` & `19:30 ICT`, 2 rounds × 5 = 10 models/day) | `contents: write`, `pull-requests: write`; single-writer `concurrency` lock; PR-only on `bot/daily-beta-mining-<date>` | **LIVE** on `main` (verified Day-2 PR #18 `5c3a863`, upgraded to 2 rounds/day in PR #19 `1ddd667`) |
| **Daily Alpha Mining Factory** | `github-actions[bot]` | Deterministic Python backtest (`scripts/alpha_mining.py`, no LLM) | GitHub Actions `ubuntu-latest` (`.github/workflows/daily-alpha-mining.yml`, `07:15` & `19:15 ICT`, 2 rounds × 10 = 20 models/day `XAUUSD + ETHUSDT`) | `contents: write`, `pull-requests: write`; single-writer `concurrency` lock; PR-only on `bot/daily-alpha-mining-<date>` | **LIVE** on `main` (merged in PR #19 `1ddd667`; awaiting first scheduled cron run evidence) |
| **GitHub Pages Dashboard Deployer** | `github-actions[bot]` | Deterministic static publisher (no LLM) | GitHub Actions `ubuntu-latest` (`.github/workflows/deploy-beta-pages.yml`) | `contents: read`, `pages: write`, `id-token: write` | **LIVE** on `main` (merged in PR #17 `518e87f`, updated in PR #19 `1ddd667`) |
| **External OVCA Nodes (`oracle-policy-tools`, `codex exec`)** | `UNKNOWN / NOT_CONNECTED` | `UNKNOWN / NOT_CONNECTED` | Not mounted in Antigravity VM | None in current runtime | Fallback to `alpha-ovca` Rust binary + Python control plane |

---

## 2. Provider-Neutral Task Routing Guide (Manual Routing First)

> ห้ามผูก Provider เดียวเข้ากับบทบาทถาวร เลือก Execution Environment ตามลักษณะงานและหลักฐานผลส่งมอบจริง การเปลี่ยนไปใช้ Auto-Routing ต้องมีหลักฐานเปรียบเทียบเพียงพอ, งบประมาณจำกัด, และ Owner Approval ก่อนเสมอ

| Task Category | Recommended Execution Pattern | Required Verification Layers |
|---|---|---|
| **Quant Research & Backtesting (Alpha / Beta)** | Deterministic Python/Rust engine + zero-lookahead tests + conservation proofs | Accounting conservation, fill sensitivity (`strict_cross` vs `touch`), crash stress, OOS / multiple-testing tracking |
| **MQL5 Model Registry & Portfolio Assembly** | Deterministic assembler (`scripts/build_ea_portfolio.py`) + normalized LF SHA-256 checksums | `python/tests/test_model_registry.py`, cross-OS line-ending verification |
| **Control Plane & Governance Hygiene** | Isolated feature branch + ADR under `docs/decisions/` + disjoint write scopes | `cargo fmt/check/test/clippy`, `github_ruleset.py`, `admission_gate.py --verify-rust-parity`, `unittest discover` |
| **Deterministic PR Audit & Review Gate** | Separate GitHub App (`alpha-mining-ovca-reviewer`, App ID `5800517`) | `scripts/pr_audit.py` (CI green + `AGENT_ACK` valid + zero semantic conflict) + human merge |
| **Scheduled Daily Mining & Pages Publishing** | GitHub Actions `cron` with `concurrency` single-writer lock + bounded PR branch scope | `python/tests/test_github_workflows.py`, artifact upload, PR-only delivery |

---

## 3. Capability Evidence Log (`Alpha_mining` — Verified Outcomes Only)

> **Evaluation Dimensions (Section 11):** Acceptance against criteria · Defect detection · Evidence accuracy & traceability · Scope/permission adherence · Rework after review · Repeatability · Time/cost where observed.
>
> **Caveat:** Initial sample sizes (`n = 1..6` per category) are **Exploratory / Reproducible operational records**, not statistically sufficient for automated model selection.

| Date (UTC) | PR & Commit | Task Category | Agent / Harness | Model ID/Version | Acceptance & Checks | Defect / Rework Notes | Evidence Source |
|---|---|---|---|---|---|---|---|
| `2026-11-23` | PR #13 (`947d88e`) | Data Engineering (Binance 1m multi-market collector -> Parquet Zstd) | Katherine / Antigravity Debian 12 VM | `UNKNOWN (not exposed by runtime)` | Accepted & merged; CI `PASS` (`45096637123`) | Zero post-merge rework | Git commit `947d88e` |
| `2026-11-23` | PR #14 (`9279973`) | Quant Backtest Engine & Isolated Store (LGB154 1m + Day-1 5 models) | Katherine / Antigravity Debian 12 VM | `UNKNOWN (not exposed by runtime)` | Accepted & merged; CI `PASS` (`45109301153`) | **Defect detected during build:** caught live `bot.py L2417` zero-fill zombie starvation & `O(N)` grid scan bottleneck; fixed with `partial_only` + `O(log N)` bisect (`~60s` for 5×1.44M bars) | Git commit `9279973` |
| `2026-11-23` | PR #15 (`619285d`) | Research UI & Scheduled Cron (9-panel zero-CDN dashboard + 07:30 ICT cron) | Katherine / Antigravity Debian 12 VM | `UNKNOWN (not exposed by runtime)` | Accepted & merged; Rust 17/17, Python 87/87, `node --check` exit 0, `alpha-mining-ovca-reviewer` approved | Caught `gh --version \| head -n 1` SIGPIPE under `pipefail` & trailing EOF whitespace before commit | Git commit `619285d` |
| `2026-11-23` | PR #16 (`450a741`) | Dashboard UX & Historical Navigation (batch date switcher, archive hub, lookback controls) | Antigravity / GitHub PR workflow | `UNKNOWN (not exposed by runtime)` | Accepted & merged; CI `PASS` + `alpha-mining-ovca-reviewer` approved | Zero post-merge rework | Git commit `450a741` |
| `2026-11-23` | PR #17 (`518e87f`) | Static Hosting Automation (GitHub Pages auto-deploy for Beta dashboard) | Antigravity / GitHub PR workflow | `UNKNOWN (not exposed by runtime)` | Accepted & merged; CI `PASS` + `alpha-mining-ovca-reviewer` approved | Zero post-merge rework | Git commit `518e87f` |
| `2026-11-24` | PR #18 (`5c3a863`) | Automated Scheduled Daily Mining (`2026-11-24` Day-2 batch) | GitHub Actions `daily-beta-mining.yml` + `alpha-mining-ovca-reviewer` | Deterministic (no LLM) | Accepted & merged; `8m 01s` run (`45316568468`), CI `PASS`, Bot approved (`45318298071`) | **Rework caught by CI (`2ebf10a`):** hardcoded Day-2 signal list in `test_beta_mining.py` needed dynamic calculation from `catalog.json` once Day-2 models entered catalog | Git commits `e87642b`, `2ebf10a`, `5c3a863` |
| `2026-11-24` | PR #19 (`1ddd667`) | Multi-Factory Expansion (5 MT5 Alpha models + 20/day Alpha Factory + 10/day Beta Factory) | External session + `alpha-mining-ovca-reviewer` | `UNKNOWN (not exposed by runtime)` | Accepted & merged; CI `rust` + `python` `SUCCESS` (`45367940260`), Bot approved `fe65cac` | **Defect caught by CI + Bot (`CHANGES_REQUESTED` on `5a30101`):** cross-OS CRLF vs LF SHA-256 mismatch in EA assembly; fixed in `fe65cac`, re-audited, and approved | Git commits `5a30101`, `fe65cac`, `1ddd667` |

### How to Append New Evidence
After any medium/high-impact PR is merged (or rejected), append one factual row above (and mirror cross-project highlights to `Katherine-HQ/docs/operations/agent-inventory.md`):
1. Exact UTC date, PR number, and merge/head SHA.
2. Task category and observed runtime/model (`UNKNOWN (not exposed by runtime)` if hidden).
3. Actual test/CI/bot outcomes and any defect caught or rework required.
4. Explicit note of sample size/conditions whenever comparing two agents or harnesses.
