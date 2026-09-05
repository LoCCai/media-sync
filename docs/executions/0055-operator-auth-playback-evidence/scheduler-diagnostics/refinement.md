**English** | [中文](refinement.zh.md)

# Pre-implementation safety refinement

This addendum preserves the original plan and is committed before implementation. Review found two existing control/display gaps at the exact new diagnostic boundaries.

- The cancellation join helper currently swallows SchedulerLeaseLostError, including a handler cleanup fence, when heartbeat fails at the same time. Propagate this specific fence before generic Exception handling so no diagnostic finalization gains authority after lease/cleanup loss. Test the simultaneous failure and completed-handler paths; preserve ordinary exception/cancellation cleanup semantics. No retry or Run rewrite.
- Job detail currently renders arbitrary Object.entries and accepts unscoped late fetches. Replace it with the existing Job-field allowlist and the explicitly sanitized new error field; reject a mismatched Job identity, use the current detail request generation, and never reflect unknown fields/errors. This is needed to bind diagnostics to the requested Job, not an expansion to other explorers.

The API diagnostic field remains optional/additive; Operation summaries and production data stay unchanged. Root owns shared API/CLI projection tests, worker agent owns service/policy/control regressions, independent database agent owns real-contention tests, Web agent owns Job display and exact-request tests.
