# Daily Brain Memory Ledger (`workflows/memory/`)

Structured daily experience logs (`YYYY-MM-DD.jsonl`) separating:
1. **Translation (`llm_translation`)**: NL ↔ JSON translation metadata only (`translator_role: "nl_to_json_only"`). LLMs never decide actions or place orders.
2. **Decision Snapshot (`decision_context`)**: Immutable point-in-time observation (`observed_at_utc`, features visible at decision time, available actions, chosen action, engine, `risk_gate_passed`).
3. **Realized Outcome (`outcome`)**: `pending | resolved | void` with strict anti-lookahead check (`outcome_at_utc >= observed_at_utc`) and lesson tags.

## Rules & Hygiene
- **Zero Secrets**: Never store tokens, private keys, or API secrets inside JSONL logs (`brain_memory.py` enforces automated redaction/rejection).
- **Zero Retrospective Tampering**: `resolve` can only transition `pending -> resolved | void` and preserves `decision_context`, `features_at_decision`, and `llm_translation` byte-identical.
- **Daily Drive Snapshot**: Pack validated daily logs + deterministic summaries via:
  ```bash
  python3 scripts/brain_memory.py validate
  python3 scripts/brain_memory.py plan-sync --manifest-dir workflows/vault_manifests
  python3 scripts/brain_memory.py pack-snapshot --session-date YYYY-MM-DD
  python3 scripts/brain_memory.py push-snapshot --manifest workflows/vault_manifests/brain-daily-YYYY-MM-DD.manifest.json
  ```
  Archives (`*.tar.zst`) stay out of Git under `.vault_cache/` and sync to Google Drive `Alpha_mining_Vault/state_snapshots/` (`11LgT2EI6OrjeBoF8y91Smz2wEfRwfxbt`), with manifest sidecars under `state_snapshots/manifests/`.
- **Automated Daily Cron**: [.github/workflows/brain-memory-cron.yml](../../.github/workflows/brain-memory-cron.yml) runs daily at `18:00 UTC` (`01:00 Asia/Bangkok`) and on manual `workflow_dispatch` (`validate` → `plan-sync` → `pack-snapshot` → `push-snapshot` when `RCLONE_CONFIG_GDRIVE` is configured, storing manifests in Actions Cache + Drive sidecar + 90-day workflow artifacts cleanly under PR-only `main` Rulesets).
