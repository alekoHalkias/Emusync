"""GC-only Dolphin memory-card format mismatch detection in _MemcardClient
(issue #428) — a mismatch must skip the pull (no merge into the local card)
instead of silently extracting an incompatible-format card on top of it.
"""
from __future__ import annotations

import json

import pytest

from cli.run_ps2 import _MemcardClient


class _FakeSyncClient:
    def __init__(self, meta: dict | None, server_hash: str = "server-hash"):
        self._meta = meta
        self._server_hash = server_hash
        self.pulled = False
        self.pushed_format = None

    def get_console_memcard_meta(self, _key: str):
        return self._meta

    def pull_console_memcard(self, _key: str, _path: str):
        self.pulled = True
        return True, self._server_hash

    def push_console_memcard(self, _key: str, _path: str, card_format: str = "") -> str:
        self.pushed_format = card_format
        return "local-hash"


@pytest.fixture
def cfg(tmp_path):
    from types import SimpleNamespace
    return SimpleNamespace(data_dir=str(tmp_path))


def test_pull_skips_when_gc_formats_differ(monkeypatch, cfg):
    monkeypatch.setattr("cli.run_ps2._dolphin_card_format", lambda path: "GCIFolder")
    fake = _FakeSyncClient({"hash": "h", "card_format": "MemoryCard"})
    mc = _MemcardClient(fake, "GC", cfg)
    mc.get_save_meta("GC")

    pulled, server_hash = mc.pull_save("GC", "/fake/GC")

    assert (pulled, server_hash) == (False, None)
    assert not fake.pulled


def test_pull_skips_and_logs_mismatch_file(monkeypatch, cfg, tmp_path):
    monkeypatch.setattr("cli.run_ps2._dolphin_card_format", lambda path: "GCIFolder")
    fake = _FakeSyncClient({"hash": "h", "card_format": "MemoryCard"})
    mc = _MemcardClient(fake, "GC", cfg)
    mc.get_save_meta("GC")

    mc.pull_save("GC", "/fake/GC")

    log_path = tmp_path / "card_format_mismatch.json"
    assert log_path.exists()
    entry = json.loads(log_path.read_text())
    assert entry["local_format"] == "GCIFolder"
    assert entry["remote_format"] == "MemoryCard"


def test_pull_proceeds_when_gc_formats_match(monkeypatch, cfg):
    monkeypatch.setattr("cli.run_ps2._dolphin_card_format", lambda path: "GCIFolder")
    fake = _FakeSyncClient({"hash": "h", "card_format": "GCIFolder"})
    mc = _MemcardClient(fake, "GC", cfg)
    mc.get_save_meta("GC")

    pulled, server_hash = mc.pull_save("GC", "/fake/GC")

    assert pulled is True
    assert fake.pulled


def test_pull_proceeds_when_local_format_unknown(monkeypatch, cfg):
    """An unreadable Dolphin.ini must not block sync — only a confident,
    known mismatch does."""
    monkeypatch.setattr("cli.run_ps2._dolphin_card_format", lambda path: "unknown")
    fake = _FakeSyncClient({"hash": "h", "card_format": "MemoryCard"})
    mc = _MemcardClient(fake, "GC", cfg)
    mc.get_save_meta("GC")

    pulled, _ = mc.pull_save("GC", "/fake/GC")

    assert pulled is True
    assert fake.pulled


def test_pull_proceeds_when_server_has_no_format_tag(monkeypatch, cfg):
    """Older server data (pre-#428) has no card_format recorded — treat as
    unknown, not a mismatch."""
    monkeypatch.setattr("cli.run_ps2._dolphin_card_format", lambda path: "GCIFolder")
    fake = _FakeSyncClient({"hash": "h", "card_format": ""})
    mc = _MemcardClient(fake, "GC", cfg)
    mc.get_save_meta("GC")

    pulled, _ = mc.pull_save("GC", "/fake/GC")

    assert pulled is True
    assert fake.pulled


def test_push_sends_local_format_for_gc(monkeypatch, cfg):
    monkeypatch.setattr("cli.run_ps2._dolphin_card_format", lambda path: "GCIFolder")
    fake = _FakeSyncClient(None)
    mc = _MemcardClient(fake, "GC", cfg)

    mc.push_save("GC", "/fake/GC")

    assert fake.pushed_format == "GCIFolder"


def test_push_sends_no_format_for_non_gc_consoles(cfg):
    """PS2/DC/PSP/3DS don't have a format axis — always push ''."""
    fake = _FakeSyncClient(None)
    mc = _MemcardClient(fake, "PS2", cfg)

    mc.push_save("PS2", "/fake/memcards")

    assert fake.pushed_format == ""


def test_pull_not_gated_for_non_gc_consoles(cfg):
    """The format check is GC-specific; PS2 etc. pull unconditionally."""
    fake = _FakeSyncClient({"hash": "h"})
    mc = _MemcardClient(fake, "PS2", cfg)
    mc.get_save_meta("PS2")

    pulled, _ = mc.pull_save("PS2", "/fake/memcards")

    assert pulled is True
    assert fake.pulled
