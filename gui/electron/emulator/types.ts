// Shared types and constants for the emulator detection / scanning subsystem.

export const ROM_EXTENSIONS = new Set([
  "sfc", "smc",                        // SNES
  "gb", "gbc",                         // Game Boy / Color
  "gba",                               // Game Boy Advance
  "nes", "fds",                        // NES
  "n64", "z64", "v64",                 // Nintendo 64
  "nds",                               // Nintendo DS
  "md", "smd", "gen",                  // Sega Genesis / Mega Drive
  "sms", "gg",                         // Sega Master System / Game Gear
  "32x",                               // Sega 32X
  "pce",                               // PC Engine
  "ws", "wsc",                         // WonderSwan
  "ngp", "ngc",                        // Neo Geo Pocket
  "a26", "a52", "a78",                 // Atari
  "lnx",                               // Atari Lynx
  "iso", "cue", "bin", "chd", "pbp",   // Disc-based (PSX, Dreamcast, PSP…)
  "gdi", "cdi",                        // Dreamcast (#402)
  "gcm", "rvz", "wbfs",                // GameCube / Wii (#402)
  "cso",                               // PSP (#402)
]);

export const DEFAULT_SAVE_EXTS = ["srm", "sav", "save"];

export interface EmulatorInfo {
  type: "native" | "flatpak";
  label: string;      // display name, e.g. "RetroArch (Flatpak)"
  execPath: string;   // binary path or "flatpak run ..."
  saveDir: string;    // root saves directory
  statesDir: string;  // root states directory
  coresDir: string;   // where core .so files live
  infoDirs: string[]; // where core .info metadata files may live (#400)
  systemDir?: string; // RetroArch system/BIOS dir — Dolphin's card path lives under it (#402)
  romDirs: string[];
}

export interface RomEntry {
  name: string;
  romPath: string;
  savePath: string;       // resolved path (may not exist yet)
  saveExists: boolean;
  statePath?: string;     // resolved state path (may not exist yet)
  stateExists?: boolean;
  launchCommand: string;
  consoleName?: string;   // e.g. "Game Boy Advance"
  coreName?: string;      // e.g. "mGBA" — the core that will be used
}

export interface EmulatorScanResult {
  emulators: EmulatorInfo[];
  romDirs: string[];
  roms: RomEntry[];
}

/** Per-launch-flavour dir templates for a standalone emulator (`~` = device home). */
export interface StandaloneDirs {
  save?: string;
  state?: string;
  memcard?: string;
}

/** A standalone emulator definition as served by the Python API (issue #292). */
export interface StandaloneDef {
  id: string;
  label: string;
  native_bins?: string[];
  flatpak_id?: string;
  flatpak_exec?: string;
  save_dir_template?: string;
  dirs?: { native?: StandaloneDirs; flatpak?: StandaloneDirs };
  launch_args?: string[];
}

export interface DetectedEmulatorOption {
  id: string;
  label: string;
  execPath: string;
  saveDir: string;
  stateDir?: string;
  corePath?: string;
  coreFolderName?: string;
  launchArgs?: string[];   // standalone-emulator flags, e.g. PCSX2 -batch -fullscreen (#293)
  systemDir?: string;      // RetroArch system dir, for shared-card resolution (#402)
  romDirs: string[];
}
