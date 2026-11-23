# LGB154 V3 Pluggable 1-Minute Backtest Engine (`Portfolio beta` #1)

Deterministic, zero-lookahead Python backtest engine implementing exact **Binance LGB154 V3** strategy parity (`STRATEGY_PARITY.md`) across both **USD-M (`ETHUSDT`)** and **COIN-M Inverse (`ETHUSD_PERP`)**, with a pluggable `SignalProvider` interface for A/B testing alternative entry/exit signals on the exact same grid, fee, funding, and risk engine.

---

## 1. Architecture & Strategy Parity

- **`python/alpha_mining/strategy/lgb154.py`**:
  - Exact `Decimal` geometric grid (`build_grid_levels`), spacing guard (`within_spacing`), partial-fill recovery (`missing_qty`), and USD-M (`PROFIT_PLUS_COMMISSION` / `NET`) + COIN-M Inverse (`NET` ETH basis) TP thresholds (`compute_net_tp_price`).
  - Pluggable closed-bar `SignalProvider` protocol (`on_closed_bar(bar) -> +1 | -1 | 0`):
    - `ha_1m` — **Baseline LGB154 V3 Heikin-Ashi** (`O(1)` streaming, verified 100% parity against 199-closed-bar `Decimal` window).
    - `ema_9_21` / `ema_<fast>_<slow>` — Fast/Slow EMA crossover.
    - `rsi_reversion` / `rsi_trend` — Wilder RSI mean-reversion or trend regime.
    - `supertrend_10_3` / `supertrend_<atr>_<mult>` — Wilder ATR Supertrend.
    - `CallableSignal` — Drop-in wrapper for any custom Python signal function.
- **`python/alpha_mining/research/kline_loader.py`**:
  - Downloads and caches official Binance Vision bulk archives (`data.binance.vision` monthly + daily ZIPs + 8h historical Funding Rates) under gitignored `data/cache/binance_vision/`.
  - Also supports public `data-api.binance.vision/api/v3/klines` REST and local `.csv` / `.zip` / `.parquet` datasets (e.g., from `01_Alpha_Mining/datasets` or `binance_collector.py`).
- **`python/alpha_mining/research/backtest_lgb154.py`**:
  - Strictly causal bar simulation (`B_{t-1}` closed bar → decision at `B_t` open → passive limit fills during `B_t`).
  - Supports both conservative `strict_cross` (`low < limit` / `high > limit`, default) and optimistic `touch` (`<=` / `>=`) fill modes, plus `--recovery-mode partial_only` (default, prevents zero-fill cancelled groups from starving near-market entries) vs `legacy_v3` (reproduces `bot.py` L2417 1:1).
  - Reports Mark-to-Market equity, realized vs unrealized PnL, worst intra-bar drawdown, liquidation check, fees, real 8h funding cashflows, Sharpe/Sortino/Calmar, and automated steepest-crash stress windows (`find_worst_crash_window`).

---

## 2. Quickstart CLI Commands

```bash
# 1. Run 1,000-day ETHUSDT USD-M Baseline (HA 1m) + Signal A/B + 30-day Crash Stress Test
python3 scripts/backtest_lgb154.py \
  --profile usdm \
  --source vision \
  --days 1000 \
  --signals ha_1m,ema_9_21,rsi_reversion,supertrend_10_3 \
  --fill-mode strict_cross \
  --stress-crash-days 30

# 2. Run on custom CSV/Parquet file placed in datasets/
python3 scripts/backtest_lgb154.py \
  --profile usdm \
  --source local \
  --local-path data/raw/ETHUSDT_1m.csv \
  --signals ha_1m,ema_9_21

# 3. Run COIN-M Inverse profile (ETHUSD_PERP 2000 -> 1500 @ 1% NET ETH)
python3 scripts/backtest_lgb154.py \
  --profile coinm \
  --source vision \
  --days 1000 \
  --signals ha_1m,rsi_reversion
```

---

## 3. Daily Beta Mining Factory (5 Models/Day + Top-9 Cashflow → DD Dashboard)

Run daily 5-model batches with isolated per-model folders (`beta_mining/models/<model_id>/`), automatic `ranking_top9.json` updates (**Primary: Net Realized Cashflow DESC → Secondary: Max MTM DD % ASC**, **Hard Gate: No Liquidation & Max DD ≤ 40%**), and a 100% self-contained offline interactive HTML Dashboard (`beta_mining/daily/<YYYY-MM-DD>/dashboard.html`):

```bash
# Run Day-1 5-model batch on 1,000d ETHUSDT (5000 -> 500, 2.0 ETH, $10,000)
python3 scripts/beta_mining.py run-daily \
  --date 2026-11-23 \
  --signals ha_1m,ema_9_21,ema_12_26,supertrend_10_3,rsi_reversion_14_40_60 \
  --days 1000 --high 5000 --low 500 --max-position-qty 2.0 --max-notional 10000 --initial-capital 10000

# Inspect Top-9 Ranking Board, individual isolated model, archived daily batches, or rebuild dashboards
python3 scripts/beta_mining.py rank --top 9 --max-dd 40
python3 scripts/beta_mining.py show beta_002_ema_9_21
python3 scripts/beta_mining.py compare --models beta_001_ha_1m,beta_002_ema_9_21
python3 scripts/beta_mining.py list-dates --json
python3 scripts/beta_mining.py rebuild-dashboard --date 2026-11-23
python3 scripts/beta_mining.py rebuild-dashboard --all-dates
```

Every `run-daily` and `rebuild-dashboard` call also updates the zero-CDN **Daily Archive Hub** (`beta_mining/index.html`) and manifest (`beta_mining/daily/index.json`). Inside each daily 9-panel dashboard (`beta_mining/daily/<YYYY-MM-DD>/dashboard.html`), use the header **Batch Date Switcher** (`◀ Prev` / Dropdown / `Next ▶` / `All Days`) to jump across historical mining days, and the Tab-1 **Lookback Window Selector** (`30D` / `90D` / `180D` / `365D` / `ALL` or custom `From`–`To` dates) to dynamically re-slice Panels 01–06, Panel 08 (window OLS Beta/Corr vs ETH), Panel 09 (window Return Correlation Matrix), and summary tables.

To plug a brand-new standalone custom signal into any model folder, drop a `signal.py` file inside `beta_mining/models/<model_id>/signal.py` defining `build_signal(spec: dict) -> SignalProvider` and load it via `BetaModelStore(Path("beta_mining")).load_signal_provider("<model_id>")`.
