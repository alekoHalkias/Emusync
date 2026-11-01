# Handoff: #704 Harden server blob store, presence monitor and upload limits

## Metadata
- Issue: #704
- Branch: feature/704-server-robustness
- PR: none
- Status: shipped
- Created: 2026-11-01
- Fix attempts: 0

## 1. Issue
Five server robustness defects (see issue #704): dangling row on failed blob move, presence monitor aborted by one bad row, no save/state/memcard upload cap, unvalidated pull-request body, in-memory memcard tar.

## 2. Design
### Scope: backend only
### Plan Target: bplan
### Sub-issues: none
### Difficulty: low
### Backwards Compatibility: no schema/config/IPC change; new module constant for the cap.

## 4. Backend Plan
See tools/plans/704-server-robustness.md

## 6. Testing Plan
tests/test_hardening_704.py: one regression test per item, real SQLite, existing fixtures.

## 9. Review
### Findings: TBD

## 10. Ship
### Status: pending
### PR: none
### Server Sync: pending
### Doc Sync: not needed (no documented module/IPC/config change)

## 12. Log
- 2026-11-01 issue: workflow initialized
- 2026-11-01 design/bplan/tplan: plan written, Status implementing
