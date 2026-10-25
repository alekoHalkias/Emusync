# Plan: #604 test suite smarter test selection

Issue: #604
Branch: feature/604-test-suite-goes-over-the-whole-list-of-t
PR: none
Status: planned
Fix attempts: 0

## Goal
Rewrite `scripts/test_changed.py` to use AST-based import graph analysis and file-type routing, so only tests that actually depend on changed files are run.

## Steps
- [ ] 1. Build AST-based reverse import map: parse each test file's imports and map source modules to the test files that import them.
  - Files: scripts/test_changed.py
  - Reuses: None (current script is a simple stem-matcher)
  - New: `_build_reverse_import_map()` function — parses AST of each test file, collects top-level imports, and builds a dict mapping source module names to sets of test file names. Handles `from server import api`, `from cli.run import ...`, `from cli.consoles_data import ...` patterns.

- [ ] 2. Add file-type routing: classify changed files and map them to test categories.
  - Files: scripts/test_changed.py
  - Reuses: existing `changed_files()` function
  - New: `_route_by_type(changed_file)` function with rules:
    - `tests/conftest.py` → full suite (all fixtures are affected)
    - `server/api/*.py` → all tests that import `server` (API tests use the app fixture)
    - `server/store/*.py` → all tests that import `server.store` or `server`
    - `cli/consoles_data.py` → console/memcard/save tests (test_cli_console_import.py, test_core_detection.py, test_defs_api.py, test_new_consoles.py, test_run_ps3.py, test_store_internals.py)
    - `cli/detect.py` → test_cli_console_import.py, test_core_detection.py, test_new_consoles.py
    - `*.toml`, `*.json` (config files) → all tests that import `server.config` or use `live_server` fixture
    - `cli/transfer.py` → test_transfer_wizard.py, test_manual_transfer_cli.py
    - `cli/netrom.py` → test_netrom.py, test_network_rom.py

- [ ] 3. Add transitive dependency resolution: if source file A imports source file B, and a test imports A, then changes to B should also trigger that test.
  - Files: scripts/test_changed.py
  - Reuses: AST parsing from step 1
  - New: `_resolve_transitive_deps(changed_files)` — builds a forward import graph of all source files, then for each changed file, finds all tests that transitively depend on it. Uses BFS to resolve the full dependency chain.

- [ ] 4. Integrate all strategies: combine AST-based matching, file-type routing, and transitive resolution; fall back to stem matching for edge cases; fall back to full suite when nothing matches.
  - Files: scripts/test_changed.py
  - Reuses: existing `changed_files()`, existing stem-matching (kept as fallback)
  - New: `_select_tests(changed_files)` — orchestrates all strategies, deduplicates results, prints the selection, runs pytest with the selected files.

- [ ] 5. Test the script: verify it selects correct tests for various changed-file scenarios, and that `make test-changed` works end to end.
  - Files: scripts/test_changed.py (self-test via manual verification)
  - Test cases:
    - Change `server/api/games.py` → expect test_games.py + any tests importing server.api
    - Change `cli/consoles_data.py` → expect console/import/detection tests
    - Change `tests/conftest.py` → expect full suite
    - Change `server/store/schema.py` → expect store_internals.py + any transitive dependents
    - Change `cli/run_switch.py` → expect test_switch_mods.py, test_switch_save_sync.py
    - No changes → expect full suite
    - Changed file with no known dependency → expect stem matching fallback, then full suite

- [ ] 6. Update Makefile if needed and commit.
  - Files: Makefile (no changes expected — `test-changed` target already calls `scripts/test_changed.py`)
  - Reuses: existing Makefile target

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- Adding per-test timing or parallelism
- Caching the import graph (could be a future optimization)
- Supporting other test frameworks (pytest-only)

## Log
