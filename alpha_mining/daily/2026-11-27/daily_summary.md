# Alpha_mining — Alpha Mining Daily Summary (2026-11-27)

- **Generated (UTC):** `2026-11-27T08:15:23Z`
- **Models Tested Today:** `30` (`ETHUSDT`: 15, `XAUUSD`: 15) | **Rounds:** `[1, 2, 3]` | **Cumulative Trials (`N_trials`):** `130`
- **Top-9 Rule:** `OOS Sharpe DESC -> Max DD ASC` | **Hard Gates:** `no liquidation`, `trades >= 30`, `OOS profit > 0`, `Max DD <= 50%`
- **Multiple-testing:** expected max daily Sharpe under H0 for `N=130` trials = `0.235946`; `DSR≈` is the probability a model beats that haircut.
- **XAUUSD data:** public feed is `PAXGUSDT` (gold-backed, 24/7) as a PROXY for broker XAUUSD; costs 2 bps/side. ETHUSDT = Binance USD-M perp, 5 bps/side.

## 1. โมเดลที่ Mine วันนี้ (2026-11-27 — 30 โมเดล)

| Model ID | Sym | TF | Dir | Return | CAGR | Max DD | Sharpe | IS Sh | OOS Sh | OOS Ret | Trades | Win% | PF | B&H |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `alpha_101_xauusd_1d_calendar_turn_x_long_lo` | XAUUSD | 1d | long_only | +13.6% | +2.1% | 18.0% | 0.28 | 0.70 | -0.09 | -4.1% | 72 | 52.8% | 1.28 | +98.9% |
| `alpha_102_xauusd_1d_calendar_turn_x_long_lo` | XAUUSD | 1d | long_only | +42.0% | +6.0% | 17.8% | 0.76 | 0.92 | 0.58 | +11.0% | 72 | 55.6% | 1.80 | +98.9% |
| `alpha_103_xauusd_1d_calendar_turn_x_long_lo` | XAUUSD | 1d | long_only | -7.1% | -1.2% | 15.3% | -0.09 | 0.20 | -0.47 | -11.4% | 312 | 52.2% | 0.96 | +98.9% |
| `alpha_104_xauusd_1d_calendar_turn_x_long_lo` | XAUUSD | 1d | long_only | -9.6% | -1.7% | 32.3% | -0.10 | -0.76 | 0.78 | +20.7% | 313 | 48.6% | 0.96 | +98.9% |
| `alpha_105_xauusd_1h_session_time_21_5_long_inside_x_lo` | XAUUSD | 1h | long_only | +33.8% | +7.6% | 14.3% | 0.87 | 0.93 | 0.92 | +14.2% | 1,044 | 52.1% | 1.19 | +104.6% |
| `alpha_106_ethusdt_1d_calendar_turn_x_long_lo` | ETHUSDT | 1d | long_only | +334.0% | +27.8% | 64.5% | 0.90 | 1.47 | -0.69 | -35.1% | 72 | 55.6% | 2.04 | +214.8% |
| `alpha_107_ethusdt_1d_calendar_turn_x_long_lo` | ETHUSDT | 1d | long_only | -35.2% | -7.0% | 59.8% | -0.19 | -0.19 | -0.23 | -8.7% | 72 | 48.6% | 0.84 | +214.8% |
| `alpha_108_ethusdt_1d_calendar_turn_x_long_lo` | ETHUSDT | 1d | long_only | -21.7% | -4.0% | 74.9% | 0.12 | 0.16 | 0.03 | -10.0% | 313 | 49.2% | 1.05 | +214.8% |
| `alpha_109_ethusdt_1d_calendar_turn_x_short_so` | ETHUSDT | 1d | short_only | -88.5% | -30.3% | 89.1% | -0.93 | -1.00 | -0.75 | -38.0% | 313 | 46.0% | 0.67 | +214.8% |
| `alpha_110_ethusdt_1h_session_time_13_21_long_inside_short_outsid` | ETHUSDT | 1h | long_short | -99.9% | -81.8% | 99.9% | -2.46 | -2.96 | -1.27 | -68.4% | 2,919 | 44.1% | 0.76 | +41.7% |
| `alpha_111_xauusd_5m_heiken_ma_cross_sma_15_45_lo` | XAUUSD | 5m | long_only | -56.1% | -42.7% | 56.6% | -2.76 | -2.27 | -4.12 | -27.6% | 2,080 | 26.7% | 0.75 | +5.1% |
| `alpha_112_xauusd_5m_donchian_breakout_60_20_lo` | XAUUSD | 5m | long_only | -32.5% | -23.3% | 34.1% | -1.83 | -1.46 | -2.88 | -14.8% | 1,115 | 30.8% | 0.80 | +5.1% |
| `alpha_113_xauusd_5m_rsi_reversion_14_25_75_50_50_ls_sl0_4tp0` | XAUUSD | 5m | long_short | -40.9% | -29.9% | 41.3% | -4.36 | -4.41 | -4.24 | -14.5% | 1,423 | 47.8% | 0.68 | +5.1% |
| `alpha_114_xauusd_5m_vol_expansion_breakout_20_2_2_12_ls` | XAUUSD | 5m | long_short | -81.8% | -68.5% | 82.0% | -7.76 | -7.44 | -8.51 | -42.4% | 4,376 | 26.4% | 0.57 | +5.1% |
| `alpha_115_xauusd_5m_asia_range_breakout_0_7_18_0_7_ls` | XAUUSD | 5m | long_short | -12.1% | -8.3% | 13.8% | -1.45 | -1.59 | -1.06 | -2.4% | 215 | 41.9% | 0.68 | +5.1% |
| `alpha_116_ethusdt_5m_donchian_breakout_72_24_ls` | ETHUSDT | 5m | long_short | -85.5% | -73.0% | 87.6% | -2.33 | -1.85 | -3.51 | -55.5% | 1,651 | 31.0% | 0.81 | -35.2% |
| `alpha_117_ethusdt_5m_bollinger_reversion_30_2_8_0_0_ls_sl1tp1_2` | ETHUSDT | 5m | long_short | -85.3% | -72.7% | 86.1% | -4.61 | -3.89 | -6.43 | -53.2% | 2,026 | 58.0% | 0.73 | -35.2% |
| `alpha_118_ethusdt_5m_vol_expansion_breakout_20_2_5_12_ls` | ETHUSDT | 5m | long_short | -46.7% | -34.7% | 58.6% | -1.22 | -0.42 | -3.53 | -35.2% | 1,209 | 37.7% | 0.87 | -35.2% |
| `alpha_119_ethusdt_5m_heiken_ma_cross_ema_18_54_lo` | ETHUSDT | 5m | long_only | -82.4% | -69.2% | 87.4% | -2.37 | -2.28 | -2.62 | -42.0% | 1,594 | 23.9% | 0.77 | -35.2% |
| `alpha_120_ethusdt_5m_rsi_reversion_14_20_80_50_50_ls_sl1_2tp0` | ETHUSDT | 5m | long_short | -46.8% | -34.8% | 46.8% | -2.27 | -2.17 | -2.56 | -17.8% | 474 | 54.6% | 0.73 | -35.2% |
| `alpha_121_xauusd_15m_ma_cross_ema_20_80_ls_sl1tp2_5` | XAUUSD | 15m | long_short | -48.1% | -23.4% | 52.8% | -1.23 | -1.51 | -0.70 | -12.4% | 1,428 | 20.5% | 0.85 | +54.1% |
| `alpha_122_xauusd_30m_donchian_breakout_30_12_lo` | XAUUSD | 30m | long_only | +8.7% | +2.8% | 22.1% | 0.26 | 0.25 | 0.27 | +2.9% | 469 | 37.1% | 1.08 | +79.9% |
| `alpha_123_xauusd_30m_donchian_breakout_50_15_lo` | XAUUSD | 30m | long_only | +26.3% | +8.1% | 24.1% | 0.58 | 0.53 | 0.69 | +9.1% | 333 | 40.8% | 1.21 | +79.9% |
| `alpha_124_xauusd_4h_ma_cross_ema_8_26_ls` | XAUUSD | 4h | long_short | +74.9% | +11.8% | 26.4% | 0.69 | 0.41 | 1.15 | +46.4% | 410 | 30.2% | 1.30 | +98.9% |
| `alpha_125_xauusd_1h_momentum_roc_48_lo` | XAUUSD | 1h | long_only | -17.4% | -4.7% | 36.8% | -0.24 | -0.72 | 0.44 | +8.5% | 1,333 | 26.5% | 0.94 | +103.9% |
| `alpha_126_ethusdt_4h_ma_cross_ema_8_26_ls` | ETHUSDT | 4h | long_short | -63.0% | -18.0% | 80.3% | -0.02 | 0.13 | -0.38 | -45.1% | 477 | 26.4% | 1.00 | -58.1% |
| `alpha_127_ethusdt_4h_ma_cross_ema_12_40_lo` | ETHUSDT | 4h | long_only | -36.5% | -8.7% | 54.8% | 0.01 | -0.02 | 0.08 | -7.3% | 160 | 21.9% | 1.03 | -58.1% |
| `alpha_128_ethusdt_30m_donchian_breakout_50_15_ls` | ETHUSDT | 30m | long_short | -64.6% | -29.2% | 74.2% | -0.46 | -0.80 | 0.37 | +6.0% | 753 | 35.6% | 0.93 | -18.0% |
| `alpha_129_ethusdt_1h_momentum_roc_48_ls` | ETHUSDT | 1h | long_short | -81.9% | -34.8% | 87.7% | -0.40 | -0.72 | 0.37 | +4.8% | 2,421 | 26.1% | 0.93 | +41.4% |
| `alpha_130_ethusdt_1h_ma_cross_ema_20_60_ls_sl3tp7_5` | ETHUSDT | 1h | long_short | -55.5% | -18.3% | 79.7% | -0.24 | 0.09 | -0.95 | -48.3% | 638 | 25.6% | 0.95 | +41.4% |

## 2. Cumulative Top-9 Ranking Board (OOS Sharpe สูงสุด → DD ต่ำสุด)

| Rank | Model ID | Sym | TF | OOS Sharpe | OOS Ret | Max DD | Trades | DSR≈ | Batch |
|---:|---|---|---|---:|---:|---:|---:|---:|---|
| **#1** | `alpha_052_xauusd_15m_asia_range_breakout_0_7_17_0_8_ls_sl0_5tp1` | XAUUSD | 15m | 2.27 | +8.9% | 24.3% | 435 | 0.00 | `2026-11-25` |
| **#2** | `alpha_065_xauusd_4h_impulse_efficiency_3_20_1_8_0_75_10_continua` | XAUUSD | 4h | 1.79 | +44.6% | 35.5% | 481 | 0.00 | `2026-11-26` |
| **#3** | `alpha_051_xauusd_15m_asia_range_breakout_0_7_20_ls` | XAUUSD | 15m | 1.31 | +15.7% | 16.1% | 772 | 0.00 | `2026-11-25` |
| **#4** | `alpha_024_xauusd_1d_momentum_roc_20_lo` | XAUUSD | 1d | 1.22 | +52.2% | 16.0% | 100 | 0.00 | `2026-11-25` |
| **#5** | `alpha_075_xauusd_4h_rsi_regime_14_55_50_45_ls` | XAUUSD | 4h | 1.17 | +43.9% | 25.4% | 609 | 0.00 | `2026-11-26` |
| **#6** | `alpha_124_xauusd_4h_ma_cross_ema_8_26_ls` | XAUUSD | 4h | 1.15 | +46.4% | 26.4% | 410 | 0.00 | `2026-11-27` |
| **#7** | `alpha_011_xauusd_4h_ma_cross_ema_5_20_ls` | XAUUSD | 4h | 1.11 | +42.4% | 34.8% | 621 | 0.00 | `2026-11-24` |
| **#8** | `alpha_022_xauusd_4h_momentum_roc_24_lo` | XAUUSD | 4h | 1.11 | +33.3% | 22.5% | 468 | 0.00 | `2026-11-25` |
| **#9** | `alpha_083_xauusd_4h_heiken_ma_cross_ema_8_21_lo` | XAUUSD | 4h | 1.01 | +29.6% | 21.8% | 216 | 0.00 | `2026-11-26` |

### โมเดลวันนี้ที่ไม่ผ่าน Hard Gate

- `alpha_128_ethusdt_30m_donchian_breakout_50_15_ls`: เหตุผล `MAX_DD_EXCEEDS_50PCT`
- `alpha_129_ethusdt_1h_momentum_roc_48_ls`: เหตุผล `MAX_DD_EXCEEDS_50PCT`
- `alpha_127_ethusdt_4h_ma_cross_ema_12_40_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE`
- `alpha_108_ethusdt_1d_calendar_turn_x_long_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE`
- `alpha_101_xauusd_1d_calendar_turn_x_long_lo`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_107_ethusdt_1d_calendar_turn_x_long_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_126_ethusdt_4h_ma_cross_ema_8_26_ls`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_103_xauusd_1d_calendar_turn_x_long_lo`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_106_ethusdt_1d_calendar_turn_x_long_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_121_xauusd_15m_ma_cross_ema_20_80_ls_sl1tp2_5`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_109_ethusdt_1d_calendar_turn_x_short_so`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_130_ethusdt_1h_ma_cross_ema_20_60_ls_sl3tp7_5`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_115_xauusd_5m_asia_range_breakout_0_7_18_0_7_ls`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_110_ethusdt_1h_session_time_13_21_long_inside_short_outsid`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_120_ethusdt_5m_rsi_reversion_14_20_80_50_50_ls_sl1_2tp0`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_119_ethusdt_5m_heiken_ma_cross_ema_18_54_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_112_xauusd_5m_donchian_breakout_60_20_lo`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_116_ethusdt_5m_donchian_breakout_72_24_ls`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_118_ethusdt_5m_vol_expansion_breakout_20_2_5_12_ls`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_111_xauusd_5m_heiken_ma_cross_sma_15_45_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_113_xauusd_5m_rsi_reversion_14_25_75_50_50_ls_sl0_4tp0`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_117_ethusdt_5m_bollinger_reversion_30_2_8_0_0_ls_sl1tp1_2`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_114_xauusd_5m_vol_expansion_breakout_20_2_2_12_ls`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
