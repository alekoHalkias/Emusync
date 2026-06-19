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
};

export type Phase =
  | "console"    // select console
  | "detecting"  // scanning for installed emulators
  | "emulator"   // pick emulator (or no-emulator message)
  | "scanning"   // scanning ROMs + saves
  | "results"    // ROM list with checkboxes
  | "importing"  // import in progress
  | "done";      // finished

export type Props = { onClose: () => void; onImported: () => void };

export type ImportedEntry = { slug: string; savePath: string; statePath: string };
export type PushStatus = "pushing" | "ok" | "offline" | "error";
export type PushResult = { deviceName: string; status: PushStatus; error?: string };
