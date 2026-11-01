# Handoff: #700 Fix SSE reconnect dropping device events

## Metadata
- Issue: #700
- Branch: feature/700-sse-reconnect-queue
- PR: none
- Status: implemented
- Created: 2026-11-01
- Fix attempts: 0

## 1. Issue
Reconnecting SSE stream: old generator's finally pops the new stream's queue, so events are dropped.
Affected: src/server/api/transfers.py stream_events_sse.
Acceptance: cleanup removes only its own queue; superseded stream closed; regression test.

## 2. Design
### Scope: backend only, one function
### Plan Target: bplan
### Sub-issues: none
### Difficulty: 2/10
### Backwards Compatibility: none (no API, schema, config or IPC change)
All _device_event_queues readers are async handlers on the event loop; no cross-thread access, no change needed.

## 4. Backend Plan
Identity-guarded pop in the generator's finally; push a None sentinel to the superseded queue so the old generator returns promptly.

## 6. Testing Plan
Test in src/tests/test_integration.py: register two queues for the same device through the real route, finish the old one, assert the new one is still registered and receives events.

## 8. Implementation Steps
See tools/plans/700-sse-reconnect-queue.md

## 12. Log
- 2026-11-01 issue: workflow initialized
- 2026-11-01 design: scope=backend, plan_target=bplan, difficulty=2/10, breaking=no
- 2026-11-01 bplan/tplan: 3 steps written
