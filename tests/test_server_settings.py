"""Generic server-wide settings key-value store (issue #322)."""
from __future__ import annotations

import tempfile

from server.store import Store


def test_get_setting_missing_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        assert store.get_setting("steamgriddb_api_key") is None


def test_set_then_get_setting_roundtrips():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        store.set_setting("steamgriddb_api_key", "abc123")
        assert store.get_setting("steamgriddb_api_key") == "abc123"


def test_set_setting_overwrites_existing_value():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(tmp)
        store.set_setting("steamgriddb_api_key", "first")
        store.set_setting("steamgriddb_api_key", "second")
        assert store.get_setting("steamgriddb_api_key") == "second"
