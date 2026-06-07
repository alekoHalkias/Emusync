"""Per-device console configuration CRUD, plus the shared upsert helper."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from server.store.models import Console

if TYPE_CHECKING:
    from server.store import Store


class ConsoleMixin:
    """Operates on `self._conn`; mixed into Store."""

    def set_console(self, console: Console) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO consoles
               (id, device_id, console_name, shortform_name, device_game_folder, device_save_folder, device_state_folder, device_emulator)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (console.id, console.device_id, console.console_name, console.shortform_name,
             console.device_game_folder, console.device_save_folder, console.device_state_folder, console.device_emulator),
        )
        self._conn.commit()

    def get_console(self, device_id: str, console_name: str) -> Optional[Console]:
        row = self._conn.execute(
            """SELECT id, device_id, console_name, shortform_name, device_game_folder, device_save_folder, device_state_folder, device_emulator
               FROM consoles WHERE device_id = ? AND console_name = ?""",
            (device_id, console_name),
        ).fetchone()
        return Console(**dict(row)) if row else None

    def list_consoles(self, device_id: str) -> list[Console]:
        rows = self._conn.execute(
            """SELECT id, device_id, console_name, shortform_name, device_game_folder, device_save_folder, device_state_folder, device_emulator
               FROM consoles WHERE device_id = ?""",
            (device_id,),
        ).fetchall()
        return [Console(**dict(r)) for r in rows]

    def remove_console(self, console_id: str) -> None:
        self._conn.execute("DELETE FROM consoles WHERE id = ?", (console_id,))
        self._conn.commit()


def upsert_console_for_game(
    store: "Store",
    device_id: str,
    console_name: str,
    rom_path: str,
    save_path: str,
    rom_folder_path: str,
) -> None:
    """Infer console folders/emulator from game paths and create-or-update the Console row.

    Called identically from the API (set_game_device) and the CLI (game add) so the
    logic lives in one place.
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
        state_folder = save_folder.replace("saves", "states")

    existing_consoles = store.list_consoles(device_id)
    existing = next(
        (c for c in existing_consoles if c.console_name == console_name and c.device_game_folder == game_folder),
        None,
    )

    if existing:
        existing.device_save_folder = save_folder
        existing.device_state_folder = state_folder
        existing.device_emulator = emulator
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
        ))
