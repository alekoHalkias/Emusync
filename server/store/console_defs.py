"""Global console/system/core/standalone definitions (source of truth).

Seeded by cli/server.py on startup (from cli/consoles_data.py) and served to the
GUI via the /console-defs, /system-defs, etc. endpoints.
"""
from __future__ import annotations

import json


class ConsoleDefMixin:
    """Operates on `self._conn`; mixed into Store."""

    def seed_console_defs(self, consoles_data: list[dict]) -> None:
        """Populate console definition tables from structured data.

        Idempotent and additive. The top-level `console_defs` row is fully
        server-owned, so it's an upsert (overwritten every startup, including
        on a key that already existed — #430). Everything nested under a
        console (systems/cores/standalones/folder names) stays INSERT OR
        IGNORE: adding a new one to an already-seeded console in
        cli/consoles_data.py gets picked up on the next startup without wiping
        the DB. (The old early-out `continue` skipped existing consoles
        entirely, so additions were silently ignored.)
        """
        for console in consoles_data:
            key = console["key"]
            label = console["label"]
            abbr = console.get("abbr", key.upper())
            suggestions = ";".join(console.get("suggestions", []))
            rom_extensions = ";".join(console.get("rom_extensions", []))
            databases = ";".join(console.get("databases", []))
            # The whole row is server-owned seed data (never user-edited), so
            # every column is overwritten on every startup — INSERT OR IGNORE
            # alone would leave a row seeded under an older cli/consoles_data.py
            # (e.g. a stale label/rom_extensions from before a console split)
            # permanently stuck at its first-ever values (#400, #430).
            self._conn.execute(
                "INSERT INTO console_defs (key, label, abbr, suggestions, rom_extensions, databases) "
                "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET "
                "label=excluded.label, abbr=excluded.abbr, suggestions=excluded.suggestions, "
                "rom_extensions=excluded.rom_extensions, databases=excluded.databases",
                (key, label, abbr, suggestions, rom_extensions, databases)
            )
            for sys_key in console["system_keys"]:
                sys_info = console["systems"].get(sys_key)
                if not sys_info:
                    continue
                self._conn.execute(
                    "INSERT OR IGNORE INTO system_defs (extension, name, save_exts) VALUES (?, ?, ?)",
                    (sys_key, sys_info["name"], ";".join(sys_info["save_exts"]))
                )
                for core in sys_info.get("cores", []):
                    self._conn.execute(
                        "INSERT OR IGNORE INTO core_defs (id, console_key, system_extension, lib_name, folder_name) VALUES (?, ?, ?, ?, ?)",
                        (f"{sys_key}-{core['lib']}", key, sys_key, core["lib"], core["folder"])
                    )
            for folder_name in console.get("folder_names", []):
                self._conn.execute(
                    "INSERT OR IGNORE INTO console_folder_names (console_key, folder_name) VALUES (?, ?)",
                    (key, folder_name)
                )
            for standalone in console.get("standalones", []):
                dirs = standalone.get("dirs", {})
                # Keep save_dir_template populated (NOT NULL) for back-compat; the
                # GUI reads the richer `dirs` blob (save/state/memcard templates).
                native_save = (dirs.get("native") or {}).get("save", "") or standalone.get("save_dir_template", "")
                self._conn.execute(
                    "INSERT OR IGNORE INTO standalone_emulators (id, console_key, label, native_bins, flatpak_id, flatpak_exec, save_dir_template, dirs_json, launch_args) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (f"{key}-{standalone['id']}", key, standalone["label"],
                     ";".join(standalone.get("native_bins", [])),
                     standalone.get("flatpak_id", ""),
                     standalone.get("flatpak_exec", ""),
                     native_save,
                     json.dumps(dirs),
                     ";".join(standalone.get("launch_args", [])))
                )
        self._conn.commit()

    def get_console_defs(self) -> list[dict]:
        """Return all console definitions with systemKeys and standalones."""
        rows = self._conn.execute("SELECT key, label, abbr, suggestions, rom_extensions, databases FROM console_defs ORDER BY key").fetchall()
        result = []
        for row in rows:
            console_key = row["key"]
            # Get system extensions (keys) for this console
            system_rows = self._conn.execute(
                "SELECT DISTINCT system_extension FROM core_defs WHERE console_key = ? ORDER BY system_extension",
                (console_key,)
            ).fetchall()
            system_keys = [r["system_extension"] for r in system_rows]

            # Get standalone emulators for this console
            standalone_rows = self._conn.execute(
                "SELECT id, label, native_bins, flatpak_id, flatpak_exec, save_dir_template, dirs_json, launch_args FROM standalone_emulators WHERE console_key = ? ORDER BY label",
                (console_key,)
            ).fetchall()
            standalones = [self._standalone_row_to_dict(sr) for sr in standalone_rows]

            result.append({
                "key": console_key,
                "label": row["label"],
                "abbr": row["abbr"],
                # Stored as a ';'-joined string (see seed_console_defs) — split it
                # back into a list so the GUI's EmulatorStep can map over it.
                "suggestions": row["suggestions"].split(";") if row["suggestions"] else [],
                "systemKeys": system_keys,
                # Scannable ROM extensions. Decoupled from core-derived systemKeys
                # so a standalone-only console (PS2) scans the right files even with
                # no libretro core; falls back to systemKeys when unset (issue #293).
                "romExtensions": row["rom_extensions"].split(";") if row["rom_extensions"] else system_keys,
                # Libretro database names, matched against installed cores'
                # .info `database` field by the import wizard's detection (#400).
                "databases": row["databases"].split(";") if row["databases"] else [],
                "standalones": standalones,
            })
        return result

    def get_system_defs(self) -> dict[str, dict]:
        """Return all system definitions keyed by extension."""
        rows = self._conn.execute("SELECT extension, name, save_exts FROM system_defs").fetchall()
        result = {}
        for row in rows:
            ext = row["extension"]
            cores = self._conn.execute(
                "SELECT lib_name, folder_name FROM core_defs WHERE system_extension = ? ORDER BY lib_name",
                (ext,)
            ).fetchall()
            result[ext] = {
                "name": row["name"],
                "save_exts": row["save_exts"].split(";"),
                "cores": [{"lib": c["lib_name"], "folder": c["folder_name"]} for c in cores]
            }
        return result

    def get_console_folder_names(self) -> dict[str, list[str]]:
        """Return console key → folder name patterns."""
        rows = self._conn.execute("SELECT console_key, folder_name FROM console_folder_names").fetchall()
        result = {}
        for row in rows:
            if row["console_key"] not in result:
                result[row["console_key"]] = []
            result[row["console_key"]].append(row["folder_name"])
        return result

    def get_standalones_for_console(self, console_key: str) -> list[dict]:
        """Return standalone emulator defs for a console."""
        rows = self._conn.execute(
            "SELECT id, label, native_bins, flatpak_id, flatpak_exec, save_dir_template, dirs_json, launch_args FROM standalone_emulators WHERE console_key = ?",
            (console_key,)
        ).fetchall()
        return [self._standalone_row_to_dict(r) for r in rows]

    @staticmethod
    def _standalone_row_to_dict(row) -> dict:
        """Shape a standalone_emulators row for the API/GUI: split the ';'-joined
        bins/args and parse the dir-template blob (issues #292, #293)."""
        try:
            dirs = json.loads(row["dirs_json"]) if row["dirs_json"] else {}
        except (ValueError, TypeError):
            dirs = {}
        return {
            "id": row["id"],
            "label": row["label"],
            "native_bins": row["native_bins"].split(";") if row["native_bins"] else [],
            "flatpak_id": row["flatpak_id"],
            "flatpak_exec": row["flatpak_exec"],
            "save_dir_template": row["save_dir_template"],
            "dirs": dirs,
            "launch_args": row["launch_args"].split(";") if row["launch_args"] else [],
        }
