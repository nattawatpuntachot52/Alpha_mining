# AGENT_ACK Template (Runtime, Environment & Handover Disclosure)

ใช้บล็อกนี้ในทุก formal handover, PR body, PR audit comment, และ workflow ledger เพื่อป้องกันความสับสนเรื่องโมเดล/เครื่อง/สิทธิการแก้ไข และแยก `Fact` ออกจาก `UNKNOWN` อย่างตรงไปตรงมา

> **กฎความซื่อสัตย์ (Anti-Guess Policy)**:
> - หาก runtime ไม่เปิดเผย exact model build ID ให้ระบุว่า `UNKNOWN (not exposed by runtime)` ห้ามเดา
> - หาก host หรือ node ใดไม่ได้เชื่อมต่อใน session ปัจจุบัน ให้ระบุ `UNKNOWN / NOT_CONNECTED`
> - ห้ามใช้คำว่า `passed` / `verified` หากยังไม่ได้รันคำสั่งตรวจในรอบปัจจุบัน (`verification not run` / `verification failed`)

```text
AGENT_ACK
mission_id: <mission_or_epic_id>
task_id: <task_or_issue_id>
assignment_id: <assignment_or_branch_id>
phase_id: <phase_or_step_id>
agent_id: <agent_name_e.g._katherine_or_elena>
ovca_role: <front_door_conditioner | coordinator | engineer | verifier | reviewer | auditor>
actual_provider_runtime: <exact_runtime_name_and_os>
actual_model_id_version: <exact_model_id_or_UNKNOWN (not exposed by runtime)>
tools_environment:
  host: <hostname_or_remote_vm_id>
  secondary_nodes: <UNKNOWN / NOT_CONNECTED_or_verified_node>
  python: <verified_python_version>
  rust: <verified_rustc_cargo_version>
  git: <verified_git_version>
  gh: <verified_gh_version_and_authenticated_account>
mutation_boundary: <READ_ONLY | exact_writable_scope_and_branch>
verification_summary: <exact_commands_run_and_real_outcomes>
```
