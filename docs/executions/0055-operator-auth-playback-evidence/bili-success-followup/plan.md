**English** | [中文](plan.zh.md)

# Frozen implementation plan

1. Commit these bilingual records before editing code; leave locked upstreams and operator data unchanged.
2. Console: exact-account authenticated status gets a neutral “login preflight not needed” view, local-state refresh and subscription navigation, explicitly not a live platform probe. Skip auto/manual start-preflight, hide/clear stale failures and fence late responses. Keep genuine unsupported, failed, expired and busy behavior. Tighten QR start gating to closed backend eligibility; do not change backend auth transitions.
3. BILI-only runner: after original update_cookies finishes, call the captured original pong once. Only `is True` authenticates; False terminates with existing fixed failed disposition, nonboolean is configuration_invalid, ordinary exceptions remain failed. Never return to crawling, retry, or invoke QR fallback. Keep other six platform semantics and initial saved-session pong unchanged. Reuse current parent deadline/cancel/process-tree controls. This is the existing upstream pong trust level, not the future strict pasted-Cookie validator.
4. Regression: authenticated/no-status/wrong-identity/expired/stale-preflight UI cases; Bili initial false + update + second false/true/malformed/exception/cancellation; other-platform compatibility and timeout/cleanup/API mapping. No secrets in fixtures, logs or records.
5. Inspect the existing production console read-only. User-selected canary author UID 252671524 may be used only after the concrete full-history and scheduling boundary is confirmed. Author preview is local syntax/policy validation, not remote proof. Do not collect unbounded history under a “one item” promise, accept licenses, or create unintended recurring work.
6. Run measured Python/Web/docs/upstream gates, review, record implemented/pending and bilingual commits, push verified commits. Production deployment remains operator-controlled; live reuse/capture/playback stay NOT_RUN unless actually observed.

