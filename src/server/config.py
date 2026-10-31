from __future__ import annotations

import os
import platform
import sys
import time
import uuid
from dataclasses import dataclass, field

import tomlkit

from server import paths

CONFIG_PATH = paths.config_dir() / "emusync.toml"


def _hostname() -> str:
    """Cross-platform machine name. `os.uname()` does not exist on Windows, and
    the project ships a Windows build, so use platform.node()."""
    return platform.node() or "emusync-device"


def _backup_path():
    return paths.data_dir() / "device_id"


def _restore_device_id() -> str:
    """device_id from the data-dir backup, else a fresh UUID. Keeps a device's
    identity when emusync.toml is lost or corrupt (#656)."""
    try:
        return str(uuid.UUID(_backup_path().read_text().strip()))
    except (OSError, ValueError):
        return str(uuid.uuid4())


def _write_private(path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.replace(tmp, path)


@dataclass
class Config:
    server_host: str = ""
    server_port: int = 8765
    data_dir: str = field(default_factory=lambda: str(paths.data_dir()))
    device_id: str = field(default_factory=_restore_device_id)
    device_name: str = field(default_factory=_hostname)
    is_server: bool = False
    server_pin: str = ""
    recent_import_folders: dict = field(default_factory=dict)
    # Opt-in background save/state watcher in sync-daemon (issue #242).
    watch_saves: bool = False
    # Auto-fetch game metadata (synopsis/release date) from Wikipedia (issue #578).
    auto_fetch_metadata: bool = True
    # Per-console remembered import ROM source + local-copy destination (issue #255).
    import_rom_source: dict = field(default_factory=dict)
    import_local_folder: dict = field(default_factory=dict)
    # Per-console ROM paths hidden from the import wizard (issue #646).
    import_ignored_roms: dict = field(default_factory=dict)
    # Per-console SteamGridDB artwork type to fetch/display: grid/hero/logo/icon (issue #324).
    art_type_by_console: dict = field(default_factory=dict)


def _int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load() -> Config:
    paths.migrate_legacy()  # #564: first run after upgrading from ~/.emusync
    if not CONFIG_PATH.exists():
        return Config()
    try:
        with open(CONFIG_PATH) as f:
            data = tomlkit.load(f)
    except tomlkit.exceptions.TOMLKitError as e:
        # Corrupt, not missing: keep the bad file instead of letting the next save() clobber it.
        backup = CONFIG_PATH.with_name(f"{CONFIG_PATH.name}.corrupt-{int(time.time() * 1000)}")
        os.replace(CONFIG_PATH, backup)
        print(f"EmuSync: config unreadable ({e}); saved as {backup}, using defaults.", file=sys.stderr)
        return Config()
    recent_folders = {}
    if "recent_import_folders" in data:
        recent_folders_data = data.get("recent_import_folders", {})
        for console_key, folders in recent_folders_data.items():
            recent_folders[console_key] = list(folders) if isinstance(folders, list) else []
    return Config(
        server_host=str(data.get("server_host", "")),
        server_port=_int(data.get("server_port"), 8765),
        data_dir=str(data.get("data_dir", str(paths.data_dir()))),
        device_id=str(data.get("device_id") or _restore_device_id()),
        device_name=str(data.get("device_name", _hostname())),
        is_server=bool(data.get("is_server", False)),
        server_pin=str(data.get("server_pin", "")),
        recent_import_folders=recent_folders,
        watch_saves=bool(data.get("watch_saves", False)),
        import_rom_source=dict(data.get("import_rom_source", {})),
        import_ignored_roms=dict(data.get("import_ignored_roms", {})),
        import_local_folder=dict(data.get("import_local_folder", {})),
        art_type_by_console=dict(data.get("art_type_by_console", {})),
        auto_fetch_metadata=bool(data.get("auto_fetch_metadata", True)),
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
    if not cfg.auto_fetch_metadata:  # default True; only persist the opt-out
        doc.add("auto_fetch_metadata", False)
    if cfg.recent_import_folders:
        doc.add("recent_import_folders", cfg.recent_import_folders)
    if cfg.import_rom_source:
        doc.add("import_rom_source", cfg.import_rom_source)
    if cfg.import_local_folder:
        doc.add("import_local_folder", cfg.import_local_folder)
    if cfg.import_ignored_roms:
        doc.add("import_ignored_roms", cfg.import_ignored_roms)
    if cfg.art_type_by_console:
        doc.add("art_type_by_console", cfg.art_type_by_console)
    # Atomic + owner-only (server_pin is stored in plaintext).
    tmp = CONFIG_PATH.with_name(CONFIG_PATH.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        tomlkit.dump(doc, f)
    os.replace(tmp, CONFIG_PATH)
    try:
        backup = _backup_path()
        if not backup.exists() or backup.read_text().strip() != cfg.device_id:
            backup.parent.mkdir(parents=True, exist_ok=True)
            _write_private(backup, cfg.device_id)
    except OSError:
        pass  # backup is best-effort; the toml is authoritative
