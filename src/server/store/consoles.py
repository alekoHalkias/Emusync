"""Per-device console configuration CRUD, plus the shared upsert helper."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from server.store.models import Console

if TYPE_CHECKING:
    from server.store import Store


def saves_path_to_states(path: str) -> str:
    """Swap the RetroArch ``saves`` path segment for ``states``.

    Only whole path components named exactly ``saves`` are replaced, so a path
    like ``/home/saves_backup/SNES`` is left untouched. RetroArch stores these
    paths with forward slashes, so we split on ``/``. Replaces the old blind
    ``.replace("saves", "states")`` calls that were duplicated (and disagreed)
    between the store and the CLI.
    """
    if not path:
        return path
    return "/".join("states" if seg == "saves" else seg for seg in path.split("/"))


def _console_from_row(row) -> Console:
    d = dict(row)
    d["device_extra_folders"] = json.loads(d["device_extra_folders"] or "[]")
    return Console(**d)


class ConsoleMixin:
    """Operates on `self._conn`; mixed into Store."""

    def set_console(self, console: Console) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO consoles
               (id, device_id, console_name, shortform_name, device_game_folder, device_save_folder,
                device_state_folder, device_emulator, device_network_folder, device_local_folder,
                device_extra_folders, network_share_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (console.id, console.device_id, console.console_name, console.shortform_name,
             console.device_game_folder, console.device_save_folder, console.device_state_folder,
             console.device_emulator, console.device_network_folder, console.device_local_folder,
             json.dumps(console.device_extra_folders), console.network_share_id),
        )
        self._conn.commit()

    def get_console(self, device_id: str, console_name: str) -> Optional[Console]:
        row = self._conn.execute(
            """SELECT id, device_id, console_name, shortform_name, device_game_folder, device_save_folder,
                      device_state_folder, device_emulator, device_network_folder, device_local_folder,
                      device_extra_folders, network_share_id
               FROM consoles WHERE device_id = ? AND console_name = ?""",
            (device_id, console_name),
        ).fetchone()
        return _console_from_row(row) if row else None

    def list_consoles(self, device_id: str) -> list[Console]:
        rows = self._conn.execute(
            """SELECT id, device_id, console_name, shortform_name, device_game_folder, device_save_folder,
                      device_state_folder, device_emulator, device_network_folder, device_local_folder,
                      device_extra_folders, network_share_id
               FROM consoles WHERE device_id = ?""",
            (device_id,),
        ).fetchall()
        return [_console_from_row(r) for r in rows]

    def remove_console(self, console_id: str) -> None:
        self._conn.execute("DELETE FROM consoles WHERE id = ?", (console_id,))
        self._conn.commit()


def _within(path: str, root: str) -> bool:
    """True when ``path`` is ``root`` or sits inside it (forward-slash compare)."""
    if not root:
        return False
    p, r = path.replace("\\", "/").rstrip("/"), root.replace("\\", "/").rstrip("/")
    return p == r or p.startswith(r + "/")


def upsert_console_for_game(
    store: "Store",
    device_id: str,
    console_name: str,
    rom_path: str,
    save_path: str,
    rom_folder_path: str,
    network_folder: str = "",
    local_folder: str = "",
) -> None:
    """Infer console folders/emulator from game paths and create-or-update the Console row.

    Called identically from the API (set_game_device) and the CLI (game add) so the
    logic lives in one place. ``network_folder``/``local_folder`` (issue #255) are
    the per-console NAS mount + local-copy destination for a network import; they
    are persisted when provided and preserved (never blanked) when empty. A game
    folder the console does not cover yet is recorded in ``device_extra_folders`` (#629).
    """
    emulator = ""
    game_folder = ""
    save_folder = ""
    state_folder = ""

    if save_path:
        save_dir = str(Path(save_path).parent)
        save_folder = save_dir
        emulator = Path(save_dir).name

    if rom_folder_path:
        game_folder = rom_folder_path
    elif rom_path:
        game_folder = str(Path(rom_path).parent.parent)

    if save_folder:
        state_folder = saves_path_to_states(save_folder)

    rows = [c for c in store.list_consoles(device_id) if c.console_name == console_name]
    # One console reads once (#629): a game folder the console doesn't know yet joins
    # device_extra_folders instead of spawning a second row. Legacy multi-row consoles
    # keep working: an exact folder match picks that row, else the first row.
    existing = next((c for c in rows if c.device_game_folder == game_folder), None)
    if not existing and rows:
        existing = rows[0]
        if not existing.device_game_folder:
            existing.device_game_folder = game_folder
        elif game_folder:
            known = [r.device_game_folder for r in rows] + existing.device_extra_folders
            # Network-sourced games must not turn the NAS mount into a local extra:
            # the GUI's sourceFor would then classify them as local.
            known.append(network_folder or existing.device_network_folder)
            if not any(_within(game_folder, k) for k in known):
                existing.device_extra_folders.append(game_folder)

    if existing:
        # Fill-only-blank: a folder already on the row (learned earlier or hand-edited
        # via PUT /devices/.../consoles/{id}, #539) is never rewritten from one game's paths.
        existing.device_save_folder = existing.device_save_folder or save_folder
        existing.device_state_folder = existing.device_state_folder or state_folder
        existing.device_emulator = existing.device_emulator or emulator
        # Only overwrite the network/local folders when new values are supplied,
        # so a later plain save/state update doesn't blank them (issue #255).
        if network_folder:
            existing.device_network_folder = network_folder
        if local_folder:
            existing.device_local_folder = local_folder
        store.set_console(existing)
    else:
        store.set_console(Console(
            id=str(uuid.uuid4()),
            device_id=device_id,
            console_name=console_name,
            shortform_name=console_name.lower()[:4],
            device_game_folder=game_folder,
            device_save_folder=save_folder,
            device_state_folder=state_folder,
            device_emulator=emulator,
            device_network_folder=network_folder,
            device_local_folder=local_folder,
        ))
