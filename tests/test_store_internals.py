"""Store-level concurrency, schema versioning, console-def seeding, and helpers."""
from __future__ import annotations

import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor

from server.store import Store, GameDevice


# ── thread safety (issue #200) ──────────────────────────────────────────────

def test_store_concurrent_access_no_misuse():
    """Hammering the store from many threads must not raise sqlite3 errors.

    Regression for `sqlite3.InterfaceError: bad parameter or other API misuse`,
    caused when a single connection was shared across threads: another thread's
    execute()/commit() between an execute() and its fetch() corrupted the
    in-flight statement. Per-thread connections eliminate the shared cursor state.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        store.ensure_device("dev-1", "PC")
        store.add_game("zelda", "Zelda")
        store.set_game_device(GameDevice("zelda", "dev-1", "/roms/z.sfc", "/saves/z.srm", "ra"))

        errors: list[Exception] = []

        def worker(n: int) -> None:
            try:
                for i in range(150):
                    # interleave reads (execute + fetch) and writes (execute + commit)
                    store.get_game_device("zelda", "dev-1")
                    store.list_devices()
                    store.push_save("zelda", "dev-1", f"save-{n}-{i}".encode())
                    store.pull_save("zelda")
                    store.set_game_device(
                        GameDevice("zelda", "dev-1", "/roms/z.sfc", "/saves/z.srm", f"ra-{n}-{i}")
                    )
            except Exception as exc:  # noqa: BLE001 — capture for assertion
                errors.append(exc)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(worker, range(8)))

        assert not errors, f"concurrent store access raised: {errors[:3]}"


def test_foreign_keys_enforced_on_worker_thread():
    """Cascade deletes must work from a non-main thread.

    PRAGMA foreign_keys is per-connection, so every thread's connection must set
    it — otherwise a delete issued off the main thread would orphan child rows.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        store.ensure_device("dev-1", "PC")

        result: dict = {}

        def worker() -> None:
            store.add_game("metroid", "Metroid")
            store.push_save("metroid", "dev-1", b"data")
            store.acquire_lock("metroid", "dev-1")
            store.remove_game("metroid")  # cascade should drop the save + lock
            data, _ = store.pull_save("metroid")
            result["save_after_delete"] = data
            result["lock_after_delete"] = store.get_lock("metroid")

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        assert result["save_after_delete"] is None
        assert result["lock_after_delete"] is None


# ── fresh-DB schema versioning (#202) ──────────────────────────────────────────

def test_fresh_db_is_stamped_at_latest_schema_version():
    """A freshly created DB must report the latest schema version so warm starts
    skip _migrate() entirely (regression: user_version was left at 0, causing the
    whole migration chain to run against a just-created schema)."""
    from server.store.schema import _SCHEMA_VERSION
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        version = store._conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == _SCHEMA_VERSION


# ── console-def seeding is additive (#202) ─────────────────────────────────────

def test_seed_console_defs_picks_up_additions():
    """Re-seeding an existing console with a new core must add it (not skip)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        base = [{
            "key": "gba", "label": "Game Boy Advance", "abbr": "GBA",
            "suggestions": [], "system_keys": ["gba"],
            "systems": {"gba": {"name": "GBA", "save_exts": ["srm"],
                                "cores": [{"lib": "mgba", "folder": "mGBA"}]}},
            "folder_names": [], "standalones": [],
        }]
        store.seed_console_defs(base)
        assert {c["lib"] for c in store.get_system_defs()["gba"]["cores"]} == {"mgba"}

        # Add a second core to the same console and re-seed.
        base[0]["systems"]["gba"]["cores"].append({"lib": "vbam", "folder": "VBA-M"})
        store.seed_console_defs(base)
        assert {c["lib"] for c in store.get_system_defs()["gba"]["cores"]} == {"mgba", "vbam"}


# ── saves→states path helper (#202) ────────────────────────────────────────────

def test_saves_path_to_states_only_swaps_whole_segment():
    from server.store import saves_path_to_states
    assert saves_path_to_states("/home/u/.config/retroarch/saves/SNES") == \
        "/home/u/.config/retroarch/states/SNES"
    assert saves_path_to_states("saves/GBA") == "states/GBA"
    # "saves" inside another segment must NOT be touched
    assert saves_path_to_states("/home/saves_backup/SNES") == "/home/saves_backup/SNES"
    assert saves_path_to_states("") == ""


# ── mDNS primary LAN IP (#9) ───────────────────────────────────────────────────

def test_primary_lan_ip_is_dotted_ipv4():
    """mDNS must advertise a real IPv4 (never crash); see _primary_lan_ip docstring."""
    from server.mdns import _primary_lan_ip
    ip = _primary_lan_ip()
    octets = ip.split(".")
    assert len(octets) == 4 and all(o.isdigit() and 0 <= int(o) <= 255 for o in octets)
