"""Per-device Eden profile for Switch saves (#727)."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from cli import run_switch as rs
from server.sync_client import GameDeviceConfig
from tests.conftest import AUTH

ARCH_UUID = bytes.fromhex("b6ff0f8448f5959ac1196b0997b94db6")
ARCH_FOLDER = "B64DB997096B19C19A95F548840FFFB6"
STRAY_FOLDER = "C19A95F548840FFFB600000000000000"
TITLE = "0100F43008C44000"


def _eden(tmp_path: Path, uuids=(ARCH_UUID,)) -> Path:
    """An Eden data dir with profiles.dat; returns the NAND save root."""
    save_root = tmp_path / "eden/nand/user/save/0000000000000000"
    save_root.mkdir(parents=True)
    dat = rs._profiles_dat(save_root)
    dat.parent.mkdir(parents=True)
    entries = b"".join(u + bytes(0xC8 - 16) for u in uuids)
    entries += bytes(0xC8) * (8 - len(uuids))
    dat.write_bytes(bytes(0x10) + entries)
    return save_root


# ── store / API ──────────────────────────────────────────────────────────────

def test_v32_migration_adds_switch_profile_id(tmp_path):
    from server.store import schema

    conn = sqlite3.connect(str(tmp_path / "old.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE consoles (
        id TEXT PRIMARY KEY, device_id TEXT NOT NULL, console_name TEXT NOT NULL,
        shortform_name TEXT NOT NULL, device_game_folder TEXT NOT NULL DEFAULT '')""")
    conn.execute("CREATE TABLE devices (id TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO consoles VALUES ('c1', 'd1', 'Switch', 'swit', '/roms/switch')")
    conn.execute("PRAGMA user_version = 32")
    conn.commit()
    schema._migrate(conn, from_version=32)
    row = conn.execute("SELECT * FROM consoles").fetchone()
    assert row["device_game_folder"] == "/roms/switch"
    assert row["switch_profile_id"] == ""
    assert conn.execute("PRAGMA user_version").fetchone()[0] == schema._SCHEMA_VERSION


async def test_console_put_stores_and_preserves_switch_profile(client):
    await client.post("/games", json={"name": "Z-A", "console": "Switch"}, headers=AUTH)
    await client.put("/games/z-a/device", json={
        "rom_path": "/roms/switch/za.nsp", "save_path": "", "rom_folder_path": "/roms/switch",
    }, headers=AUTH)
    dev = (await client.get("/whoami", headers=AUTH)).json()["device_id"]
    row = next(c for c in (await client.get(f"/devices/{dev}/consoles", headers=AUTH)).json()
               if c["console_name"] == "Switch")
    assert row["switch_profile_id"] == ""
    folders = {k: row[k] for k in ("device_game_folder", "device_save_folder", "device_state_folder",
                                   "device_emulator", "device_network_folder", "device_local_folder")}
    r = await client.put(f"/devices/{dev}/consoles/{row['id']}",
                         json={**folders, "switch_profile_id": ARCH_FOLDER}, headers=AUTH)
    assert r.status_code == 200
    r = await client.put(f"/devices/{dev}/consoles/{row['id']}", json=folders, headers=AUTH)
    assert r.status_code == 200
    row = next(c for c in (await client.get(f"/devices/{dev}/consoles", headers=AUTH)).json()
               if c["id"] == row["id"])
    assert row["switch_profile_id"] == ARCH_FOLDER
    assert row["device_game_folder"] == "/roms/switch"


# ── profile detection / placement ────────────────────────────────────────────

def test_profiles_dat_gives_real_folder_and_skips_empty_entries(tmp_path):
    assert rs._eden_profile_folders(_eden(tmp_path)) == [ARCH_FOLDER]


def test_missing_or_truncated_profiles_dat_falls_back_to_scan(tmp_path, monkeypatch):
    save_root = tmp_path / "eden/nand/user/save/0000000000000000"
    (save_root / "SOMEPROFILE").mkdir(parents=True)
    monkeypatch.setattr(rs, "_SWITCH_NAND_ROOTS", (save_root,))
    assert rs._eden_profile_folders(save_root) == []
    assert rs._switch_profile_dirs() == [save_root / "SOMEPROFILE"]
    dat = rs._profiles_dat(save_root)
    dat.parent.mkdir(parents=True)
    dat.write_bytes(b"\x00" * 0x20)
    assert rs._switch_profile_dirs() == [save_root / "SOMEPROFILE"]


def test_device_profile_is_the_only_place_saves_are_found_seeded_or_detected(tmp_path, monkeypatch):
    save_root = _eden(tmp_path)
    monkeypatch.setattr(rs, "_SWITCH_NAND_ROOTS", (save_root,))
    stray = save_root / STRAY_FOLDER / TITLE
    stray.mkdir(parents=True)
    (stray / "main").write_text("stray")
    (save_root / f"{ARCH_FOLDER}.bak").mkdir()
    live = save_root / ARCH_FOLDER / TITLE
    live.mkdir(parents=True)
    (live / "main").write_text("live")
    rs._set_switch_profile(ARCH_FOLDER)

    assert rs._switch_profile_dirs() == [save_root / ARCH_FOLDER]
    assert rs._find_local_switch_save(TITLE) == str(live)
    assert rs._resolve_written_switch_save(time.time() - 60) == str(live)

    pulled = []

    class _Save:
        def pull_save(self, key, dest):
            pulled.append(dest)
            return True, "h"

    assert rs._seed_switch_save(_Save(), "z-a", TITLE) == [str(live)]
    assert pulled == [str(live)]


def test_profiles_dat_alone_excludes_stray_folder(tmp_path, monkeypatch):
    save_root = _eden(tmp_path)
    monkeypatch.setattr(rs, "_SWITCH_NAND_ROOTS", (save_root,))
    (save_root / STRAY_FOLDER).mkdir()
    (save_root / ARCH_FOLDER).mkdir()
    assert rs._switch_profile_dirs() == [save_root / ARCH_FOLDER]


class _Consoles:
    def __init__(self, stored=""):
        self.rows = [{"id": "c1", "console_name": "Switch", "device_game_folder": "/r",
                      "switch_profile_id": stored}]
        self.puts = []

    def get_device_consoles(self, device_id):
        return self.rows

    def update_device_console(self, device_id, console):
        self.puts.append(console["switch_profile_id"])


def test_resolve_fills_blank_profile_once_and_stored_wins(tmp_path, monkeypatch):
    monkeypatch.setattr(rs, "_SWITCH_NAND_ROOTS", (_eden(tmp_path),))
    c = _Consoles()
    assert rs._resolve_switch_profile(c, "dev") == ARCH_FOLDER
    assert c.puts == [ARCH_FOLDER]
    c = _Consoles(stored="0F9E31CF8F16E6677DFF94055FFF9B3D")
    assert rs._resolve_switch_profile(c, "dev") == "0F9E31CF8F16E6677DFF94055FFF9B3D"
    assert c.puts == []


def test_resolve_store_failure_only_warns(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rs, "_SWITCH_NAND_ROOTS", (_eden(tmp_path),))
    c = _Consoles()

    def boom(device_id, console):
        raise RuntimeError("offline")
    c.update_device_console = boom
    assert rs._resolve_switch_profile(c, "dev") == ARCH_FOLDER
    assert "failed to store the Switch profile" in capsys.readouterr().err


# ── run_game ─────────────────────────────────────────────────────────────────

def test_run_moves_save_path_from_stray_profile_to_device_profile(monkeypatch, tmp_path):
    """Regression (#727): the Deck's save_path sat in a malformed profile folder
    Eden never reads; the run re-places it in the device profile."""
    import cli.run as run_mod

    save_root = _eden(tmp_path)
    monkeypatch.setattr(rs, "_SWITCH_NAND_ROOTS", (save_root,))
    cfg = SimpleNamespace(data_dir=str(tmp_path), device_id="dev-local", device_name="Deck")
    monkeypatch.setattr(run_mod.cfg_module, "load", lambda: cfg)
    stray = save_root / STRAY_FOLDER / TITLE
    live = save_root / ARCH_FOLDER / TITLE
    for d in (stray, live):
        d.mkdir(parents=True)
        (d / "main").write_bytes(b"progress")
    gd = GameDeviceConfig(rom_path=str(tmp_path / "za.nsp"), save_path=str(stray),
                          launch_command="eden", state_path="", rom_folder_path=str(tmp_path))
    stored = []

    class _C(_Consoles):
        def health(self, retries=0, retry_delay=1.5): return True
        def get_game_device(self, slug): return gd
        def get_game(self, slug):
            return {"name": "Pokemon Legends Z-A", "console": "Switch", "switch_title_id": TITLE}
        def get_lock(self, slug): return {"locked": False}
        def acquire_lock(self, slug): pass
        def release_lock(self, slug): pass
        def get_save_meta(self, slug): return None
        def get_save_sync_baseline(self, slug): return None
        def push_save(self, slug, path): return "h"
        def set_game_device(self, slug, updated_gd): stored.append(updated_gd.save_path)
        def list_switch_mods(self, title_id): return []
        def update_game(self, slug, name, switch_title_id=""): pass

    monkeypatch.setattr(run_mod, "_client", lambda c: _C())
    monkeypatch.setattr(run_mod, "_launch_and_wait", lambda argv, pid_file: 0)
    monkeypatch.setattr(run_mod, "_resolve_written_switch_save", lambda since: None)
    with pytest.raises(SystemExit):
        run_mod.run_game.callback(game_slug="pokemon-legends-z-a", command=())
    assert stored and stored[0] == str(live)
