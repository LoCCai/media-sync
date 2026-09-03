**English** | [中文](plan.zh.md)

# Execution 0048 plan

- Status: Executed
- Date: 2026-09-03

## Delivery sequence

1. Phase A calibration: rewrite READMEs as status pages, create `docs/status.md`, correct architecture claims, defer 0043, rescope 0044, restructure 0047.
2. Build reproducibility: pin uv, BASE_IMAGE ARG, hashed upstream lock, BUILD-MANIFEST, Emby mount example.
3. Implement 0044-minimal (endpoints + shared CLI helper + console + tests).
4. Run the 3.11/3.12/3.13 matrix and the complete suite with ffmpeg/ffprobe and `.upstream` present; fix what the fresh numbers expose; record honest numbers and the workstation-suspect list.
5. Secret scan and dependency audit spot-runs; gates; bilingual records; commits.

## Risks and rollback

- Documentation and additive endpoints only (plus the tuple-acceptance fix and the CLI extraction which is covered by the orchestration/API suites); rollback reverts the corresponding commits.
