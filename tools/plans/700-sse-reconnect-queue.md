# Plan: #700 Fix SSE reconnect dropping device events

Issue: #700
Branch: feature/700-sse-reconnect-queue
PR: none
Status: planned
Fix attempts: 0

## Goal
A superseded SSE stream must not unregister its replacement's queue.

## Design Alignment
- **Backend Pattern**: module-level per-device queue registry in _core.py, mutated only from async handlers on the event loop.
- **Recommendations**: none

## Steps
- [ ] 1. In stream_events_sse, when registering, put a None sentinel on any previous queue; the generator returns on None; finally pops only if the registered queue is its own.
  - Files: src/server/api/transfers.py
  - Reuses: _device_event_queues
  - New: none
- [ ] 2. Tests: src/tests/test_integration.py, open two streams for one device, close the first, assert a posted event still reaches the second. Real SQLite.
- [ ] 3. Docs: none needed - internal fix, no rule or interface change.

## Checklist
Schema bump: no. New IPC channel: no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Threading changes (none needed; all access is on the event loop).

## Log
