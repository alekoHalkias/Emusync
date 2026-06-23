from __future__ import annotations

import platform
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import tomlkit

CONFIG_PATH = Path.home() / ".emusync" / "emusync.toml"


def _hostname() -> str:
    """Cross-platform machine name. `os.uname()` does not exist on Windows, and
    the project ships a Windows build, so use platform.node()."""
    return platform.node() or "emusync-device"


@dataclass
class Config:
    server_host: str = ""
    server_port: int = 8765
    data_dir: str = field(default_factory=lambda: str(Path.home() / ".emusync"))
    device_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    device_name: str = field(default_factory=_hostname)
    is_server: bool = False
    server_pin: str = ""
    recent_import_folders: dict = field(default_factory=dict)
    # Opt-in background save/state watcher in sync-daemon (issue #242).
    watch_saves: bool = False


def load() -> Config:
    if not CONFIG_PATH.exists():
        return Config()
    with open(CONFIG_PATH) as f:
        data = tomlkit.load(f)
    recent_folders = {}
    if "recent_import_folders" in data:
        recent_folders_data = data.get("recent_import_folders", {})
        for console_key, folders in recent_folders_data.items():
            recent_folders[console_key] = list(folders) if isinstance(folders, list) else []
    return Config(
        server_host=str(data.get("server_host", "")),
        server_port=int(data.get("server_port", 8765)),
        data_dir=str(data.get("data_dir", str(Path.home() / ".emusync"))),
        device_id=str(data.get("device_id", str(uuid.uuid4()))),
        device_name=str(data.get("device_name", _hostname())),
        is_server=bool(data.get("is_server", False)),
        server_pin=str(data.get("server_pin", "")),
        recent_import_folders=recent_folders,
        watch_saves=bool(data.get("watch_saves", False)),
    )


def save(cfg: Config) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    doc = tomlkit.document()
    doc.add("server_host", cfg.server_host)
    doc.add("server_port", cfg.server_port)
    doc.add("data_dir", cfg.data_dir)
    doc.add("device_id", cfg.device_id)
    doc.add("device_name", cfg.device_name)
    doc.add("is_server", cfg.is_server)
    if cfg.server_pin:
        doc.add("server_pin", cfg.server_pin)
    if cfg.watch_saves:
        doc.add("watch_saves", cfg.watch_saves)
    if cfg.recent_import_folders:
        doc.add("recent_import_folders", cfg.recent_import_folders)
    with open(CONFIG_PATH, "w") as f:
        tomlkit.dump(doc, f)
