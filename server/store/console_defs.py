"""Global console/system/core/standalone definitions (source of truth).

Seeded by cli/server.py on startup (from cli/consoles_data.py) and served to the
GUI via the /console-defs, /system-defs, etc. endpoints.
"""
from __future__ import annotations


class ConsoleDefMixin:
    """Operates on `self._conn`; mixed into Store."""

    def seed_console_defs(self, consoles_data: list[dict]) -> None:
        """Populate console definition tables from structured data.

        Idempotent *and* additive: every insert is INSERT OR IGNORE, so adding a
        new core/system/standalone to an already-seeded console in
        cli/consoles_data.py gets picked up on the next startup without wiping the
        DB. (The old early-out `continue` skipped existing consoles entirely, so
        additions were silently ignored.)
        """
        for console in consoles_data:
            key = console["key"]
            self._conn.execute(
                "INSERT OR IGNORE INTO console_defs (key, label, abbr, suggestions) VALUES (?, ?, ?, ?)",
                (key, console["label"], console.get("abbr", key.upper()),
                 ";".join(console.get("suggestions", [])))
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
                self._conn.execute(
                    "INSERT OR IGNORE INTO standalone_emulators (id, console_key, label, native_bins, flatpak_id, flatpak_exec, save_dir_template) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (f"{key}-{standalone['id']}", key, standalone["label"],
                     ";".join(standalone.get("native_bins", [])),
                     standalone.get("flatpak_id", ""),
                     standalone.get("flatpak_exec", ""),
                     standalone.get("save_dir_template", ""))
                )
        self._conn.commit()

    def get_console_defs(self) -> list[dict]:
        """Return all console definitions with systemKeys and standalones."""
        rows = self._conn.execute("SELECT key, label, abbr, suggestions FROM console_defs ORDER BY key").fetchall()
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
                "SELECT id, label, native_bins, flatpak_id, flatpak_exec, save_dir_template FROM standalone_emulators WHERE console_key = ? ORDER BY label",
                (console_key,)
            ).fetchall()
            standalones = []
            for sr in standalone_rows:
                standalones.append({
                    "id": sr["id"],
                    "label": sr["label"],
                    "native_bins": sr["native_bins"].split(";") if sr["native_bins"] else [],
                    "flatpak_id": sr["flatpak_id"],
                    "flatpak_exec": sr["flatpak_exec"],
                    "save_dir_template": sr["save_dir_template"],
                })

            result.append({
                "key": console_key,
                "label": row["label"],
                "abbr": row["abbr"],
                "suggestions": row["suggestions"],
                "systemKeys": system_keys,
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
            "SELECT id, label, native_bins, flatpak_id, flatpak_exec, save_dir_template FROM standalone_emulators WHERE console_key = ?",
            (console_key,)
        ).fetchall()
        return [dict(r) for r in rows]
