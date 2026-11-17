# Separate Bot / GitHub App Account Setup (`Review Quorum >= 1`)

## เหตุผลที่ต้องตั้งค่า `required_approving_review_count = 0` ชั่วคราว

GitHub ไม่อนุญาตให้ **ผู้เปิด Pull Request (PR Author)** กด approve PR ของตัวเองได้  
ปัจจุบัน repository `nattawatpuntachot52/Alpha_mining` มี collaborator เพียง 1 บัญชีคือ `nattawatpuntachot52` หากตั้ง `required_approving_review_count >= 1` ทันที ทุก PR ที่เปิดโดยบัญชีหลักจะเกิด **Self-Approval Deadlock** (merge ไม่ได้)

ระบบจึงแบ่ง Ruleset เป็น 2 ชั้นไว้ล่วงหน้า:
1. [standard-main-protection.json](../config/github/rulesets/standard-main-protection.json) (`required_approving_review_count: 0` ชั่วคราว + `dismiss_stale_reviews_on_push: true` + `required_review_thread_resolution: true`)
2. [details-main-protection.json](../config/github/rulesets/details-main-protection.json) (`strict_required_status_checks_policy: true`, บังคับ check `rust` และ `python`)

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
