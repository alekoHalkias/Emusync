"""Thread-safe SQLite connection wrapper.

FastAPI runs synchronous endpoints (and the presence-monitor thread) in
concurrent worker threads, so every database operation is serialized through a
single lock held for the *duration* of each call.
"""
from __future__ import annotations

import sqlite3
import threading
from typing import Any


class _LockedConnection:
    """Wraps sqlite3.Connection and serializes all access via a lock."""

    def __init__(self, conn: sqlite3.Connection, lock: threading.RLock) -> None:
        self._conn = conn
        self._lock = lock

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return self._conn.execute(*args, **kwargs)

    def commit(self) -> None:
        with self._lock:
            return self._conn.commit()

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._conn, name)
        if callable(attr):
            lock = self._lock
            def _locked(*args: Any, **kwargs: Any) -> Any:
                with lock:
                    return attr(*args, **kwargs)
            return _locked
        with self._lock:
            return attr
