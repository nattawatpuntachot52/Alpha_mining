# Alpha_mining — Alpha Mining Daily Summary (2026-11-25)

- **Generated (UTC):** `2026-11-25T05:10:17Z`
- **Models Tested Today:** `20` (`ETHUSDT`: 10, `XAUUSD`: 10) | **Rounds:** `[1, 2]` | **Cumulative Trials (`N_trials`):** `40`
- **Top-9 Rule:** `OOS Sharpe DESC -> Max DD ASC` | **Hard Gates:** `no liquidation`, `trades >= 30`, `OOS profit > 0`, `Max DD <= 50%`
- **Multiple-testing:** expected max daily Sharpe under H0 for `N=40` trials = `0.107742`; `DSR≈` is the probability a model beats that haircut.
- **XAUUSD data:** public feed is `PAXGUSDT` (gold-backed, 24/7) as a PROXY for broker XAUUSD; costs 2 bps/side. ETHUSDT = Binance USD-M perp, 5 bps/side.

## 1. โมเดลที่ Mine วันนี้ (2026-11-25 — 20 โมเดล)

| Model ID | Sym | TF | Dir | Return | CAGR | Max DD | Sharpe | IS Sh | OOS Sh | OOS Ret | Trades | Win% | PF | B&H |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `alpha_021_xauusd_1h_momentum_roc_14_ls` | XAUUSD | 1h | long_short | -94.8% | -52.2% | 95.2% | -3.35 | -5.79 | -0.12 | -8.3% | 5,318 | 23.6% | 0.67 | +106.7% |
| `alpha_022_xauusd_4h_momentum_roc_24_lo` | XAUUSD | 4h | long_only | +82.5% | +12.8% | 22.5% | 0.90 | 0.80 | 1.11 | +33.3% | 468 | 34.8% | 1.45 | +101.3% |
| `alpha_023_xauusd_4h_momentum_roc_48_ls` | XAUUSD | 4h | long_short | +21.9% | +4.0% | 32.0% | 0.30 | 0.48 | 0.09 | -1.7% | 575 | 29.7% | 1.13 | +101.3% |
| `alpha_024_xauusd_1d_momentum_roc_20_lo` | XAUUSD | 1d | long_only | +97.0% | +12.0% | 16.0% | 0.83 | 0.59 | 1.22 | +52.2% | 100 | 37.0% | 2.40 | +98.6% |
| `alpha_025_xauusd_30m_momentum_roc_28_0_25_lo` | XAUUSD | 30m | long_only | -60.6% | -26.6% | 61.2% | -1.99 | -3.13 | 0.05 | -0.6% | 2,223 | 24.1% | 0.73 | +84.6% |
| `alpha_026_ethusdt_1h_momentum_roc_24_ls` | ETHUSDT | 1h | long_short | -99.7% | -76.0% | 99.7% | -1.99 | -2.45 | -0.90 | -58.7% | 3,490 | 23.2% | 0.76 | +41.8% |
| `alpha_027_ethusdt_4h_momentum_roc_18_lo` | ETHUSDT | 4h | long_only | -35.3% | -8.4% | 70.7% | 0.04 | 0.33 | -0.74 | -45.4% | 598 | 30.4% | 1.02 | -61.4% |
| `alpha_028_ethusdt_4h_momentum_roc_42_ls` | ETHUSDT | 4h | long_short | -15.4% | -3.3% | 68.3% | 0.26 | 0.41 | -0.13 | -30.9% | 790 | 30.9% | 1.09 | -61.4% |
| `alpha_029_ethusdt_1d_momentum_roc_14_lo` | ETHUSDT | 1d | long_only | +717.5% | +42.0% | 46.2% | 0.92 | 0.99 | 0.72 | +50.9% | 126 | 36.5% | 1.98 | +228.7% |
| `alpha_030_ethusdt_1d_momentum_roc_30_ls` | ETHUSDT | 1d | long_short | +1926.5% | +65.2% | 68.6% | 1.07 | 0.83 | 1.84 | +394.7% | 160 | 32.5% | 2.05 | +228.7% |
| `alpha_031_xauusd_30m_donchian_breakout_40_10_ls` | XAUUSD | 30m | long_short | -25.8% | -9.5% | 41.9% | -0.40 | -1.08 | 0.87 | +16.5% | 847 | 34.7% | 0.91 | +80.6% |
| `alpha_032_xauusd_1h_donchian_breakout_20_10_lo` | XAUUSD | 1h | long_only | +17.8% | +4.2% | 21.6% | 0.35 | 0.19 | 0.66 | +12.6% | 391 | 37.3% | 1.13 | +102.2% |
| `alpha_033_xauusd_1h_donchian_breakout_40_15_14_0_9_lo` | XAUUSD | 1h | long_only | +0.0% | +0.0% | 0.0% | 0.00 | 0.00 | 0.00 | +0.0% | 0 | 0.0% | 0.00 | +102.2% |
| `alpha_034_xauusd_4h_donchian_breakout_55_20_lo` | XAUUSD | 4h | long_only | +27.3% | +5.0% | 21.6% | 0.43 | 0.10 | 0.95 | +24.9% | 70 | 40.0% | 1.49 | +97.0% |
| `alpha_035_xauusd_15m_donchian_breakout_60_20_14_0_85_lo` | XAUUSD | 15m | long_only | +0.0% | +0.0% | 0.0% | 0.00 | 0.00 | 0.00 | +0.0% | 0 | 0.0% | 0.00 | +53.6% |
| `alpha_036_ethusdt_30m_donchian_breakout_40_10_ls` | ETHUSDT | 30m | long_short | -65.3% | -29.7% | 69.7% | -0.48 | -0.63 | -0.09 | -12.0% | 974 | 35.5% | 0.92 | -15.8% |
| `alpha_037_ethusdt_1h_donchian_breakout_24_12_ls` | ETHUSDT | 1h | long_short | -83.6% | -36.4% | 90.0% | -0.61 | -0.95 | 0.10 | -10.9% | 808 | 33.8% | 0.88 | +41.8% |
| `alpha_038_ethusdt_4h_donchian_breakout_20_10_lo` | ETHUSDT | 4h | long_only | -15.5% | -3.3% | 54.6% | 0.11 | 0.07 | 0.22 | +2.1% | 151 | 28.5% | 1.08 | -61.4% |
| `alpha_039_ethusdt_1d_donchian_breakout_20_10_ls` | ETHUSDT | 1d | long_short | +88.5% | +11.2% | 80.0% | 0.48 | 0.63 | 0.06 | -16.8% | 62 | 40.3% | 1.53 | +228.7% |
| `alpha_040_ethusdt_15m_donchian_breakout_80_20_14_0_85_ls` | ETHUSDT | 15m | long_short | +0.0% | +0.0% | 0.0% | 0.00 | 0.00 | 0.00 | +0.0% | 0 | 0.0% | 0.00 | -53.6% |

## 2. Cumulative Top-9 Ranking Board (OOS Sharpe สูงสุด → DD ต่ำสุด)

| Rank | Model ID | Sym | TF | OOS Sharpe | OOS Ret | Max DD | Trades | DSR≈ | Batch |
|---:|---|---|---|---:|---:|---:|---:|---:|---|
| **#1** | `alpha_024_xauusd_1d_momentum_roc_20_lo` | XAUUSD | 1d | 1.22 | +52.2% | 16.0% | 100 | 0.00 | `2026-11-25` |
| **#2** | `alpha_011_xauusd_4h_ma_cross_ema_5_20_ls` | XAUUSD | 4h | 1.11 | +42.4% | 34.8% | 621 | 0.00 | `2026-11-24` |
| **#3** | `alpha_022_xauusd_4h_momentum_roc_24_lo` | XAUUSD | 4h | 1.11 | +33.3% | 22.5% | 468 | 0.00 | `2026-11-25` |
| **#4** | `alpha_034_xauusd_4h_donchian_breakout_55_20_lo` | XAUUSD | 4h | 0.95 | +24.9% | 21.6% | 70 | 0.00 | `2026-11-25` |
| **#5** | `alpha_031_xauusd_30m_donchian_breakout_40_10_ls` | XAUUSD | 30m | 0.87 | +16.5% | 41.9% | 847 | 0.00 | `2026-11-25` |
| **#6** | `alpha_029_ethusdt_1d_momentum_roc_14_lo` | ETHUSDT | 1d | 0.72 | +50.9% | 46.2% | 126 | 0.00 | `2026-11-25` |
| **#7** | `alpha_013_xauusd_1h_session_time_19_2_long_inside_lo` | XAUUSD | 1h | 0.71 | +12.2% | 23.2% | 1,461 | 0.00 | `2026-11-24` |
| **#8** | `alpha_032_xauusd_1h_donchian_breakout_20_10_lo` | XAUUSD | 1h | 0.66 | +12.6% | 21.6% | 391 | 0.00 | `2026-11-25` |
| **#9** | `alpha_015_xauusd_1d_calendar_turn_x_long_lo` | XAUUSD | 1d | 0.60 | +7.8% | 6.9% | 72 | 0.00 | `2026-11-24` |

### โมเดลวันนี้ที่ไม่ผ่าน Hard Gate

- `alpha_030_ethusdt_1d_momentum_roc_30_ls`: เหตุผล `MAX_DD_EXCEEDS_50PCT`
- `alpha_038_ethusdt_4h_donchian_breakout_20_10_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT`
- `alpha_037_ethusdt_1h_donchian_breakout_24_12_ls`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE`
- `alpha_023_xauusd_4h_momentum_roc_48_ls`: เหตุผล `OOS_NOT_PROFITABLE`
- `alpha_039_ethusdt_1d_donchian_breakout_20_10_ls`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE`
- `alpha_025_xauusd_30m_momentum_roc_28_0_25_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE`
- `alpha_033_xauusd_1h_donchian_breakout_40_15_14_0_9_lo`: เหตุผล `TRADES_LT_30, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_035_xauusd_15m_donchian_breakout_60_20_14_0_85_lo`: เหตุผล `TRADES_LT_30, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_040_ethusdt_15m_donchian_breakout_80_20_14_0_85_ls`: เหตุผล `TRADES_LT_30, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_036_ethusdt_30m_donchian_breakout_40_10_ls`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_021_xauusd_1h_momentum_roc_14_ls`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_028_ethusdt_4h_momentum_roc_42_ls`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_027_ethusdt_4h_momentum_roc_18_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_026_ethusdt_1h_momentum_roc_24_ls`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
