# Handoff: #739 Evaluate a manifest save format and merged save tables

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
- [ ] Decision recorded: proceed (split into implementation issues) or close

## 2. Design
### Scope: evaluation only, no code
### Backend Changes: none
### UI Changes: none
### Plan Target: none (awaiting user decision; recommendation is close)
### Sub-issues: none; if proceeding: (1) manifest format + one-time blob conversion, (2) owner-keyed table merge
### Difficulty: 1/10 (evaluation); D 9/10, E 6/10 if implemented
### Backwards Compatibility: D breaking (server-first, every client must update); E server-internal, irreversible

## 12. Log
- 2026-11-20 issue: workflow initialized (resume from #739)
- 2026-11-20 design: scope=none (evaluation), plan_target=none, difficulty=1/10, breaking=no; evaluation posted, recommendation close
