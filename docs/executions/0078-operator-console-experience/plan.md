**English** | [中文](plan.zh.md)

# Execution 0078 plan

- Status: In progress
- Date: 2026-09-23

## Delivery sequence

1. Track A first (operator enablement): bilingual `docs/handoff-checklist.md`/`.zh.md` distilled from the 0077 handoff with the troubleshooting table; link from journal navigation.
2. Frontend QR panel: new Svelte component in the accounts area polling `/crawler/api/crawler/qrcode` every 2 seconds while active; state machine waiting → showing (with digest-change detection for silent refresh) → expired/failed with platform guidance; off by default, started by an explicit "显示登录二维码" toggle. Component tests with mocked fetch sequences.
3. Backend log bridge: extend the WebUI manager's `push_log` path to also append each already-redacted line to the existing rolling log-center writer under a dedicated source tag; respect segment/total budgets and the 512-item in-memory bound; unit tests with fixture lines including redaction assertions.
4. Artifact overview card: settings/library page card rendering the three configured roots from `GET /api/v1/settings` (plus the fixed runtime layer paths); UI tests.
5. Documentation debt: refresh `docs/status.md`(+zh) tables to the 0077 boundary; backfill index rows 0059–0068 in `docs/README.md`(+zh) from status narratives; navigation links.
6. Gates: ruff/format/mypy strict/compileall/check_docs; vitest; focused pytest; complete suite on the authoring workstation with fresh honest numbers; bilingual progress/verification records; three-commit start/implementation/closeout series; push and reconcile.

## Risks and rollback

- Frontend-only panels and a read-only log bridge: rollback removes the component, the bridge call and the doc edits; no schema, authority or platform logic is touched. The QR panel must never appear to *guarantee* a login — it is a viewer for an existing relay with honest empty/error states.
