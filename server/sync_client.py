from __future__ import annotations

import io
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx


@dataclass
class GameDeviceConfig:
    rom_path: str = ""
    save_path: str = ""
    launch_command: str = ""
    state_path: str = ""
    rom_folder_path: str = ""


class SyncClient:
    def __init__(self, host: str, port: int, pin: str, device_id: str, device_name: str) -> None:
        self._base = f"http://{host}:{port}"
        self._headers = {
            **({"Authorization": f"Bearer {pin}"} if pin else {}),
            "X-Device-ID": device_id,
            "X-Device-Name": device_name,
        }

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    def health(self) -> bool:
        try:
            r = httpx.get(self._url("/health"), timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def list_devices(self) -> list[dict]:
        r = httpx.get(self._url("/devices"), headers=self._headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def list_games(self) -> list[dict]:
        r = httpx.get(self._url("/games"), headers=self._headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def add_game(self, name: str, console: str = "") -> dict:
        r = httpx.post(self._url("/games"), json={"name": name, "console": console}, headers=self._headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def get_game(self, slug: str) -> Optional[dict]:
        r = httpx.get(self._url(f"/games/{slug}"), headers=self._headers, timeout=10)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def update_game(self, slug: str, name: str) -> None:
        r = httpx.put(self._url(f"/games/{slug}"), json={"name": name}, headers=self._headers, timeout=10)
        r.raise_for_status()

    def remove_game(self, slug: str) -> None:
        r = httpx.delete(self._url(f"/games/{slug}"), headers=self._headers, timeout=10)
        r.raise_for_status()

    def list_game_devices(self, slug: str) -> list[dict]:
        r = httpx.get(self._url(f"/games/{slug}/devices"), headers=self._headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def get_game_device(self, slug: str) -> Optional[GameDeviceConfig]:
        r = httpx.get(self._url(f"/games/{slug}/device"), headers=self._headers, timeout=10)
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
        )

    def set_game_device(self, slug: str, cfg: GameDeviceConfig) -> None:
        r = httpx.put(
            self._url(f"/games/{slug}/device"),
            json={"rom_path": cfg.rom_path, "save_path": cfg.save_path, "launch_command": cfg.launch_command,
                  "state_path": cfg.state_path, "rom_folder_path": cfg.rom_folder_path},
            headers=self._headers,
            timeout=10,
        )
        r.raise_for_status()

    def list_my_game_devices(self) -> list[dict]:
        """Return all games configured for this device (slug, name, console, rom_path, …)."""
        r = httpx.get(self._url("/game-devices"), headers=self._headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def get_device_consoles(self, device_id: str) -> list[dict]:
        """Return console configs for a specific device (to find its ROM folders)."""
        r = httpx.get(self._url(f"/devices/{device_id}/consoles"), headers=self._headers, timeout=10)
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

        r = httpx.post(
            self._url(f"/games/{slug}/rom-transfer"),
            content=_stream(),
            headers={
                **self._headers,
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
        r = httpx.get(self._url("/rom-transfers/pending"), headers=self._headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def download_transfer(self, transfer_id: str, destination_path: str) -> None:
        """Stream a staged ROM file to disk at the given destination path."""
        path = Path(destination_path)
        # If destination_path is a directory, we can't write to it directly
        if path.is_dir() or not path.suffix:
            raise ValueError(
                f"destination_path must be a full file path, not a directory: {destination_path}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream(
            "GET",
            self._url(f"/rom-transfers/{transfer_id}/file"),
            headers=self._headers,
            timeout=httpx.Timeout(None),
        ) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            received = 0
            with open(destination_path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=64 * 1024):
                    f.write(chunk)
                    received += len(chunk)
                    if total:
                        pct = received * 100 // total
                        mb = received / (1024 * 1024)
                        print(f"\r  {mb:.1f} / {total/(1024*1024):.1f} MB ({pct}%)", end="", flush=True)
            print(flush=True)

    def complete_transfer(self, transfer_id: str, status: str = "completed") -> None:
        r = httpx.put(
            self._url(f"/rom-transfers/{transfer_id}"),
            json={"status": status},
            headers=self._headers,
            timeout=10,
        )
        r.raise_for_status()

    def stream_events(self):
        """Generator that yields parsed SSE event dicts. Blocks until disconnected."""
        import json as _json
        with httpx.stream(
            "GET",
            self._url("/events/stream"),
            headers=self._headers,
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
        r = httpx.get(self._url(f"/games/{slug}/save"), headers=self._headers, timeout=30)
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
        r = httpx.post(
            self._url(f"/games/{slug}/save"),
            content=data,
            headers={**self._headers, "Content-Type": "application/octet-stream"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["hash"]

    def pull_state(self, slug: str, state_path: str) -> tuple[bool, Optional[str]]:
        """Write server state to disk. Returns (pulled, server_hash). pulled=False if no state exists."""
        r = httpx.get(self._url(f"/games/{slug}/state"), headers=self._headers, timeout=30)
        if r.status_code == 204:
            return False, None
        r.raise_for_status()
        p = Path(state_path)
        if p.is_dir() or not p.suffix:
            # state_path is the states FOLDER — extract the tar.gz archive into it.
            p.mkdir(parents=True, exist_ok=True)
            for existing in list(p.iterdir()):
                if existing.is_file() and not existing.name.endswith(".bak"):
                    existing.rename(str(existing) + ".bak")
            try:
                with tarfile.open(fileobj=io.BytesIO(r.content), mode="r:gz") as tar:
                    tar.extractall(path=str(p))
                for bak in p.glob("*.bak"):
                    bak.unlink(missing_ok=True)
            except tarfile.TarError:
                # Legacy: server stored a raw state file; write it as GameName.state
                dest = p / f"{p.name}.state"
                dest.write_bytes(r.content)
        else:
            if p.exists():
                shutil.copy2(p, p.with_suffix(p.suffix + ".bak"))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(r.content)
        return True, r.headers.get("X-State-Hash")

    def push_state(self, slug: str, state_path: str) -> str:
        p = Path(state_path)
        if p.is_dir():
            # Pack all files in the states folder as a tar.gz archive.
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                for f in sorted(p.iterdir()):
                    if f.is_file():
                        tar.add(str(f), arcname=f.name)
            data = buf.getvalue()
        else:
            data = p.read_bytes()
        r = httpx.post(
            self._url(f"/games/{slug}/state"),
            content=data,
            headers={**self._headers, "Content-Type": "application/octet-stream"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["hash"]

    def acquire_lock(self, slug: str) -> None:
        r = httpx.post(self._url(f"/games/{slug}/lock"), headers=self._headers, timeout=10)
        if r.status_code == 409:
            raise ValueError(r.json().get("detail", "Game is locked by another device"))
        r.raise_for_status()

    def release_lock(self, slug: str) -> None:
        r = httpx.delete(self._url(f"/games/{slug}/lock"), headers=self._headers, timeout=10)
        r.raise_for_status()

    def get_lock(self, slug: str) -> dict:
        r = httpx.get(self._url(f"/games/{slug}/lock"), headers=self._headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def list_device_games(self, device_id: str) -> list[dict]:
        """Return all games configured for a specific device."""
        r = httpx.get(self._url(f"/devices/{device_id}/game-devices"), headers=self._headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def create_pull_request(self, slug: str, from_device_id: str, destination_path: str) -> dict:
        """Request the source device to push a ROM to this device via the server."""
        r = httpx.post(
            self._url(f"/games/{slug}/rom-pull-request"),
            json={"from_device_id": from_device_id, "destination_path": destination_path},
            headers=self._headers,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    def list_pending_pull_requests(self) -> list[dict]:
        """Return pull requests pending for this device to fulfill (as the source)."""
        r = httpx.get(self._url("/rom-pull-requests/pending"), headers=self._headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def complete_pull_request(self, pull_request_id: str, status: str = "fulfilled") -> None:
        r = httpx.put(
            self._url(f"/rom-pull-requests/{pull_request_id}"),
            json={"status": status},
            headers=self._headers,
            timeout=10,
        )
        r.raise_for_status()

    def get_save_meta(self, slug: str) -> Optional[dict]:
        r = httpx.get(self._url(f"/games/{slug}/save/meta"), headers=self._headers, timeout=10)
        if r.status_code == 204:
            return None
        r.raise_for_status()
        return r.json()

    def get_console_defs(self) -> list[dict]:
        """Return all console definitions from server."""
        r = httpx.get(self._url("/console-defs"), headers=self._headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def get_system_defs(self) -> dict:
        """Return all system definitions from server."""
        r = httpx.get(self._url("/system-defs"), headers=self._headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def get_console_folder_names(self) -> dict:
        """Return console key → folder name patterns from server."""
        r = httpx.get(self._url("/console-folder-names"), headers=self._headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def get_standalones(self, console_key: str) -> list[dict]:
        """Return standalone emulators for a console from server."""
        r = httpx.get(self._url(f"/standalones/{console_key}"), headers=self._headers, timeout=10)
        r.raise_for_status()
        return r.json()
