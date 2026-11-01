# Plan: #705 Confine received ROM writes to configured folders

Issue: #705
Branch: feature/705-confine-rom-writes
PR: none
Status: shipped
Fix attempts: 0

## Goal
Reject incoming ROM transfers whose destination is outside this device's configured ROM folders; document the null-origin CORS limitation.

## Design Alignment
- **Backend Pattern**: helper in cli/transfer.py beside the other transfer helpers; failure path reuses the existing log + `complete_transfer(status="failed")`.
- **Recommendations**: none. No schema, config or IPC change.

## Steps
- [x] 1. Add `_allowed_roots(client, device_id)` and `_destination_allowed(dest, roots, folder_kind)` to cli/transfer.py; call at the top of `_receive_transfer` (inside the try so failure marks the transfer failed and logs a clear reason).
  - Files: src/cli/transfer.py
  - Reuses: client.get_device_consoles, client.list_my_game_devices (rom_folder_path), cfg device id
  - New: path-confinement helper (realpath + commonpath, nothing existing)
- [x] 2. Tests in src/tests/test_receive_confine.py.
- [x] 3. Docs: GOTCHAS.md note (receive confinement, null origin limitation, set a PIN); one CLAUDE.md rule line.

## Testing
Pure path tests plus _receive_transfer rejection with a small stub client that records complete_transfer and asserts no file written.

## Log
