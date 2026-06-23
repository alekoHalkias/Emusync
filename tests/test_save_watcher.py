"""Background save/state watcher (issue #242).

Exercises SaveWatcher's per-target decision logic with a fake client (not a DB
mock — the no-mocks rule is about SQLite; here we stand in for the HTTP client).
"""
from __future__ import annotations

import os
from pathlib import Path

from cli.watch import SaveWatcher, _state_token


class _FakeClient:
    def __init__(self, save_meta=None, lock=None):
        self._save_meta = save_meta  # dict {hash, size} or None
        self._lock = lock or {"locked": False}
        self.pushed_saves: list[str] = []
        self.pushed_states: list[str] = []

    def get_lock(self, slug):
        return self._lock

    def get_save_meta(self, slug):
        return self._save_meta

    def push_save(self, slug, path):
        self.pushed_saves.append(path)
        return "pushed-hash"

    def push_state(self, slug, path):
        self.pushed_states.append(path)
        return "pushed-hash"


def _write(path: Path, data: bytes, age_seconds: float = 0.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if age_seconds:
        past = path.stat().st_mtime - age_seconds
        os.utime(path, (past, past))


# ── settle gate ────────────────────────────────────────────────────────────────

def test_unsettled_save_is_not_pushed(tmp_path):
    save = tmp_path / "g.srm"
    _write(save, b"x" * 1000)  # mtime == now → not settled
    client = _FakeClient()
    w = SaveWatcher(client, "dev-1", settle_seconds=5)
    assert w.check_save("g", "Game", str(save)) is False
    assert client.pushed_saves == []


def test_settled_changed_save_is_pushed(tmp_path):
    save = tmp_path / "g.srm"
    _write(save, b"x" * 1000, age_seconds=30)  # settled
    client = _FakeClient(save_meta=None)  # server has no save yet
    w = SaveWatcher(client, "dev-1", settle_seconds=5)
    assert w.check_save("g", "Game", str(save)) is True
    assert client.pushed_saves == [str(save)]


# ── dedupe ──────────────────────────────────────────────────────────────────────

def test_unchanged_save_not_pushed_twice(tmp_path):
    save = tmp_path / "g.srm"
    _write(save, b"x" * 1000, age_seconds=30)
    client = _FakeClient(save_meta=None)
    w = SaveWatcher(client, "dev-1", settle_seconds=5)
    assert w.check_save("g", "Game", str(save)) is True
    # Second pass: same content → no second push.
    assert w.check_save("g", "Game", str(save)) is False
    assert len(client.pushed_saves) == 1


def test_save_already_current_on_server_is_not_pushed(tmp_path):
    save = tmp_path / "g.srm"
    _write(save, b"abc" * 100, age_seconds=30)
    import hashlib
    h = hashlib.sha256((b"abc" * 100)).hexdigest()
    client = _FakeClient(save_meta={"hash": h, "size": 300})
    w = SaveWatcher(client, "dev-1", settle_seconds=5)
    assert w.check_save("g", "Game", str(save)) is False
    assert client.pushed_saves == []


# ── lock + safety gates ──────────────────────────────────────────────────────────

def test_save_locked_by_other_device_is_skipped(tmp_path):
    save = tmp_path / "g.srm"
    _write(save, b"x" * 1000, age_seconds=30)
    client = _FakeClient(save_meta=None, lock={"locked": True, "device_id": "other"})
    w = SaveWatcher(client, "dev-1", settle_seconds=5)
    assert w.check_save("g", "Game", str(save)) is False
    assert client.pushed_saves == []


def test_save_locked_by_self_still_pushes(tmp_path):
    save = tmp_path / "g.srm"
    _write(save, b"x" * 1000, age_seconds=30)
    client = _FakeClient(save_meta=None, lock={"locked": True, "device_id": "dev-1"})
    w = SaveWatcher(client, "dev-1", settle_seconds=5)
    assert w.check_save("g", "Game", str(save)) is True
    assert client.pushed_saves == [str(save)]


def test_truncated_save_is_refused(tmp_path):
    save = tmp_path / "g.srm"
    _write(save, b"x" * 100, age_seconds=30)  # shrunk far below server's 32768
    client = _FakeClient(save_meta={"hash": "old", "size": 32768})
    w = SaveWatcher(client, "dev-1", settle_seconds=5)
    assert w.check_save("g", "Game", str(save)) is False
    assert client.pushed_saves == []


def test_zero_byte_save_is_refused(tmp_path):
    save = tmp_path / "g.srm"
    _write(save, b"", age_seconds=30)
    client = _FakeClient(save_meta={"hash": "old", "size": 32768})
    w = SaveWatcher(client, "dev-1", settle_seconds=5)
    assert w.check_save("g", "Game", str(save)) is False
    assert client.pushed_saves == []


def test_missing_save_file_is_noop(tmp_path):
    client = _FakeClient()
    w = SaveWatcher(client, "dev-1", settle_seconds=5)
    assert w.check_save("g", "Game", str(tmp_path / "nope.srm")) is False


# ── states ───────────────────────────────────────────────────────────────────────

def test_state_folder_pushed_when_changed_and_settled(tmp_path):
    folder = tmp_path / "states" / "Game"
    _write(folder / "Game.state", b"slot0", age_seconds=30)
    _write(folder / "Game.state1", b"slot1", age_seconds=30)
    client = _FakeClient()
    w = SaveWatcher(client, "dev-1", settle_seconds=5)
    assert w.check_state("g", "Game", str(folder)) is True
    assert client.pushed_states == [str(folder)]
    # Unchanged on the next pass → no re-push.
    assert w.check_state("g", "Game", str(folder)) is False
    assert len(client.pushed_states) == 1


def test_state_token_ignores_bak_files(tmp_path):
    folder = tmp_path / "states" / "Game"
    _write(folder / "Game.state", b"slot0", age_seconds=30)
    token_before, _ = _state_token(folder)
    _write(folder / "Game.state.bak", b"old-backup", age_seconds=30)
    token_after, _ = _state_token(folder)
    assert token_before == token_after  # .bak doesn't change the token


def test_state_locked_by_other_is_skipped(tmp_path):
    folder = tmp_path / "states" / "Game"
    _write(folder / "Game.state", b"slot0", age_seconds=30)
    client = _FakeClient(lock={"locked": True, "device_id": "other"})
    w = SaveWatcher(client, "dev-1", settle_seconds=5)
    assert w.check_state("g", "Game", str(folder)) is False
    assert client.pushed_states == []
