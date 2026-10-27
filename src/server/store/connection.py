"""Per-thread SQLite connections.

A single sqlite3.Connection cannot be shared across threads for concurrent
cursor use. The store is hit from many threads — uvicorn runs endpoints in a
worker-thread pool and the presence monitor runs in its own daemon thread — and
interleaved execute()/fetch()/commit() from different threads on one connection
corrupts statement state, raising `sqlite3.InterfaceError: bad parameter or
other API misuse`, after which the connection is unusable.

So each thread gets its own connection, created lazily and cached in
`threading.local`. WAL mode (enabled per connection) gives concurrent readers
plus a single writer; the busy timeout handles writer contention. Because
`PRAGMA foreign_keys` is per-connection, it is set on every connection so cascade
deletes are enforced no matter which thread issues them.
"""
from __future__ import annotations

import sqlite3
import threading
from typing import Any

_BUSY_TIMEOUT = 30.0


class _ThreadLocalConnection:
    """Dispatches execute()/commit()/attribute access to a per-thread connection."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._local = threading.local()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self._db_path, check_same_thread=False, timeout=_BUSY_TIMEOUT)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        return self._conn().execute(*args, **kwargs)

    def commit(self) -> None:
        return self._conn().commit()

    def __getattr__(self, name: str) -> Any:
        # _db_path / _local are real instance attributes, so they resolve before
        # this runs; everything else is delegated to this thread's connection.
        return getattr(self._conn(), name)
