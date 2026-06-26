"""Helpers for the network-drive ROM source feature (issue #255).

Pure, dependency-free path utilities plus a bounded mount-liveness probe. These
are shared by ``cli/run.py`` (launch resolution), ``cli/transfer.py`` (push/pull
guards), ``cli/watch.py`` (save watcher), and the ``emusync rom`` commands.

Path model: ROMs on a network share are stored as a POSIX-normalized
``rom_rel_path`` relative to a per-console, per-device ``network_rom_folder``.
Each device joins the rel-path against *its own* mount root, so the same library
works across devices that mount the NAS at different paths — and on Windows where
the root may be a UNC path (``\\\\NAS\\roms``) or a mapped drive (``Z:\\``).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import threading
from typing import Optional


def normalize_rel_path(path: str) -> str:
    """Normalize a relative ROM path for storage: forward slashes, no edge slashes.

    Accepts either separator (so a Windows-derived ``GBA\\game.gba`` and a POSIX
    ``GBA/game.gba`` store identically) and collapses redundant separators.
    """
    if not path:
        return ""
    parts = [p for p in path.replace("\\", "/").split("/") if p not in ("", ".")]
    return "/".join(parts)


def is_safe_rel_path(rel: str) -> bool:
    """True if *rel* is a safe relative path with no traversal or absolute escape.

    Rejects ``..`` components, absolute POSIX paths (leading ``/``), and Windows
    absolute forms (leading ``\\`` or a drive letter like ``Z:``). Used at the
    receiving end before joining a broadcast rel-path to a local mount root.
    """
    if not rel:
        return False
    raw = rel.replace("\\", "/")
    if raw.startswith("/"):
        return False
    # Drive-letter (``Z:``) or any colon signals an absolute/qualified Windows path.
    if ":" in raw:
        return False
    return all(part not in ("..",) for part in raw.split("/"))


def sanitize_rel_path(rel: str) -> str:
    """Return the normalized rel-path, or raise ValueError if it isn't safe."""
    if not is_safe_rel_path(rel):
        raise ValueError(f"unsafe ROM relative path: {rel!r}")
    return normalize_rel_path(rel)


def compute_rel_path(network_root: str, rom_path: str) -> Optional[str]:
    """Derive a POSIX rel-path for *rom_path* under *network_root*.

    Returns ``None`` if the ROM is not actually under the root (so callers can
    fall back to a plain local import rather than store a bogus rel-path).
    Computed with ``os.path`` on the device's own OS, so it's correct for both
    POSIX mounts and Windows UNC/drive roots.
    """
    if not network_root or not rom_path:
        return None
    try:
        root = os.path.normpath(network_root)
        target = os.path.normpath(rom_path)
        rel = os.path.relpath(target, root)
    except (ValueError, OSError):
        # relpath raises ValueError across drives on Windows.
        return None
    norm = normalize_rel_path(rel)
    if not norm or norm.startswith("..") or not is_safe_rel_path(norm):
        return None
    return norm


def join_network(network_root: str, rel: str) -> str:
    """Join a stored POSIX rel-path onto a (possibly Windows) mount root."""
    safe = sanitize_rel_path(rel)
    return os.path.join(network_root, *safe.split("/"))


def _probe_isfile(path: str, result: list) -> None:
    try:
        result.append(os.path.isfile(path))
    except OSError:
        result.append(False)


def path_is_reachable(path: str, timeout: float = 2.0) -> bool:
    """True iff *path* is an existing file reachable within *timeout* seconds.

    The check runs in a daemon thread so a hung/dead network mount — where
    ``os.path.isfile`` can block on the OS uninterruptibly — never freezes the
    caller (launch, the save watcher, push/pull). A timeout is treated as
    "unreachable", letting callers fall back to a local copy or skip the path.
    """
    if not path:
        return False
    result: list = []
    t = threading.Thread(target=_probe_isfile, args=(path, result), daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return False  # mount is hung — abandon the probe thread, treat as offline
    return bool(result and result[0])


def resolve_rom_path(
    rom_source: str,
    rom_path: str,
    local_rom_path: str,
    timeout: float = 2.0,
) -> Optional[str]:
    """Resolve the ROM path to actually launch from, or ``None`` if unavailable.

    - ``local`` source: the configured ``rom_path`` (legacy behaviour, unchanged).
    - ``network`` source: prefer the network ``rom_path`` when the mount is live;
      otherwise fall back to a localized copy; otherwise ``None`` (caller refuses).

    ``rom_path`` for a network game is the denormalized resolution of this
    device's ``network_rom_folder + rom_rel_path``, so no console lookup is needed
    here.
    """
    if rom_source != "network":
        return rom_path or None
    if rom_path and path_is_reachable(rom_path, timeout):
        return rom_path
    if local_rom_path and os.path.isfile(local_rom_path):
        return local_rom_path
    return None


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    """Stream-hash a file (1 MiB chunks) so a multi-GB ROM isn't read into memory."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


class LocalizeError(Exception):
    """Raised by :func:`localize_rom` when a copy cannot be completed."""


def localize_rom(network_path: str, local_path: str, *, verify: bool = True) -> str:
    """Copy a network ROM to *local_path* atomically; return the master's sha256.

    Safety: checks free space first, copies to a ``.part`` temp then ``os.replace``
    so a crash never leaves a half-written ROM in place, and re-hashes the
    destination to confirm an intact copy. Never touches *network_path* (the
    master). Raises :class:`LocalizeError` on any failure, leaving no partial file.
    """
    if not network_path or not path_is_reachable(network_path):
        raise LocalizeError(f"network ROM not reachable: {network_path}")
    if os.path.abspath(network_path) == os.path.abspath(local_path):
        raise LocalizeError("local destination equals the network master")

    parent = os.path.dirname(local_path) or "."
    os.makedirs(parent, exist_ok=True)

    size = os.path.getsize(network_path)
    free = shutil.disk_usage(parent).free
    if free < size:
        raise LocalizeError(
            f"not enough free space: need {size} bytes, {free} available at {parent}"
        )

    tmp = local_path + ".part"
    try:
        shutil.copyfile(network_path, tmp)
        master_hash = sha256_file(network_path)
        if verify and sha256_file(tmp) != master_hash:
            raise LocalizeError("copy verification failed (hash mismatch)")
        os.replace(tmp, local_path)
    except OSError as exc:
        raise LocalizeError(str(exc)) from exc
    finally:
        if os.path.exists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass
    return master_hash


def delocalize_rom(local_path: str, network_path: str) -> bool:
    """Delete a localized copy, refusing to touch the network master.

    Returns True if a file was removed. Guard: never unlinks *local_path* when it
    resolves to the same file as *network_path* (the canonical NAS copy).
    """
    if not local_path or not os.path.isfile(local_path):
        return False
    if network_path and os.path.abspath(local_path) == os.path.abspath(network_path):
        raise LocalizeError("refusing to delete the network master")
    os.unlink(local_path)
    return True
