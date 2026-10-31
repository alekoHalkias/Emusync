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
- [ ] 2. `mac_for_ip(ip) -> str | None`: parse `/proc/net/arp` when present, else run `arp -a` (timeout 2s) and regex the IP's line; lowercase, colon-normalized; reject `00:00:00:00:00:00`/incomplete; return None for unknown IP/any error. Module constant `_ARP_PATH = Path("/proc/net/arp")` is read first (tests point it at a tmp file); `arp -a` only when it does not exist.
  - Files: src/server/arp.py (new)
  - Reuses: stdlib `subprocess`, `re`
  - New: arp.py - nothing in the codebase reads the neighbor table; one small function, kept out of the store; the `_ARP_PATH` constant is the test seam.
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
- [ ] 6. Tests for MAC merge: extend src/tests/test_devices.py (cases under Testing). `server.arp` exposes `_ARP_PATH`; tests monkeypatch it to a tmp file of sample `/proc/net/arp` text, so real parsing and real SQLite run, no mocks.
  - Files: src/tests/test_devices.py
  - Reuses: `client`, `_device_auth`, `Store`, the existing `test_touch_device_updates_last_seen` and `test_clear_devices_removes_all` setup style
  - New: none - same area as existing device tests (testing guide: extend, do not add files)
- [ ] 7. Backup the device ID outside the config file: `save()` also writes `device_id` to `paths.data_dir()/device_id` (atomic, 0600, only when changed); `load()` uses that value instead of a fresh uuid4 when `emusync.toml` is missing, corrupt, or lacks `device_id` (validated with `uuid.UUID`, ignored if invalid). Covers lost/corrupt config where the data dir survives; a full wipe still relies on the MAC merge. On Windows config and data share one dir, so this only covers toml loss there.
  - Files: src/server/config.py, src/tests/test_config_roundtrip.py (cases under Testing)
  - Reuses: `paths.data_dir()`, existing atomic 0600 write helper used by `save()` (#535), `Config.device_id` default factory
  - New: small `_restore_device_id()` helper - no existing code reads a second ID source.
- [ ] 8. Docs: add a short rule to CLAUDE.md (Config / paths / DB: devices merged by server-resolved ARP MAC, schema v32, #656) and a note in docs/ARCHITECTURE.md device/auth section; GOTCHAS entry for the ARP on-link limitation and the device_id backup file.
  - Files: CLAUDE.md, src/docs/ARCHITECTURE.md, src/docs/GOTCHAS.md

## Testing
- **Test File**: src/tests/test_devices.py (MAC merge), src/tests/test_config_roundtrip.py (device_id backup). Both existing files, using the `_ARP_PATH` monkeypatch and `monkeypatch.setenv("EMUSYNC_CONFIG_DIR"/"EMUSYNC_DATA_DIR")` + `importlib.reload`/`CONFIG_PATH` pattern already used in test_config_roundtrip.
- **Test Cases**:
  - arp parse: sample table returns lowercase MAC for a listed IP; incomplete entry (`0x0` flags / `00:00:00:00:00:00`) and unlisted IP return None.
  - touch merges new UUID: seed device A (game_devices row, save, console, baseline) with mac M via touch; touch new device B from same IP/MAC; A gone, its rows now belong to B, `PRAGMA foreign_key_check` empty, device list has one entry.
  - collision: B already has a game_devices row for the same game; merge keeps B's row, drops A's, no error.
  - different MAC: A and B both remain.
  - no MAC (IP not in ARP file): A and B both remain, behaviour unchanged.
  - existing duplicates (same mac stored on two rows, seeded directly): next touch of one collapses them.
  - end to end: request through `client` with ARP file listing 127.0.0.1 and a second `_device_auth` identity merges via `_auth`; `GET /devices` returns one device.
  - schema: v31 -> v32 migration adds `devices.mac` (same style as `test_v9_to_v10_migration`).
  - config: missing toml with backup file present restores device_id; corrupt toml restores device_id; invalid backup content ignored (fresh uuid); `save()` writes `device_id` file and leaves no tmp.
- **Edge Cases**:
  - Merge when old and new are the same id (no-op).
  - `locks` row held by the old device moves to the new device.
  - `arp -a` fallback not exercised (no mocks, platform-specific); manual note in PR.
- **Integration Points**:
  - `_auth` -> `ensure_device` -> `touch_device` -> `merge_devices`; `GET /devices` reflects the merge.
  - `config.load()`/`save()` used by CLI and server startup.

## Checklist
Schema bump: yes (v32). New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: yes (new `device_id` backup file in the data dir).

## Not in this plan
Client-sent MAC header; showing the MAC in DevicesPanel; matching devices across subnets or by hostname; mDNS-based identity.

## Log
