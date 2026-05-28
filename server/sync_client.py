from __future__ import annotations

import shutil
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
        state = Path(state_path)
        if state.exists():
            shutil.copy2(state, state.with_suffix(state.suffix + ".bak"))
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_bytes(r.content)
        return True, r.headers.get("X-State-Hash")

    def push_state(self, slug: str, state_path: str) -> str:
        data = Path(state_path).read_bytes()
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

    def get_save_meta(self, slug: str) -> Optional[dict]:
        r = httpx.get(self._url(f"/games/{slug}/save/meta"), headers=self._headers, timeout=10)
        if r.status_code == 204:
            return None
        r.raise_for_status()
        return r.json()

    def pull_rom(self, slug: str, dest_path: str, on_progress) -> str:
        """Stream ROM from server to disk. Returns filename. Calls on_progress(downloaded, total)."""
        with httpx.stream("GET", self._url(f"/games/{slug}/rom"),
                          headers=self._headers, timeout=None) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            filename = r.headers.get("X-Rom-Filename", Path(dest_path).name)
            downloaded = 0
            with open(dest_path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    on_progress(downloaded, total)
        return filename

    def push_rom(self, slug: str, rom_path: str, on_progress, dest_folder: str = "") -> dict:
        """Stream ROM from disk to target server. Returns server's response dict."""
        filename = Path(rom_path).name
        total = Path(rom_path).stat().st_size
        uploaded = [0]

        def gen():
            with open(rom_path, "rb") as f:
                while chunk := f.read(65536):
                    uploaded[0] += len(chunk)
                    on_progress(uploaded[0], total)
                    yield chunk

        extra_headers = {"X-Rom-Filename": filename}
        if dest_folder:
            extra_headers["X-Dest-Folder"] = dest_folder

        r = httpx.post(
            self._url(f"/games/{slug}/rom"),
            content=gen(),
            headers={**self._headers,
                     "Content-Type": "application/octet-stream",
                     "Content-Length": str(total),
                     **extra_headers},
            timeout=None,
        )
        r.raise_for_status()
        return r.json()
