from __future__ import annotations

import io
import os
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx


def _extract_state_folder(content: bytes, folder: Path) -> None:
    """Overwrite a states folder with a tar.gz archive, keeping a one-generation
    ``.bak`` backup of every file it replaces.

    State pulls must not be destructive: the previous code renamed existing files
    to ``.bak`` and then *deleted* those backups on success, so an overwrite was
    unrecoverable (saves, by contrast, retain a ``.bak``). Here the backups are
    retained. ``os.replace`` overwrites any prior ``.bak`` so only one generation
    is kept and it works on Windows (where ``Path.rename`` errors if the target
    exists). ``.bak`` files are skipped when backing up so they don't recurse.
    """
    folder.mkdir(parents=True, exist_ok=True)
    for existing in list(folder.iterdir()):
        if existing.is_file() and not existing.name.endswith(".bak"):
            os.replace(str(existing), str(existing) + ".bak")
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
            _safe_extract_tar(tar, folder)
    except tarfile.TarError:
        # Legacy: server stored a raw state file; write it as <FolderName>.state.
        (folder / f"{folder.name}.state").write_bytes(content)


def _merge_extract_state_folder(content: bytes, folder: Path) -> None:
    """Extract a state tar.gz into *folder*, backing up only the files the archive
    overwrites and leaving every other file untouched.

    Unlike `_extract_state_folder` (which `.bak`s every file first), this is for a
    SHARED states directory — PCSX2's `sstates/`, which holds every PS2 game's
    states — so a pull for one game must not disturb other games' state files
    (issue #294)."""
    folder.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                target = folder / Path(member.name).name
                if target.exists():  # back up only what we're about to overwrite
                    os.replace(str(target), str(target) + ".bak")
            _safe_extract_tar(tar, folder)
    except tarfile.TarError:
        # A shared folder has no single canonical filename, so a legacy raw blob
        # can't be placed safely — ignore it (PS2 states are always tar archives).
        pass


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
    tar.extractall(path=str(dest))


@dataclass
class GameDeviceConfig:
    rom_path: str = ""
    save_path: str = ""
    launch_command: str = ""
    state_path: str = ""
    rom_folder_path: str = ""
    # Network-ROM source fields (issue #255); default keeps pre-#255 behaviour.
    rom_source: str = "local"
    rom_rel_path: str = ""
    local_rom_path: str = ""
    rom_sha256: str = ""
    # Console-level network/local folder config; transient — populates the console row.
    device_network_folder: str = ""
    device_local_folder: str = ""


def memcard_bytes(card_path: Path) -> bytes:
    """Serialize a memcard for network transfer and local hashing.

    Folder-based memcards (PCSX2 .ps2 folders) are packed as a deterministic
    plain tar archive (sorted entries, mtime=0) so the SHA-256 is stable across
    calls for unchanged content — required for _reconcile_save's hash comparison.
    Walks the whole tree (``rglob``, not a single-level ``iterdir``): PCSX2
    nests each game's saves one level down in its own subfolder, so a
    top-level-only walk would silently drop every game's data and push just
    the loose top-level files (e.g. ``_pcsx2_superblock``). File-based
    memcards are returned as raw bytes.
    """
    if card_path.is_dir():
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for f in sorted(card_path.rglob("*")):
                if not f.is_file() or f.name.endswith(".bak"):
                    continue
                rel = f.relative_to(card_path).as_posix()
                data = f.read_bytes()
                info = tarfile.TarInfo(name=rel)
                info.size = len(data)
                info.mtime = 0
                tar.addfile(info, io.BytesIO(data))
        return buf.getvalue()
    return card_path.read_bytes()


def _write_memcard(card: Path, data: bytes) -> None:
    """Write received memcard bytes to disk.

    Detects tar archives (folder-based memcards) by attempting to open the
    bytes as a tar; falls back to writing raw bytes (file-based memcard).
    Backs up any existing file before overwriting, preserving the tar's
    relative subfolder structure — PCSX2 nests each game's saves under its
    own subfolder (e.g. ``GAME1/GAME1``, ``GAME1/icon.sys``), so backing up
    by basename alone collides with the subfolder itself (a directory, not
    a file) and crashes. Extraction goes through ``_safe_extract_tar`` so a
    member can't escape *card* the same way a state archive can't.
    """
    try:
        tf = tarfile.open(fileobj=io.BytesIO(data))
        bak = card.parent / (card.name + ".bak")
        if card.is_dir():
            if bak.exists():
                shutil.rmtree(bak)
            shutil.copytree(card, bak)
        elif card.is_file():
            shutil.copy2(card, bak)
            card.unlink()
        card.mkdir(parents=True, exist_ok=True)
        _safe_extract_tar(tf, card)
        tf.close()
    except tarfile.TarError:
        if card.exists() and card.is_file():
            shutil.copy2(card, card.parent / (card.name + ".bak"))
        if not card.exists() or card.is_file():
            card.parent.mkdir(parents=True, exist_ok=True)
            card.write_bytes(data)


class SyncClient:
    def __init__(self, host: str, port: int, pin: str, device_id: str, device_name: str) -> None:
        self._base = f"http://{host}:{port}"
        self._headers = {
            **({"Authorization": f"Bearer {pin}"} if pin else {}),
            "X-Device-ID": device_id,
            "X-Device-Name": device_name,
        }
        self._client = httpx.Client(headers=self._headers)

    def close(self) -> None:
        self._client.close()

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    def health(self) -> bool:
        try:
            r = self._client.get(self._url("/health"), timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def list_devices(self) -> list[dict]:
        r = self._client.get(self._url("/devices"), timeout=10)
        r.raise_for_status()
        return r.json()

    def list_games(self) -> list[dict]:
        r = self._client.get(self._url("/games"), timeout=10)
        r.raise_for_status()
        return r.json()

    def add_game(self, name: str, console: str = "") -> dict:
        r = self._client.post(self._url("/games"), json={"name": name, "console": console}, timeout=10)
        r.raise_for_status()
        return r.json()

    def get_game(self, slug: str) -> Optional[dict]:
        r = self._client.get(self._url(f"/games/{slug}"), timeout=10)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def update_game(self, slug: str, name: str) -> None:
        r = self._client.put(self._url(f"/games/{slug}"), json={"name": name}, timeout=10)
        r.raise_for_status()

    def remove_game(self, slug: str) -> None:
        r = self._client.delete(self._url(f"/games/{slug}"), timeout=10)
        r.raise_for_status()

    def list_game_devices(self, slug: str) -> list[dict]:
        r = self._client.get(self._url(f"/games/{slug}/devices"), timeout=10)
        r.raise_for_status()
        return r.json()

    def get_game_device(self, slug: str) -> Optional[GameDeviceConfig]:
        r = self._client.get(self._url(f"/games/{slug}/device"), timeout=10)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        d = r.json()
        return GameDeviceConfig(
            rom_path=d.get("rom_path", ""),
            save_path=d.get("save_path", ""),
            launch_command=d.get("launch_command", ""),
            state_path=d.get("state_path", ""),
            rom_folder_path=d.get("rom_folder_path", ""),
            rom_source=d.get("rom_source", "local"),
            rom_rel_path=d.get("rom_rel_path", ""),
            local_rom_path=d.get("local_rom_path", ""),
            rom_sha256=d.get("rom_sha256", ""),
        )

    def set_game_device(self, slug: str, cfg: GameDeviceConfig) -> None:
        r = self._client.put(
            self._url(f"/games/{slug}/device"),
            json={"rom_path": cfg.rom_path, "save_path": cfg.save_path, "launch_command": cfg.launch_command,
                  "state_path": cfg.state_path, "rom_folder_path": cfg.rom_folder_path,
                  "rom_source": cfg.rom_source, "rom_rel_path": cfg.rom_rel_path,
                  "local_rom_path": cfg.local_rom_path, "rom_sha256": cfg.rom_sha256,
                  "device_network_folder": cfg.device_network_folder,
                  "device_local_folder": cfg.device_local_folder},
            timeout=10,
        )
        r.raise_for_status()

    def list_my_game_devices(self) -> list[dict]:
        """Return all games configured for this device (slug, name, console, rom_path, …)."""
        r = self._client.get(self._url("/game-devices"), timeout=10)
        r.raise_for_status()
        return r.json()

    def get_device_consoles(self, device_id: str) -> list[dict]:
        """Return console configs for a specific device (to find its ROM folders)."""
        r = self._client.get(self._url(f"/devices/{device_id}/consoles"), timeout=10)
        r.raise_for_status()
        return r.json()

    def create_rom_transfer(
        self, slug: str, to_device_id: str, destination_path: str, rom_path: str
    ) -> dict:
        """Upload a ROM to the server and queue it for delivery to target device."""
        path = Path(rom_path)
        file_size = path.stat().st_size
        mb_total = file_size / (1024 * 1024)
        transferred = [0]

        def _stream():
            chunk_size = 64 * 1024
            with open(rom_path, "rb") as f:
                while chunk := f.read(chunk_size):
                    transferred[0] += len(chunk)
                    pct = transferred[0] * 100 // file_size
                    mb = transferred[0] / (1024 * 1024)
                    print(f"\r  {mb:.1f} / {mb_total:.1f} MB ({pct}%)", end="", flush=True)
                    yield chunk
            print(flush=True)

        r = self._client.post(
            self._url(f"/games/{slug}/rom-transfer"),
            content=_stream(),
            headers={
                "Content-Type": "application/octet-stream",
                "X-To-Device-ID": to_device_id,
                "X-Destination-Path": destination_path,
                "X-Filename": path.name,
            },
            timeout=httpx.Timeout(None),
        )
        r.raise_for_status()
        return r.json()

    def list_pending_transfers(self) -> list[dict]:
        """Return transfers queued for this device that haven't been delivered yet."""
        r = self._client.get(self._url("/rom-transfers/pending"), timeout=10)
        r.raise_for_status()
        return r.json()

    def download_transfer(self, transfer_id: str, destination_path: str, expected_hash: Optional[str] = None) -> None:
        """Stream a staged ROM file to disk at the given destination path.

        Verifies the download against the server-recorded SHA256 (passed in or read
        from the ``X-Rom-Hash`` response header). On mismatch the partial file is
        deleted and ValueError is raised, so a corrupt transfer over flaky Wi-Fi is
        caught instead of landing an unplayable ROM (issue #214).
        """
        import hashlib as _hashlib

        path = Path(destination_path)
        if path.is_dir() or not path.suffix:
            raise ValueError(
                f"destination_path must be a full file path, not a directory: {destination_path}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        hasher = _hashlib.sha256()
        with self._client.stream(
            "GET",
            self._url(f"/rom-transfers/{transfer_id}/file"),
            timeout=httpx.Timeout(None),
        ) as r:
            r.raise_for_status()
            expected = expected_hash or r.headers.get("X-Rom-Hash")
            total = int(r.headers.get("content-length", 0))
            received = 0
            with open(destination_path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=64 * 1024):
                    f.write(chunk)
                    hasher.update(chunk)
                    received += len(chunk)
                    if total:
                        pct = received * 100 // total
                        mb = received / (1024 * 1024)
                        print(f"\r  {mb:.1f} / {total/(1024*1024):.1f} MB ({pct}%)", end="", flush=True)
            print(flush=True)
        if expected and hasher.hexdigest() != expected:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            raise ValueError(
                f"ROM transfer integrity check failed (expected {expected[:12]}…, got {hasher.hexdigest()[:12]}…)"
            )

    def complete_transfer(self, transfer_id: str, status: str = "completed") -> None:
        r = self._client.put(
            self._url(f"/rom-transfers/{transfer_id}"),
            json={"status": status},
            timeout=10,
        )
        r.raise_for_status()

    def stream_events(self):
        """Generator that yields parsed SSE event dicts. Blocks until disconnected."""
        import json as _json
        with self._client.stream(
            "GET",
            self._url("/events/stream"),
            timeout=httpx.Timeout(None),
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if line.startswith("data: "):
                    try:
                        yield _json.loads(line[6:])
                    except (ValueError, KeyError):
                        pass

    def pull_save(self, slug: str, save_path: str) -> tuple[bool, Optional[str]]:
        """Write server save to disk. Returns (pulled, server_hash). pulled=False if no save exists."""
        r = self._client.get(self._url(f"/games/{slug}/save"), timeout=30)
        if r.status_code == 204:
            return False, None
        r.raise_for_status()
        save = Path(save_path)
        if save.exists():
            shutil.copy2(save, save.with_suffix(save.suffix + ".bak"))
        save.parent.mkdir(parents=True, exist_ok=True)
        save.write_bytes(r.content)
        return True, r.headers.get("X-Save-Hash")

    def push_save(self, slug: str, save_path: str) -> str:
        data = Path(save_path).read_bytes()
        r = self._client.post(
            self._url(f"/games/{slug}/save"),
            content=data,
            headers={"Content-Type": "application/octet-stream"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["hash"]

    # ── console-scoped shared memory card (issue #295) ──────────────────────────
    # PS2's single card, shared across all the console's games. Mirrors the save
    # methods but keyed by console_key so _reconcile_save works against it.

    def get_console_memcard_meta(self, console_key: str) -> Optional[dict]:
        r = self._client.get(self._url(f"/consoles/{console_key}/memcard/meta"), timeout=10)
        if r.status_code == 204:
            return None
        r.raise_for_status()
        return r.json()

    def pull_console_memcard(self, console_key: str, card_path: str) -> tuple[bool, Optional[str]]:
        """Write the server's shared card to disk (backing up any existing one).

        Folder-based memcards arrive as a plain tar archive; file-based cards
        arrive as raw bytes. _write_memcard detects which and handles both.
        """
        r = self._client.get(self._url(f"/consoles/{console_key}/memcard"), timeout=30)
        if r.status_code == 204:
            return False, None
        r.raise_for_status()
        _write_memcard(Path(card_path), r.content)
        return True, r.headers.get("X-Save-Hash")

    def push_console_memcard(self, console_key: str, card_path: str) -> str:
        data = memcard_bytes(Path(card_path))
        r = self._client.post(
            self._url(f"/consoles/{console_key}/memcard"),
            content=data,
            headers={"Content-Type": "application/octet-stream"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["hash"]

    def pull_state(self, slug: str, state_path: str) -> tuple[bool, Optional[str]]:
        """Write server state to disk. Returns (pulled, server_hash). pulled=False if no state exists."""
        r = self._client.get(self._url(f"/games/{slug}/state"), timeout=30)
        if r.status_code == 204:
            return False, None
        r.raise_for_status()
        p = Path(state_path)
        if p.is_dir() or not p.suffix:
            # state_path is the states FOLDER — extract the tar.gz, retaining a
            # .bak of every file it overwrites (non-destructive).
            _extract_state_folder(r.content, p)
        else:
            if p.exists():
                shutil.copy2(p, p.with_suffix(p.suffix + ".bak"))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(r.content)
        return True, r.headers.get("X-State-Hash")

    def pull_state_merge(self, slug: str, state_path: str) -> tuple[bool, Optional[str]]:
        """Pull state into a SHARED states folder, overwriting only this game's
        files (PCSX2 sstates/, issue #294). Returns (pulled, server_hash)."""
        r = self._client.get(self._url(f"/games/{slug}/state"), timeout=30)
        if r.status_code == 204:
            return False, None
        r.raise_for_status()
        _merge_extract_state_folder(r.content, Path(state_path))
        return True, r.headers.get("X-State-Hash")

    def push_state(self, slug: str, state_path: str, name_prefix: Optional[str] = None) -> str:
        p = Path(state_path)
        if p.is_dir():
            # Pack the states folder as a tar.gz. When name_prefix is set, only
            # files whose name starts with it are packed — for a SHARED states dir
            # (PCSX2 sstates/) this selects just this game's serial files (#294).
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                for f in sorted(p.iterdir()):
                    # Skip .bak backups so they don't propagate to the server/peers.
                    if not (f.is_file() and not f.name.endswith(".bak")):
                        continue
                    if name_prefix is not None and not f.name.startswith(name_prefix):
                        continue
                    tar.add(str(f), arcname=f.name)
            data = buf.getvalue()
        else:
            data = p.read_bytes()
        r = self._client.post(
            self._url(f"/games/{slug}/state"),
            content=data,
            headers={"Content-Type": "application/octet-stream"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["hash"]

    def acquire_lock(self, slug: str) -> None:
        r = self._client.post(self._url(f"/games/{slug}/lock"), timeout=10)
        if r.status_code == 409:
            raise ValueError(r.json().get("detail", "Game is locked by another device"))
        r.raise_for_status()

    def release_lock(self, slug: str) -> None:
        r = self._client.delete(self._url(f"/games/{slug}/lock"), timeout=10)
        r.raise_for_status()

    def get_lock(self, slug: str) -> dict:
        r = self._client.get(self._url(f"/games/{slug}/lock"), timeout=10)
        r.raise_for_status()
        return r.json()

    def list_device_games(self, device_id: str) -> list[dict]:
        """Return all games configured for a specific device."""
        r = self._client.get(self._url(f"/devices/{device_id}/game-devices"), timeout=10)
        r.raise_for_status()
        return r.json()

    def create_pull_request(self, slug: str, from_device_id: str, destination_path: str) -> dict:
        """Request the source device to push a ROM to this device via the server."""
        r = self._client.post(
            self._url(f"/games/{slug}/rom-pull-request"),
            json={"from_device_id": from_device_id, "destination_path": destination_path},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    def list_pending_pull_requests(self) -> list[dict]:
        """Return pull requests pending for this device to fulfill (as the source)."""
        r = self._client.get(self._url("/rom-pull-requests/pending"), timeout=10)
        r.raise_for_status()
        return r.json()

    def complete_pull_request(self, pull_request_id: str, status: str = "fulfilled") -> None:
        r = self._client.put(
            self._url(f"/rom-pull-requests/{pull_request_id}"),
            json={"status": status},
            timeout=10,
        )
        r.raise_for_status()

    def get_save_meta(self, slug: str) -> Optional[dict]:
        r = self._client.get(self._url(f"/games/{slug}/save/meta"), timeout=10)
        if r.status_code == 204:
            return None
        r.raise_for_status()
        return r.json()

    def _list_history(self, kind: str, slug: str) -> list[dict]:
        """Return every retained generation of `kind` ('save'/'state') for a game."""
        r = self._client.get(self._url(f"/games/{slug}/{kind}/history"), timeout=10)
        r.raise_for_status()
        return r.json()

    def _restore(self, kind: str, slug: str, version_id: str) -> dict:
        """Make a past generation of `kind` the current one on the server."""
        r = self._client.post(self._url(f"/games/{slug}/{kind}/restore"), json={"version_id": version_id}, timeout=10)
        r.raise_for_status()
        return r.json()

    def report_conflict(self, slug: str, winner_device_id: str, loser_device_id: str,
                        winner_hash: str, loser_hash: str) -> dict:
        """Record an auto-resolved save divergence on the server (issue #243)."""
        r = self._client.post(
            self._url(f"/games/{slug}/conflicts"),
            json={
                "winner_device_id": winner_device_id,
                "loser_device_id": loser_device_id,
                "winner_hash": winner_hash or "",
                "loser_hash": loser_hash or "",
            },
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    def list_save_history(self, slug: str) -> list[dict]:
        return self._list_history("save", slug)

    def restore_save(self, slug: str, version_id: str) -> dict:
        return self._restore("save", slug, version_id)

    def list_state_history(self, slug: str) -> list[dict]:
        return self._list_history("state", slug)

    def restore_state(self, slug: str, version_id: str) -> dict:
        return self._restore("state", slug, version_id)

    def get_console_defs(self) -> list[dict]:
        """Return all console definitions from server."""
        r = self._client.get(self._url("/console-defs"), timeout=10)
        r.raise_for_status()
        return r.json()

    def get_system_defs(self) -> dict:
        """Return all system definitions from server."""
        r = self._client.get(self._url("/system-defs"), timeout=10)
        r.raise_for_status()
        return r.json()

    def get_console_folder_names(self) -> dict:
        """Return console key → folder name patterns from server."""
        r = self._client.get(self._url("/console-folder-names"), timeout=10)
        r.raise_for_status()
        return r.json()

    def get_standalones(self, console_key: str) -> list[dict]:
        """Return standalone emulators for a console from server."""
        r = self._client.get(self._url(f"/standalones/{console_key}"), timeout=10)
        r.raise_for_status()
        return r.json()
