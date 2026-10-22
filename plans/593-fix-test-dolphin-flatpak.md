# Plan: #593 fix gamecube standalone test leaking real filesystem

Issue: #593
Branch: feature/593-fix-test-dolphin-flatpak
PR: none
Status: implementing
Fix attempts: 0

## Goal

Fix `test_gamecube_standalone_dolphin_detected_via_flatpak_when_no_native_bin` so mocking `os.path.exists` fully suppresses the native Dolphin detection by also mocking `os.path.isdir` and `os.listdir`.

## Steps

- [x] 1. Add `os.path.isdir` and `os.listdir` mocks to the test
  - Files: tests/test_new_consoles.py
  - Reuses: none (pure test fix)
  - New: two monkeypatch calls after the existing `os.path.exists` mock:
    ```python
    monkeypatch.setattr("cli.detect.os.path.isdir", lambda p: False)
    monkeypatch.setattr("cli.detect.os.listdir", lambda d: [])
    ```
  - Why: `_resolve_case_insensitive()` falls through to `os.path.isdir()` + `os.listdir()` when `os.path.exists` is False; without these mocks the real filesystem is probed and finds `/usr/bin/dolphin-emu`.

- [x] 2. Tests: run `make test-changed` to verify the fix and no regressions.

- [x] 3. Docs: none needed - pure test fix.

## Checklist
Schema bump: no. New IPC channel: no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
## Log
