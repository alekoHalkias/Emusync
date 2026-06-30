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


# ── on-disk blob storage (#239) ────────────────────────────────────────────────

def test_save_bytes_live_on_disk_not_in_sqlite():
    """A pushed save's bytes go to blobs/saves/<id> on disk; SQLite keeps only meta."""
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        store.ensure_device("dev-1", "PC")
        store.add_game("zelda", "Zelda")
        meta = store.push_save("zelda", "dev-1", b"hello-save")

        # The blob file exists on disk and holds exactly the pushed bytes.
        row = store._conn.execute(
            "SELECT id, size FROM saves WHERE game_slug = ?", ("zelda",)
        ).fetchone()
        blob_file = Path(tmpdir) / "blobs" / "saves" / row["id"]
        assert blob_file.read_bytes() == b"hello-save"
        assert row["size"] == len(b"hello-save") == meta.size

        # The saves table no longer carries a data column at all.
        cols = {c[1] for c in store._conn.execute("PRAGMA table_info(saves)").fetchall()}
        assert "data" not in cols

        # Round-trips through the byte API.
        assert store.pull_save("zelda")[0] == b"hello-save"


def test_remove_game_deletes_on_disk_blobs():
    """Removing a game unlinks its save/state files, not just the DB rows (#239)."""
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        store.ensure_device("dev-1", "PC")
        store.add_game("zelda", "Zelda")
        store.push_save("zelda", "dev-1", b"save-bytes")
        store.push_state("zelda", "dev-1", b"state-bytes")

        saves_dir = Path(tmpdir) / "blobs" / "saves"
        states_dir = Path(tmpdir) / "blobs" / "states"
        assert list(saves_dir.iterdir()) and list(states_dir.iterdir())

        store.remove_game("zelda")
        assert list(saves_dir.iterdir()) == []
        assert list(states_dir.iterdir()) == []


def test_prune_unlinks_old_generation_files():
    """Pushing past HISTORY_LIMIT prunes both the rows and their on-disk files."""
    from pathlib import Path
    from server.store.blobs import HISTORY_LIMIT
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        store.ensure_device("dev-1", "PC")
        store.add_game("zelda", "Zelda")
        for i in range(HISTORY_LIMIT + 5):
            store.push_save("zelda", "dev-1", f"save-{i}".encode())

        saves_dir = Path(tmpdir) / "blobs" / "saves"
        rows = store._conn.execute("SELECT COUNT(*) AS n FROM saves").fetchone()["n"]
        assert rows == HISTORY_LIMIT
        # File count tracks row count — no orphans left behind.
        assert len(list(saves_dir.iterdir())) == HISTORY_LIMIT


def test_v7_to_v8_migration_moves_blobs_to_disk():
    """A v7 DB with BLOBs in SQLite migrates its bytes to disk and drops the column.

    Builds a realistic pre-migration `saves` row (data BLOB, no size column), opens
    it through Store(), and asserts the bytes are now on disk and still pullable.
    No mocks — a real on-disk SQLite file, per the project's testing rule.
    """
    import sqlite3
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "emusync.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(
            """
            CREATE TABLE devices (id TEXT PRIMARY KEY, name TEXT NOT NULL);
            CREATE TABLE games (slug TEXT PRIMARY KEY, name TEXT NOT NULL, console TEXT DEFAULT '');
            CREATE TABLE saves (
                id TEXT PRIMARY KEY, game_slug TEXT NOT NULL, device_id TEXT NOT NULL,
                data BLOB NOT NULL, hash TEXT NOT NULL, pushed_at TEXT NOT NULL
            );
            CREATE TABLE states (
                id TEXT PRIMARY KEY, game_slug TEXT NOT NULL, device_id TEXT NOT NULL,
                data BLOB NOT NULL, hash TEXT NOT NULL, pushed_at TEXT NOT NULL
            );
            """
        )
        conn.execute("INSERT INTO devices (id, name) VALUES ('dev-1', 'PC')")
        conn.execute("INSERT INTO games (slug, name) VALUES ('zelda', 'Zelda')")
        conn.execute(
            "INSERT INTO saves (id, game_slug, device_id, data, hash, pushed_at) "
            "VALUES ('v1', 'zelda', 'dev-1', ?, 'h', '2026-01-01T00:00:00+00:00')",
            (b"legacy-save-bytes",),
        )
        conn.execute("PRAGMA user_version = 7")
        conn.commit()
        conn.close()

        # Opening through Store() runs the v8 migration.
        store = Store(tmpdir)

        assert store._conn.execute("PRAGMA user_version").fetchone()[0] >= 8
        cols = {c[1] for c in store._conn.execute("PRAGMA table_info(saves)").fetchall()}
        assert "data" not in cols and "size" in cols

        blob_file = Path(tmpdir) / "blobs" / "saves" / "v1"
        assert blob_file.read_bytes() == b"legacy-save-bytes"
        data, meta = store.pull_save("zelda")
        assert data == b"legacy-save-bytes"
        assert meta.size == len(b"legacy-save-bytes")


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


def test_seed_and_serve_standalones():
    """Standalones round-trip through seed → get_console_defs/get_standalones
    with split native_bins and a parsed `dirs` blob (issue #292)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        store.seed_console_defs([{
            "key": "gba", "label": "Game Boy Advance", "abbr": "GBA",
            "suggestions": [], "system_keys": ["gba"],
            "systems": {"gba": {"name": "GBA", "save_exts": ["srm"], "cores": []}},
            "folder_names": [],
            "standalones": [{
                "id": "mgba", "label": "mGBA",
                "native_bins": ["/usr/bin/mgba-qt", "~/.local/bin/mgba-qt"],
                "flatpak_id": "io.mgba.mGBA", "flatpak_exec": "flatpak run io.mgba.mGBA",
                "dirs": {"native": {"save": "~/.local/share/mGBA/saves"},
                         "flatpak": {"save": "~/.var/app/io.mgba.mGBA/data/mGBA/saves"}},
            }],
        }])
        gba = {c["key"]: c for c in store.get_console_defs()}["gba"]
        assert len(gba["standalones"]) == 1
        s = gba["standalones"][0]
        assert s["native_bins"] == ["/usr/bin/mgba-qt", "~/.local/bin/mgba-qt"]
        assert s["flatpak_id"] == "io.mgba.mGBA"
        assert s["dirs"]["native"]["save"] == "~/.local/share/mGBA/saves"
        assert s["dirs"]["flatpak"]["save"].endswith("/mGBA/saves")
        # The per-console endpoint helper returns the same parsed shape.
        viac = store.get_standalones_for_console("gba")
        assert viac[0]["dirs"]["flatpak"]["save"] == s["dirs"]["flatpak"]["save"]


def test_real_seed_data_includes_mgba_standalone():
    """The actual import seed data must now carry standalones (regression for the
    empty-standalones bug that made mGBA unselectable — issue #292)."""
    from cli.consoles_data import _prepare_console_seed_data
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        store.seed_console_defs(_prepare_console_seed_data())
        gba = {c["key"]: c for c in store.get_console_defs()}["gba"]
        labels = {s["label"] for s in gba["standalones"]}
        assert "mGBA" in labels
        mgba = next(s for s in gba["standalones"] if s["label"] == "mGBA")
        assert mgba["dirs"]["native"]["save"].startswith("~/")


def test_real_seed_data_includes_ps2_pcsx2():
    """PS2 is a standalone-only console: PCSX2 with launch args, explicit
    romExtensions, and no RetroArch systemKeys (issue #293)."""
    from cli.consoles_data import _prepare_console_seed_data
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        store.seed_console_defs(_prepare_console_seed_data())
        ps2 = {c["key"]: c for c in store.get_console_defs()}.get("ps2")
        assert ps2 is not None, "PS2 console missing from seed data"
        # No libretro core → no systemKeys (so PS1 disc cores aren't offered)...
        assert ps2["systemKeys"] == []
        # ...but the scannable extensions are declared explicitly.
        assert set(ps2["romExtensions"]) == {"iso", "chd", "bin"}
        pcsx2 = next(s for s in ps2["standalones"] if s["label"] == "PCSX2")
        assert pcsx2["launch_args"] == ["-batch", "-fullscreen"]
        assert pcsx2["flatpak_id"] == "net.pcsx2.PCSX2"
        assert pcsx2["dirs"]["native"]["state"].endswith("/sstates")
        assert pcsx2["dirs"]["native"]["memcard"].endswith("/memcards")


def test_console_rom_extensions_default_to_system_keys():
    """A console without explicit rom_extensions reports its systemKeys (#293)."""
    from cli.consoles_data import _prepare_console_seed_data
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        store.seed_console_defs(_prepare_console_seed_data())
        gba = {c["key"]: c for c in store.get_console_defs()}["gba"]
        assert gba["romExtensions"] == gba["systemKeys"]
        assert "gba" in gba["romExtensions"]


def test_get_console_defs_returns_suggestions_as_list():
    """suggestions is stored ';'-joined but must read back as a list so the GUI
    can map over it (a string crashed EmulatorStep — issue #270)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        store.seed_console_defs([{
            "key": "gba", "label": "Game Boy Advance", "abbr": "GBA",
            "suggestions": ["RetroArch with mGBA core", "mGBA standalone"],
            "system_keys": ["gba"],
            "systems": {"gba": {"name": "GBA", "save_exts": ["srm"], "cores": []}},
            "folder_names": [], "standalones": [],
        }])
        defs = {c["key"]: c for c in store.get_console_defs()}
        assert defs["gba"]["suggestions"] == ["RetroArch with mGBA core", "mGBA standalone"]


def test_get_console_defs_empty_suggestions_is_empty_list():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = Store(tmpdir)
        store.seed_console_defs([{
            "key": "nes", "label": "NES", "abbr": "NES", "suggestions": [],
            "system_keys": ["nes"],
            "systems": {"nes": {"name": "NES", "save_exts": ["srm"], "cores": []}},
            "folder_names": [], "standalones": [],
        }])
        defs = {c["key"]: c for c in store.get_console_defs()}
        assert defs["nes"]["suggestions"] == []


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
