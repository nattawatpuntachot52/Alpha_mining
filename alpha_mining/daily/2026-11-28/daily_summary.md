# Alpha_mining — Alpha Mining Daily Summary (2026-11-28)

- **Generated (UTC):** `2026-11-28T00:15:24Z`
- **Models Tested Today:** `10` (`ETHUSDT`: 5, `XAUUSD`: 5) | **Rounds:** `[1]` | **Cumulative Trials (`N_trials`):** `140`
- **Top-9 Rule:** `OOS Sharpe DESC -> Max DD ASC` | **Hard Gates:** `no liquidation`, `trades >= 30`, `OOS profit > 0`, `Max DD <= 50%`
- **Multiple-testing:** expected max daily Sharpe under H0 for `N=140` trials = `0.232966`; `DSR≈` is the probability a model beats that haircut.
- **XAUUSD data:** public feed is `PAXGUSDT` (gold-backed, 24/7) as a PROXY for broker XAUUSD; costs 2 bps/side. ETHUSDT = Binance USD-M perp, 5 bps/side.

## 1. โมเดลที่ Mine วันนี้ (2026-11-28 — 10 โมเดล)

| Model ID | Sym | TF | Dir | Return | CAGR | Max DD | Sharpe | IS Sh | OOS Sh | OOS Ret | Trades | Win% | PF | B&H |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `alpha_052_xauusd_15m_asia_range_breakout_0_7_17_0_8_ls_sl0_5tp1` | XAUUSD | 15m | long_short | -15.1% | -6.4% | 24.3% | -1.14 | -2.32 | 2.07 | +7.9% | 434 | 39.6% | 0.80 | +53.8% |
| `alpha_065_xauusd_4h_impulse_efficiency_3_20_1_8_0_75_10_continua` | XAUUSD | 4h | long_short | +22.0% | +4.1% | 35.5% | 0.39 | -0.44 | 1.84 | +46.8% | 481 | 44.7% | 1.10 | +98.4% |
| `alpha_051_xauusd_15m_asia_range_breakout_0_7_20_ls` | XAUUSD | 15m | long_short | +5.9% | +2.3% | 15.8% | 0.24 | -0.27 | 1.09 | +12.8% | 772 | 43.9% | 1.04 | +53.8% |
| `alpha_024_xauusd_1d_momentum_roc_20_lo` | XAUUSD | 1d | long_only | +94.9% | +11.8% | 16.0% | 0.82 | 0.58 | 1.20 | +50.9% | 100 | 36.0% | 2.35 | +97.9% |
| `alpha_075_xauusd_4h_rsi_regime_14_55_50_45_ls` | XAUUSD | 4h | long_short | +79.5% | +12.4% | 25.4% | 0.76 | 0.48 | 1.22 | +46.2% | 609 | 32.8% | 1.28 | +98.4% |
| `alpha_029_ethusdt_1d_momentum_roc_14_lo` | ETHUSDT | 1d | long_only | +674.3% | +40.7% | 46.2% | 0.90 | 0.97 | 0.72 | +50.9% | 126 | 35.7% | 1.96 | +193.0% |
| `alpha_100_ethusdt_4h_vol_expansion_breakout_14_1_6_8_ls` | ETHUSDT | 4h | long_short | +34.5% | +6.1% | 41.1% | 0.34 | 0.34 | 0.35 | +9.9% | 321 | 46.7% | 1.13 | -60.8% |
| `alpha_059_ethusdt_15m_asia_range_breakout_0_7_21_ls` | ETHUSDT | 15m | long_short | +91.1% | +30.1% | 41.7% | 0.80 | 1.11 | -0.14 | -8.7% | 824 | 44.9% | 1.14 | -54.0% |
| `alpha_006_ethusdt_1h_momentum_roc_14_lo` | ETHUSDT | 1h | long_only | -66.8% | -24.1% | 76.8% | -0.38 | 0.33 | -2.18 | -71.2% | 2,281 | 26.3% | 0.94 | +44.8% |
| `alpha_007_ethusdt_1h_momentum_roc_90_lo` | ETHUSDT | 1h | long_only | -42.2% | -12.8% | 69.2% | -0.09 | 0.43 | -1.47 | -55.4% | 864 | 27.1% | 0.98 | +44.8% |

## 2. Cumulative Top-9 Ranking Board (OOS Sharpe สูงสุด → DD ต่ำสุด)

| Rank | Model ID | Sym | TF | OOS Sharpe | OOS Ret | Max DD | Trades | DSR≈ | Batch |
|---:|---|---|---|---:|---:|---:|---:|---:|---|
| **#1** | `alpha_052_xauusd_15m_asia_range_breakout_0_7_17_0_8_ls_sl0_5tp1` | XAUUSD | 15m | 2.07 | +7.9% | 24.3% | 434 | 0.00 | `2026-11-28` |
| **#2** | `alpha_065_xauusd_4h_impulse_efficiency_3_20_1_8_0_75_10_continua` | XAUUSD | 4h | 1.84 | +46.8% | 35.5% | 481 | 0.00 | `2026-11-28` |
| **#3** | `alpha_075_xauusd_4h_rsi_regime_14_55_50_45_ls` | XAUUSD | 4h | 1.22 | +46.2% | 25.4% | 609 | 0.00 | `2026-11-28` |
| **#4** | `alpha_024_xauusd_1d_momentum_roc_20_lo` | XAUUSD | 1d | 1.20 | +50.9% | 16.0% | 100 | 0.00 | `2026-11-28` |
| **#5** | `alpha_124_xauusd_4h_ma_cross_ema_8_26_ls` | XAUUSD | 4h | 1.15 | +46.4% | 26.4% | 410 | 0.00 | `2026-11-27` |
| **#6** | `alpha_011_xauusd_4h_ma_cross_ema_5_20_ls` | XAUUSD | 4h | 1.11 | +42.4% | 34.8% | 621 | 0.00 | `2026-11-24` |
| **#7** | `alpha_022_xauusd_4h_momentum_roc_24_lo` | XAUUSD | 4h | 1.11 | +33.3% | 22.5% | 468 | 0.00 | `2026-11-25` |
| **#8** | `alpha_051_xauusd_15m_asia_range_breakout_0_7_20_ls` | XAUUSD | 15m | 1.09 | +12.8% | 15.8% | 772 | 0.00 | `2026-11-28` |
| **#9** | `alpha_083_xauusd_4h_heiken_ma_cross_ema_8_21_lo` | XAUUSD | 4h | 1.01 | +29.6% | 21.8% | 216 | 0.00 | `2026-11-26` |

### โมเดลวันนี้ที่ไม่ผ่าน Hard Gate

- `alpha_059_ethusdt_15m_asia_range_breakout_0_7_21_ls`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_007_ethusdt_1h_momentum_roc_90_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_006_ethusdt_1h_momentum_roc_14_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
