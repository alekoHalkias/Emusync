// Non-recursive library-root scan for the bulk-library import wizard (#462).
// Matches each immediate subfolder of a chosen library root against every
// known console's key/abbr/label/folder_names aliases so the wizard can
// propose a console per folder before the user confirms/corrects it.
import { existsSync, readdirSync } from "fs";
import { join } from "path";
import { rt } from "../runtime";

export type LibraryFolderMatch = { path: string; folderName: string; consoleKey: string | null };

/** Lowercase, alphanumeric-only — so "Mega Drive", "megadrive", and "MEGA_DRIVE" all compare equal. */
function normalize(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]/g, "");
}

export function scanLibraryFolders(libraryRoot: string): LibraryFolderMatch[] {
  if (!libraryRoot || !existsSync(libraryRoot)) return [];

  const consoleDefs = Object.values(rt.cachedConsoleDefs ?? {}) as Array<{ key: string; label?: string; abbr?: string }>;
  const folderNames = rt.cachedConsoleFolderNames ?? {};

  // Richest alias -> console key lookup, built once per scan. First console
  // to claim an alias wins (defs don't currently overlap on any of these).
  const aliasToKey = new Map<string, string>();
  for (const def of consoleDefs) {
    const aliases = [def.key, def.abbr, def.label, ...(folderNames[def.key] ?? [])];
    for (const alias of aliases) {
      if (!alias) continue;
      const norm = normalize(alias);
      if (norm && !aliasToKey.has(norm)) aliasToKey.set(norm, def.key);
    }
  }

  let entryNames: string[];
  try {
    entryNames = readdirSync(libraryRoot, { withFileTypes: true })
      .filter(e => e.isDirectory())
      .map(e => e.name);
  } catch {
    return [];
  }

  return entryNames.map(name => ({
    path: join(libraryRoot, name),
    folderName: name,
    consoleKey: aliasToKey.get(normalize(name)) ?? null,
  }));
}
