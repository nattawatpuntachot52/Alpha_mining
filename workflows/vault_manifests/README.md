# Vault Manifests (`workflows/vault_manifests/`)

ชั้นนี้เก็บ **SHA-256 Metadata Manifest** ขนาดเล็กของข้อมูล Quant (เช่น Parquet feature datasets, backtest caches, state snapshots) เพื่อไม่ให้ไฟล์ไบนารีขนาดใหญ่ถูก commit เข้า Git repo

## สถาปัตยกรรม 3 ชั้น

1. **Git Repo SSOT (`workflows/vault_manifests/*.manifest.json`)**: เก็บ `artifact_id`, `category`, `compression`, `archive_sha256`, รายชื่อไฟล์พร้อม `sha256` รายไฟล์, `cache_key` และ `gdrive_file_id`
2. **Hot Cache (GitHub Actions Cache 10 GB / `.vault_cache/`)**: ดึง/พักไฟล์จาก `actions/cache` ด้วย `cache_key` เพื่อลดเวลาโหลดใน CI และงานรันซ้ำ
3. **Master Durable Vault (Google Drive: `Alpha_mining_Vault`)**:
   - `datasets/` (`12q4OVX65a0R1fubWJuey5kqkXUNoDXsX`)
   - `backtests/` (`1mSUfgnR4yNhSi3ggM_DYHMjP9ynB5Yxr`)
   - `state_snapshots/` (`11LgT2EI6OrjeBoF8y91Smz2wEfRwfxbt`)

## ตัวอย่างการใช้งาน

```bash
# 1. แพ็กข้อมูลและสร้าง SHA-256 manifest
python3 scripts/vault_sync.py pack \
  --source data/raw/btc_1m \
  --artifact-id btc_1m_2026 \
  --category dataset

# 2. อัปโหลดเข้า Google Drive Alpha_mining_Vault และอัปเดต gdrive_file_id ลง manifest
python3 scripts/vault_sync.py push-drive \
  --manifest workflows/vault_manifests/btc_1m_2026.manifest.json

# 3. ดึงและตรวจสอบ SHA-256 ครบทุกไฟล์ (ใช้ hot cache .vault_cache/ ก่อนถ้าตรง sha256)
python3 scripts/vault_sync.py pull-drive \
  --manifest workflows/vault_manifests/btc_1m_2026.manifest.json \
  --dest .vault_staging/btc_1m_2026
```
