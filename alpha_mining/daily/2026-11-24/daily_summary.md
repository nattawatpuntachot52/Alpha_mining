# Alpha_mining — Alpha Mining Daily Summary (2026-11-24)

- **Generated (UTC):** `2026-11-24T11:27:16Z`
- **Models Tested Today:** `20` (`ETHUSDT`: 10, `XAUUSD`: 10) | **Rounds:** `[1, 2]` | **Cumulative Trials (`N_trials`):** `20`
- **Top-9 Rule:** `OOS Sharpe DESC -> Max DD ASC` | **Hard Gates:** `no liquidation`, `trades >= 30`, `OOS profit > 0`, `Max DD <= 50%`
- **Multiple-testing:** expected max daily Sharpe under H0 for `N=20` trials = `0.076038`; `DSR≈` is the probability a model beats that haircut.
- **XAUUSD data:** public feed is `PAXGUSDT` (gold-backed, 24/7) as a PROXY for broker XAUUSD; costs 2 bps/side. ETHUSDT = Binance USD-M perp, 5 bps/side.

## 1. โมเดลที่ Mine วันนี้ (2026-11-24 — 20 โมเดล)

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
| `alpha_011_xauusd_4h_ma_cross_ema_5_20_ls` | XAUUSD | 4h | long_short | +46.8% | +8.0% | 34.8% | 0.51 | 0.13 | 1.11 | +42.4% | 621 | 28.5% | 1.17 | +102.5% |
| `alpha_012_xauusd_1h_session_time_20_4_long_inside_lo` | XAUUSD | 1h | long_only | +10.7% | +2.6% | 20.7% | 0.29 | 0.29 | 0.32 | +4.7% | 1,461 | 48.4% | 1.05 | +108.0% |
| `alpha_013_xauusd_1h_session_time_19_2_long_inside_lo` | XAUUSD | 1h | long_only | +3.5% | +0.9% | 23.2% | 0.13 | -0.30 | 0.71 | +12.2% | 1,461 | 46.9% | 1.02 | +108.0% |
| `alpha_014_xauusd_1h_impulse_efficiency_3_20_2_0_0_75_12_continua` | XAUUSD | 1h | long_short | -37.4% | -11.1% | 41.6% | -1.41 | -1.61 | -1.06 | -12.0% | 1,018 | 49.9% | 0.82 | +108.0% |
| `alpha_015_xauusd_1d_calendar_turn_x_long_lo` | XAUUSD | 1d | long_only | +24.6% | +3.7% | 6.9% | 0.78 | 1.09 | 0.60 | +7.8% | 72 | 58.3% | 2.09 | +98.9% |
| `alpha_016_ethusdt_1h_impulse_efficiency_3_20_2_0_0_75_12_continu` | ETHUSDT | 1h | long_short | -64.8% | -23.0% | 74.3% | -0.68 | -0.26 | -1.64 | -49.5% | 1,165 | 39.7% | 0.91 | +43.2% |
| `alpha_017_ethusdt_1d_ibs_reversion_0_2_0_85_0_7_5_lo` | ETHUSDT | 1d | long_only | -3.5% | -0.6% | 56.2% | 0.20 | 0.03 | 0.73 | +41.2% | 231 | 59.3% | 1.08 | +200.1% |
| `alpha_018_ethusdt_1h_session_time_13_21_long_inside_lo` | ETHUSDT | 1h | long_only | -94.3% | -51.2% | 95.4% | -1.39 | -1.33 | -1.53 | -62.5% | 1,460 | 44.4% | 0.80 | +43.2% |
| `alpha_019_ethusdt_4h_donchian_breakout_30_10_14_0_9_ls` | ETHUSDT | 4h | long_short | +0.0% | +0.0% | 0.0% | 0.00 | 0.00 | 0.00 | +0.0% | 0 | 0.0% | 0.00 | -60.4% |
| `alpha_020_ethusdt_1h_rsi_regime_14_58_50_42_ls` | ETHUSDT | 1h | long_short | -77.6% | -31.2% | 85.3% | -0.43 | -0.69 | 0.17 | -5.9% | 1,551 | 26.8% | 0.93 | +43.2% |

## 2. Cumulative Top-9 Ranking Board (OOS Sharpe สูงสุด → DD ต่ำสุด)

| Rank | Model ID | Sym | TF | OOS Sharpe | OOS Ret | Max DD | Trades | DSR≈ | Batch |
|---:|---|---|---|---:|---:|---:|---:|---:|---|
| **#1** | `alpha_011_xauusd_4h_ma_cross_ema_5_20_ls` | XAUUSD | 4h | 1.11 | +42.4% | 34.8% | 621 | 0.02 | `2026-11-24` |
| **#2** | `alpha_013_xauusd_1h_session_time_19_2_long_inside_lo` | XAUUSD | 1h | 0.71 | +12.2% | 23.2% | 1,461 | 0.00 | `2026-11-24` |
| **#3** | `alpha_015_xauusd_1d_calendar_turn_x_long_lo` | XAUUSD | 1d | 0.60 | +7.8% | 6.9% | 72 | 0.05 | `2026-11-24` |
| **#4** | `alpha_005_xauusd_30m_donchian_breakout_40_10_lo` | XAUUSD | 30m | 0.56 | +6.8% | 22.1% | 443 | 0.03 | `2026-11-24` |
| **#5** | `alpha_012_xauusd_1h_session_time_20_4_long_inside_lo` | XAUUSD | 1h | 0.32 | +4.7% | 20.7% | 1,461 | 0.01 | `2026-11-24` |

### โมเดลวันนี้ที่ไม่ผ่าน Hard Gate

- `alpha_017_ethusdt_1d_ibs_reversion_0_2_0_85_0_7_5_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT`
- `alpha_009_ethusdt_30m_donchian_breakout_40_10_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT`
- `alpha_020_ethusdt_1h_rsi_regime_14_58_50_42_ls`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE`
- `alpha_002_xauusd_1h_momentum_roc_90_lo`: เหตุผล `OOS_NOT_PROFITABLE`
- `alpha_001_xauusd_1h_momentum_roc_14_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE`
- `alpha_019_ethusdt_4h_donchian_breakout_30_10_14_0_9_ls`: เหตุผล `TRADES_LT_30, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_010_ethusdt_4h_ma_cross_ema_5_20_ls`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_004_xauusd_15m_ma_cross_sma_28_101_lo`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_014_xauusd_1h_impulse_efficiency_3_20_2_0_0_75_12_continua`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_007_ethusdt_1h_momentum_roc_90_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_018_ethusdt_1h_session_time_13_21_long_inside_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_016_ethusdt_1h_impulse_efficiency_3_20_2_0_0_75_12_continu`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_006_ethusdt_1h_momentum_roc_14_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_008_ethusdt_15m_heiken_ma_cross_sma_12_26_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_003_xauusd_15m_heiken_ma_cross_sma_12_26_x_lo`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
