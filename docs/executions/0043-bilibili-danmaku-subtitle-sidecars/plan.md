**English** | [中文](plan.zh.md)

# Execution 0043 plan

- Status: Planned
- Date: 2026-09-03

## Delivery sequence (when implemented)

1. Extend the strict Bilibili detail protocol (v7+) with a closed danmaku/subtitle descriptor read from the already-fetched play payload; runtime-only signed URLs, recursive strip before persistence.
2. Implement a pure offline XML→ASS converter with a frozen rule set and bounded output; unit-test it against generated fixtures.
3. Derive sidecars in the export layout as same-stem files; extend zero-work replay/recovery and retained-tree scans to cover them.
4. Add contract + integration compositions (download → archive → Emby with sidecars) and run the full quality-gate family on the Linux deployment host; record exact numbers here before closeout.

## Risks and rollback

- Sidecars are derived artifacts: rollback removes the converter, descriptor and layout emission without touching media identity or schema.
