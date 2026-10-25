# Plan: #604 test suite smarter test selection

Issue: #604
Branch: feature/604-test-suite-goes-over-the-whole-list-of-t
PR: none
Status: implementing
Fix attempts: 0

## Goal
Rewrite `scripts/test_changed.py` to use AST-based import graph analysis and file-type routing, so only tests that actually depend on changed files are run.

## Steps
- [x] 1. Build AST-based reverse import map: parse each test file's imports and map source modules to the test files that import them.
  - Files: scripts/test_changed.py
  - Reuses: None (current script is a simple stem-matcher)
  - New: `_build_reverse_import_map()` function — parses AST of each test file, collects top-level imports, and builds a dict mapping source module names to sets of test file names. Handles `from server import api`, `from cli.run import ...`, `from cli.consoles_data import ...` patterns.

- [x] 2. Add file-type routing: classify changed files and map them to test categories.
  - Files: scripts/test_changed.py
  - Reuses: existing `changed_files()` function
  - New: `_route_by_type(changed_file)` function and `_FILE_TYPE_ROUTES` dict with rules:
    - `tests/conftest.py` → full suite (all fixtures are affected)
    - `server/api/*.py` → all tests that import `server` (API tests use the app fixture)
    - `server/store/*.py` → all tests that import `server.store` or `server`
    - `cli/consoles_data.py` → console/memcard/save tests (test_cli_console_import.py, test_core_detection.py, test_defs_api.py, test_new_consoles.py, test_run_ps3.py, test_store_internals.py)
    - `cli/detect.py` → test_cli_console_import.py, test_core_detection.py, test_new_consoles.py
    - `*.toml`, `*.json` (config files) → all tests that import `server.config` or use `live_server` fixture
    - `cli/transfer.py` → test_transfer_wizard.py, test_manual_transfer_cli.py
    - `cli/netrom.py` → test_netrom.py, test_network_rom.py

- [x] 3. Add transitive dependency resolution: if source file A imports source file B, and a test imports A, then changes to B should also trigger that test.
  - Files: scripts/test_changed.py
  - Reuses: AST parsing from step 1
  - New: `_resolve_transitive_deps(changed_files)` — builds a forward import graph of all source files, then for each changed file, finds all tests that transitively depend on it. Uses BFS to resolve the full dependency chain.

- [x] 4. Integrate all strategies: combine AST-based matching, file-type routing, and transitive resolution; fall back to stem matching for edge cases; fall back to full suite when nothing matches.
  - Files: scripts/test_changed.py
  - Reuses: existing `changed_files()`, existing stem-matching (kept as fallback)
  - New: `_select_tests(changed_files)` — orchestrates all strategies, deduplicates results, prints the selection, runs pytest with the selected files.

- [x] 5. Test the script: verify it selects correct tests for various changed-file scenarios, and that `make test-changed` works end to end.
  - Files: scripts/test_changed.py (self-test via manual verification)
  - Test cases:
    - Change `server/api/games.py` → 5 test files (test_games.py, test_conflict_check.py, test_conflicts.py, test_devices.py, test_integrity.py)
    - Change `cli/consoles_data.py` → 23 test files (console/import/detection tests)
    - Change `tests/conftest.py` → full suite
    - Change `server/store/schema.py` → 1 test file (test_store_internals.py)
    - Change `cli/run_switch.py` → 15 test files (switch/run tests)
    - No changes → full suite
    - Changed file with no known dependency → stem matching fallback, then full suite

- [x] 6. Update Makefile if needed and commit.
  - Files: Makefile (no changes expected — `test-changed` target already calls `scripts/test_changed.py`)
  - Reuses: existing Makefile target

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- Adding per-test timing or parallelism
- Caching the import graph (could be a future optimization)
- Supporting other test frameworks (pytest-only)

## Additional Steps (beyond original plan)
- [ ] 7. Write docs/WORKFLOW.md — end-to-end workflow guide documenting the full `/issue` -> `/design` -> `/plan` -> `/implement` -> `/ship` pipeline, handoff file format, and resume mode.
  - Files: docs/WORKFLOW.md
  - Reuses: none (new document)
  - New: comprehensive workflow reference for the skill-based pipeline

## Log
- Step 1-4: Implemented all strategies (AST map, file-type routing, transitive deps, integration) in a single rewrite of scripts/test_changed.py.
- Step 5: Verified 6 scenarios — all selected correct test files.
