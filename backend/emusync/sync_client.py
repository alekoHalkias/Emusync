import shutil
from pathlib import Path
from typing import Dict, List, Optional

import httpx


class SyncClient:
    def __init__(self, host: str, port: int, token: str):
        self.base_url = f"http://{host}:{port}"
        self.headers = {"Authorization": f"Bearer {token}"}

    def health(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/health", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def pair(self, master_token: str, device_id: str, device_name: str) -> str:
        r = httpx.post(
            f"{self.base_url}/pair",
            json={"master_token": master_token, "device_id": device_id, "device_name": device_name},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()["token"]

    def pull_save(self, slug: str, save_path: str) -> bool:
        r = httpx.get(f"{self.base_url}/games/{slug}/save", headers=self.headers, timeout=30)
        if r.status_code == 204:
            return False
        r.raise_for_status()
        p = Path(save_path)
        if p.exists():
            shutil.copy2(save_path, str(save_path) + ".bak")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(r.content)
        return True

    def push_save(self, slug: str, save_path: str):
        data = Path(save_path).read_bytes()
        r = httpx.post(
            f"{self.base_url}/games/{slug}/save",
            content=data,
            headers={**self.headers, "Content-Type": "application/octet-stream"},
            timeout=30,
        )
        r.raise_for_status()

    def acquire_lock(self, slug: str):
        r = httpx.post(f"{self.base_url}/games/{slug}/lock", headers=self.headers, timeout=10)
        r.raise_for_status()

    def release_lock(self, slug: str):
        try:
            httpx.delete(f"{self.base_url}/games/{slug}/lock", headers=self.headers, timeout=10)
        except Exception:
            pass

    def list_games(self) -> List[Dict]:
        r = httpx.get(f"{self.base_url}/games", headers=self.headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def add_game(self, slug: str, name: str):
        r = httpx.post(
            f"{self.base_url}/games",
            json={"slug": slug, "name": name},
            headers=self.headers,
            timeout=10,
        )
        r.raise_for_status()

    def remove_game(self, slug: str):
        r = httpx.delete(f"{self.base_url}/games/{slug}", headers=self.headers, timeout=10)
        r.raise_for_status()

    def get_game(self, slug: str) -> Optional[Dict]:
        r = httpx.get(f"{self.base_url}/games/{slug}", headers=self.headers, timeout=10)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def set_game_device(self, slug: str, rom_path: str, save_path: str, launch_command: str):
        r = httpx.put(
            f"{self.base_url}/games/{slug}/device",
            json={"rom_path": rom_path, "save_path": save_path, "launch_command": launch_command},
            headers=self.headers,
            timeout=10,
        )
        r.raise_for_status()

    def get_game_device(self, slug: str) -> Optional[Dict]:
        r = httpx.get(f"{self.base_url}/games/{slug}/device", headers=self.headers, timeout=10)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def get_save_meta(self, slug: str) -> Optional[Dict]:
        r = httpx.get(f"{self.base_url}/games/{slug}/save/meta", headers=self.headers, timeout=10)
        if r.status_code == 204:
            return None
        r.raise_for_status()
        return r.json()

    def get_lock(self, slug: str) -> Dict:
        r = httpx.get(f"{self.base_url}/games/{slug}/lock", headers=self.headers, timeout=10)
        r.raise_for_status()
        return r.json()

    def list_devices(self) -> List[Dict]:
        r = httpx.get(f"{self.base_url}/devices", headers=self.headers, timeout=10)
        r.raise_for_status()
        return r.json()
