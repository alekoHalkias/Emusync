"""StoreBase: owns the SQLite connection and runs schema init / migrations.

The concrete `Store` (in __init__.py) composes this with the per-domain mixins,
all of which operate on `self._conn`.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from server.store.connection import _LockedConnection
from server.store.schema import _SCHEMA, _SCHEMA_VERSION, _migrate


class StoreBase:
    _conn: _LockedConnection
    _lock: threading.RLock

    def __init__(self, data_dir: str) -> None:
        db_path = Path(data_dir) / "emusync.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        is_fresh = not db_path.exists()
        self._lock = threading.RLock()
        raw_conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30.0)
        raw_conn.row_factory = sqlite3.Row
        self._conn = _LockedConnection(raw_conn, self._lock)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.commit()
        if is_fresh:
            # Split schema statements and execute individually (executescript() incompatible with WAL)
            for statement in _SCHEMA.split(";"):
                statement = statement.strip()
                if statement:
                    self._conn.execute(statement)
                    self._conn.commit()
        db_version: int = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if db_version < _SCHEMA_VERSION:
            _migrate(raw_conn, db_version)
        self._conn.commit()
