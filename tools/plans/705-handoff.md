# Handoff: #705 Confine received ROM writes to configured folders and document null-origin CORS

## Metadata
- Issue: #705
- Branch: feature/705-confine-rom-writes
- PR: none
- Status: implementing
- Created: 2026-11-01
- Fix attempts: 0

## 1. Issue
### Summary
Receiving device writes incoming ROM to sender-supplied destination_path; CORS accepts Origin null.
### Acceptance Criteria
- [ ] Destination outside configured ROM folders rejected, nothing written, transfer marked failed.
- [ ] Traversal and root-equal rom-folder rejected; in-folder still works.
- [ ] null-origin limitation documented.
- [ ] Tests for accept and reject.

## 2. Design
### Scope: backend only (bplan)
### Backend Changes: `_destination_allowed` in cli/transfer.py called at top of `_receive_transfer`.
### UI Changes: none
### Plan Target: bplan
### Sub-issues: none
### Difficulty: low
### Backwards Compatibility: transfers to a console not yet set up on the receiver now fail with a clear message; the sender's interactive prompt remains. Part (b): custom protocol rejected because gui/electron/art.ts relies on file:// artwork URLs and the GUI cannot be verified here; documented instead.

## 3. Frontend Plan
none

## 4. Backend Plan
See tools/plans/705-confine-rom-writes.md

## 5. Merged Plan
none (single plan)

## 6. Testing Plan
### Test File: src/tests/test_receive_confine.py
### Test Cases: in-root accepted; outside rejected; .. traversal rejected; rom-folder root rejected; extra/network/local folders accepted
### Summary: pure-function tests plus one _receive_transfer rejection against a stub client (no mocks of the store; helper is path logic only)

## 7. Test Design
See section 6.

## 8. Implementation Steps
See plan file.

## 9. Review
### Findings: TBD

## 10. Ship
### Status: pending
### PR: none
### Server Sync: pending
### Doc Sync: pending

## 12. Log
- 2026-11-01 issue: workflow initialized
- 2026-11-01 design/plan/tplan: bplan only, plan approved by fork (autopilot)
