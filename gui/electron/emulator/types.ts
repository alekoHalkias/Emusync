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
]);

export const DEFAULT_SAVE_EXTS = ["srm", "sav", "save"];

export interface EmulatorInfo {
  type: "native" | "flatpak";
  label: string;      // display name, e.g. "RetroArch (Flatpak)"
  execPath: string;   // binary path or "flatpak run ..."
  saveDir: string;    // root saves directory
  statesDir: string;  // root states directory
  coresDir: string;   // where core .so files live
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

export interface DetectedEmulatorOption {
  id: string;
  label: string;
  execPath: string;
  saveDir: string;
  stateDir?: string;
  corePath?: string;
  coreFolderName?: string;
  romDirs: string[];
}
