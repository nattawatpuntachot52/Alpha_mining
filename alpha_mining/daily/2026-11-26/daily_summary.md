# Alpha_mining — Alpha Mining Daily Summary (2026-11-26)

- **Generated (UTC):** `2026-11-26T00:15:31Z`
- **Models Tested Today:** `10` (`ETHUSDT`: 5, `XAUUSD`: 5) | **Rounds:** `[1]` | **Cumulative Trials (`N_trials`):** `70`
- **Top-9 Rule:** `OOS Sharpe DESC -> Max DD ASC` | **Hard Gates:** `no liquidation`, `trades >= 30`, `OOS profit > 0`, `Max DD <= 50%`
- **Multiple-testing:** expected max daily Sharpe under H0 for `N=70` trials = `0.213674`; `DSR≈` is the probability a model beats that haircut.
- **XAUUSD data:** public feed is `PAXGUSDT` (gold-backed, 24/7) as a PROXY for broker XAUUSD; costs 2 bps/side. ETHUSDT = Binance USD-M perp, 5 bps/side.

## 1. โมเดลที่ Mine วันนี้ (2026-11-26 — 10 โมเดล)

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

## 2. Cumulative Top-9 Ranking Board (OOS Sharpe สูงสุด → DD ต่ำสุด)

| Rank | Model ID | Sym | TF | OOS Sharpe | OOS Ret | Max DD | Trades | DSR≈ | Batch |
|---:|---|---|---|---:|---:|---:|---:|---:|---|
| **#1** | `alpha_052_xauusd_15m_asia_range_breakout_0_7_17_0_8_ls_sl0_5tp1` | XAUUSD | 15m | 2.27 | +8.9% | 24.3% | 435 | 0.00 | `2026-11-25` |
| **#2** | `alpha_065_xauusd_4h_impulse_efficiency_3_20_1_8_0_75_10_continua` | XAUUSD | 4h | 1.79 | +44.6% | 35.5% | 481 | 0.00 | `2026-11-26` |
| **#3** | `alpha_051_xauusd_15m_asia_range_breakout_0_7_20_ls` | XAUUSD | 15m | 1.31 | +15.7% | 16.1% | 772 | 0.00 | `2026-11-25` |
| **#4** | `alpha_024_xauusd_1d_momentum_roc_20_lo` | XAUUSD | 1d | 1.22 | +52.2% | 16.0% | 100 | 0.00 | `2026-11-25` |
| **#5** | `alpha_011_xauusd_4h_ma_cross_ema_5_20_ls` | XAUUSD | 4h | 1.11 | +42.4% | 34.8% | 621 | 0.00 | `2026-11-24` |
| **#6** | `alpha_022_xauusd_4h_momentum_roc_24_lo` | XAUUSD | 4h | 1.11 | +33.3% | 22.5% | 468 | 0.00 | `2026-11-25` |
| **#7** | `alpha_055_xauusd_1h_session_time_13_20_short_inside_so` | XAUUSD | 1h | 0.97 | +18.6% | 43.8% | 1,460 | 0.00 | `2026-11-25` |
| **#8** | `alpha_034_xauusd_4h_donchian_breakout_55_20_lo` | XAUUSD | 4h | 0.95 | +24.9% | 21.6% | 70 | 0.00 | `2026-11-25` |
| **#9** | `alpha_031_xauusd_30m_donchian_breakout_40_10_ls` | XAUUSD | 30m | 0.87 | +16.5% | 41.9% | 847 | 0.00 | `2026-11-25` |

### โมเดลวันนี้ที่ไม่ผ่าน Hard Gate

- `alpha_069_ethusdt_4h_impulse_efficiency_3_20_1_8_0_75_12_continu`: เหตุผล `MAX_DD_EXCEEDS_50PCT`
- `alpha_070_ethusdt_1h_impulse_efficiency_6_24_2_0_0_7_18_continua`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_066_ethusdt_1h_impulse_efficiency_3_20_2_2_0_78_12_reversa`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_061_xauusd_1h_impulse_efficiency_3_20_1_8_0_7_10_continuat`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_068_ethusdt_30m_impulse_efficiency_3_24_2_0_0_75_12_contin`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_064_xauusd_30m_impulse_efficiency_3_24_2_0_0_75_12_continu`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_062_xauusd_1h_impulse_efficiency_3_20_2_2_0_8_12_reversal`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_067_ethusdt_15m_impulse_efficiency_4_30_2_4_0_78_16_contin`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_063_xauusd_15m_impulse_efficiency_4_30_2_2_0_75_16_continu`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
