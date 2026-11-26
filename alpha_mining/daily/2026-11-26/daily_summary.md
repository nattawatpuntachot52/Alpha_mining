# Alpha_mining — Alpha Mining Daily Summary (2026-11-26)

- **Generated (UTC):** `2026-11-26T15:15:50Z`
- **Models Tested Today:** `40` (`ETHUSDT`: 20, `XAUUSD`: 20) | **Rounds:** `[1, 2, 3, 4]` | **Cumulative Trials (`N_trials`):** `100`
- **Top-9 Rule:** `OOS Sharpe DESC -> Max DD ASC` | **Hard Gates:** `no liquidation`, `trades >= 30`, `OOS profit > 0`, `Max DD <= 50%`
- **Multiple-testing:** expected max daily Sharpe under H0 for `N=100` trials = `0.217915`; `DSR≈` is the probability a model beats that haircut.
- **XAUUSD data:** public feed is `PAXGUSDT` (gold-backed, 24/7) as a PROXY for broker XAUUSD; costs 2 bps/side. ETHUSDT = Binance USD-M perp, 5 bps/side.

## 1. โมเดลที่ Mine วันนี้ (2026-11-26 — 40 โมเดล)

| Model ID | Sym | TF | Dir | Return | CAGR | Max DD | Sharpe | IS Sh | OOS Sh | OOS Ret | Trades | Win% | PF | B&H |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `alpha_061_xauusd_1h_impulse_efficiency_3_20_1_8_0_7_10_continuat` | XAUUSD | 1h | long_short | -57.3% | -19.2% | 59.2% | -1.91 | -2.64 | -0.80 | -13.1% | 1,274 | 40.1% | 0.76 | +102.8% |
| `alpha_062_xauusd_1h_impulse_efficiency_3_20_2_2_0_8_12_reversal` | XAUUSD | 1h | long_short | -27.6% | -7.8% | 34.7% | -0.97 | -0.73 | -1.42 | -15.6% | 825 | 51.1% | 0.86 | +102.8% |
| `alpha_063_xauusd_15m_impulse_efficiency_4_30_2_2_0_75_16_continu` | XAUUSD | 15m | long_short | -50.8% | -25.0% | 53.0% | -2.75 | -2.56 | -3.17 | -23.8% | 1,511 | 37.0% | 0.77 | +54.2% |
| `alpha_064_xauusd_30m_impulse_efficiency_3_24_2_0_0_75_12_continu` | XAUUSD | 30m | long_only | -11.7% | -4.1% | 23.1% | -0.50 | -0.06 | -1.40 | -10.5% | 690 | 41.7% | 0.92 | +79.1% |
| `alpha_065_xauusd_4h_impulse_efficiency_3_20_1_8_0_75_10_continua` | XAUUSD | 4h | long_short | +16.7% | +3.1% | 35.5% | 0.32 | -0.52 | 1.79 | +44.6% | 481 | 44.5% | 1.08 | +97.6% |
| `alpha_066_ethusdt_1h_impulse_efficiency_3_20_2_2_0_78_12_reversa` | ETHUSDT | 1h | long_short | -80.6% | -33.7% | 82.8% | -1.42 | -1.80 | -0.61 | -22.2% | 1,000 | 48.6% | 0.81 | +39.3% |
| `alpha_067_ethusdt_15m_impulse_efficiency_4_30_2_4_0_78_16_contin` | ETHUSDT | 15m | long_short | -79.5% | -47.5% | 81.4% | -1.78 | -1.45 | -2.74 | -46.1% | 1,401 | 40.6% | 0.83 | -54.4% |
| `alpha_068_ethusdt_30m_impulse_efficiency_3_24_2_0_0_75_12_contin` | ETHUSDT | 30m | long_short | -77.5% | -39.1% | 81.9% | -1.12 | -1.04 | -1.33 | -39.0% | 1,662 | 40.8% | 0.89 | -14.1% |
| `alpha_069_ethusdt_4h_impulse_efficiency_3_20_1_8_0_75_12_continu` | ETHUSDT | 4h | long_short | +27.0% | +4.9% | 58.7% | 0.31 | -0.12 | 1.29 | +83.0% | 438 | 41.8% | 1.08 | -59.2% |
| `alpha_070_ethusdt_1h_impulse_efficiency_6_24_2_0_0_7_18_continua` | ETHUSDT | 1h | long_only | +66.5% | +13.6% | 34.2% | 0.56 | 0.87 | -0.17 | -11.0% | 326 | 46.9% | 1.20 | +39.3% |
| `alpha_071_xauusd_1d_rsi_reversion_2_10_90_65_35_lo` | XAUUSD | 1d | long_only | -9.0% | -1.6% | 18.9% | -0.13 | -0.34 | 0.14 | +1.8% | 92 | 62.0% | 0.90 | +98.6% |
| `alpha_072_xauusd_4h_rsi_reversion_3_15_85_60_40_lo` | XAUUSD | 4h | long_only | +0.3% | +0.1% | 18.2% | 0.05 | 0.39 | -0.32 | -7.4% | 322 | 66.2% | 1.02 | +99.2% |
| `alpha_073_xauusd_1h_rsi_reversion_14_28_72_55_45_ls` | XAUUSD | 1h | long_short | -28.5% | -8.1% | 44.3% | -0.48 | 0.11 | -1.38 | -29.7% | 310 | 57.4% | 0.81 | +104.4% |
| `alpha_074_xauusd_1h_rsi_regime_14_58_50_42_lo` | XAUUSD | 1h | long_only | -7.9% | -2.0% | 33.1% | -0.10 | -0.48 | 0.43 | +7.6% | 790 | 28.4% | 0.97 | +104.4% |
| `alpha_075_xauusd_4h_rsi_regime_14_55_50_45_ls` | XAUUSD | 4h | long_short | +79.4% | +12.4% | 25.4% | 0.76 | 0.51 | 1.17 | +43.9% | 609 | 32.8% | 1.28 | +99.2% |
| `alpha_076_ethusdt_1d_rsi_reversion_2_10_90_65_35_lo` | ETHUSDT | 1d | long_only | -24.8% | -4.6% | 62.0% | 0.12 | 0.08 | 0.24 | +2.9% | 99 | 63.6% | 1.03 | +223.6% |
| `alpha_077_ethusdt_4h_rsi_reversion_4_20_80_55_45_ls` | ETHUSDT | 4h | long_short | -86.4% | -33.0% | 90.5% | -0.52 | -0.30 | -1.06 | -61.2% | 607 | 63.1% | 0.85 | -59.2% |
| `alpha_078_ethusdt_1h_rsi_reversion_14_25_75_50_50_ls_sl2_5tp0` | ETHUSDT | 1h | long_short | -71.0% | -26.6% | 76.5% | -1.48 | -1.80 | -0.75 | -18.7% | 284 | 48.6% | 0.69 | +39.3% |
| `alpha_079_ethusdt_4h_rsi_regime_14_55_50_45_ls` | ETHUSDT | 4h | long_short | -59.1% | -16.4% | 76.4% | -0.02 | 0.02 | -0.11 | -27.4% | 657 | 26.5% | 1.00 | -59.2% |
| `alpha_080_ethusdt_1d_rsi_regime_14_55_48_42_lo` | ETHUSDT | 1d | long_only | +795.6% | +44.2% | 53.8% | 0.96 | 0.91 | 1.13 | +107.2% | 45 | 33.3% | 2.74 | +223.6% |
| `alpha_081_xauusd_30m_heiken_ma_cross_sma_12_26_lo` | XAUUSD | 30m | long_only | +4.9% | +1.6% | 28.2% | 0.18 | 0.13 | 0.26 | +2.9% | 1,149 | 32.8% | 1.03 | +80.5% |
| `alpha_082_xauusd_1h_heiken_ma_cross_ema_9_21_ls` | XAUUSD | 1h | long_short | -34.4% | -10.0% | 55.8% | -0.39 | -1.59 | 1.11 | +40.6% | 1,536 | 26.2% | 0.92 | +104.4% |
| `alpha_083_xauusd_4h_heiken_ma_cross_ema_8_21_lo` | XAUUSD | 4h | long_only | +88.8% | +13.6% | 21.8% | 0.95 | 0.94 | 1.01 | +29.6% | 216 | 33.8% | 1.64 | +99.2% |
| `alpha_084_xauusd_1h_ma_cross_ema_12_48_lo` | XAUUSD | 1h | long_only | +51.6% | +11.0% | 22.4% | 0.78 | 0.77 | 0.84 | +19.3% | 439 | 28.9% | 1.31 | +104.4% |
| `alpha_085_xauusd_1d_ma_cross_ema_10_50_lo` | XAUUSD | 1d | long_only | +118.4% | +13.9% | 15.2% | 0.94 | 0.79 | 1.23 | +53.9% | 25 | 40.0% | 5.10 | +98.6% |
| `alpha_086_ethusdt_15m_ma_cross_sma_28_101_lo` | ETHUSDT | 15m | long_only | -30.5% | -13.7% | 54.5% | -0.05 | -0.18 | 0.35 | +4.8% | 545 | 32.8% | 0.99 | -54.1% |
| `alpha_087_ethusdt_1h_ma_cross_ema_12_36_ls` | ETHUSDT | 1h | long_short | -58.3% | -19.6% | 70.3% | -0.08 | 0.15 | -0.62 | -47.7% | 1,082 | 25.1% | 0.99 | +40.4% |
| `alpha_088_ethusdt_1h_heiken_ma_cross_ema_9_26_ls` | ETHUSDT | 1h | long_short | -85.2% | -38.0% | 88.4% | -0.49 | -0.48 | -0.52 | -45.4% | 1,425 | 25.3% | 0.92 | +40.4% |
| `alpha_089_ethusdt_4h_heiken_ma_cross_ema_8_21_ls` | ETHUSDT | 4h | long_short | -74.9% | -24.1% | 84.5% | -0.14 | 0.11 | -0.76 | -62.0% | 521 | 26.5% | 0.97 | -58.9% |
| `alpha_090_ethusdt_1d_ma_cross_ema_10_30_lo` | ETHUSDT | 1d | long_only | +51.5% | +7.2% | 71.2% | 0.39 | 0.16 | 1.01 | +89.2% | 35 | 34.3% | 1.47 | +226.0% |
| `alpha_091_xauusd_15m_bollinger_reversion_20_2_2_0_0_ls_sl0_6tp0` | XAUUSD | 15m | long_short | -48.3% | -23.5% | 55.9% | -2.34 | -1.82 | -3.51 | -26.3% | 2,706 | 60.9% | 0.83 | +55.4% |
| `alpha_092_xauusd_1h_bollinger_reversion_20_2_0_0_0_lo` | XAUUSD | 1h | long_only | -9.2% | -2.4% | 32.0% | -0.15 | 0.97 | -1.25 | -25.3% | 623 | 68.7% | 0.95 | +104.4% |
| `alpha_093_xauusd_5m_bollinger_reversion_30_2_5_0_0_ls_sl0_35tp0` | XAUUSD | 5m | long_short | -65.3% | -51.1% | 65.4% | -7.20 | -7.38 | -7.03 | -30.5% | 2,651 | 51.9% | 0.66 | +6.2% |
| `alpha_094_xauusd_1h_vol_expansion_breakout_14_1_6_8_ls` | XAUUSD | 1h | long_short | -40.4% | -12.1% | 46.9% | -0.99 | -1.74 | 0.21 | +2.4% | 869 | 40.9% | 0.80 | +104.4% |
| `alpha_095_xauusd_30m_vol_expansion_breakout_20_1_8_10_lo` | XAUUSD | 30m | long_only | -10.2% | -3.5% | 27.8% | -0.39 | -0.29 | -0.56 | -6.3% | 467 | 44.3% | 0.91 | +80.5% |
| `alpha_096_ethusdt_1h_bollinger_reversion_20_2_2_0_0_ls_sl2_5tp0` | ETHUSDT | 1h | long_short | -77.7% | -31.3% | 79.2% | -1.04 | -0.89 | -1.37 | -44.2% | 1,178 | 61.4% | 0.87 | +40.4% |
| `alpha_097_ethusdt_4h_bollinger_reversion_20_2_0_0_0_lo` | ETHUSDT | 4h | long_only | -76.3% | -25.0% | 81.8% | -0.52 | -0.70 | -0.08 | -15.1% | 200 | 64.5% | 0.73 | -58.9% |
| `alpha_098_ethusdt_15m_bollinger_reversion_24_2_5_0_0_ls_sl1_5tp2` | ETHUSDT | 15m | long_short | -88.5% | -58.4% | 89.0% | -2.65 | -2.31 | -3.63 | -53.4% | 1,906 | 58.5% | 0.79 | -54.1% |
| `alpha_099_ethusdt_1h_vol_expansion_breakout_14_1_8_8_ls` | ETHUSDT | 1h | long_short | -13.1% | -3.4% | 41.6% | 0.05 | 0.09 | -0.05 | -8.0% | 782 | 45.4% | 1.01 | +40.4% |
| `alpha_100_ethusdt_4h_vol_expansion_breakout_14_1_6_8_ls` | ETHUSDT | 4h | long_short | +36.4% | +6.4% | 41.1% | 0.35 | 0.35 | 0.35 | +9.9% | 322 | 46.9% | 1.13 | -58.9% |

## 2. Cumulative Top-9 Ranking Board (OOS Sharpe สูงสุด → DD ต่ำสุด)

| Rank | Model ID | Sym | TF | OOS Sharpe | OOS Ret | Max DD | Trades | DSR≈ | Batch |
|---:|---|---|---|---:|---:|---:|---:|---:|---|
| **#1** | `alpha_052_xauusd_15m_asia_range_breakout_0_7_17_0_8_ls_sl0_5tp1` | XAUUSD | 15m | 2.27 | +8.9% | 24.3% | 435 | 0.00 | `2026-11-25` |
| **#2** | `alpha_065_xauusd_4h_impulse_efficiency_3_20_1_8_0_75_10_continua` | XAUUSD | 4h | 1.79 | +44.6% | 35.5% | 481 | 0.00 | `2026-11-26` |
| **#3** | `alpha_051_xauusd_15m_asia_range_breakout_0_7_20_ls` | XAUUSD | 15m | 1.31 | +15.7% | 16.1% | 772 | 0.00 | `2026-11-25` |
| **#4** | `alpha_024_xauusd_1d_momentum_roc_20_lo` | XAUUSD | 1d | 1.22 | +52.2% | 16.0% | 100 | 0.00 | `2026-11-25` |
| **#5** | `alpha_075_xauusd_4h_rsi_regime_14_55_50_45_ls` | XAUUSD | 4h | 1.17 | +43.9% | 25.4% | 609 | 0.00 | `2026-11-26` |
| **#6** | `alpha_011_xauusd_4h_ma_cross_ema_5_20_ls` | XAUUSD | 4h | 1.11 | +42.4% | 34.8% | 621 | 0.00 | `2026-11-24` |
| **#7** | `alpha_022_xauusd_4h_momentum_roc_24_lo` | XAUUSD | 4h | 1.11 | +33.3% | 22.5% | 468 | 0.00 | `2026-11-25` |
| **#8** | `alpha_083_xauusd_4h_heiken_ma_cross_ema_8_21_lo` | XAUUSD | 4h | 1.01 | +29.6% | 21.8% | 216 | 0.00 | `2026-11-26` |
| **#9** | `alpha_055_xauusd_1h_session_time_13_20_short_inside_so` | XAUUSD | 1h | 0.97 | +18.6% | 43.8% | 1,460 | 0.00 | `2026-11-25` |

### โมเดลวันนี้ที่ไม่ผ่าน Hard Gate

- `alpha_069_ethusdt_4h_impulse_efficiency_3_20_1_8_0_75_12_continu`: เหตุผล `MAX_DD_EXCEEDS_50PCT`
- `alpha_085_xauusd_1d_ma_cross_ema_10_50_lo`: เหตุผล `TRADES_LT_30`
- `alpha_080_ethusdt_1d_rsi_regime_14_55_48_42_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT`
- `alpha_082_xauusd_1h_heiken_ma_cross_ema_9_21_ls`: เหตุผล `MAX_DD_EXCEEDS_50PCT`
- `alpha_090_ethusdt_1d_ma_cross_ema_10_30_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT`
- `alpha_086_ethusdt_15m_ma_cross_sma_28_101_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT`
- `alpha_076_ethusdt_1d_rsi_reversion_2_10_90_65_35_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT`
- `alpha_099_ethusdt_1h_vol_expansion_breakout_14_1_8_8_ls`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_097_ethusdt_4h_bollinger_reversion_20_2_0_0_0_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_079_ethusdt_4h_rsi_regime_14_55_50_45_ls`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_070_ethusdt_1h_impulse_efficiency_6_24_2_0_0_7_18_continua`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_072_xauusd_4h_rsi_reversion_3_15_85_60_40_lo`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_088_ethusdt_1h_heiken_ma_cross_ema_9_26_ls`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_095_xauusd_30m_vol_expansion_breakout_20_1_8_10_lo`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_066_ethusdt_1h_impulse_efficiency_3_20_2_2_0_78_12_reversa`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_087_ethusdt_1h_ma_cross_ema_12_36_ls`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_078_ethusdt_1h_rsi_reversion_14_25_75_50_50_ls_sl2_5tp0`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_089_ethusdt_4h_heiken_ma_cross_ema_8_21_ls`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_061_xauusd_1h_impulse_efficiency_3_20_1_8_0_7_10_continuat`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_077_ethusdt_4h_rsi_reversion_4_20_80_55_45_ls`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_092_xauusd_1h_bollinger_reversion_20_2_0_0_0_lo`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_068_ethusdt_30m_impulse_efficiency_3_24_2_0_0_75_12_contin`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_096_ethusdt_1h_bollinger_reversion_20_2_2_0_0_ls_sl2_5tp0`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_073_xauusd_1h_rsi_reversion_14_28_72_55_45_ls`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_064_xauusd_30m_impulse_efficiency_3_24_2_0_0_75_12_continu`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_062_xauusd_1h_impulse_efficiency_3_20_2_2_0_8_12_reversal`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_067_ethusdt_15m_impulse_efficiency_4_30_2_4_0_78_16_contin`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_063_xauusd_15m_impulse_efficiency_4_30_2_2_0_75_16_continu`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_091_xauusd_15m_bollinger_reversion_20_2_2_0_0_ls_sl0_6tp0`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_098_ethusdt_15m_bollinger_reversion_24_2_5_0_0_ls_sl1_5tp2`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_093_xauusd_5m_bollinger_reversion_30_2_5_0_0_ls_sl0_35tp0`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
