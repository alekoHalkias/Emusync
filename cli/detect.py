"""Emulator/core/ROM detection helpers for the console import wizard.

Mirrors the detection logic in gui/electron/main.ts so the CLI wizard matches
the GUI Add Console flow.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from cli.consoles_data import _IMPORT_SYSTEMS, _ROM_EXTENSIONS


def _parse_retroarch_cfg(cfg_path: str) -> dict[str, str]:
    """Parse key = "value" lines from a retroarch.cfg, expanding leading ~/."""
    out: dict[str, str] = {}
    if not os.path.exists(cfg_path):
        return out
    home = str(Path.home())
    with open(cfg_path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            m = re.match(r'^\s*(\w+)\s*=\s*"?([^"#\r\n]*)"?\s*$', line)
            if m:
                key, val = m.group(1).strip(), m.group(2).strip()
                if val.startswith("~/"):
                    val = os.path.join(home, val[2:])
                elif val == "~":
                    val = home
                out[key] = val
    return out


def _info_dir_candidates(cfg: dict[str, str], cores_dir: str) -> list[str]:
    """Candidate dirs for core .info metadata files, best source first (#400).
    Mirrors detect.ts's infoDirCandidates()."""
    candidates = [cfg.get("libretro_info_path", ""), cores_dir, "/usr/share/libretro/info"]
    return list(dict.fromkeys(c for c in candidates if c))


def _detect_retroarch() -> list[dict]:
    """Return list of detected RetroArch installs (native + flatpak)."""
    home = str(Path.home())
    infos: list[dict] = []

    # Native
    native_bins = ["/usr/bin/retroarch", "/usr/local/bin/retroarch",
                   os.path.join(home, ".local/bin/retroarch")]
    native_cfg = os.path.join(home, ".config/retroarch/retroarch.cfg")
    for bin_path in native_bins:
        if os.path.exists(bin_path):
            cfg = _parse_retroarch_cfg(native_cfg)
            rom_dir = cfg.get("rgui_browser_directory", "")
            if rom_dir == "default":
                rom_dir = ""
            cores_dir = cfg.get("libretro_directory") or os.path.join(home, ".config/retroarch/cores")
            infos.append({
                "type": "native",
                "label": "RetroArch",
                "exec_path": bin_path,
                "save_dir": cfg.get("savefile_directory") or os.path.join(home, ".config/retroarch/saves"),
                "states_dir": cfg.get("savestate_directory") or os.path.join(home, ".config/retroarch/states"),
                "cores_dir": cores_dir,
                "info_dirs": _info_dir_candidates(cfg, cores_dir),
                "rom_dirs": [rom_dir] if rom_dir else [],
            })
            break

    # Flatpak
    try:
        result = subprocess.run(
            ["flatpak", "list", "--app", "--columns=application"],
            capture_output=True, text=True, timeout=5,
        )
        if "org.libretro.RetroArch" in result.stdout:
            flat_cfg_path = os.path.join(
                home, ".var/app/org.libretro.RetroArch/config/retroarch/retroarch.cfg"
            )
            cfg = _parse_retroarch_cfg(flat_cfg_path)
            rom_dir = cfg.get("rgui_browser_directory", "")
            if rom_dir == "default":
                rom_dir = ""
            cores_dir = cfg.get("libretro_directory") or os.path.join(
                home, ".var/app/org.libretro.RetroArch/data/retroarch/cores")
            infos.append({
                "type": "flatpak",
                "label": "RetroArch (Flatpak)",
                "exec_path": "flatpak run org.libretro.RetroArch",
                "save_dir": cfg.get("savefile_directory") or os.path.join(
                    home, ".var/app/org.libretro.RetroArch/config/retroarch/saves"),
                "states_dir": cfg.get("savestate_directory") or os.path.join(
                    home, ".var/app/org.libretro.RetroArch/config/retroarch/states"),
                "cores_dir": cores_dir,
                "info_dirs": _info_dir_candidates(cfg, cores_dir),
                "rom_dirs": [rom_dir] if rom_dir else [],
            })
    except Exception:
        pass

    return infos


def _find_installed_cores(cores_dir: str, system: dict) -> list[dict]:
    """Every core whose .so exists in cores_dir, in list order — all of them,
    not just the first, so alternate cores show as options (#400)."""
    found: list[dict] = []
    for core in system["cores"]:
        so_path = os.path.join(cores_dir, f"{core['lib']}.so")
        if os.path.exists(so_path):
            found.append({"lib": so_path, "folder": core["folder"]})
    return found


def _discover_cores_by_info(cores_dir: str, info_dirs: list[str], databases: list[str]) -> list[dict]:
    """Discover installed cores for a console from RetroArch's own .info
    metadata (#400): each core ships a `<lib>.info` whose `database` field names
    the systems it runs (pipe-separated libretro database names) and whose
    `corename` is the exact name RetroArch uses for `saves/<CoreName>/`.
    Matching that against the console def's `databases` recognizes ANY core for
    a supported console — including ones not in the hardcoded seed lists.
    Mirrors detect.ts's discoverCoresByInfo()."""
    if not databases or not os.path.isdir(cores_dir):
        return []
    wanted = set(databases)
    found: list[dict] = []
    try:
        so_files = sorted(f for f in os.listdir(cores_dir) if f.endswith(".so"))
    except OSError:
        return []
    for so in so_files:
        base = so[:-3]  # strip ".so"
        info_path = next(
            (p for d in info_dirs if os.path.exists(p := os.path.join(d, f"{base}.info"))), None)
        if not info_path:
            continue
        info = _parse_retroarch_cfg(info_path)  # same key = "value" format
        corename = info.get("corename", "")
        db_names = {db.strip() for db in info.get("database", "").split("|")}
        if not corename or not (db_names & wanted):
            continue
        found.append({"lib": os.path.join(cores_dir, so), "folder": corename})
    return found


def _expand_home(path: str) -> str:
    """Expand a leading `~/` or bare `~`, mirroring detect.ts's `expand()` — os.path
    functions never do shell-style expansion on their own."""
    if not path:
        return path
    home = str(Path.home())
    if path == "~":
        return home
    if path.startswith("~/"):
        return os.path.join(home, path[2:])
    return path


def _detect_emulators_for_console(console_def: dict) -> list[dict]:
    """Detect installed emulators/cores for a console. Mirrors detectEmulatorsForConsole in main.ts."""
    home = str(Path.home())
    options: list[dict] = []

    # RetroArch. Every installed core for this console: the seeded core lists
    # first (preferred order), then any extra cores discovered via .info
    # metadata — so an unlisted-but-valid core still shows up with the right
    # save folder (#400). Mirrors detectEmulatorsForConsole in detect.ts.
    for ra in _detect_retroarch():
        cores: list[dict] = []
        seen_cores: set[str] = set()

        def _add(core: dict) -> None:
            if core["lib"] not in seen_cores:
                seen_cores.add(core["lib"])
                cores.append(core)

        for sys_key in console_def["system_keys"]:
            system = _IMPORT_SYSTEMS.get(sys_key)
            if system:
                for core in _find_installed_cores(ra["cores_dir"], system):
                    _add(core)
        for core in _discover_cores_by_info(
                ra["cores_dir"], ra["info_dirs"], console_def.get("databases", [])):
            _add(core)

        for core in cores:
            options.append({
                "id": f"{ra['type']}-{core['folder'].lower().replace(' ', '-')}",
                "label": f"{ra['label']} · {core['folder']}",
                "exec_path": ra["exec_path"],
                "save_dir": os.path.join(ra["save_dir"], core["folder"]),
                "state_dir": os.path.join(ra["states_dir"], core["folder"]),
                "core_path": core["lib"],
                "core_folder": core["folder"],
                "rom_dirs": ra["rom_dirs"],
            })

    # Standalone emulators. `dirs` carries `~`-templated save/state/memcard paths
    # per launch flavour (native/flatpak) — mirrors detect.ts's `expand()` handling
    # of StandaloneDef.dirs (issue #292).
    flatpak_list: str | None = None
    for s in console_def.get("standalones", []):
        dirs = s.get("dirs", {})
        found = False
        for bin_path in s["native_bins"]:
            if os.path.exists(_expand_home(bin_path)):
                native_dirs = dirs.get("native", {})
                options.append({
                    "id": f"{s['id']}-native",
                    "label": s["label"],
                    "exec_path": _expand_home(bin_path),
                    "save_dir": _expand_home(native_dirs.get("save", "")),
                    "state_dir": _expand_home(native_dirs["state"]) if native_dirs.get("state") else None,
                    "core_path": None,
                    "core_folder": None,
                    "rom_dirs": [],
                })
                found = True
                break
        if not found and s.get("flatpak_id"):
            if flatpak_list is None:
                try:
                    r = subprocess.run(
                        ["flatpak", "list", "--app", "--columns=application"],
                        capture_output=True, text=True, timeout=5,
                    )
                    flatpak_list = r.stdout
                except Exception:
                    flatpak_list = ""
            if s["flatpak_id"] in flatpak_list:
                flatpak_dirs = dirs.get("flatpak", {})
                default_save = os.path.join(home, f".var/app/{s['flatpak_id']}/data/{s['id']}/saves")
                options.append({
                    "id": f"{s['id']}-flatpak",
                    "label": f"{s['label']} (Flatpak)",
                    "exec_path": s["flatpak_exec"],
                    "save_dir": _expand_home(flatpak_dirs.get("save", "")) or default_save,
                    "state_dir": _expand_home(flatpak_dirs["state"]) if flatpak_dirs.get("state") else None,
                    "core_path": None,
                    "core_folder": None,
                    "rom_dirs": [],
                })

    return options


def _scan_rom_dir(directory: str, depth: int = 0) -> list[str]:
    """Recursively collect ROM files (depth ≤ 3)."""
    if depth > 3:
        return []
    roms: list[str] = []
    try:
        with os.scandir(directory) as it:
            for entry in it:
                if entry.is_file():
                    ext = os.path.splitext(entry.name)[1].lstrip(".").lower()
                    if ext in _ROM_EXTENSIONS:
                        roms.append(entry.path)
                elif entry.is_dir():
                    roms.extend(_scan_rom_dir(entry.path, depth + 1))
    except PermissionError:
        pass
    return roms


def _match_save_file(save_dir: str, base_name: str, exts: list[str]) -> dict:
    """Find save file in save_dir matching base_name + any extension."""
    for ext in exts:
        p = os.path.join(save_dir, f"{base_name}.{ext}")
        if os.path.exists(p):
            return {"path": p, "exists": True}
    return {"path": os.path.join(save_dir, f"{base_name}.{exts[0]}"), "exists": False}


# Fallback filename per shared-memcard console when the memcards folder can't be
# scanned or is empty (mirrors scan.ts's SHARED_MEMCARD_FALLBACK, issue #314).
_SHARED_MEMCARD_FALLBACK: dict[str, str] = {"PS2": "Mcd001.ps2"}


def _find_first_by_ext(dir_path: str, ext: str) -> str | None:
    """First entry (file or folder) in dir_path whose name ends in ext, or None.
    Mirrors scan.ts's findFirstByExt()."""
    try:
        with os.scandir(dir_path) as it:
            for entry in it:
                if entry.name.lower().endswith(ext):
                    return entry.path
    except OSError:
        pass
    return None


def _dir_has_any_file(dir_path: str) -> bool:
    """True if dir_path contains at least one file. Mirrors scan.ts's use of
    findLatestFileInDir() as an existence check."""
    try:
        with os.scandir(dir_path) as it:
            return any(entry.is_file() for entry in it)
    except OSError:
        return False


def _resolve_shared_memcard_save_state(emu: dict, console_abbr: str) -> tuple[dict, dict | None]:
    """Resolve the shared save/state location for a shared-memcard console (PS2):
    the memcard is one file/folder per console, not one per game. Mirrors the
    `isSharedMemcard` branch in scan.ts (issue #295)."""
    save_dir = emu["save_dir"]
    found = _find_first_by_ext(save_dir, ".ps2")
    card_path = found or os.path.join(save_dir, _SHARED_MEMCARD_FALLBACK.get(console_abbr, "Mcd001.ps2"))
    save_match = {"path": card_path, "exists": os.path.exists(card_path)}

    state_match: dict | None = None
    if emu.get("state_dir"):
        state_dir = emu["state_dir"]
        state_match = {"path": state_dir, "exists": _dir_has_any_file(state_dir)}
    return save_match, state_match
