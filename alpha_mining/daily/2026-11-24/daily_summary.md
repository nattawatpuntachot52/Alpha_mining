# Alpha_mining — Alpha Mining Daily Summary (2026-11-24)

- **Generated (UTC):** `2026-11-24T09:56:24Z`
- **Models Tested Today:** `10` (`ETHUSDT`: 5, `XAUUSD`: 5) | **Rounds:** `[1]` | **Cumulative Trials (`N_trials`):** `10`
- **Top-9 Rule:** `OOS Sharpe DESC -> Max DD ASC` | **Hard Gates:** `no liquidation`, `trades >= 30`, `OOS profit > 0`, `Max DD <= 50%`
- **Multiple-testing:** expected max daily Sharpe under H0 for `N=10` trials = `0.066439`; `DSR≈` is the probability a model beats that haircut.
- **XAUUSD data:** public feed is `PAXGUSDT` (gold-backed, 24/7) as a PROXY for broker XAUUSD; costs 2 bps/side. ETHUSDT = Binance USD-M perp, 5 bps/side.

## 1. โมเดลที่ Mine วันนี้ (2026-11-24 — 10 โมเดล)

| Model ID | Sym | TF | Dir | Return | CAGR | Max DD | Sharpe | IS Sh | OOS Sh | OOS Ret | Trades | Win% | PF | B&H |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `alpha_001_xauusd_1h_momentum_roc_14_lo` | XAUUSD | 1h | long_only | -66.1% | -23.7% | 67.3% | -1.76 | -2.98 | 0.00 | -2.1% | 2,663 | 24.6% | 0.76 | +108.0% |
| `alpha_002_xauusd_1h_momentum_roc_90_lo` | XAUUSD | 1h | long_only | +5.6% | +1.4% | 29.5% | 0.17 | 0.28 | 0.05 | -2.1% | 846 | 26.2% | 1.05 | +108.0% |
| `alpha_003_xauusd_15m_heiken_ma_cross_sma_12_26_x_lo` | XAUUSD | 15m | long_only | -35.1% | -16.1% | 37.0% | -1.15 | -0.41 | -2.79 | -27.0% | 1,676 | 28.3% | 0.85 | +53.3% |
| `alpha_004_xauusd_15m_ma_cross_sma_28_101_lo` | XAUUSD | 15m | long_only | +57.2% | +20.1% | 17.2% | 1.22 | 2.04 | -0.60 | -8.0% | 529 | 32.5% | 1.35 | +53.3% |
| `alpha_005_xauusd_30m_donchian_breakout_40_10_lo` | XAUUSD | 30m | long_only | +13.3% | +4.2% | 22.1% | 0.35 | 0.27 | 0.56 | +6.8% | 443 | 38.4% | 1.11 | +85.5% |
| `alpha_006_ethusdt_1h_momentum_roc_14_lo` | ETHUSDT | 1h | long_only | -66.5% | -23.9% | 76.8% | -0.38 | 0.31 | -2.08 | -70.1% | 2,284 | 26.3% | 0.94 | +43.2% |
| `alpha_007_ethusdt_1h_momentum_roc_90_lo` | ETHUSDT | 1h | long_only | -40.0% | -12.0% | 68.7% | -0.07 | 0.42 | -1.36 | -53.4% | 864 | 27.1% | 0.98 | +43.2% |
| `alpha_008_ethusdt_15m_heiken_ma_cross_sma_12_26_lo` | ETHUSDT | 15m | long_only | -76.2% | -44.2% | 76.2% | -1.01 | -0.46 | -2.53 | -57.0% | 1,845 | 32.6% | 0.88 | -55.1% |
| `alpha_009_ethusdt_30m_donchian_breakout_40_10_lo` | ETHUSDT | 30m | long_only | -14.9% | -5.2% | 55.2% | 0.03 | -0.09 | 0.31 | +4.7% | 504 | 35.5% | 1.00 | -14.5% |
| `alpha_010_ethusdt_4h_ma_cross_ema_5_20_ls` | ETHUSDT | 4h | long_short | -69.7% | -21.3% | 87.1% | -0.08 | 0.12 | -0.54 | -53.8% | 683 | 26.2% | 0.99 | -60.4% |

## 2. Cumulative Top-9 Ranking Board (OOS Sharpe สูงสุด → DD ต่ำสุด)

| Rank | Model ID | Sym | TF | OOS Sharpe | OOS Ret | Max DD | Trades | DSR≈ | Batch |
|---:|---|---|---|---:|---:|---:|---:|---:|---|
| **#1** | `alpha_005_xauusd_30m_donchian_breakout_40_10_lo` | XAUUSD | 30m | 0.56 | +6.8% | 22.1% | 443 | 0.06 | `2026-11-24` |

### โมเดลวันนี้ที่ไม่ผ่าน Hard Gate

- `alpha_009_ethusdt_30m_donchian_breakout_40_10_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT`
- `alpha_002_xauusd_1h_momentum_roc_90_lo`: เหตุผล `OOS_NOT_PROFITABLE`
- `alpha_001_xauusd_1h_momentum_roc_14_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE`
- `alpha_010_ethusdt_4h_ma_cross_ema_5_20_ls`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_004_xauusd_15m_ma_cross_sma_28_101_lo`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_007_ethusdt_1h_momentum_roc_90_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_006_ethusdt_1h_momentum_roc_14_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_008_ethusdt_15m_heiken_ma_cross_sma_12_26_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_003_xauusd_15m_heiken_ma_cross_sma_12_26_x_lo`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
