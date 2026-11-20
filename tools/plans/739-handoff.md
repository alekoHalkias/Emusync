# Handoff: #739 Replace save blob formats with a manifest payload

## Metadata
- Issue: #739
- Branch: feature/739-evaluate-manifest-format
- PR: none
- Status: designed
- Created: 2026-11-20
- Fix attempts: 0

## 1. Issue
### Summary
Evaluate replacing raw/tar/tar.gz enveloped blobs with a manifest payload (Phase D) and merging game/console history, baseline and conflict tables into owner-keyed tables (Phase E). Split from #737.
### Motivation
Remaining after #737/#749: CardFormatMismatch (#718), envelope-skipping hashes, no per-file info, two table families.
### Proposed Behavior / Steps to Reproduce
Evaluation only; deliverable is a written evaluation and a proceed/close decision.
### Affected Area
src/server/sync_client.py, src/server/store/{blobs,conflicts,schema,devices}.py, src/server/api/{blobs,conflicts}.py, src/cli/run_reconcile.py
### Acceptance Criteria
- [x] Written evaluation posted on the issue (issuecomment-7047489929)
- [x] Decision recorded: proceed with Phase D only, Phase E dropped
- [ ] Saves, states and memory cards push/pull/restore through one manifest format
- [ ] CardFormatMismatch and envelope header-skipping hash helpers removed
- [ ] One-time server conversion with backup (DB snapshot, originals kept until verified)
- [ ] Docs updated

## 2. Design
### Scope: backend only (Phase D). Phase E dropped by user decision 2026-11-20.
### Backend Changes: new manifest envelope format in sync_client.py; one manifest-driven extract/merge/restore replacing raw/tar/tar.gz paths; manifest-derived content hash (replaces _payload_sha256/_memcard_payload_bytes header skipping); remove CardFormatMismatch and its run_reconcile handling; schema migration converting all stored blobs with DB snapshot + originals kept until verified; old-client upload wrapping in api/blobs.py.
### UI Changes: none (GUI push/pull shell out to CLI, #479)
### Plan Target: bplan
### Sub-issues: none
### Difficulty: 9/10 (includes +2 breaking)
### Backwards Compatibility: breaking. Server updates first; clients require the manifest format. Accepted: one user, three self-managed devices.

## 12. Log
- 2026-11-20 issue: workflow initialized (resume from #739)
- 2026-11-20 design: scope=none (evaluation), plan_target=none, difficulty=1/10, breaking=no; evaluation posted, recommendation close
- 2026-11-20 design: user decision proceed with D only; scope=backend, plan_target=bplan, difficulty=9/10, breaking=yes
