# Plan for #642: Library Import Redesign & Network Drive Validation

## Metadata
- **Issue**: #642
- Status: implementing
- **Branch**: feature/642-library-import-redesign

## Context
The current `LibraryImport` wizard is bulky and handles network drives by simply setting a `source` flag in the device's local `emusync.toml`. This makes it impossible to ensure that different devices using "network" for the same console are actually pointing to the same remote location.

## Goals
1. **Redesign `LibraryImport.tsx` UI**:
   - Compact "Library Path" input.
   - Optional "Network Drive" section with "Remote Path" and "Local Destination".
2. **Backend Schema Update**:
   - Add `import_is_network` and `import_remote_path` to the `Console` model in SQLite.
3. **Cross-Device Validation**:
   - When a device updates its console configuration, the server checks if other devices have already set a different `import_remote_path` for the same console.
4. **Config Updates**:
   - Update how `import_rom_source` is structured to support the new fields.

## Implementation Steps

### Phase 1: Backend (Schema & Store)
- [x] Modify `src/server/store/models.py` to add `import_is_network` and `import_remote_path` to `Console`.
- [ ] Modify `src/server/store/consoles.py` to update `set_console`, `_console_from_row`, and `upsert_console_for_game`.

### Phase 2: Backend (API & Validation)
- [ ] Modify `src/server/api/devices.py` to update `ConsoleFoldersRequest` and implement validation logic in `update_device_console`.

### Phase 3: Frontend (UI & State)
- [ ] Modify `src/gui/renderer/src/components/LibraryImport.tsx`:
    - Redesign the `source` phase.
    - Update state to handle nested `import_rom_source` data.
    - Update `startImport` to pass the new fields.

## Critical Files
- `src/server/store/models.py`
- `src/server/store/consoles.py`
- `src/server/api/devices.py`
- `src/gui/renderer/src/components/LibraryImport.tsx`

## Verification
- [ ] Write/Update integration tests to ensure schema migration works.
- [ ] Test the validation logic by simulating two devices with different remote paths for the same console.


## Context
The current `LibraryImport` wizard is bulky and handles network drives by simply setting a `source` flag in the device's local `emusync.toml`. This makes it impossible to ensure that different devices using "network" for the same console are actually pointing to the same remote location.

## Goals
1. **Redesign `LibraryImport.tsx` UI**:
   - Compact "Library Path" input.
   - Optional "Network Drive" section with "Remote Path" and "Local Destination".
2. **Backend Schema Update**:
   - Add `import_is_network` and `import_remote_path` to the `Console` model in SQLite.
3. **Cross-Device Validation**:
   - When a device updates its console configuration, the server checks if other devices have already set a different `import_remote_path` for the same console.
4. **Config Updates**:
   - Update how `import_rom_source` is structured to support the new fields.

## Implementation Steps

### Phase 1: Backend (Schema & Store)
- [ ] Modify `src/server/store/models.py` to add `import_is_network` and `import_remote_path` to `Console`.
- [ ] Modify `src/server/store/consoles.py` to update `set_console`, `_console_from_row`, and `upsert_console_for_game`.

### Phase 2: Backend (API & Validation)
- [ ] Modify `src/server/api/devices.py` to update `ConsoleFoldersRequest` and implement validation logic in `update_device_console`.

### Phase 3: Frontend (UI & State)
- [ ] Modify `src/gui/renderer/src/components/LibraryImport.tsx`:
    - Redesign the `source` phase.
    - Update state to handle nested `import_rom_source` data.
    - Update `startImport` to pass the new fields.

## Critical Files
- `src/server/store/models.py`
- `src/server/store/consoles.py`
- `src/server/api/devices.py`
- `src/gui/renderer/src/components/LibraryImport.tsx`

## Verification
- [ ] Write/Update integration tests to ensure schema migration works.
- [ ] Test the validation logic by simulating two devices with different remote paths for the same console.
