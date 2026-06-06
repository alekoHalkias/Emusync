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
            infos.append({
                "type": "native",
                "label": "RetroArch",
                "exec_path": bin_path,
                "save_dir": cfg.get("savefile_directory") or os.path.join(home, ".config/retroarch/saves"),
                "states_dir": cfg.get("savestate_directory") or os.path.join(home, ".config/retroarch/states"),
                "cores_dir": cfg.get("libretro_directory") or os.path.join(home, ".config/retroarch/cores"),
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
            infos.append({
                "type": "flatpak",
                "label": "RetroArch (Flatpak)",
                "exec_path": "flatpak run org.libretro.RetroArch",
                "save_dir": cfg.get("savefile_directory") or os.path.join(
                    home, ".var/app/org.libretro.RetroArch/config/retroarch/saves"),
                "states_dir": cfg.get("savestate_directory") or os.path.join(
                    home, ".var/app/org.libretro.RetroArch/config/retroarch/states"),
                "cores_dir": cfg.get("libretro_directory") or os.path.join(
                    home, ".var/app/org.libretro.RetroArch/data/retroarch/cores"),
                "rom_dirs": [rom_dir] if rom_dir else [],
            })
    except Exception:
        pass

    return infos


def _find_installed_core(cores_dir: str, system: dict) -> dict | None:
    """Return first core whose .so exists in cores_dir, or None."""
    for core in system["cores"]:
        so_path = os.path.join(cores_dir, f"{core['lib']}.so")
        if os.path.exists(so_path):
            return {"lib": so_path, "folder": core["folder"]}
    return None


def _detect_emulators_for_console(console_def: dict) -> list[dict]:
    """Detect installed emulators/cores for a console. Mirrors detectEmulatorsForConsole in main.ts."""
    home = str(Path.home())
    options: list[dict] = []

    # RetroArch
    seen_cores: set[str] = set()
    for ra in _detect_retroarch():
        for sys_key in console_def["system_keys"]:
            system = _IMPORT_SYSTEMS.get(sys_key)
            if not system:
                continue
            core = _find_installed_core(ra["cores_dir"], system)
            if not core or core["lib"] in seen_cores:
                continue
            seen_cores.add(core["lib"])
            save_dir = os.path.join(ra["save_dir"], core["folder"])
            state_dir = os.path.join(ra["states_dir"], core["folder"])
            options.append({
                "id": f"{ra['type']}-{core['folder'].lower().replace(' ', '-')}",
                "label": f"{ra['label']} · {core['folder']}",
                "exec_path": ra["exec_path"],
                "save_dir": save_dir,
                "state_dir": state_dir,
                "core_path": core["lib"],
                "core_folder": core["folder"],
                "rom_dirs": ra["rom_dirs"],
            })

    # Standalone emulators
    flatpak_list: str | None = None
    for s in console_def.get("standalones", []):
        found = False
        for bin_path in s["native_bins"]:
            if os.path.exists(bin_path):
                options.append({
                    "id": f"{s['id']}-native",
                    "label": s["label"],
                    "exec_path": bin_path,
                    "save_dir": s["save_dir"],
                    "state_dir": None,
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
                options.append({
                    "id": f"{s['id']}-flatpak",
                    "label": f"{s['label']} (Flatpak)",
                    "exec_path": s["flatpak_exec"],
                    "save_dir": os.path.join(
                        home, f".var/app/{s['flatpak_id']}/data/{s['id']}/saves"),
                    "state_dir": None,
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
