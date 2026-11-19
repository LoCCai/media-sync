**English** | [中文](goal.zh.md)

# Goal: independent six-discipline code review

## Why this execution exists

Executions 0084–0087 were each verified by their own author against their own
tests. That is a weak form of verification: a test written from the same
misunderstanding as the code passes. In particular, 0085 and 0086 were declared
"complete locally" on the strength of tests that drove the new repositories
directly — bypassing exactly the production paths where the wiring could be
missing.

This execution therefore asks six reviewers with disjoint scopes to attack the
tree at `830b4d0` **without trusting the previous closeouts**, and to prove
findings by reading production code and running targeted probes.

## Review scopes

| Reviewer | Scope |
| --- | --- |
| Creator chain | Weibo/Tieba/Zhihu state machines and capture shims, against the four older references |
| Migrations | 0018/0019/0020 DDL versus the ORM models, the ingestion transaction boundary |
| Media | request profiles, URL validation, stream ranking, download resume, probe/mux |
| API/CLI | subscription payloads, `ingest_*_bounded` dispatch, policy wiring, manifest round-trip |
| Frontend | Svelte state/async/error handling and payload/type agreement with the API |
| Security | `secure_delete` coverage, secret reach, path safety, auth/CSRF, subprocess env |

## Rules the reviewers were given

- Verify by reading production code; a passing test is not evidence on its own.
- Report only confirmed findings, each with severity, file:line, a concrete
  failing scenario and a fix; separate "verified" from "could not confirm".
- Do not report style opinions or propose refactors.
- Do not edit, commit, or run the full suite.

## Deliverable

A single record that:

1. lists every fixed defect with the concrete failure it prevented;
2. lists the claims that were **rejected** after re-verification, so the record
   does not overstate the findings;
3. lists defects that are real but deliberately **not** fixed here, with the
   reason, so they become the next execution's scope rather than being silently
   dropped;
4. carries the full gate results for the tree after the fixes.

## Out of scope

- Any behaviour change to 0076/0081/0083 (XHS/Weibo URL validation, Kuaishou host
  allowlist, Douyin stream cap): each needs its own execution that re-derives the
  pinned upstream facts.
- Deployment, real login, or any platform request. Every live row stays
  `NOT_RUN` per [0087](../0087-operator-canary/qualification.md).
