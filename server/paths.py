"""Where EmuSync keeps its files (#564).

Single source of truth for the Python side; `gui/electron/paths.ts` mirrors it
(tests/test_paths.py checks they agree). Three roots:

- config: ``emusync.toml``, ``display.json``
- data:   everything else (db, blobs, game_cache, pid/token, logs, per-game art, ...)
- cache:  regenerable downloads (``switch_titledb.json``, console icons/logos)

Linux honours ``XDG_*_HOME``; ``EMUSYNC_{CONFIG,DATA,CACHE}_DIR`` override any
platform (used by tests and for running an isolated instance).
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_OVERRIDES = ("EMUSYNC_CONFIG_DIR", "EMUSYNC_DATA_DIR", "EMUSYNC_CACHE_DIR")

NOTE_NAME = "MOVED_TO_XDG.txt"

# Legacy ~/.emusync entries that belong in config / cache; the rest is data.
_CONFIG_FILES = ("emusync.toml", "display.json")
_CACHE_FILES = ("switch_titledb.json",)


def _base(kind: str) -> Path:
    override = os.environ.get(f"EMUSYNC_{kind.upper()}_DIR")
    if override:
        return Path(override)
    home = Path.home()
    if sys.platform == "win32":
        roaming = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
        local = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local")
        return (local / "emusync" / "cache") if kind == "cache" else (roaming / "emusync")
    if sys.platform == "darwin":
        lib = home / "Library"
        return (lib / "Caches" / "emusync") if kind == "cache" else (lib / "Application Support" / "emusync")
    xdg = {"config": ("XDG_CONFIG_HOME", ".config"),
           "data": ("XDG_DATA_HOME", ".local/share"),
           "cache": ("XDG_CACHE_HOME", ".cache")}[kind]
    root = os.environ.get(xdg[0])
    return (Path(root) if root and os.path.isabs(root) else home / xdg[1]) / "emusync"


def config_dir() -> Path:
    return _base("config")


def data_dir() -> Path:
    return _base("data")


def cache_dir() -> Path:
    return _base("cache")


def legacy_dir() -> Path:
    return Path.home() / ".emusync"


def _server_running(legacy: Path) -> bool:
    try:
        pid = int((legacy / ".server_pid").read_text().strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def _move(src: Path, dst: Path) -> None:
    """Move without ever overwriting; a directory merges into an existing one."""
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))  # rename on one filesystem, copy+delete across
    elif src.is_dir() and dst.is_dir():
        for child in list(src.iterdir()):
            _move(child, dst / child.name)
        try:
            src.rmdir()
        except OSError:
            pass
    # else: target exists — keep both, the old one stays behind in legacy_dir


def migrate_legacy() -> bool:
    """Move an existing ``~/.emusync`` into the XDG-style dirs. Idempotent and
    non-destructive: never overwrites, and refuses to run if a server is live
    from the old dir or the new data dir already holds a database. Returns
    True if anything moved. A no-op when an ``EMUSYNC_*_DIR`` override is set."""
    if any(os.environ.get(v) for v in _OVERRIDES):
        return False
    old = legacy_dir()
    if not old.is_dir():
        return False
    entries = [p for p in old.iterdir() if p.name != NOTE_NAME]
    if not entries or _server_running(old) or (data_dir() / "emusync.db").exists():
        return False

    cfg, data, cache = config_dir(), data_dir(), cache_dir()
    for p in entries:
        if p.name in _CONFIG_FILES or p.name.startswith("emusync.toml."):
            _move(p, cfg / p.name)
        elif p.name in _CACHE_FILES:
            _move(p, cache / p.name)
        elif p.name == "art" and (p / "consoles").exists():
            _move(p / "consoles", cache / "consoles")
            _move(p, data / "art")
        else:
            _move(p, data / p.name)

    _rewrite_data_dir(cfg / "emusync.toml", old, data)
    try:
        (old / NOTE_NAME).write_text(
            f"EmuSync moved its files (#564):\n  config: {cfg}\n  data:   {data}\n  cache:  {cache}\n"
            "Anything left in this folder could not be moved without overwriting.\n"
        )
    except OSError:
        pass
    return True


def _rewrite_data_dir(toml_path: Path, old: Path, new: Path) -> None:
    """A config saved by an old build pins data_dir to the legacy folder."""
    try:
        text = toml_path.read_text()
    except OSError:
        return
    import tomlkit
    try:
        doc = tomlkit.parse(text)
    except tomlkit.exceptions.TOMLKitError:
        return
    if str(doc.get("data_dir", "")) != str(old):
        return
    doc["data_dir"] = str(new)
    tmp = toml_path.with_name(toml_path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(tomlkit.dumps(doc))
    os.replace(tmp, toml_path)
