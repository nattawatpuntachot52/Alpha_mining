# Alpha_mining — Alpha Mining Daily Summary (2026-11-27)

- **Generated (UTC):** `2026-11-27T00:15:24Z`
- **Models Tested Today:** `10` (`ETHUSDT`: 5, `XAUUSD`: 5) | **Rounds:** `[1]` | **Cumulative Trials (`N_trials`):** `110`
- **Top-9 Rule:** `OOS Sharpe DESC -> Max DD ASC` | **Hard Gates:** `no liquidation`, `trades >= 30`, `OOS profit > 0`, `Max DD <= 50%`
- **Multiple-testing:** expected max daily Sharpe under H0 for `N=110` trials = `0.214848`; `DSR≈` is the probability a model beats that haircut.
- **XAUUSD data:** public feed is `PAXGUSDT` (gold-backed, 24/7) as a PROXY for broker XAUUSD; costs 2 bps/side. ETHUSDT = Binance USD-M perp, 5 bps/side.

## 1. โมเดลที่ Mine วันนี้ (2026-11-27 — 10 โมเดล)

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

- `alpha_108_ethusdt_1d_calendar_turn_x_long_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE`
- `alpha_101_xauusd_1d_calendar_turn_x_long_lo`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_107_ethusdt_1d_calendar_turn_x_long_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_103_xauusd_1d_calendar_turn_x_long_lo`: เหตุผล `OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_106_ethusdt_1d_calendar_turn_x_long_lo`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_109_ethusdt_1d_calendar_turn_x_short_so`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
- `alpha_110_ethusdt_1h_session_time_13_21_long_inside_short_outsid`: เหตุผล `MAX_DD_EXCEEDS_50PCT, OOS_NOT_PROFITABLE, OOS_SHARPE_LE_0`
