"""Read-only console / system / emulator definition endpoints (drive the
GUI import wizard)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ._core import _auth, _get_store

router = APIRouter()


@router.get("/console-defs")
def get_console_defs(device_id: str = Depends(_auth)) -> list[dict]:
    """Return all console definitions."""
    return _get_store().get_console_defs()


@router.get("/system-defs")
def get_system_defs(device_id: str = Depends(_auth)) -> dict:
    """Return all system definitions (keyed by ROM extension)."""
    return _get_store().get_system_defs()


@router.get("/console-folder-names")
def get_console_folder_names(device_id: str = Depends(_auth)) -> dict:
    """Return console key → folder name patterns."""
    return _get_store().get_console_folder_names()


@router.get("/standalones/{console_key}")
def get_standalones(console_key: str, device_id: str = Depends(_auth)) -> list[dict]:
    """Return standalone emulators for a console."""
    return _get_store().get_standalones_for_console(console_key)
