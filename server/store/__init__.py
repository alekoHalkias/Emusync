"""SQLite persistence layer for EmuSync.

`Store` is composed from one mixin per table-group (see the sibling modules);
each mixin operates on the shared lock-wrapped connection set up by `StoreBase`.
The public surface — `Store`, `LOCK_TTL_HOURS`, `upsert_console_for_game`, and the
row dataclasses — is re-exported here so callers keep importing from `server.store`.
"""
from __future__ import annotations

from server.store._base import StoreBase
from server.store.blobs import SaveStateMixin
from server.store.conflicts import ConflictMixin
from server.store.console_defs import ConsoleDefMixin
from server.store.consoles import ConsoleMixin, saves_path_to_states, upsert_console_for_game
from server.store.devices import DeviceMixin
from server.store.events import EventMixin
from server.store.games import GameDeviceMixin, GameMixin
from server.store.locks import LOCK_TTL_HOURS, LockMixin
from server.store.models import (
    Console,
    Device,
    Game,
    GameDevice,
    Lock,
    RomPullRequest,
    RomTransfer,
    SaveMeta,
)
from server.store.settings import SettingsMixin
from server.store.transfers import TransferMixin


class Store(
    DeviceMixin,
    ConsoleMixin,
    GameMixin,
    GameDeviceMixin,
    SaveStateMixin,
    LockMixin,
    EventMixin,
    TransferMixin,
    ConsoleDefMixin,
    ConflictMixin,
    SettingsMixin,
    StoreBase,
):
    """SQLite-backed store. CRUD is split across the mixins above; connection and
    schema/migration setup live in StoreBase."""


__all__ = [
    "Store",
    "LOCK_TTL_HOURS",
    "upsert_console_for_game",
    "saves_path_to_states",
    "Device",
    "Game",
    "Console",
    "GameDevice",
    "SaveMeta",
    "Lock",
    "RomTransfer",
    "RomPullRequest",
]
