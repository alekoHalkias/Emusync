# Plan: #656 Deduplicate devices by MAC address

Issue: #656
Branch: feature/656-device-mac-dedupe
PR: none
Status: planned
Fix attempts: 0

## Goal
Silently resolve each client's MAC from the server's ARP table and merge devices that share a MAC into the most recent UUID, so the Devices panel shows one entry per physical machine.

## Design Alignment
- **Backend Pattern**: Additive nullable column (schema v32), logic in the existing `DeviceMixin` (`touch_device` is already the throttled per-request write path), `_auth` unchanged except passing nothing new. No client, API-shape, or UI change: MAC is resolved server-side from `/proc/net/arp` (Linux) or `arp -a` (Windows/macOS). ARP only lists on-link neighbors, so a routed client never yields the gateway MAC; loopback and ARP misses return None and keep UUID-only behavior.
- **Recommendations**: Merge direction is old UUID into the UUID making the current request (that is the one in the client's config, so the client keeps working with no config rewrite). MAC is a dedupe hint only; PIN auth is untouched. Known ceiling: DHCP/NAT/Docker-bridge setups where many clients share one source MAC; accepted (ARP resolves the bridge MAC for containers, which would merge containers on one bridge - acceptable, they share the host anyway).

## Steps
- [ ] 1. Schema v32: add `devices.mac TEXT` to `_SCHEMA`, bump `_SCHEMA_VERSION` to 32, add `if from_version < 32` block with `_try(conn, "ALTER TABLE devices ADD COLUMN mac TEXT")`, keep trailing user_version stamp.
  - Files: src/server/store/schema.py
  - Reuses: existing `_try` migration pattern (v31 block)
  - New: none
- [ ] 2. `mac_for_ip(ip) -> str | None`: parse `/proc/net/arp` when present, else run `arp -a` (timeout 2s) and regex the IP's line; lowercase, colon-normalized; reject `00:00:00:00:00:00`/incomplete; return None for loopback/unknown/any error.
  - Files: src/server/arp.py (new)
  - Reuses: stdlib `subprocess`, `re`
  - New: arp.py - nothing in the codebase reads the neighbor table; one small function, kept out of the store so it is stubbable via a real tmp file path argument in tests (`mac_for_ip(ip, arp_text=None)` parses supplied text).
- [ ] 3. `DeviceMixin.merge_devices(old_id, new_id)`: in one transaction (`PRAGMA defer_foreign_keys = ON`), for each (table, column) in a module-level `_DEVICE_REFS` list (consoles.device_id, game_devices.device_id, saves, states, locks, rom_transfers from/to, rom_pull_requests from/to, switch_mods.pushed_by, save_sync_baseline, console_save_history, console_save_sync_baseline, console_saves, save_conflicts and console_save_conflicts winner/loser, events.device_id) run `UPDATE OR IGNORE ... SET col=new WHERE col=old` then `DELETE ... WHERE col=old` for rows that collided (new device's data wins); finally `DELETE FROM devices WHERE id=old`; commit.
  - Files: src/server/store/devices.py
  - Reuses: same transaction and table-list style as `remove_device`
  - New: merge_devices + `_DEVICE_REFS` - remove_device deletes rather than re-keys, so it cannot be reused; the list is the single source for the merge.
- [ ] 4. Wire into `touch_device`: in the branch that actually writes (already throttled to 30s), call `mac_for_ip(ip)`; if a MAC is found, store it (`UPDATE devices SET last_ip, last_seen_at, mac`) and `merge_devices(other, device_id)` for every other device row with the same MAC. This covers brand-new UUIDs (new row has no `last_ip`, so it always takes the write branch), pre-existing duplicates after upgrade, and re-pairing. Row with no MAC found keeps `mac` unchanged.
  - Files: src/server/store/devices.py
  - Reuses: `touch_device` throttle and write path; `_auth` in src/server/api/_core.py already calls ensure_device then touch_device, so no edit there
  - New: none
- [ ] 5. Drop stale presence for merged ids: have `touch_device` return the list of merged old ids (default empty) and in `_auth` discard them from `_online_devices`/`_device_names`; print one activity line "<name> re-paired, merged duplicate" so it is visible but silent to the user flow.
  - Files: src/server/store/devices.py, src/server/api/_core.py
  - Reuses: `_print_activity`, `_presence_lock`, existing sets
  - New: none
- [ ] 6. Tests (real SQLite, no mocks): `mac_for_ip` parsing from sample `/proc/net/arp` text (match, incomplete entry, missing IP); store-level `merge_devices` moves game_devices/saves/consoles/baseline and drops colliding rows; `touch_device` with a monkeypatched `server.arp` path-level input is avoided by passing arp text through a small module-level `_ARP_PATH` read from a tmp file set via monkeypatch of the path constant; case 1 new UUID same MAC merges and keeps game config, case 2 different MAC untouched, case 3 no MAC leaves both devices, case 4 existing same-MAC duplicates collapse on next touch, case 5 FK integrity (`PRAGMA foreign_key_check` empty) after merge.
  - Files: src/tests/test_device_mac.py (new)
  - Reuses: fixtures/pattern from src/tests/test_auth.py and test_events.py
  - New: test file - new behavior area
- [ ] 7. Docs: add a short rule to CLAUDE.md (Config / paths / DB: devices merged by server-resolved ARP MAC, schema v32, #656) and a note in docs/ARCHITECTURE.md device/auth section; GOTCHAS entry for the ARP on-link limitation.
  - Files: CLAUDE.md, src/docs/ARCHITECTURE.md, src/docs/GOTCHAS.md

## Checklist
Schema bump: yes (v32). New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Client-sent MAC header; showing the MAC in DevicesPanel; matching devices across subnets or by hostname; mDNS-based identity.

## Log
