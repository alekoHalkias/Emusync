"""Console schema migration tests — v30 adds import_is_network / import_remote_path."""
from __future__ import annotations

import tempfile

from server.store import Store


def test_migration_from_v29_adds_import_columns(tmp_path):
    """A v29 database gets import_is_network and import_remote_path on upgrade."""
    db = str(tmp_path / "emusync")
    # Build a v29 database: create consoles table without the new columns.
    s = Store(db)
    s._conn.execute("PRAGMA user_version = 29")
    s._conn.commit()

    # Simulate the old schema — drop the new columns if they exist (fresh DB
    # already has them via CREATE TABLE, so we rebuild).
    s._conn.execute("DROP TABLE consoles")
    s._conn.execute("""
        CREATE TABLE consoles (
            id              TEXT PRIMARY KEY,
            device_id       TEXT NOT NULL,
            console_name    TEXT NOT NULL,
            shortform_name  TEXT NOT NULL DEFAULT '',
            device_game_folder   TEXT NOT NULL DEFAULT '',
            device_save_folder   TEXT NOT NULL DEFAULT '',
            device_state_folder  TEXT NOT NULL DEFAULT '',
            device_emulator      TEXT NOT NULL DEFAULT '',
            device_network_folder TEXT NOT NULL DEFAULT '',
            device_local_folder   TEXT NOT NULL DEFAULT '',
            device_extra_folders  TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        )
    """)
    s._conn.execute("PRAGMA user_version = 29")
    s._conn.commit()

    # Reopen triggers migration.
    s2 = Store(str(tmp_path / "emusync2"))
    row = s2._conn.execute(
        "PRAGMA table_info(consoles)"
    ).fetchall()
    col_names = [r[1] for r in row]
    assert "import_is_network" in col_names
    assert "import_remote_path" in col_names
    assert s2._conn.execute("PRAGMA user_version").fetchone()[0] == 30


def test_migration_from_v29_preserves_existing_consoles(tmp_path):
    """Existing console rows survive the v29→v30 migration with defaults."""
    # Build a v29 database with an existing console.
    s = Store(str(tmp_path / "emusync"))
    s._conn.execute("PRAGMA user_version = 29")
    s._conn.commit()
    s._conn.execute("DROP TABLE consoles")
    s._conn.execute("""
        CREATE TABLE consoles (
            id              TEXT PRIMARY KEY,
            device_id       TEXT NOT NULL,
            console_name    TEXT NOT NULL,
            shortform_name  TEXT NOT NULL DEFAULT '',
            device_game_folder   TEXT NOT NULL DEFAULT '',
            device_save_folder   TEXT NOT NULL DEFAULT '',
            device_state_folder  TEXT NOT NULL DEFAULT '',
            device_emulator      TEXT NOT NULL DEFAULT '',
            device_network_folder TEXT NOT NULL DEFAULT '',
            device_local_folder   TEXT NOT NULL DEFAULT '',
            device_extra_folders  TEXT NOT NULL DEFAULT '[]',
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        )
    """)
    s._conn.execute(
        "INSERT INTO devices (id, name) VALUES (?, ?)", ("d1", "PC")
    )
    s._conn.execute(
        "INSERT INTO consoles (id, device_id, console_name, shortform_name, "
        "device_game_folder, device_save_folder, device_state_folder, "
        "device_emulator, device_network_folder, device_local_folder, "
        "device_extra_folders) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("c1", "d1", "SNES", "snes", "/roms/snes", "", "", "", "", "", "[]"),
    )
    s._conn.commit()

    # Reopen → migration runs, existing row survives with new column defaults.
    s2 = Store(str(tmp_path / "emusync"))
    consoles = s2.list_consoles("d1")
    assert len(consoles) == 1
    assert consoles[0].import_is_network is False
    assert consoles[0].import_remote_path == ""


def test_fresh_db_has_new_columns(tmp_path):
    """A brand-new Store gets the columns directly from CREATE TABLE."""
    s = Store(str(tmp_path / "emusync"))
    row = s._conn.execute(
        "PRAGMA table_info(consoles)"
    ).fetchall()
    col_names = [r[1] for r in row]
    assert "import_is_network" in col_names
    assert "import_remote_path" in col_names
    assert s._conn.execute("PRAGMA user_version").fetchone()[0] == 30


def test_console_from_row_parses_new_fields(tmp_path):
    """_console_from_row correctly handles import_is_network / import_remote_path."""
    s = Store(str(tmp_path / "emusync"))
    from server.store.models import Console
    s.ensure_device("d1", "PC")
    s.set_console(Console(
        id="c1", device_id="d1", console_name="PS2", shortform_name="ps2",
        device_game_folder="/roms/ps2",
        import_is_network=True, import_remote_path="/mnt/nas/ps2",
    ))
    consoles = s.list_consoles("d1")
    assert len(consoles) == 1
    assert consoles[0].import_is_network is True
    assert consoles[0].import_remote_path == "/mnt/nas/ps2"
