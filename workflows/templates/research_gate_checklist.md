# Conditioner Pre-Intake & Research Gate Checklist

ใช้ก่อนเปิด OVCA workflow (`alpha-ovca init-workflow`) ทุกงานที่มีความซับซ้อนหรืองานวิจัย:

## A. Framing Gate (Define → Decompose)
- [ ] **Inputs / Outputs / Variables**: ระบุชนิด หน่วย Timezone และขอบเขตครบ
- [ ] **Constraints & Assumptions**: แยกข้อจำกัดจริงออกจากสมมติฐาน
- [ ] **Unknowns**: ระบุสิ่งที่ยังไม่รู้ชัด และ **ไม่แอบเติมกฎเอง**
- [ ] **Acceptance Criteria**: มีเกณฑ์ผ่าน/ไม่ผ่านที่วัดผลได้จริง

## B. Research Gate (Hypothesize → Formalize → Falsify)
- [ ] **Economic Rationale**: อธิบายกลไกตลาดเชิงเศรษฐศาสตร์ได้ (ไม่ใช่แค่ curve-fitting)
- [ ] **Falsifiable Hypothesis**: ระบุเงื่อนไขที่ทำให้สมมติฐานถูกปฏิเสธล่วงหน้า
- [ ] **Alternative Explanations**: พิจารณาคำอธิบายคู่แข่ง (เช่น volatility regime, microstructure bounce)
- [ ] **Costs, Leakage & Multiple Testing**: รวมต้นทุนเทรดครบ แยกข้อมูลตามเวลา ไม่ทำ leakage และนับจำนวน trials

## C. Verification & OVCA Gate (Solve → Independently Verify)
- [ ] **Solver ≠ Verifier**: แยก `solver_actor` ออกจาก `verifier_actor`, `reviewer_actor`, และ `auditor_actor`
- [ ] **Budget Formula**: `max_events >= 8 + 6 * max_repair_attempts`
- [ ] **Honest Evidence Status**: รายงานสถานะตามจริง (`Proposed → Exploratory → Reproducible → Robustness Validated → Independently Replicated`) พร้อม Negative Results และ Limitations
