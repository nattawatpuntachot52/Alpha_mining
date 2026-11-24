# ADR-0002: Isolated LGB154 1m Backtest Engine, `partial_only` Recovery & Daily 9-Panel Beta Mining Factory

- **Status:** `Accepted`
- **Date:** `2026-11-23`
- **Owner:** `@nattawatpuntachot52`
- **Scope:** `Alpha_mining` (`python/alpha_mining/strategy/lgb154.py`, `python/alpha_mining/research/{backtest_lgb154,beta_store,beta_dashboard,kline_loader}.py`, `scripts/beta_mining.py`, `.github/workflows/daily-beta-mining.yml`, `config/beta_mining/daily_queue.json`)

## Context
The owner's live production LGB154 V3 bot (`bot.py`) needed a systematic daily Beta Mining workflow (evaluating 5+ pluggable closed-bar signals per day over 1,000 days of real 1m `ETHUSDT` USD-M data with real 8h funding rates, ranking cumulative Top-9 models by cashflow and drawdown, and rendering a 9-panel research dashboard comparing all models in each daily batch).

## Decision
1. **Strict Production Isolation:** Build a dedicated, strictly causal (zero-lookahead) 1m limit-order backtest engine completely decoupled from live `bot.py`; never mutate live production bot code during research.
2. **Default Beta Mining Parameters (Owner-Approved):**
   - `ETHUSDT` `USD_M`, Geometric Zone `5000 → 500` (practical geometric floor satisfying Binance `$5` `min_notional` for `0.01 ETH` while covering 100% of ETH's 1,000-day observed range `$1,384–$4,958`), `max_position_quantity = 2.0 ETH`, `initial_capital = $10,000`, `1,000 days`, `strict_cross` conservative fills.
3. **Recovery Mode (`partial_only` Default):**
   - Inspection of live `bot.py L2417` revealed that cancelled 0-fill BUY groups remained in active recovery tracking and starved near-market entries when price moved higher. The backtest engine defaults to `--recovery-mode partial_only` while retaining `legacy_v3` purely for optional parity reproduction.
4. **Top-9 Ranking Rule & Hard Safety Gate:**
   - Primary: `Net Realized Cashflow DESC`, Secondary: `Max MTM DD % ASC`.
   - Hard Gate: `No Liquidation` AND `Max MTM DD <= 40%` (disqualified models are transparently preserved, never silently dropped).
5. **Zero-CDN 9-Panel Multi-Model Daily Dashboard + Scheduled Cron (`07:30 ICT` / `00:30 UTC`):**
   - Replace the 5.0 MB 2-model Plotly reference with an offline zero-CDN HTML5 Canvas 9-panel dashboard comparing all daily batch models simultaneously, with historical batch date switching, GitHub Pages deployment, and PR-only daily cron (`daily-beta-mining.yml`).

## Alternatives Considered
1. **Backtest by monkey-patching live `bot.py`:** Rejected due to unacceptable production safety risk and slow execution on 1.44M 1m bars.
2. **Embed `plotly.min.js` (~4.8 MB) in every daily `dashboard.html`:** Rejected to keep repository diffs lightweight (`~270 KB/day`) and guarantee 100% offline zero-CDN usability.

## Consequences & Guardrails
- **Benefits:** Reproducible 1,000-day runs (`~60s` for 5 models locally via `O(log N)` bisect grid lookup), isolated per-model folders (`beta_mining/models/<model_id>/`), exact ISO-week cashflow conservation, and transparent MTM drawdown / Beta / Correlation diagnostics.
- **Trade-offs / Risks:** Full-window mining without OOS split increases multiple-testing risk as `N_trials` grows; `catalog.json` tracks cumulative `total_trials` explicitly so Top-9 leaders still require robustness & out-of-sample / paper validation before any live promotion.
- **Rollback Path:** Pause `.github/workflows/daily-beta-mining.yml` in GitHub Actions without disturbing isolated stored models under `beta_mining/models/`.

## Verification / Evidence
- Delivered and verified across PR #14 (`9279973`), PR #15 (`619285d`), PR #16 (`450a741`), PR #17 (`518e87f`), first automated Day-2 run PR #18 (`5c3a863`, `8m 01s`, CI + OVCA Bot approved), and expanded to 2 rounds/day (10 Beta/day + 20 Alpha/day) in PR #19 (`1ddd667`).
