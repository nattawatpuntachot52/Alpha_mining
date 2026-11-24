# Separate Bot / GitHub App Account Setup (`Review Quorum >= 1`) — `Alpha_mining`

## สถานะปัจจุบัน (`Independently Verified Result` ล่าสุด `2026-11-24`)

- **ปลดล็อกและใช้งานจริงแล้วบน `nattawatpuntachot52/Alpha_mining`:**
  - GitHub App: **`alpha-mining-ovca-reviewer`** (`OVCA_REVIEWER_APP_ID = 5800517` + Repository Secret `OVCA_REVIEWER_APP_PRIVATE_KEY` ตั้งค่าตั้งแต่ `2026-11-17`)
  - Live Rulesets บน `main` (ตรวจผ่าน `python3 scripts/github_ruleset.py verify`):
    1. [standard-main-protection.json](../config/github/rulesets/standard-main-protection.json) (Live Ruleset ID `27447738`): **`required_approving_review_count: 1`**, `dismiss_stale_reviews_on_push: true`, `required_review_thread_resolution: true`
    2. [details-main-protection.json](../config/github/rulesets/details-main-protection.json) (Live Ruleset ID `27447741`): `strict_required_status_checks_policy: true`, บังคับ check `rust` และ `python`
  - **หลักฐานการใช้งานจริง:** `alpha-mining-ovca-reviewer` อนุมัติ PR #15 (`619285d`), PR #18 (`5c3a863`, run `45318298071`), และตรวจจับ-ส่งกลับ-อนุมัติจริงในวงจร `CHANGES_REQUESTED -> fix -> APPROVED` บน PR #19 (`5a30101` → `fe65cac` → `1ddd667`)
- **การนำไปใช้ซ้ำบน `Katherine-HQ`:** ไม่ต้องสร้าง GitHub App ใหม่ ให้เพิ่ม `nattawatpuntachot52/Katherine-HQ` เข้า Installation ของ App `5800517` แล้วตั้ง Secret `OVCA_REVIEWER_APP_PRIVATE_KEY` ก่อนตั้ง Variable `OVCA_REVIEWER_APP_ID = 5800517` (ดูคู่มือใน `Katherine-HQ/docs/bot-account-setup.md`)

---

## เหตุผลเชิงสถาปัตยกรรมที่เริ่มด้วย `required_approving_review_count = 0` ก่อนสลับเป็น `1`

GitHub ไม่อนุญาตให้ **ผู้เปิด Pull Request (PR Author)** กด approve PR ของตัวเองได้

ในระยะแรกที่ repository `nattawatpuntachot52/Alpha_mining` มี collaborator เพียง 1 บัญชีคือ `nattawatpuntachot52` การตั้ง `required_approving_review_count >= 1` ทันทีจะทำให้เกิด **Self-Approval Deadlock** (merge ไม่ได้) ระบบจึงวาง Ruleset 2 ชั้นและสลับเป็น `1` หลังติดตั้ง Separate GitHub App สำเร็จแล้ว คู่มือด้านล่างเก็บไว้สำหรับการหมุนเวียนกุญแจ (key rotation) หรือตั้งค่าซ้ำใน repository อื่นค่ะ

---

## ขั้นตอนสร้าง Separate Bot (แนะนำ: GitHub App)

GitHub App ปลอดภัยกว่า Machine User PAT เพราะได้ short-lived token ต่อ job และจำกัดสิทธิ์เฉพาะ repo ได้:

1. เปิด **GitHub Settings → Developer settings → GitHub Apps → New GitHub App**:
   - **GitHub App name**: เช่น `alpha-mining-ovca-reviewer`
   - **Homepage URL**: `https://github.com/nattawatpuntachot52/Alpha_mining`
   - **Webhook**: ปิด **Active** (ไม่จำเป็นต้องเปิด webhook server)
   - **Repository permissions**:
     - `Pull requests`: **Read and write** (เพื่อให้ `ovca-reviewer[bot]` โพสต์ผล `pr_audit.py` และ submit review ได้)
     - `Checks` / `Statuses`: **Read-only**
     - `Metadata`: **Read-only** (ค่า default)
   - กดสร้าง App → จด **App ID** → กด **Generate a private key** (จะได้ไฟล์ `.pem`)
2. กด **Install App** ลงเฉพาะ repository `nattawatpuntachot52/Alpha_mining`
3. ใส่ค่าใน GitHub Repository Settings (**Settings → Secrets and variables → Actions**):
   - **Variables**: `OVCA_REVIEWER_APP_ID` = `<App ID>`
   - **Secrets**: `OVCA_REVIEWER_APP_PRIVATE_KEY` = เนื้อหาไฟล์ `.pem` ทั้งหมด

> Workflow [ovca-reviewer-bot.yml](../.github/workflows/ovca-reviewer-bot.yml) ถูกวางแบบปลอดภัยไว้แล้ว (checkout เฉพาะ `main`, รัน [pr_audit.py](../scripts/pr_audit.py), โพสต์รายงาน และอนุมัติเฉพาะ PR ภายใน repo ที่ `CI` ผ่าน + ไม่ใช่ Draft + `verdict` เป็น `READY_TO_MERGE` เท่านั้น)

---

## การสลับ Quorum เป็น `>= 1` เมื่อพร้อม

หลังติดตั้ง App และทดสอบว่า workflow `OVCA Reviewer Bot` รัน comment/approve บน PR ทดลองได้จริง ให้รัน:

```bash
# Dry-run ตรวจสอบ payload ก่อน
python3 scripts/github_ruleset.py set-review-quorum --count 1 --confirm-bot-ready --dry-run

# อัปเดต config ใน repo และยิง PUT อัปเดต Live Ruleset บน GitHub (ควรส่ง config ผ่าน PR ก่อนหรืออัปเดตพร้อมกัน)
python3 scripts/github_ruleset.py set-review-quorum --count 1 --confirm-bot-ready
python3 scripts/github_ruleset.py verify
```

> หมายเหตุ: หากใช้เป็น **Machine User Account** แทน GitHub App ให้เชิญบัญชีนั้นเป็น Collaborator (`Write` role) ก่อนแล้วรัน `set-review-quorum --count 1` (ตัว script จะตรวจ `/collaborators >= 2` ให้อัตโนมัติ)
