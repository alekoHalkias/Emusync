# Handoff: #656 Deduplicate devices by MAC address

## Metadata
- Issue: #656
- Branch: feature/656-device-mac-dedupe
- PR: none
- Status: shipped
- Created: 2026-10-31
- Fix attempts: 0

## 1. Issue
### Summary
Devices are keyed only by the `device_id` UUID in `emusync.toml`. A regenerated UUID (reinstall, wiped/corrupt config) registers a new device on the same IP, leaving duplicates in the Devices panel. Silently send the machine MAC and use it to map back to the existing device.
### Motivation
Duplicate devices accumulate on one IP; per-device configs, locks, saves and baselines get split across stale and new IDs.
### Proposed Behavior / Steps to Reproduce
- Client sends primary NIC MAC (e.g. `X-Device-MAC`) with `X-Device-ID`; no user action.
- Server stores MAC per device; an unknown UUID with a known MAC resolves to the existing device (or client adopts the canonical UUID) instead of creating a row.
- Existing duplicates with the same MAC are consolidated, preserving referencing rows.
- No MAC available: current UUID-only behaviour. MAC is never the sole trust factor (PIN unchanged).
- Devices panel shows one entry per physical device.
### Affected Area
`src/server/api/_core.py` (`_auth`), `src/server/store/devices.py`, `schema.py` (new `devices.mac`, next free version after 31), `models.py`, `src/server/config.py`, `src/server/sync_client.py`, `DevicesPanel.tsx`, `api.ts`, `src/tests/test_integration.py`.
### Acceptance Criteria
- [ ] Client sends MAC silently
- [ ] Known MAC with new UUID resolves to existing device, no duplicate
- [ ] Existing duplicates consolidated without data loss
- [ ] No MAC: behaviour unchanged
- [ ] Migration adds MAC column with next free schema number
- [ ] Devices panel lists each physical device once
- [ ] Tests: match, no-match, missing MAC, merge duplicates

## 2. Design
### Scope: backend only
### Backend Changes: Resolve client MAC server-side from the OS neighbor table (ARP) for request.client.host in `_auth`/`touch_device`; no client header changes (7 header sites avoided). New `devices.mac` column (schema v32; v30 intentionally empty, 31 taken). `ensure_device`: unknown UUID with MAC matching an existing device re-keys that device's rows to the new UUID instead of inserting a duplicate; one-time consolidation of existing same-MAC duplicates. No MAC (loopback, routed, VM, ARP miss) = UUID-only fallback. MAC is a dedupe hint, never a credential.
### UI Changes: none (DevicesPanel shows list_devices(); dedupe happens server-side)
### Plan Target: bplan
### Sub-issues: none
### Difficulty: 5/10
### Backwards Compatibility: Non-breaking. Additive nullable column + `from_version < 32` migration. Plan must handle PK re-key across all device-referencing tables with conflict handling where the new UUID already has rows.

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: Fits DeviceMixin and the existing throttled touch_device write path; additive schema v32; no API/client/UI change.
### Backend Pattern: Server-side ARP MAC lookup (src/server/arp.py), merge_devices re-keys old UUID rows into the requesting UUID via a single _DEVICE_REFS table list.
### Recommendations: Merge into the requesting UUID so client config needs no rewrite; MAC is a dedupe hint only. Ceiling: shared-MAC bridges/NAT. Backend design guide unchanged (no new reusable pattern).

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: src/tests/test_devices.py (MAC merge), src/tests/test_config_roundtrip.py (device_id backup); both existing, no new file.
### Test Cases: arp parse; touch merges new UUID and moves rows; collision keeps existing row; different MAC untouched; no MAC unchanged; stored same-MAC duplicates collapse; end-to-end via _auth and GET /devices; v31->v32 migration; config restore from backup (missing, corrupt, invalid backup, save writes file).
### Edge Cases: same-id no-op; lock row moves; arp -a fallback not tested (platform-specific, no mocks), noted in PR.
### Integration Points: _auth -> ensure_device -> touch_device -> merge_devices; GET /devices; config.load/save.

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: see tools/plans/656-device-mac-dedupe.md
1. Schema v32 - schema.py; reuses _try migration pattern; no new code.
2. arp.py mac_for_ip - new file; nothing existing reads the neighbor table.
3. merge_devices + _DEVICE_REFS - devices.py; reuses remove_device transaction style; remove_device deletes rather than re-keys.
4. Wire into touch_device - devices.py; reuses throttled write path; _auth unchanged.
5. Presence cleanup - devices.py, _core.py; reuses _print_activity and presence sets.
6. Tests - test_devices.py and test_config_roundtrip.py extended (no new file); reuses client, _device_auth, _ARP_PATH monkeypatch.
7. device_id backup in data dir - config.py; reuses paths.data_dir and save()'s atomic write; new _restore_device_id helper (no second ID source exists).
8. Docs - CLAUDE.md, ARCHITECTURE.md, GOTCHAS.md.

## 9. Review
### Findings: 1 medium (fixed): two live instances sharing a MAC (dev server with isolated config) would be merged back and forth every 30s, churning rows. Fix: only merge devices idle > 5 min (_MERGE_MIN_IDLE_SECONDS), test added. No other findings: schema bump + migration present, config write atomic 0600, tests real SQLite, docs updated.
### Blocked: no
### Blockers: none

## 10. Ship
### Status: pending
### PR: none
### Server Sync: pending
### Doc Sync: pending

## 11. Fix Attempts
### Attempt 1: none
### Attempt 2: none
### Attempt 3: none

## 12. Log
- 2026-10-31 issue: workflow initialized
- 2026-10-31 design: scope=backend, plan_target=bplan, difficulty=5/10, breaking=no
- 2026-10-31 bplan: 7 steps written, backend_pattern=server-side ARP MAC + merge_devices in touch_device
- 2026-10-31 bplan: added step 7 (device_id backup in data dir) at user request
- 2026-10-31 tplan: test_file=src/tests/test_devices.py + test_config_roundtrip.py, 9 test cases defined
- 2026-10-31 implement: step 1 done (schema v32 devices.mac)
- 2026-10-31 implement: step 2 done (server/arp.py mac_for_ip)
- 2026-10-31 implement: step 3 done (merge_devices + _DEVICE_REFS)
- 2026-10-31 implement: step 4 done (touch_device resolves MAC and merges)
- 2026-10-31 implement: step 5 done (_auth presence cleanup)
- 2026-10-31 implement: step 7 done (device_id backup in data dir)
- 2026-10-31 implement: step 6 done (tests in test_devices.py and test_config_roundtrip.py)
- 2026-10-31 implement: step 8 done (docs)
- 2026-10-31 review: 1 findings, blocked=no (fixed: idle threshold before merge)
