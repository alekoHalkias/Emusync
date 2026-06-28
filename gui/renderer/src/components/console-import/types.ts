// Shared types for the Add-Console import wizard.

export type ConsoleOption = { key: string; label: string; abbr?: string };

export type EmulatorOption = {
  id: string;
  label: string;
  execPath: string;
  saveDir: string;
  corePath?: string;
  coreFolderName?: string;
  romDirs: string[];
};

export type RomEntry = {
  name: string;
  romPath: string;
  romFileName: string;
  savePath: string;
  saveExists: boolean;
  launchCommand: string;
  consoleName?: string;
  coreName?: string;
  statePath?: string;
  stateExists?: boolean;
  existingGameSlug?: string;
  romFolderPath: string;
  linkedSlug?: string;
  linkedName?: string;
  // Network import (issue #270): where this ROM was found relative to the chosen
  // source roots. "network" = only on the share, "local" = only on local disk
  // (will be uploaded to the share + treated as already localized), "both" = on
  // the share with a local copy already present. Unset for local-source imports.
  presence?: "network" | "local" | "both";
  // For a local/both ROM, the path of the local copy (used to upload to the
  // master and recorded as local_rom_path so it's treated as localized).
  localRomPath?: string;
};

export type Phase =
  | "console"    // select console
  | "detecting"  // scanning for installed emulators
  | "emulator"   // pick emulator (or no-emulator message)
  | "scanning"   // scanning ROMs + saves
  | "results"    // ROM list with checkboxes
  | "importing"  // import in progress
  | "done";      // finished

export type Props = { onClose: () => void; onImported: () => void; initialConsole?: string };

export type ImportedEntry = { slug: string; savePath: string; statePath: string };
export type PushStatus = "pushing" | "ok" | "offline" | "error";
export type PushResult = { deviceName: string; status: PushStatus; error?: string };
