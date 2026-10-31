# Handoff: #640 Fix malformed auto-update feed URL

## Metadata
- Issue: #640
- Branch: feature/640-update-feed-owner
- PR: #641
- Status: shipped
- Created: 2026-10-31
- Fix attempts: 0

## 1. Issue
### Summary
Auto-update check 404s: feed URL is github.com/Emusync/alekoHalkias/Emusync/releases.atom because build.publish has no owner.
### Motivation
Auto-update (#634) is non-functional in v0.7.0.
### Proposed Behavior / Steps to Reproduce
Set publish owner alekoHalkias and repo Emusync in src/gui/package.json; cut v0.7.1.
### Affected Area
src/gui/package.json
### Acceptance Criteria
- [ ] build.publish sets owner and repo separately
- [ ] generated app-update.yml has correct owner/repo
- [ ] v0.7.1 published

## 2. Design
### Scope: CI/build config only
### Backend Changes: None
### UI Changes: None
### Plan Target: bplan
### Sub-issues: None
### Difficulty: 1/10
### Backwards Compatibility: No breaking changes; v0.7.0 installs need one manual upgrade

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: TBD
### Backend Pattern: TBD
### Recommendations: TBD

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: none (verify app-update.yml in unpacked build)
### Test Cases: TBD
### Edge Cases: TBD
### Integration Points: TBD

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/640-update-feed-owner.md (3 steps)
- Step 1: touches package.json; reuses build.publish; no new code.
- Step 2: verification only, no test file.
- Step 3: no docs needed.

## 9. Review
### Findings: 0 (one-line config diff)
### Blocked: no
### Blockers: none

## 10. Ship
### Status: shipped
### PR: #641
### Server Sync: done
### Doc Sync: done (CLAUDE.md)

## 11. Fix Attempts
### Attempt 1: none
### Attempt 2: none
### Attempt 3: none

## 12. Log
- 2026-10-31 issue: workflow initialized
- 2026-10-31 design: scope=build-config, plan_target=bplan, difficulty=1/10, breaking=no
- 2026-10-31 bplan: 3 steps written, backend_pattern=none (build config)
- 2026-10-31 tplan: test_file=none, 1 verification case
- 2026-10-31 implement: steps 1-3 done (publish owner/repo split; unpacked build app-update.yml verified)
- 2026-10-31 review: 0 findings, blocked=no
- 2026-10-31 ship: PR #641, server sync done, doc sync updated CLAUDE.md
