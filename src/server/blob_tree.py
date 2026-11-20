"""Manifest blob format (#739): the one wire and storage format for saves,
states, memory cards, Switch mods and rom-folder transfers.

A blob is the #478 envelope (``ES1\\0`` + format byte 3) followed by an
uncompressed tar. The tar's first member is ``.emusync-manifest.json``::

    {"v": 1, "kind": "file" | "dir", "files": [{"path", "size", "sha256"}, ...]}

``file`` = one entry with ``path ""`` stored as member ``.emusync-file`` (the
local filename never travels, so the same save under two names hashes alike).
``dir`` = one entry per regular file, relative POSIX paths, sorted.

Content hash (``manifest_hash``): a file's plain sha256 (unchanged from the
pre-#739 raw format, which GUI ``files:getFileHash`` relies on), or for a folder
the sha256 of the compact JSON ``[[path, size, sha256], ...]``, independent of
tar framing and mtimes. Every reader verifies each member against the manifest.

Formats 0-2 (raw, tar, tar.gz) are only read by ``legacy_to_tree`` for the
schema v38 conversion.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Callable, Iterable, Optional

_ENVELOPE_MAGIC = b"ES1\0"
_ENVELOPE_HEADER_LEN = len(_ENVELOPE_MAGIC) + 1  # magic + 1 format byte
_FMT_RAW = 0     # legacy: single file, payload is its raw bytes
_FMT_TAR = 1     # legacy: folder, payload is an uncompressed tar
_FMT_TARGZ = 2   # legacy: folder, payload is a gzip'd tar
_FMT_TREE = 3    # manifest tar (#739)

_MANIFEST = ".emusync-manifest.json"
_FILE_MEMBER = ".emusync-file"
_MAX_MANIFEST = 64 * 1024 * 1024
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_CHUNK = 1 << 20


def _pack_envelope(fmt: int, payload: bytes) -> bytes:
    return _ENVELOPE_MAGIC + bytes([fmt]) + payload


def _unpack_envelope(data: bytes) -> tuple[Optional[int], bytes]:
    """(format, payload) if *data* has the envelope header, else (None, data)."""
    if data[:4] == _ENVELOPE_MAGIC:
        return data[4], data[5:]
    return None, data


# ── tar safety (moved from sync_client, re-exported there) ─────────────────────

def _safe_extract_tar(tar: tarfile.TarFile, dest: Path) -> None:
    """Extract a tar archive, refusing any member that resolves outside *dest*.

    Guards against malicious archives using ``../`` paths, absolute paths, or
    symlink/hardlink targets that would write outside the destination folder.
    (``TarFile.extractall``'s ``filter="data"`` argument only exists on Python
    3.12+, and this project supports 3.10+.)
    """
    dest_root = dest.resolve()
    for member in tar.getmembers():
        if member.islnk() or member.issym():
            raise tarfile.TarError(f"refusing link member in archive: {member.name}")
        target = (dest_root / member.name).resolve()
        if target != dest_root and dest_root not in target.parents:
            raise tarfile.TarError(f"refusing member outside destination: {member.name}")
    if hasattr(tarfile, "data_filter"):  # 3.12+ and security backports
        tar.extractall(path=str(dest), filter="data")
        return
    # Older Pythons: reject devices/FIFOs and drop setuid/setgid/sticky bits (#699).
    for member in tar.getmembers():
        if not (member.isreg() or member.isdir()):
            raise tarfile.TarError(f"refusing special member in archive: {member.name}")
        member.mode &= 0o777
    tar.extractall(path=str(dest))


def _mk_tmp(parent: Path) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=str(parent), prefix=".emusync-"))
    os.chmod(tmp, 0o755)  # mkdtemp is 0700; the dir may become the card itself
    return tmp


def _extract_tar_to_tmp(data: bytes, mode: str, parent: Path) -> Path:
    """Extract tar *data* into a fresh temp dir under *parent* (same filesystem,
    so callers can ``os.replace`` out of it) and return it. Any failure removes
    the temp dir and re-raises, so a bad archive never touches the real target
    (#692). Used for the bare rom-folder tar from GUI ``rom:push``."""
    tmp = _mk_tmp(parent)
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode=mode) as tar:
            _safe_extract_tar(tar, tmp)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return tmp


# ── building ───────────────────────────────────────────────────────────────────

Opener = Callable[[], BinaryIO]


def _hash_stream(f: BinaryIO) -> tuple[int, str]:
    h, n = hashlib.sha256(), 0
    while chunk := f.read(_CHUNK):
        h.update(chunk)
        n += len(chunk)
    return n, h.hexdigest()


def _local_items(path: Path, include: Optional[Callable[[str], bool]]) -> tuple[str, list[tuple[str, Opener]]]:
    """(kind, [(manifest path, opener)]) for a local file or folder. Folders walk
    the whole tree sorted (PCSX2 nests saves a level down, #402) and never pack
    ``.bak`` backups or, with *include*, names it rejects (shared PCSX2 sstates/, #294).
    ponytail: empty subfolders are not recorded; add dir entries if an emulator needs them."""
    path = Path(path)
    if path.is_dir():
        items = []
        for f in sorted(path.rglob("*")):
            if not f.is_file() or f.name.endswith(".bak"):
                continue
            rel = f.relative_to(path).as_posix()
            if include is not None and not include(rel):
                continue
            items.append((rel, lambda f=f: open(f, "rb")))
        return "dir", items
    if not path.is_file():
        raise FileNotFoundError(str(path))
    return "file", [("", lambda: open(path, "rb"))]


def _manifest_from(kind: str, items: Iterable[tuple[str, Opener]]) -> dict:
    files = []
    for rel, opener in items:
        with opener() as f:
            size, sha = _hash_stream(f)
        files.append({"path": rel, "size": size, "sha256": sha})
    return {"v": 1, "kind": kind, "files": sorted(files, key=lambda e: e["path"])}


def manifest_hash(manifest: dict) -> str:
    """The content hash a manifest stands for (see module docstring)."""
    if manifest["kind"] == "file":
        return manifest["files"][0]["sha256"]
    rows = [[e["path"], e["size"], e["sha256"]] for e in manifest["files"]]
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def _info(name: str, size: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)  # mtime/uid/gid 0, mode 0644: deterministic bytes
    info.size = size
    info.mode = 0o644
    return info


def _pack(kind: str, items: list[tuple[str, Opener]]) -> bytes:
    manifest = _manifest_from(kind, items)
    body = json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode()
    opener_by_path = dict(items)
    buf = io.BytesIO()
    buf.write(_ENVELOPE_MAGIC + bytes([_FMT_TREE]))
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        tar.addfile(_info(_MANIFEST, len(body)), io.BytesIO(body))
        for e in manifest["files"]:
            with opener_by_path[e["path"]]() as f:
                tar.addfile(_info(e["path"] or _FILE_MEMBER, e["size"]), f)
    return buf.getvalue()


def pack_tree(path, include: Optional[Callable[[str], bool]] = None) -> bytes:
    """A local save file or folder as an enveloped format-3 blob."""
    return _pack(*_local_items(Path(path), include))


def local_manifest(path, include: Optional[Callable[[str], bool]] = None) -> dict:
    """The manifest ``pack_tree(path, include)`` would carry, without packing."""
    return _manifest_from(*_local_items(Path(path), include))


def content_hash(path, include: Optional[Callable[[str], bool]] = None) -> str:
    """Content hash of a local save file or folder, equal to the hash the server
    records for ``pack_tree(path, include)``."""
    return manifest_hash(local_manifest(path, include))


def manifest_size(manifest: dict) -> int:
    """Content bytes a manifest describes. Recorded as a generation's ``size`` and
    used by the shrink guards (#213, #285): blob file size includes tar padding."""
    return sum(e["size"] for e in manifest["files"])


# ── reading ────────────────────────────────────────────────────────────────────

def _check_rel(rel: str) -> None:
    p = PurePosixPath(rel)
    if (not rel or "\\" in rel or "\0" in rel or p.is_absolute() or p.as_posix() != rel
            or any(part in ("", ".", "..") for part in rel.split("/"))
            or rel == _MANIFEST):
        raise ValueError(f"unsafe path in blob manifest: {rel!r}")


def _parse_manifest(raw: bytes) -> dict:
    try:
        m = json.loads(raw)
        files = m["files"]
        ok = m.get("v") == 1 and m.get("kind") in ("file", "dir") and isinstance(files, list)
    except (ValueError, KeyError, TypeError):
        ok = False
    if not ok:
        raise ValueError("invalid blob manifest")
    seen = set()
    for e in files:
        if not (isinstance(e, dict) and isinstance(e.get("path"), str)
                and type(e.get("size")) is int and e["size"] >= 0
                and isinstance(e.get("sha256"), str) and _SHA_RE.match(e["sha256"])):
            raise ValueError("invalid blob manifest entry")
        if m["kind"] == "dir":
            _check_rel(e["path"])
        if e["path"] in seen:
            raise ValueError(f"duplicate path in blob manifest: {e['path']!r}")
        seen.add(e["path"])
    if m["kind"] == "file" and (len(files) != 1 or files[0]["path"] != ""):
        raise ValueError("file blob manifest must have exactly one unnamed entry")
    return m


def _check_header(header: bytes) -> None:
    if header[:4] != _ENVELOPE_MAGIC:
        raise ValueError("blob has no format header; update the EmuSync server")
    if header[4:5] != bytes([_FMT_TREE]):
        raise ValueError(f"unsupported blob format {header[4] if len(header) > 4 else None}; "
                         "update the EmuSync server and clients (#739)")


def _walk(f: BinaryIO, sink: Optional[Callable[[str, BinaryIO], None]] = None) -> dict:
    """Read and verify a format-3 blob from binary file *f* (at offset 0).

    Each member after the manifest must be a regular file named in it, appear
    once, and match its size and sha256; every entry must be present. *sink*
    (manifest path, stream) consumes member bytes while they are hashed. Raises
    ValueError on any mismatch or a missing/old format header."""
    _check_header(f.read(_ENVELOPE_HEADER_LEN))
    try:
        with tarfile.open(fileobj=f, mode="r:") as tar:
            first = tar.next()
            if first is None or first.name != _MANIFEST or not first.isreg() or first.size > _MAX_MANIFEST:
                raise ValueError("blob manifest missing")
            m = _parse_manifest(tar.extractfile(first).read())
            want = {(e["path"] or _FILE_MEMBER): e for e in m["files"]}
            seen = set()
            while (member := tar.next()) is not None:  # iterating the TarFile would replay the manifest
                e = want.get(member.name)
                if e is None or member.name in seen or not member.isreg():
                    raise ValueError(f"unexpected member in blob: {member.name!r}")
                seen.add(member.name)
                src = _HashingReader(tar.extractfile(member))
                if sink is not None:
                    sink(e["path"], src)
                src.drain()
                if (src.size, src.hexdigest()) != (e["size"], e["sha256"]):
                    raise ValueError(f"blob member does not match manifest: {member.name!r}")
            if seen != set(want):
                raise ValueError("blob is missing files listed in its manifest")
    except tarfile.TarError as exc:
        raise ValueError(f"corrupt blob: {exc}") from exc
    return m


class _HashingReader:
    def __init__(self, f: BinaryIO) -> None:
        self._f, self._h, self.size = f, hashlib.sha256(), 0

    def read(self, n: int = -1) -> bytes:
        chunk = self._f.read(n)
        self._h.update(chunk)
        self.size += len(chunk)
        return chunk

    def drain(self) -> None:
        while self.read(_CHUNK):
            pass

    def hexdigest(self) -> str:
        return self._h.hexdigest()


def verify_blob(src) -> tuple[dict, str]:
    """(manifest, content hash) of a stored or staged blob (a path, or the bytes);
    ValueError if it is not a valid format-3 blob."""
    if isinstance(src, (bytes, bytearray)):
        m = _walk(io.BytesIO(src))
    else:
        with open(src, "rb") as f:
            m = _walk(f)
    return m, manifest_hash(m)


def blob_kind(data: bytes) -> str:
    """'file' or 'dir' from a blob's manifest, without reading the members."""
    f = io.BytesIO(data)
    _check_header(f.read(_ENVELOPE_HEADER_LEN))
    try:
        with tarfile.open(fileobj=f, mode="r:") as tar:
            first = tar.next()
            if first is None or first.name != _MANIFEST or first.size > _MAX_MANIFEST:
                raise ValueError("blob manifest missing")
            return _parse_manifest(tar.extractfile(first).read())["kind"]
    except tarfile.TarError as exc:
        raise ValueError(f"corrupt blob: {exc}") from exc


def extract_tree(data: bytes, parent: Path) -> tuple[str, Path]:
    """Extract and verify a blob into a fresh temp dir under *parent* (same
    filesystem, so callers ``os.replace`` out of it). Returns (kind, tmp): for
    ``dir`` the tree is *tmp* itself, for ``file`` the content is
    ``tmp / ".emusync-file"``. Any failure removes *tmp* and re-raises, so a bad
    blob never touches the real target (#692)."""
    tmp = _mk_tmp(Path(parent))
    root = tmp.resolve()

    def sink(rel: str, src: BinaryIO) -> None:
        dest = tmp / (rel or _FILE_MEMBER)
        if root not in dest.resolve().parents:
            raise ValueError(f"unsafe path in blob manifest: {rel!r}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as out:
            shutil.copyfileobj(src, out, _CHUNK)

    try:
        m = _walk(io.BytesIO(data), sink)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return m["kind"], tmp


def legacy_to_tree(fmt: int, payload: bytes) -> bytes:
    """A format 0/1/2 payload as a format-3 blob (schema v38 conversion only).
    Tar members keep their relative paths; directories are dropped, links or
    special members raise ValueError."""
    if fmt == _FMT_RAW:
        return _pack("file", [("", lambda: io.BytesIO(payload))])
    if fmt not in (_FMT_TAR, _FMT_TARGZ):
        raise ValueError(f"unknown legacy blob format {fmt}")
    items: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:*") as tar:
            for member in tar:
                if member.isdir():
                    continue
                if not member.isreg():
                    raise ValueError(f"unsupported member in legacy blob: {member.name!r}")
                rel = PurePosixPath(member.name).as_posix()
                rel = rel[2:] if rel.startswith("./") else rel
                _check_rel(rel)
                items[rel] = tar.extractfile(member).read()  # last duplicate wins, as extraction did
    except tarfile.TarError as exc:
        raise ValueError(f"corrupt legacy blob: {exc}") from exc
    return _pack("dir", [(rel, lambda d=d: io.BytesIO(d)) for rel, d in items.items()])
