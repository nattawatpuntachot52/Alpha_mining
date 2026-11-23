# Binance 1-Minute Multi-Market Collector (Singapore VPS Runbook)

Lightweight, crash-safe Python collector for **Alpha_mining** (`01_Alpha_Mining`) capturing synchronized **1-minute UTC snapshots** across 4 Binance market tables, compacting daily into **Parquet (Zstd)** with SHA-256 manifests, and uploading non-destructively to Google Drive (`00_Katherine_Workspace/01_Alpha_Mining/datasets/binance_1m/`).

---

## 1. Captured Markets & Public Endpoints (Read-Only, No API Key Required)

| Dataset Table | Binance Host | Endpoints Used | Key Fields Captured |
|---|---|---|---|
| `options_chain` | `https://eapi.binance.com` | `/eapi/v1/exchangeInfo` (cached 10m), `/eapi/v1/mark`, `/eapi/v1/ticker`, `/eapi/v1/index`, `/eapi/v1/openInterest` | Expiry, DTE, strike, `C`/`P`, spot index, bid/ask/qty, mid, spread%, mark price, `bid_iv`/`ask_iv`/`mark_iv`, Greeks (`delta`, `gamma`, `vega`, `theta`), OI, 24h volume |
| `spot_1m` | `https://data-api.binance.vision` | `/api/v3/ticker/bookTicker`, `/api/v3/ticker/24hr`, `/api/v3/klines` (`1m`, latest closed bar) | Live best bid/ask/qty, mid, spread (bps), 24h volume, plus exact closed 1-minute OHLCV bar (`kline_open`..`kline_trades`) |
| `futures_delivery_usdm` | `https://fapi.binance.com` | `/fapi/v1/exchangeInfo` (cached 10m), `/fapi/v1/premiumIndex`, `/fapi/v1/ticker/bookTicker`, `/fapi/v1/ticker/24hr`, `/fapi/v1/openInterest` | `CURRENT_QUARTER`, `NEXT_QUARTER`, `PERPETUAL` (`BTC`, `ETH`): delivery date, DTE, bid/ask, mark, index, estimated settle, `basis`, `basis_bps`, `annualized_basis`, funding rate, OI |
| `futures_delivery_coinm` | `https://dapi.binance.com` | `/dapi/v1/exchangeInfo` (cached 10m), `/dapi/v1/premiumIndex`, `/dapi/v1/ticker/bookTicker`, `/dapi/v1/ticker/24hr`, `/dapi/v1/openInterest` | `CURRENT_QUARTER`, `NEXT_QUARTER`, `PERPETUAL` (`BTC`, `ETH`): same unified schema + `contract_size` for cross-venue basis / carry / synthetic-forward research |

> **Why Singapore (or Tokyo) VPS?** Binance derivatives hosts (`eapi.binance.com`, `fapi.binance.com`, `dapi.binance.com`) reject US-region cloud IPs (HTTP 451) and GitHub Actions `cron` cannot reliably run at 1-minute cadence. A minimal 1 vCPU / 1–2 GB RAM Linux VPS in Singapore runs this collector comfortably under `< 150 MB` RAM and `< 1.5%` of Binance IP rate limits.

---

## 2. Crash-Safe Spool → Daily Parquet (Zstd) → Google Drive Flow

1. **Every UTC minute (`HH:MM:02Z`):** Captures all enabled markets and appends compact JSONL rows immediately to `data/collector_spool/<YYYY-MM-DD>/<dataset>.jsonl` with line flush (never accumulates a full day in RAM). Writes heartbeat telemetry to `data/collector_spool/health.json`.
2. **At UTC midnight rollover (or next startup after reboot):**
   - Reads the completed day's spool (tolerating/counting any truncated line from sudden power loss).
   - Deduplicates by `(ts_utc_ms, symbol)` and sorts deterministically.
   - Atomically writes typed **Parquet (`zstd`, level 6, dictionary encoding)** to:
     `data/collector_parquet/<dataset>/<YYYY-MM>/<dataset>_<YYYY-MM-DD>.parquet`
   - Writes `<dataset>_<YYYY-MM-DD>.manifest.json` containing SHA-256, row count, unique symbols, minute coverage (`unique_minutes / 1440`), and corrupt-line count.
3. **Non-Destructive Google Drive Upload (`rclone copy`):**
   - Copies both `.parquet` and `.manifest.json` to:
     `gdrive:00_Katherine_Workspace/01_Alpha_Mining/datasets/binance_1m/<dataset>/<YYYY-MM>/`
   - Writes `<dataset>_<YYYY-MM-DD>.uploaded.json` receipt with SHA-256.
   - Any day whose upload fails transiently is automatically retried on the next rollover (or manually via `upload-pending`).
4. **Safe Local Retention Pruning:** Local `.parquet` files older than `retention_local_days` (default: 3 days) are deleted **only** when `.uploaded.json` exists and matches the local file's SHA-256.

---

## 3. Quick Deploy on a Debian/Ubuntu Singapore VPS

```bash
# 1. Install system prerequisites
sudo apt-get update && sudo apt-get install -y git python3 python3-venv rclone

# 2. Configure rclone remote named 'gdrive' pointing to Google Drive
rclone config
rclone lsd gdrive:00_Katherine_Workspace/01_Alpha_Mining/datasets

# 3. Clone Alpha_mining into /opt/alpha_mining (or your preferred path)
sudo mkdir -p /opt/alpha_mining && sudo chown "$USER:$USER" /opt/alpha_mining
git clone https://github.com/nattawatpuntachot52/Alpha_mining.git /opt/alpha_mining
cd /opt/alpha_mining

# 4. Run repeatable setup + config validation + 1-tick smoke test
chmod +x deploy/vps/setup_singapore_vps.sh
./deploy/vps/setup_singapore_vps.sh

# 5. Install and start 24/7 systemd service (edit User/Group in unit file first if not 'alpha')
sudo cp deploy/vps/binance-1m-collector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now binance-1m-collector.service
```

---

## 4. Operational Commands

```bash
# Validate config
.venv-collector/bin/python scripts/collect_binance_1m.py validate-config

# Run one immediate tick
.venv-collector/bin/python scripts/collect_binance_1m.py once

# Check collector heartbeat, spooled days, and local Parquet inventory
.venv-collector/bin/python scripts/collect_binance_1m.py status

# Manually compact a day to Parquet Zstd and upload to Drive
.venv-collector/bin/python scripts/collect_binance_1m.py compact --date 2026-11-23 --upload --prune

# Retry any past compacted days whose Drive upload previously failed
.venv-collector/bin/python scripts/collect_binance_1m.py upload-pending

# Follow live systemd logs
journalctl -u binance-1m-collector.service -f
```
