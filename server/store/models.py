"""Row-shaped dataclasses returned by the Store methods."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Device:
    id: str
    name: str
    last_ip: Optional[str] = None
    last_seen_at: Optional[str] = None


@dataclass
class Game:
    slug: str
    name: str
    console: str = ""


@dataclass
class Console:
    id: str
    device_id: str
    console_name: str
    shortform_name: str
    device_game_folder: str = ""
    device_save_folder: str = ""
    device_state_folder: str = ""
    device_emulator: str = ""


@dataclass
class GameDevice:
    game_slug: str
    device_id: str
    rom_path: str
    save_path: str
    launch_command: str
    state_path: str = ""
    rom_folder_path: str = ""


@dataclass
class SaveMeta:
    game_slug: str
    device_id: str
    hash: str
    pushed_at: str
    size: Optional[int] = None  # bytes; populated by metadata queries, not by push


@dataclass
class Lock:
    game_slug: str
    device_id: str
    acquired_at: str


@dataclass
class RomTransfer:
    id: str
    slug: str
    from_device_id: str
    to_device_id: str
    destination_path: str
    staged_file: str
    status: str
    queued_at: str
    completed_at: Optional[str] = None
    sha256: Optional[str] = None  # hash of the staged ROM, for download integrity checks


@dataclass
class RomPullRequest:
    id: str
    slug: str
    from_device_id: str
    to_device_id: str
    destination_path: str
    status: str
    requested_at: str
    fulfilled_at: Optional[str] = None
