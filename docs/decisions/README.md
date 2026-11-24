# Architecture & Quant Decision Records (ADRs) — `Alpha_mining`

โฟลเดอร์นี้เก็บ **Decision Records (ADR)** แบบสั้นสำหรับมติสำคัญด้านสถาปัตยกรรม, Quant Research Gates, Backtest Isolation, Ruleset/Reviewer Quorum, และ Data/Vault Hygiene ของโปรเจกต์ `01_Alpha_Mining` เพื่อให้ตรวจสอบเหตุผลย้อนหลังได้จาก repository โดยตรง

## เมื่อไหร่ควรเขียน ADR
- เปลี่ยนโครงสร้าง Backtest Engine, Fill/Accounting Semantics, หรือ Hard Risk Gate (เช่น Liquidation / Max DD Limit)
- เปลี่ยนกติกา PR Protection, Reviewer Quorum, หรือ Scheduled Mining Factory
- ตัดสินใจ Trade-off เชิง Quant หรือ Engineering ที่มีผลระยะยาว (ไม่ต้องเขียนสำหรับแก้บั๊กหรือปรับโค้ดทั่วไป)

## รายการ ADR
| ID | Title | Status | Date |
|---|---|---|---|
| [0000](0000-template.md) | ADR Template | Template | 2026-11-24 |
| [0001](0001-ovca-control-plane-and-live-reviewer-quorum.md) | OVCA Control Plane, 2-Layer Main Protection & Live Separate Reviewer Bot (`Quorum = 1`) | Accepted | 2026-11-24 |
| [0002](0002-lgb154-isolated-backtest-and-daily-beta-factory.md) | Isolated LGB154 1m Backtest Engine, `partial_only` Recovery & Daily 9-Panel Beta Mining Factory | Accepted | 2026-11-23 |
