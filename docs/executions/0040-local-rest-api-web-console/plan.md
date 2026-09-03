**English** | [中文](plan.zh.md)

# Execution 0040 plan

- Status: Executed (implementation); full gates deferred to Linux
- Date: 2026-09-03

## Delivery sequence

1. Mirror the CLI surface in a FastAPI application factory reusing the CLI's payload builders and worker composition helpers so API and CLI stay byte-consistent.
2. Add an in-process operation registry with exclusive keys for login/export so double-starts return 409 and the console can poll outcomes.
3. Extend the login child's QR hook with an opt-in-by-deployment file relay and per-attempt cleanup; keep the no-op browser-only default behavior.
4. Serve a dependency-free Chinese single-page console and add `media-sync serve`.
5. Add offline API contract tests; run static gates locally; leave the complete suite to the Linux host.

## Risks and rollback

- The API adds authority only where the CLI already had it, bound to loopback by default; rollback is deleting `api.py`, `console.html`, the `serve` command and the QR relay block.
