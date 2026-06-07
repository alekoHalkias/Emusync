"""StoreBase: owns the SQLite connection and runs schema init / migrations.

The concrete `Store` (in __init__.py) composes this with the per-domain mixins,
all of which operate on `self._conn`.
"""
from __future__ import annotations

from pathlib import Path

from server.store.connection import _ThreadLocalConnection
from server.store.schema import _SCHEMA, _SCHEMA_VERSION, _migrate


class StoreBase:
    _conn: _ThreadLocalConnection

    def __init__(self, data_dir: str) -> None:
        db_path = Path(data_dir) / "emusync.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        is_fresh = not db_path.exists()
        # Per-thread connections; PRAGMAs (WAL, synchronous, foreign_keys) are
        # applied to each connection as it is created (see connection.py).
        self._conn = _ThreadLocalConnection(str(db_path))
        if is_fresh:
            # Split schema statements and execute individually (executescript() incompatible with WAL)
            for statement in _SCHEMA.split(";"):
                statement = statement.strip()
                if statement:
                    self._conn.execute(statement)
            self._conn.commit()
        db_version: int = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if db_version < _SCHEMA_VERSION:
            _migrate(self._conn, db_version)
        self._conn.commit()
