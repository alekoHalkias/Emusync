"""Hardcoded console/system/core definitions used by the import wizard and
seeded into the server's global definition tables on startup."""
from __future__ import annotations

# Standalone-emulator definitions. Dir templates use a leading `~` (the running
# device's home), expanded client-side in detect.ts — never the server's home —
# so a save dir resolves correctly on whichever device runs the emulator (#292).
_MGBA = {
    "id": "mgba", "label": "mGBA",
    "native_bins": ["/usr/bin/mgba-qt", "/usr/bin/mgba", "~/.local/bin/mgba-qt"],
    "flatpak_id": "io.mgba.mGBA",
    "flatpak_exec": "flatpak run io.mgba.mGBA",
    "dirs": {
        "native":  {"save": "~/.local/share/mGBA/saves"},
        "flatpak": {"save": "~/.var/app/io.mgba.mGBA/data/mGBA/saves"},
    },
}

# PCSX2 (PS2) — standalone only; no usable libretro core. `-batch -fullscreen`
# boots the disc straight into fullscreen without the picker UI. The save dir is
# the shared memory-card folder and state dir the shared save-state folder; PS2
# save/state sync is handled in later stages (#294/#295). (Issue #293.)
_PCSX2 = {
    "id": "pcsx2", "label": "PCSX2",
    "native_bins": ["/usr/bin/pcsx2-qt", "/usr/bin/pcsx2", "~/.local/bin/pcsx2-qt",
                    "~/Applications/PCSX2.AppImage", "~/.local/bin/pcsx2.AppImage"],
    "flatpak_id": "net.pcsx2.PCSX2",
    "flatpak_exec": "flatpak run net.pcsx2.PCSX2",
    "launch_args": ["-batch", "-fullscreen"],
    "dirs": {
        "native": {
            "save":    "~/.config/PCSX2/memcards",
            "state":   "~/.config/PCSX2/sstates",
            "memcard": "~/.config/PCSX2/memcards",
        },
        "flatpak": {
            "save":    "~/.var/app/net.pcsx2.PCSX2/config/PCSX2/memcards",
            "state":   "~/.var/app/net.pcsx2.PCSX2/config/PCSX2/sstates",
            "memcard": "~/.var/app/net.pcsx2.PCSX2/config/PCSX2/memcards",
        },
    },
}

# Dolphin (GameCube/Wii) standalone. `-b` runs headless/batch and requires the
# ROM path, passed positionally like the other standalones (issue #415). Save
# dir is the GC memory-card folder directly (no "User/GC" subpath — that's a
# RetroArch-core-only layout); Wii NAND title saves stay out of scope, same as
# the RetroArch core.
_DOLPHIN = {
    "id": "dolphin", "label": "Dolphin",
    "native_bins": ["/usr/bin/dolphin-emu", "/usr/bin/dolphin-emu-qt2",
                    "~/.local/bin/dolphin-emu", "~/Applications/Dolphin.AppImage"],
    "flatpak_id": "org.DolphinEmu.dolphin-emu",
    "flatpak_exec": "flatpak run org.DolphinEmu.dolphin-emu",
    "launch_args": ["-b"],
    "dirs": {
        "native": {
            "save":  "~/.local/share/dolphin-emu/GC",
            "state": "~/.local/share/dolphin-emu/StateSaves",
        },
        "flatpak": {
            "save":  "~/.var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/GC",
            "state": "~/.var/app/org.DolphinEmu.dolphin-emu/data/dolphin-emu/StateSaves",
        },
    },
}

# Azahar (3DS) standalone — no usable libretro core. Citra (the original
# standalone) was taken down by Nintendo; Azahar is the maintained successor
# (merger of the Lime3DS and PabloMK7 Citra forks) and keeps Citra's exact
# user-data layout, just renamed `azahar-emu`. Save data lives nested under
# sdmc/Nintendo 3DS/<ID0>/<ID1>/title/ — the ID0/ID1 hash folders are usually
# all-zeros for a single local profile but not guaranteed, so `dirs.*.save`
# points at the SD-card root (one level up) and the ID0/ID1/title path is
# resolved by probing for an existing folder first (see detect.py), falling
# back to the well-documented all-zeros default (issue #418).
_AZAHAR = {
    "id": "azahar", "label": "Azahar",
    "native_bins": ["/usr/bin/azahar", "~/.local/bin/azahar",
                    "~/Applications/azahar.AppImage"],
    "flatpak_id": "org.azahar_emu.Azahar",
    "flatpak_exec": "flatpak run org.azahar_emu.Azahar",
    "dirs": {
        "native":  {"save": "~/.local/share/azahar-emu/sdmc/Nintendo 3DS"},
        "flatpak": {"save": "~/.var/app/org.azahar_emu.Azahar/data/azahar-emu/sdmc/Nintendo 3DS"},
    },
}

# `databases` = the libretro database names for the console, matched against an
# installed core's .info `database` field so ANY core for the console (present
# or future) is recognized without being hardcoded in a core list (#400).
_IMPORT_CONSOLES = [
    {"key": "gba",     "label": "Game Boy Advance",          "abbr": "GBA",
     "system_keys": ["gba"],
     "databases": ["Nintendo - Game Boy Advance"],
     "standalones": [_MGBA],
     "suggestions": ["RetroArch with mGBA core", "mGBA standalone"]},
    {"key": "gb",      "label": "Game Boy / Game Boy Color", "abbr": "GB",
     "system_keys": ["gb", "gbc"],
     "databases": ["Nintendo - Game Boy", "Nintendo - Game Boy Color"],
     "standalones": [_MGBA],
     "suggestions": ["RetroArch with Gambatte or mGBA core", "mGBA standalone"]},
    {"key": "snes",    "label": "Super Nintendo (SNES)",      "abbr": "SNES",
     "system_keys": ["sfc", "smc"],
     "databases": ["Nintendo - Super Nintendo Entertainment System"],
     "standalones": [], "suggestions": ["RetroArch with Snes9x core"]},
    {"key": "nes",     "label": "NES / Famicom",              "abbr": "NES",
     "system_keys": ["nes", "fds"],
     "databases": ["Nintendo - Nintendo Entertainment System",
                   "Nintendo - Family Computer Disk System"],
     "standalones": [], "suggestions": ["RetroArch with Nestopia UE or FCEUmm core"]},
    {"key": "n64",     "label": "Nintendo 64",                "abbr": "N64",
     "system_keys": ["n64", "z64", "v64"],
     "databases": ["Nintendo - Nintendo 64", "Nintendo - Nintendo 64DD"],
     "standalones": [], "suggestions": ["RetroArch with Mupen64Plus-Next core"]},
    {"key": "nds",     "label": "Nintendo DS",                "abbr": "NDS",
     "system_keys": ["nds"],
     "databases": ["Nintendo - Nintendo DS", "Nintendo - Nintendo DSi"],
     "standalones": [], "suggestions": ["RetroArch with melonDS or DeSmuME core"]},
    {"key": "genesis", "label": "Sega Genesis / Mega Drive",  "abbr": "Genesis",
     "system_keys": ["md", "smd", "gen"],
     "databases": ["Sega - Mega Drive - Genesis"],
     "standalones": [], "suggestions": ["RetroArch with Genesis Plus GX core"]},
    {"key": "sms",     "label": "Master System / Game Gear",  "abbr": "SMS",
     "system_keys": ["sms", "gg"],
     "databases": ["Sega - Master System - Mark III", "Sega - Game Gear"],
     "standalones": [], "suggestions": ["RetroArch with Genesis Plus GX core"]},
    {"key": "pce",     "label": "PC Engine",                  "abbr": "PCE",
     "system_keys": ["pce"],
     "databases": ["NEC - PC Engine - TurboGrafx 16", "NEC - PC Engine SuperGrafx"],
     "standalones": [], "suggestions": ["RetroArch with Beetle PCE core"]},
    {"key": "psx",     "label": "PlayStation",                "abbr": "PSX",
     "system_keys": ["iso", "bin", "cue", "chd", "pbp"],
     "databases": ["Sony - PlayStation"],
     "standalones": [], "suggestions": ["RetroArch with PCSX-ReARMed or Beetle PSX HW core"]},
    # PS2 is standalone-only (no libretro core), so it has no `system_keys`
    # (which would otherwise surface PS1's disc cores for shared .iso/.chd). Its
    # scannable extensions are declared explicitly via `rom_extensions` (#293).
    {"key": "ps2",     "label": "PlayStation 2",              "abbr": "PS2",
     "system_keys": [],
     "rom_extensions": ["iso", "chd", "bin"],
     "databases": ["Sony - PlayStation 2"],
     "standalones": [_PCSX2], "suggestions": ["PCSX2 standalone"]},
    # dc / gamecube / psp (#402) follow the PS2 pattern: no `system_keys` (so
    # PSX's disc cores never surface for shared .iso/.chd/.bin), explicit
    # `rom_extensions`, cores matched purely via `databases` ↔ .info files
    # (#400). All three are shared-save consoles (console-scoped card, see
    # _SHARED_MEMCARD_CONSOLES / usesSharedSaveLayout); states are normal
    # per-content RetroArch states.
    {"key": "dc",      "label": "Sega Dreamcast",             "abbr": "DC",
     "system_keys": [],
     "rom_extensions": ["gdi", "cdi", "chd", "cue"],
     "databases": ["Sega - Dreamcast"],
     "standalones": [], "suggestions": ["RetroArch with Flycast core"]},
    {"key": "gamecube", "label": "GameCube / Wii",            "abbr": "GC",
     "system_keys": [],
     "rom_extensions": ["iso", "gcm", "rvz", "wbfs"],
     "databases": ["Nintendo - GameCube", "Nintendo - Wii"],
     "standalones": [_DOLPHIN],
     "suggestions": ["RetroArch with Dolphin core", "Dolphin standalone"]},
    {"key": "psp",     "label": "PlayStation Portable",       "abbr": "PSP",
     "system_keys": [],
     "rom_extensions": ["iso", "cso", "pbp"],
     "databases": ["Sony - PlayStation Portable"],
     "standalones": [], "suggestions": ["RetroArch with PPSSPP core"]},
    # 3DS is standalone-only (no viable libretro core) and shares the
    # PS2/dc/gamecube/psp shared-save-layout pattern — Azahar's SD-card save
    # tree nests per-title, same shape as PSP's SAVEDATA folder (#418).
    {"key": "3ds",     "label": "Nintendo 3DS",               "abbr": "3DS",
     "system_keys": [],
     "rom_extensions": ["3ds", "cci", "cxi"],
     "databases": ["Nintendo - Nintendo 3DS"],
     "standalones": [_AZAHAR], "suggestions": ["Azahar standalone"]},
]

_IMPORT_SYSTEMS: dict[str, dict] = {
    "gba": {"name": "Game Boy Advance", "save_exts": ["sav", "srm"],
            "cores": [{"lib": "mgba_libretro", "folder": "mGBA"},
                      {"lib": "vba_next_libretro", "folder": "VBA Next"},
                      {"lib": "vbam_libretro", "folder": "VBA-M"},
                      {"lib": "gpsp_libretro", "folder": "gpSP"},
                      {"lib": "mednafen_gba_libretro", "folder": "Beetle GBA"}]},
    "gb":  {"name": "Game Boy", "save_exts": ["sav", "srm"],
            "cores": [{"lib": "gambatte_libretro", "folder": "Gambatte"},
                      {"lib": "mgba_libretro", "folder": "mGBA"},
                      {"lib": "gearboy_libretro", "folder": "Gearboy"},
                      {"lib": "sameboy_libretro", "folder": "SameBoy"},
                      {"lib": "tgbdual_libretro", "folder": "TGB Dual"}]},
    "gbc": {"name": "Game Boy Color", "save_exts": ["sav", "srm"],
            "cores": [{"lib": "gambatte_libretro", "folder": "Gambatte"},
                      {"lib": "mgba_libretro", "folder": "mGBA"},
                      {"lib": "gearboy_libretro", "folder": "Gearboy"},
                      {"lib": "sameboy_libretro", "folder": "SameBoy"},
                      {"lib": "tgbdual_libretro", "folder": "TGB Dual"}]},
    "sfc": {"name": "SNES", "save_exts": ["srm", "sav"],
            "cores": [{"lib": "snes9x_libretro", "folder": "Snes9x"},
                      {"lib": "bsnes_libretro", "folder": "bsnes"},
                      {"lib": "snes9x2010_libretro", "folder": "Snes9x 2010"},
                      {"lib": "snes9x2005_plus_libretro", "folder": "Snes9x 2005 Plus"},
                      {"lib": "snes9x2005_libretro", "folder": "Snes9x 2005"},
                      {"lib": "mesen-s_libretro", "folder": "Mesen-S"},
                      {"lib": "bsnes_hd_beta_libretro", "folder": "bsnes-hd beta"}]},
    "smc": {"name": "SNES", "save_exts": ["srm", "sav"],
            "cores": [{"lib": "snes9x_libretro", "folder": "Snes9x"},
                      {"lib": "bsnes_libretro", "folder": "bsnes"},
                      {"lib": "snes9x2010_libretro", "folder": "Snes9x 2010"},
                      {"lib": "snes9x2005_plus_libretro", "folder": "Snes9x 2005 Plus"},
                      {"lib": "snes9x2005_libretro", "folder": "Snes9x 2005"},
                      {"lib": "mesen-s_libretro", "folder": "Mesen-S"},
                      {"lib": "bsnes_hd_beta_libretro", "folder": "bsnes-hd beta"}]},
    "nes": {"name": "NES", "save_exts": ["sav", "srm"],
            "cores": [{"lib": "nestopia_libretro", "folder": "Nestopia UE"},
                      {"lib": "fceumm_libretro", "folder": "FCEUmm"},
                      {"lib": "mesen_libretro", "folder": "Mesen"},
                      {"lib": "quicknes_libretro", "folder": "QuickNES"}]},
    "fds": {"name": "Famicom Disk System", "save_exts": ["sav", "srm"],
            "cores": [{"lib": "nestopia_libretro", "folder": "Nestopia UE"},
                      {"lib": "fceumm_libretro", "folder": "FCEUmm"},
                      {"lib": "mesen_libretro", "folder": "Mesen"}]},
    "n64": {"name": "Nintendo 64", "save_exts": ["srm", "sav", "eep", "mpk"],
            "cores": [{"lib": "mupen64plus_next_libretro", "folder": "Mupen64Plus-Next"},
                      {"lib": "parallel_n64_libretro", "folder": "ParaLLEl N64"}]},
    "z64": {"name": "Nintendo 64", "save_exts": ["srm", "sav", "eep", "mpk"],
            "cores": [{"lib": "mupen64plus_next_libretro", "folder": "Mupen64Plus-Next"},
                      {"lib": "parallel_n64_libretro", "folder": "ParaLLEl N64"}]},
    "v64": {"name": "Nintendo 64", "save_exts": ["srm", "sav", "eep", "mpk"],
            "cores": [{"lib": "mupen64plus_next_libretro", "folder": "Mupen64Plus-Next"},
                      {"lib": "parallel_n64_libretro", "folder": "ParaLLEl N64"}]},
    "nds": {"name": "Nintendo DS", "save_exts": ["sav", "dsv", "srm"],
            "cores": [{"lib": "melonds_libretro", "folder": "melonDS"},
                      {"lib": "melondsds_libretro", "folder": "melonDS DS"},
                      {"lib": "desmume_libretro", "folder": "DeSmuME"},
                      {"lib": "desmume2015_libretro", "folder": "DeSmuME 2015"}]},
    "md":  {"name": "Sega Genesis", "save_exts": ["srm", "sav"],
            "cores": [{"lib": "genesis_plus_gx_libretro", "folder": "Genesis Plus GX"},
                      {"lib": "picodrive_libretro", "folder": "PicoDrive"},
                      {"lib": "blastem_libretro", "folder": "BlastEm"}]},
    "smd": {"name": "Sega Genesis", "save_exts": ["srm", "sav"],
            "cores": [{"lib": "genesis_plus_gx_libretro", "folder": "Genesis Plus GX"},
                      {"lib": "picodrive_libretro", "folder": "PicoDrive"},
                      {"lib": "blastem_libretro", "folder": "BlastEm"}]},
    "gen": {"name": "Sega Genesis", "save_exts": ["srm", "sav"],
            "cores": [{"lib": "genesis_plus_gx_libretro", "folder": "Genesis Plus GX"},
                      {"lib": "picodrive_libretro", "folder": "PicoDrive"},
                      {"lib": "blastem_libretro", "folder": "BlastEm"}]},
    "sms": {"name": "Sega Master System", "save_exts": ["srm", "sav"],
            "cores": [{"lib": "genesis_plus_gx_libretro", "folder": "Genesis Plus GX"},
                      {"lib": "picodrive_libretro", "folder": "PicoDrive"},
                      {"lib": "gearsystem_libretro", "folder": "Gearsystem"},
                      {"lib": "smsplus_libretro", "folder": "SMS Plus GX"}]},
    "gg":  {"name": "Game Gear", "save_exts": ["srm", "sav"],
            "cores": [{"lib": "genesis_plus_gx_libretro", "folder": "Genesis Plus GX"},
                      {"lib": "gearsystem_libretro", "folder": "Gearsystem"},
                      {"lib": "smsplus_libretro", "folder": "SMS Plus GX"}]},
    "pce": {"name": "PC Engine", "save_exts": ["srm", "sav"],
            "cores": [{"lib": "mednafen_pce_libretro", "folder": "Beetle PCE"},
                      {"lib": "mednafen_pce_fast_libretro", "folder": "Beetle PCE Fast"},
                      {"lib": "mednafen_supergrafx_libretro", "folder": "Beetle SuperGrafx"}]},
    # Flycast was removed from the disc systems (#400): it's a Dreamcast core,
    # and these systems back the PSX console — it matched the wrong console.
    "iso": {"name": "Disc", "save_exts": ["mcr", "srm", "sav"],
            "cores": [{"lib": "pcsx_rearmed_libretro", "folder": "PCSX-ReARMed"},
                      {"lib": "mednafen_psx_hw_libretro", "folder": "Beetle PSX HW"},
                      {"lib": "mednafen_psx_libretro", "folder": "Beetle PSX"},
                      {"lib": "swanstation_libretro", "folder": "SwanStation"}]},
    "bin": {"name": "Disc", "save_exts": ["mcr", "srm", "sav"],
            "cores": [{"lib": "pcsx_rearmed_libretro", "folder": "PCSX-ReARMed"},
                      {"lib": "mednafen_psx_hw_libretro", "folder": "Beetle PSX HW"},
                      {"lib": "mednafen_psx_libretro", "folder": "Beetle PSX"},
                      {"lib": "swanstation_libretro", "folder": "SwanStation"}]},
    "cue": {"name": "Disc", "save_exts": ["mcr", "srm", "sav"],
            "cores": [{"lib": "pcsx_rearmed_libretro", "folder": "PCSX-ReARMed"},
                      {"lib": "mednafen_psx_hw_libretro", "folder": "Beetle PSX HW"},
                      {"lib": "mednafen_psx_libretro", "folder": "Beetle PSX"},
                      {"lib": "swanstation_libretro", "folder": "SwanStation"}]},
    "chd": {"name": "Disc (CHD)", "save_exts": ["mcr", "srm", "sav"],
            "cores": [{"lib": "pcsx_rearmed_libretro", "folder": "PCSX-ReARMed"},
                      {"lib": "mednafen_psx_hw_libretro", "folder": "Beetle PSX HW"},
                      {"lib": "mednafen_psx_libretro", "folder": "Beetle PSX"},
                      {"lib": "swanstation_libretro", "folder": "SwanStation"}]},
    # PPSSPP was removed from this list (#402): it's a PSP core with its own
    # console now — PS1 eboot .pbp files play via the PS1 disc cores below.
    "pbp": {"name": "PSP / PS1", "save_exts": ["srm", "sav", "mcr"],
            "cores": [{"lib": "pcsx_rearmed_libretro", "folder": "PCSX-ReARMed"},
                      {"lib": "mednafen_psx_hw_libretro", "folder": "Beetle PSX HW"}]},
}

_DEFAULT_SAVE_EXTS = ["srm", "sav", "save"]
_DEFAULT_STATE_EXTS = ["state", "state.auto"]

# Keep in sync with gui/electron/emulator/types.ts's ROM_EXTENSIONS — that
# mirror gates scanRomDir() before the per-console rom_extensions filter even
# runs, so a new extension missing there silently drops matching files from
# every GUI scan even though the CLI wizard (which reads this set directly)
# finds them fine (#418 regression: .3ds/.cci/.cxi added here but not there).
_ROM_EXTENSIONS = {
    "sfc", "smc", "gb", "gbc", "gba", "nes", "fds",
    "n64", "z64", "v64", "nds", "md", "smd", "gen",
    "sms", "gg", "pce", "iso", "cue", "bin", "chd", "pbp",
    "gdi", "cdi",                 # Dreamcast (#402)
    "gcm", "rvz", "wbfs",         # GameCube / Wii (#402)
    "cso",                        # PSP (#402)
    "3ds", "cci", "cxi",          # Nintendo 3DS (#418)
}


def _prepare_console_seed_data() -> list[dict]:
    """Convert hardcoded _IMPORT_CONSOLES and _IMPORT_SYSTEMS into seed format for Store.seed_console_defs()."""
    result = []
    for console_def in _IMPORT_CONSOLES:
        entry = {
            "key": console_def["key"],
            "label": console_def["label"],
            "abbr": console_def.get("abbr", console_def["key"].upper()),
            "suggestions": console_def.get("suggestions", []),
            "rom_extensions": console_def.get("rom_extensions", []),
            "databases": console_def.get("databases", []),
            "system_keys": console_def.get("system_keys", []),
            "systems": {},
            "folder_names": [],
            "standalones": console_def.get("standalones", []),
        }
        for sys_key in console_def.get("system_keys", []):
            if sys_key in _IMPORT_SYSTEMS:
                entry["systems"][sys_key] = {
                    "name": _IMPORT_SYSTEMS[sys_key]["name"],
                    "save_exts": _IMPORT_SYSTEMS[sys_key]["save_exts"],
                    "cores": [{"lib": c["lib"], "folder": c["folder"]} for c in _IMPORT_SYSTEMS[sys_key].get("cores", [])],
                }
        result.append(entry)
    return result
