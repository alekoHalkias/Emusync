"""State-folder pull backups (#204) and tar-extraction hardening (#202)."""
from __future__ import annotations

import io
import tarfile

import pytest


def _make_state_archive(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, payload in files.items():
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


# ── state pull keeps backups (#204) ────────────────────────────────────────────

def test_extract_state_folder_retains_backup_of_overwritten_files(tmp_path):
    """A state pull that overwrites a slot must leave a recoverable .bak."""
    from server.sync_client import _extract_state_folder

    folder = tmp_path / "states" / "Metroid"
    folder.mkdir(parents=True)
    (folder / "game.state").write_bytes(b"OLD-slot0")

    _extract_state_folder(_make_state_archive(
        {"game.state": b"NEW-slot0", "game.state1": b"NEW-slot1"}), folder)

    assert (folder / "game.state").read_bytes() == b"NEW-slot0"
    assert (folder / "game.state1").read_bytes() == b"NEW-slot1"
    # The overwritten file is still recoverable.
    assert (folder / "game.state.bak").read_bytes() == b"OLD-slot0"


def test_extract_state_folder_keeps_single_backup_generation(tmp_path):
    """A second pull overwrites the prior .bak rather than erroring (Windows-safe)."""
    from server.sync_client import _extract_state_folder

    folder = tmp_path / "states" / "Metroid"
    folder.mkdir(parents=True)
    (folder / "game.state").write_bytes(b"v1")

    _extract_state_folder(_make_state_archive({"game.state": b"v2"}), folder)
    _extract_state_folder(_make_state_archive({"game.state": b"v3"}), folder)

    assert (folder / "game.state").read_bytes() == b"v3"
    assert (folder / "game.state.bak").read_bytes() == b"v2"  # one generation


def test_extract_state_folder_legacy_raw_blob(tmp_path):
    """A non-tar (legacy) blob is written as <FolderName>.state, not exploded."""
    from server.sync_client import _extract_state_folder

    folder = tmp_path / "states" / "Zelda"
    folder.mkdir(parents=True)
    _extract_state_folder(b"not-a-tar-archive", folder)
    assert (folder / "Zelda.state").read_bytes() == b"not-a-tar-archive"


# ── tar extraction hardening (#202) ────────────────────────────────────────────

def test_safe_extract_tar_rejects_path_traversal(tmp_path):
    """A state archive with a ../ member must be rejected, not written outside."""
    from server.sync_client import _safe_extract_tar

    dest = tmp_path / "states"
    dest.mkdir()

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        payload = b"pwned"
        info = tarfile.TarInfo(name="../escape.state")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    buf.seek(0)

    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        with pytest.raises(tarfile.TarError):
            _safe_extract_tar(tar, dest)

    assert not (tmp_path / "escape.state").exists()


def test_safe_extract_tar_allows_normal_members(tmp_path):
    """A well-formed archive extracts normally into the destination folder."""
    from server.sync_client import _safe_extract_tar

    dest = tmp_path / "states"
    dest.mkdir()

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, payload in (("game.state", b"slot0"), ("game.state1", b"slot1")):
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            tar.addfile(info, io.BytesIO(payload))
    buf.seek(0)

    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        _safe_extract_tar(tar, dest)

    assert (dest / "game.state").read_bytes() == b"slot0"
    assert (dest / "game.state1").read_bytes() == b"slot1"
