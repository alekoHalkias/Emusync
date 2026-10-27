#!/usr/bin/env python3
"""Run only the tests relevant to files changed vs. main.

Uses AST-based import graph analysis, file-type routing, and transitive
dependency resolution to select the minimal set of tests that cover the
changed files. Falls back to stem matching for edge cases, and to the full
suite when no matches are found.
"""
import ast
import subprocess
import sys
from pathlib import Path
from collections import deque

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "src/tests"
SRC_DIRS = [ROOT / "src/server", ROOT / "src/cli"]
VENV_PYTHON = str(ROOT / ".cache/.venv/bin/python")


def changed_files() -> list[str]:
    diffs = []
    for args in (
        ["git", "diff", "--name-only", "main...HEAD"],
        ["git", "diff", "--name-only"],
        ["git", "diff", "--name-only", "--cached"],
    ):
        out = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=False)
        diffs += out.stdout.splitlines()
    return sorted(set(f for f in diffs if f))


# ---------------------------------------------------------------------------
# AST-based reverse import map
# ---------------------------------------------------------------------------

def _get_imports(filepath: Path) -> set[str]:
    """Return top-level module names imported by *filepath*."""
    try:
        with open(filepath) as f:
            tree = ast.parse(f.read(), filename=str(filepath))
    except Exception:
        return set()
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                imports.add(node.module)
    return imports


def _build_module_map() -> dict[str, Path]:
    """Map dotted module names to their source file paths."""
    modules: dict[str, Path] = {}
    for sd in SRC_DIRS:
        for pyfile in sd.rglob("*.py"):
            rel = str(pyfile.relative_to(ROOT))
            mod_name = rel.replace("/", ".").removesuffix(".py")
            modules[mod_name] = pyfile
    return modules


def _build_reverse_import_map() -> dict[str, set[str]]:
    """Map source module names -> set of test file names that import them."""
    modules = _build_module_map()
    reverse: dict[str, set[str]] = {}

    for tf in TESTS_DIR.glob("test_*.py"):
        imports = _get_imports(tf)
        for imp in imports:
            for mod_name, mod_path in modules.items():
                if imp == mod_name or imp.startswith(mod_name + "."):
                    reverse.setdefault(mod_name, set()).add(tf.name)
    return reverse


# ---------------------------------------------------------------------------
# Transitive dependency resolution
# ---------------------------------------------------------------------------

def _build_forward_import_graph() -> dict[str, set[str]]:
    """Map source module names -> set of source module names they import."""
    modules = _build_module_map()
    graph: dict[str, set[str]] = {}

    for mod_name, mod_path in modules.items():
        imports = _get_imports(mod_path)
        deps: set[str] = set()
        for imp in imports:
            for other_mod in modules:
                if imp == other_mod or imp.startswith(other_mod + "."):
                    deps.add(other_mod)
        graph[mod_name] = deps

    return graph


def _resolve_transitive_deps(
    changed_files: list[str],
    reverse_map: dict[str, set[str]],
    forward_graph: dict[str, set[str]],
) -> set[str]:
    """For each changed file, find all tests that transitively depend on it."""
    file_to_module: dict[Path, set[str]] = {}

    for mod_name, mod_path in _build_module_map().items():
        file_to_module.setdefault(mod_path, set()).add(mod_name)

    changed_modules: set[str] = set()
    for f in changed_files:
        fp = ROOT / f
        if fp in file_to_module:
            changed_modules.update(file_to_module[fp])

    # BFS: find all modules that transitively depend on changed modules
    transitive_modules: set[str] = set(changed_modules)
    queue: deque[str] = deque(changed_modules)

    while queue:
        current = queue.popleft()
        for mod_name, deps in forward_graph.items():
            if current in deps and mod_name not in transitive_modules:
                transitive_modules.add(mod_name)
                queue.append(mod_name)

    tests: set[str] = set()
    for mod_name in transitive_modules:
        if mod_name in reverse_map:
            tests.update(reverse_map[mod_name])

    return tests


# ---------------------------------------------------------------------------
# File-type routing
# ---------------------------------------------------------------------------

_CONFIG_EXTENSIONS = {".toml", ".json"}

# Explicit file-to-test mappings for files with no clean AST module match
_FILE_TYPE_ROUTES: dict[str, set[str]] = {
    "src/tests/conftest.py": {"__full_suite__"},
    "cli/consoles_data.py": {
        "test_cli_console_import.py",
        "test_core_detection.py",
        "test_defs_api.py",
        "test_new_consoles.py",
        "test_run_ps3.py",
        "test_store_internals.py",
    },
    "cli/detect.py": {
        "test_cli_console_import.py",
        "test_core_detection.py",
        "test_new_consoles.py",
    },
    "cli/transfer.py": {
        "test_transfer_wizard.py",
        "test_manual_transfer_cli.py",
    },
    "cli/netrom.py": {
        "test_netrom.py",
        "test_network_rom.py",
    },
    "cli/watch.py": {
        "test_save_watcher.py",
    },
    "cli/game.py": {
        "test_game_remove.py",
        "test_manual_transfer_cli.py",
        "test_switch_ensure_save_folder.py",
        "test_switch_pull_no_local_save.py",
    },
    "cli/run.py": {
        "test_launch_command_token.py",
        "test_lock_heartbeat_interval.py",
        "test_new_consoles.py",
        "test_run_reconcile.py",
        "test_state_sync.py",
    },
    "cli/run_switch.py": {
        "test_switch_mods.py",
        "test_switch_save_sync.py",
    },
    "cli/run_ps2.py": {
        "test_console_memcard.py",
        "test_gc_card_format_mismatch.py",
        "test_new_consoles.py",
        "test_ps2_playtime.py",
        "test_run_reconcile.py",
    },
    "cli/run_wii.py": {"test_wii_save_sync.py"},
    "cli/run_ps3.py": {"test_run_ps3.py"},
    "cli/run_reconcile.py": {"test_run_reconcile.py"},
    "cli/run_offline.py": {"test_run_reconcile.py"},
    "cli/run_conflicts.py": {"test_run_reconcile.py"},
    "cli/server.py": {
        "test_server_logging.py",
        "test_server_start_guard.py",
    },
    "cli/console.py": {
        "test_manual_transfer_cli.py",
        "test_new_consoles.py",
    },
    "cli/common.py": {
        "test_run_reconcile.py",
        "test_time_format.py",
    },
    "cli/mod.py": {"test_switch_mods.py"},
    "cli/device.py": {"test_devices.py"},
    "cli/rom.py": {
        "test_rom_import.py",
        "test_rom_transfer.py",
    },
    # Server API modules
    "server/api/games.py": {
        "test_games.py",
        "test_conflict_check.py",
        "test_conflicts.py",
        "test_devices.py",
        "test_integrity.py",
    },
    "server/api/devices.py": {"test_devices.py"},
    "server/api/conflicts.py": {
        "test_conflicts.py",
        "test_conflicts_prune.py",
        "test_conflict_check.py",
    },
    "server/api/locks.py": {
        "test_locks.py",
        "test_lock_heartbeat_interval.py",
    },
    "server/api/blobs.py": {
        "test_saves.py",
        "test_console_memcard.py",
        "test_store_internals.py",
    },
    "server/api/metadata.py": {"test_metadata_api.py"},
    "server/api/settings.py": {
        "test_settings_api.py",
        "test_server_settings.py",
    },
    "server/api/transfers.py": {
        "test_transfer_wizard.py",
        "test_rom_transfer.py",
    },
    "server/api/mods.py": {"test_switch_mods.py"},
    "server/api/defs.py": {"test_defs_api.py"},
    "server/api/_core.py": {
        "test_lock_heartbeat_interval.py",
        "test_devices.py",
        "test_integrity.py",
    },
    # Server store modules
    "server/store/games.py": {
        "test_games.py",
        "test_saves.py",
        "test_store_internals.py",
    },
    "server/store/devices.py": {"test_devices.py"},
    "server/store/locks.py": {"test_locks.py"},
    "server/store/events.py": {"test_events.py"},
    "server/store/schema.py": {"test_store_internals.py"},
    "server/store/blobs.py": {
        "test_saves.py",
        "test_console_memcard.py",
        "test_store_internals.py",
    },
    "server/store/conflicts.py": {
        "test_conflicts.py",
        "test_conflicts_prune.py",
        "test_conflict_check.py",
    },
    "server/store/metadata.py": {"test_metadata_api.py"},
    "server/store/settings.py": {"test_settings_api.py"},
    "server/store/transfers.py": {"test_transfer_wizard.py"},
    "server/store/console_defs.py": {
        "test_defs_api.py",
        "test_new_consoles.py",
        "test_store_internals.py",
    },
    "server/store/switch_mods.py": {"test_switch_mods.py"},
    # Server config/paths/mdns
    "server/config.py": {
        "test_config_roundtrip.py",
        "test_game_remove.py",
        "test_manual_transfer_cli.py",
        "test_server_logging.py",
        "test_switch_ensure_save_folder.py",
        "test_switch_pull_no_local_save.py",
        "test_transfer_wizard.py",
    },
    "server/paths.py": {"test_paths.py"},
    "server/mdns.py": {"test_store_internals.py"},
    "server/sync_client.py": {
        "test_game_remove.py",
        "test_health_retry.py",
        "test_manual_transfer_cli.py",
        "test_memcard_folder_sync.py",
        "test_new_consoles.py",
        "test_run_reconcile.py",
        "test_saves.py",
        "test_state_sync.py",
        "test_switch_ensure_save_folder.py",
        "test_switch_mods.py",
        "test_switch_pull_no_local_save.py",
        "test_transfer_wizard.py",
        "test_wii_save_sync.py",
    },
    # Server API init (imports all routers)
    "server/api/__init__.py": {
        "test_games.py",
        "test_devices.py",
        "test_conflicts.py",
        "test_conflicts_prune.py",
        "test_conflict_check.py",
        "test_locks.py",
        "test_lock_heartbeat_interval.py",
        "test_saves.py",
        "test_console_memcard.py",
        "test_metadata_api.py",
        "test_settings_api.py",
        "test_server_settings.py",
        "test_transfer_wizard.py",
        "test_rom_transfer.py",
        "test_switch_mods.py",
        "test_defs_api.py",
        "test_integrity.py",
    },
    # Server store init
    "server/store/__init__.py": {
        "test_games.py",
        "test_devices.py",
        "test_conflicts.py",
        "test_conflicts_prune.py",
        "test_conflict_check.py",
        "test_locks.py",
        "test_events.py",
        "test_saves.py",
        "test_console_memcard.py",
        "test_metadata_api.py",
        "test_settings_api.py",
        "test_transfer_wizard.py",
        "test_rom_transfer.py",
        "test_switch_mods.py",
        "test_store_internals.py",
        "test_config_roundtrip.py",
        "test_game_remove.py",
        "test_manual_transfer_cli.py",
        "test_server_logging.py",
        "test_switch_ensure_save_folder.py",
        "test_switch_pull_no_local_save.py",
        "test_new_consoles.py",
    },
    # CLI init/root
    "cli/__init__.py": {
        "test_game_remove.py",
        "test_manual_transfer_cli.py",
        "test_transfer_wizard.py",
    },
    "cli/root.py": {
        "test_game_remove.py",
        "test_manual_transfer_cli.py",
        "test_transfer_wizard.py",
    },
}


def _route_by_type(changed_file: str, all_test_files: set[str]) -> set[str] | None:
    """Return tests to run for a changed file based on its type, or None."""
    if changed_file == "src/tests/conftest.py":
        return {"__full_suite__"}

    path = Path(changed_file)
    if path.suffix in _CONFIG_EXTENSIONS:
        config_tests = {
            "test_config_roundtrip.py",
            "test_game_remove.py",
            "test_manual_transfer_cli.py",
            "test_server_logging.py",
            "test_switch_ensure_save_folder.py",
            "test_switch_pull_no_local_save.py",
            "test_transfer_wizard.py",
        }
        return config_tests & all_test_files

    if changed_file in _FILE_TYPE_ROUTES:
        return _FILE_TYPE_ROUTES[changed_file]

    return None


# ---------------------------------------------------------------------------
# Stem matching (fallback)
# ---------------------------------------------------------------------------

def _stem_match(changed_file: str, all_test_files: set[str]) -> set[str]:
    """Fall back to stem matching for files without explicit routes."""
    path = Path(changed_file)
    stem = path.stem
    if not stem:
        return set()
    selected: set[str] = set()
    for t in all_test_files:
        if stem and stem in t:
            selected.add(t)
    return selected


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _select_tests(changed_files: list[str], all_test_files: set[str]) -> set[str] | None:
    """Orchestrate all strategies and return the selected test files."""
    tests: set[str] = set()
    full_suite_triggered = False

    # Strategy 1: File-type routing
    for f in changed_files:
        routed = _route_by_type(f, all_test_files)
        if routed is None:
            continue
        if "__full_suite__" in routed:
            full_suite_triggered = True
            break
        tests.update(routed)

    if full_suite_triggered:
        return {"__full_suite__"}

    # Strategy 2: AST-based reverse import map + transitive deps
    reverse_map = _build_reverse_import_map()
    forward_graph = _build_forward_import_graph()
    transitive_tests = _resolve_transitive_deps(changed_files, reverse_map, forward_graph)
    tests.update(transitive_tests)

    # Strategy 3: Stem matching fallback
    for f in changed_files:
        path = Path(f)
        if path.parts[:1] == ("tests",) and path.name in all_test_files:
            tests.add(path.name)
            continue
        stem_tests = _stem_match(f, all_test_files)
        tests.update(stem_tests)

    return tests if tests else None


def main() -> int:
    changed = changed_files()
    if not changed:
        print("No changes detected vs. main — running full suite.")
        return subprocess.run(
            [VENV_PYTHON, "-m", "pytest", "src/tests/", "-v"],
            cwd=ROOT,
        ).returncode

    all_test_files = {p.name for p in TESTS_DIR.glob("test_*.py")}
    selected = _select_tests(changed, all_test_files)

    if not selected:
        print(f"Changed files: {changed}")
        print("No matching test file found — running full suite as a safety net.")
        return subprocess.run(
            [VENV_PYTHON, "-m", "pytest", "src/tests/", "-v"],
            cwd=ROOT,
        ).returncode

    if selected == {"__full_suite__"}:
        print("conftest.py changed — running full suite.")
        return subprocess.run(
            [VENV_PYTHON, "-m", "pytest", "src/tests/", "-v"],
            cwd=ROOT,
        ).returncode

    print(f"Running {len(selected)} test file(s) matched to changed files:")
    for t in sorted(selected):
        print(f"  - {t}")
    args = [
        VENV_PYTHON,
        "-m",
        "pytest",
        *(f"src/tests/{t}" for t in sorted(selected)),
        "-v",
    ]
    return subprocess.run(args, cwd=ROOT).returncode


if __name__ == "__main__":
    sys.exit(main())
