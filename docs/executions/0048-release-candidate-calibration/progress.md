**English** | [中文](progress.zh.md)

# Execution 0048 progress

- Status: Complete for the calibration scope
- Date: 2026-09-03

## Completed

- Phase A: bilingual README status rewrite; `docs/status.md`/`.zh.md` single source of truth; architecture-doc status corrections (REST API, console, Docker, supervisor); 0043 deferred to 0.2; 0044 rescoped; 0047 rewritten as the canary-first acceptance master phase.
- Build reproducibility: `uv==0.12.9` pinned; `BASE_IMAGE` ARG with digest procedure; `docker/mediacrawler-requirements.lock` (78 hashed pins, playwright 1.62.0); `/opt/BUILD-MANIFEST.txt` written at build; Emby bind-mount example in compose.
- 0044-minimal implemented: three endpoints, shared `_execute_asset_download` (CLI body extracted; CLI behavior byte-equivalent — orchestration suite 38 passed), console drawer + re-download, API tests extended (5 passed).
- Environment completion on the workstation: ffmpeg/ffprobe installed (static build) and both `.upstream` checkouts cloned at locked SHAs — `check_upstreams.py` now passes locally and the pinned source-contract suites run.
- **Defect fixed**: JSONL reader tuple-freezing vs the 0039 v2 `isinstance(list)` check quarantined all real multi-live records; fixed to `(list, tuple)`; all 28 live-gallery tests pass. Root cause: those tests were committed collected-but-never-executed (exactly the gap the review flagged).
- Python matrix executed (sync+full suite per version) — see verification for numbers and the honest divergence list.

## Deviations and decisions

- A set of scheduler-handler process-protocol tests (~11) fails identically on a clean checkout of this workstation (verified via stash) — recorded as workstation-suspect, not product regression; the Linux-host rerun in Phase B adjudicates and any real defect enters the 0047 defect loop.
- Docker Hub API unreachable from this network, so the base-image digest could not be resolved here; the ARG + documented `docker buildx imagetools inspect` procedure is the delivered mechanism and the operator pins the digest on the build host.

## Remaining

- Operator Phase B (Linux baseline) → Phase C canaries → … → Phase F RC tag, per the restructured 0047.
