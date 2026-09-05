**English** | [中文](progress.zh.md)

# Progress

Fresh baseline verified. Independent read-only audits found the unbounded fixed30 upload loop, incorrect default Enum order serialization, swallowed detail errors, the absent cursor/coverage handoff, and the watermark loss hazard. Existing cursor must retain {value:string}; receipt success alone proves no creator coverage. Current Bili creator mode captures uploads only, not dynamic attachments. The frozen plan precedes implementation; no production work occurred.

## Implementation and review

Frozen plan commit: `c24e400`. Separate owners implement the replayable scan/shim, atomic ingestion and safe API/Web projections; the main owner wires the bridge, actual scheduler, normalization and CLI. The manifest adds only the optional `bili_scan` v1 object, containing the true stored input cursor and a bound state; old manifests retain their serialization and acknowledgement gate. New scheduled Bili forward requests and dry-run use the bounded contract. Legacy cursors initialize a fresh scan with no inherited timestamp authority; malformed versioned scan cursors fail closed.

Exactly one `_media_sync_bili_coverage.jsonl` is sealed by the existing receipt. Normalization replays its pure transition and compares its consumed identities with a reserved private identity field and normalized aid/time/content type. The sidecar is not counted as content. The bounded DB entry point atomically publishes at most30 records, refresh provenance, continuation and succeeded Run, retaining the old watermark unchanged. The public UI describes one completed unit, not completed author history, and hides raw cursors/queued identities.

Independent review found and requested fixes for prematurely moving to the next page after using both list requests (losing the previous witness), and promoting a head boundary from an old queued page without revalidation. Regression tests must cover both before release. Continuous remote insert/delete can force conservative restarts; lane fairness is scheduling fairness, not a claim that an ever-changing remote page API provides a stable snapshot. WBI signing may separately read navigation/key metadata; the author-list cap is not a total-request claim.

Production login, subscription state, retry, pipeline downloads/exports, deployment and supervisor remain untouched. The historical canary cause is not established by these offline corrections.

The independent wiring review subsequently found that normalized creator identity came from trusted context, so that comparison alone was not independent evidence of the sealed source author. The owned identity field now includes a SHA256 derived from the validated View.owner.mid, held across the actual store call and checked by the parent against manifest scope; no raw mid is added to upstream output. Missing/wrong fingerprints reject before ingestion. The review also identified overly strict post-commit subscription revision equality. Bounded handler truth now checks the exact Run input/output/revision and accepts a newer subscription cursor without overwriting it. Legacy interpretation stays unchanged. Real sealed recovery, both newer-checkpoint return/ack-loss cases and exact once-per-Run pipeline publication are tested.

Bounded CLI ingestion now also reads durable Run truth even if the service returns a plausible result or loses its commit acknowledgement. No commit cannot report success. A separate duplicate CLI import still creates an attempt and safely rejects the already-consumed artifact; it is not presented as a successful replay API. Complete goal and remaining platform/archive/live work are unchanged.
