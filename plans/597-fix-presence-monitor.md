# Plan: #597 Fix race conditions and potential SQLite contention in presence monitor

Issue: #597
Branch: feature/597-fix-presence-monitor
PR: none
Status: planned
Fix attempts: 0

## Goal
Synchronize the presence monitor thread to prevent race conditions and SQLite contention.

## Steps
- [ ] 1. Wrap the device status check and lock-release logic in `_monitor_presence` within the existing `_presence_lock` to ensure atomicity relative to device presence updates.
  - Files: server/api/_core.py
  - Reuses: server/api/_core.py:`_presence_lock`
  - New: none
- [ ] 2. Verify the fix with an integration test that simulates concurrent presence updates and lock releases.
  - Files: tests/test_integration.py
  - Reuses: tests/test_integration.py
  - New: none
- [ ] 3. Docs: none needed - internal logic change.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
## Log
