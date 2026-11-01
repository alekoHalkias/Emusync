# Handoff: #701 Fix upload and staging file leaks, check game exists on save/state push

## Metadata
- Issue: #701
- Branch: feature/701-upload-leaks
- PR: #710
- Status: shipped
- Created: 2026-11-01
- Fix attempts: 0

## 1. Issue
### Summary
Upload temp files leak on error/no-op paths; save/state push for unknown game is staged then 500s.
### Motivation
Disk leaks under .uploads and rom_staging.
### Proposed Behavior / Steps to Reproduce
See issue #701.
### Affected Area
src/server/api/blobs.py, src/server/store/blobs.py, src/server/api/_core.py, src/server/config.py, tests.
### Acceptance Criteria
- _push deletes tmp on store error
- push_console_save_file unlinks src on hash match
- unknown game save/state push -> 404 before staging
- sweep removes pending transfers older than configurable age (default 7 days)
- regression tests

## 2. Design
### Scope: backend only
### Backend Changes: api/blobs.py (_push cleanup + game check), store/blobs.py (unlink on dedupe), api/_core.py (_sweep_stale_staging age rule), server/config.py (staging_max_age_days)
### UI Changes: none
### Plan Target: bplan
### Sub-issues: none
### Difficulty: 3/10
### Backwards Compatibility: no breaking change; new optional toml key with default

## 8. Implementation Steps
### Steps: TBD (written by /plan skills)

## 10. Ship
### Status: pending
### PR: #710
### Server Sync: done
### Doc Sync: done (none needed)

## 12. Log
- 2026-11-01 issue: workflow initialized
- 2026-11-01 design: scope=backend, plan_target=bplan, difficulty=3/10, breaking=no
- 2026-11-01 implement: steps 1-5 done in one commit (full suite 630 passed)
- 2026-11-01 ship: PR #710, server sync done, no doc changes needed
