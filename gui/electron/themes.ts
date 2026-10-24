// Big Picture user themes (#527): folders in <config dir>/themes/<id>/ holding
// theme.json ({name, author, css}), a CSS file and optional assets. Assets are
// served via emusync-theme://<id>/<path> (see registerThemeScheme).
//
// Bundled themes live in gui/electron/themes/bundled/<id>/ and are copied to
// <config dir>/themes/<id>/ on first launch so they appear in listThemes().
//
// Theme import (#595): .theme/.zip files are extracted, validated (manifest
// required, safe paths), and installed into <config dir>/themes/<id>/.
import { app, ipcMain, net, protocol } from "electron";
import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "fs";
import { extname, join, resolve, sep } from "path";
import { pathToFileURL } from "url";
import { configDir } from "./paths";

const SCHEME = "emusync-theme";
export const themesDir = (): string => join(configDir(), "themes");
const bundledThemesDir = (): string => join(resolve(__dirname, ".."), "electron", "themes", "bundled");

export interface ThemeInfo { id: string; name: string; author: string }

// --- Internal helpers ---

/** Resolve rel inside the theme's folder; null if id/rel escape it. Checks user dir first, then bundled. */
export function themeFile(id: string, rel: string): string | null {
  // Check user themes first
  const root = resolve(themesDir());
  const userDir = resolve(root, id);
  if (userDir.startsWith(root + sep)) {
    const file = resolve(userDir, rel);
    if (file.startsWith(userDir + sep)) return file;
  }
  // Fall back to bundled themes
  const bundledRoot = resolve(bundledThemesDir());
  const bundledDir = resolve(bundledRoot, id);
  if (bundledDir.startsWith(bundledRoot + sep)) {
    const file = resolve(bundledDir, rel);
    if (file.startsWith(bundledDir + sep)) return file;
  }
  return null;
}

function readManifest(id: string): Record<string, unknown> | null {
  const f = themeFile(id, "theme.json");
  try {
    return f && existsSync(f) ? JSON.parse(readFileSync(f, "utf-8")) : null;
  } catch { return null; } // bad theme.json — skip the theme
}

/** Copy bundled themes to config dir if not already present. */
function initBundledThemes(): void {
  let bundledIds: string[] = [];
  try { bundledIds = readdirSync(bundledThemesDir()).filter((d) => statSync(join(bundledThemesDir(), d)).isDirectory()); } catch { return; }
  const existing = new Set<string>();
  try {
    for (const d of readdirSync(themesDir())) {
      if (statSync(join(themesDir(), d)).isDirectory()) existing.add(d);
    }
  } catch { /* no themes dir yet */ }
  for (const id of bundledIds) {
    if (existing.has(id)) continue; // user already has this theme
    const src = join(bundledThemesDir(), id);
    const dest = join(themesDir(), id);
    const copyRecursive = (srcPath: string, destPath: string): void => {
      mkdirSync(destPath, { recursive: true });
      for (const entry of readdirSync(srcPath, { withFileTypes: true })) {
        const s = join(srcPath, entry.name);
        const d = join(destPath, entry.name);
        if (entry.isDirectory()) copyRecursive(s, d);
        else writeFileSync(d, readFileSync(s));
      }
    };
    copyRecursive(src, dest);
  }
}

/** Slugify a theme name into a safe directory ID; deduplicate against existing IDs. */
function makeId(name: string, existing: Set<string>): string {
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "untitled";
  if (!existing.has(slug)) return slug;
  let n = 2;
  while (existing.has(`${slug}-${n}`)) n++;
  return `${slug}-${n}`;
}

// --- ZIP extraction ---

/** Extract a ZIP to dir; reject paths that escape dir. */
async function extractZip(zipPath: string, destDir: string): Promise<void> {
  // @ts-expect-error adm-zip@0.5.16 lacks .d.ts files
  const { default: AdmZip } = await import("adm-zip");
  const zip = new (AdmZip as unknown as new (path: string) => { getEntries: () => Array<{ isDirectory: boolean; entryName: string; getData: () => Buffer }> })(zipPath);
  const entries = zip.getEntries();
  for (const entry of entries) {
    if (entry.isDirectory) continue;
    const dest = join(destDir, entry.entryName);
    const resolved = resolve(dest);
    if (!resolved.startsWith(resolve(destDir) + sep)) {
      throw new Error("Theme ZIP contains path-traversal entry");
    }
    mkdirSync(resolve(dest), { recursive: true });
    // @ts-expect-error adm-zip@0.5.16 lacks .d.ts files
    zip.extractEntryTo(entry, dest, false, true);
  }
}

// --- Public API ---

/** Import a .theme/.zip file; returns the installed theme ID. */
export async function importThemeZip(zipPath: string): Promise<string> {
  if (!existsSync(zipPath)) throw new Error("File not found");
  const ext = extname(zipPath).toLowerCase();
  if (ext !== ".theme" && ext !== ".zip") throw new Error("Only .theme or .zip files are accepted");

  // Read and validate manifest first
  let name = "";
  try {
    // @ts-expect-error adm-zip@0.5.16 lacks .d.ts files
    const { default: AdmZip } = await import("adm-zip");
    const zip = new (AdmZip as unknown as new (path: string) => { getEntries: () => Array<{ entryName: string; getData: () => Buffer }> })(zipPath);
    const manifestEntry = zip.getEntries().find((e) => e.entryName === "theme.json");
    if (!manifestEntry) throw new Error("Missing theme.json in archive");
    const data = JSON.parse(manifestEntry.getData().toString("utf-8"));
    if (!data.name) throw new Error("theme.json missing 'name'");
    name = String(data.name);
  } catch (err: unknown) {
    if (err instanceof Error && err.message === "Missing theme.json in archive") throw err;
    if (err instanceof Error && err.message === "theme.json missing 'name'") throw err;
    throw new Error("Invalid theme archive: " + (err instanceof Error ? err.message : String(err)));
  }

  // Collect existing IDs for dedup
  const existing = new Set<string>();
  try {
    for (const d of readdirSync(themesDir())) {
      if (statSync(join(themesDir(), d)).isDirectory()) existing.add(d);
    }
  } catch { /* no themes dir yet */ }

  const id = makeId(name, existing);
  const destDir = join(themesDir(), id);
  mkdirSync(destDir, { recursive: true });

  // Extract
  try {
    await extractZip(zipPath, destDir);
  } catch (err: unknown) {
    // Clean up on failure
    try { rmSync(destDir, { recursive: true, force: true }); } catch { /* ignore */ }
    throw err;
  }

  return id;
}

/** Import a theme folder; returns the installed theme ID. */
export async function importThemeFolder(folderPath: string): Promise<string> {
  if (!existsSync(folderPath)) throw new Error("Folder not found");
  const stat = statSync(folderPath);
  if (!stat.isDirectory()) throw new Error("Path is not a directory");

  // Validate manifest
  const manifestPath = join(folderPath, "theme.json");
  if (!existsSync(manifestPath)) throw new Error("Missing theme.json in folder");
  let name = "";
  try {
    const data = JSON.parse(readFileSync(manifestPath, "utf-8"));
    if (!data.name) throw new Error("theme.json missing 'name'");
    name = String(data.name);
  } catch (err: unknown) {
    if (err instanceof Error && err.message === "theme.json missing 'name'") throw err;
    throw new Error("Invalid theme folder: " + (err instanceof Error ? err.message : String(err)));
  }

  // Collect existing IDs for dedup
  const existing = new Set<string>();
  try {
    for (const d of readdirSync(themesDir())) {
      if (statSync(join(themesDir(), d)).isDirectory()) existing.add(d);
    }
  } catch { /* no themes dir yet */ }

  const id = makeId(name, existing);
  const destDir = join(themesDir(), id);

  // Copy folder contents (with path traversal protection)
  const srcResolved = resolve(folderPath);
  const destResolved = resolve(destDir);
  const copyRecursive = (src: string, destOut: string): void => {
    mkdirSync(destOut, { recursive: true });
    for (const entry of readdirSync(src, { withFileTypes: true })) {
      const srcPath = join(src, entry.name);
      const destPath = join(destOut, entry.name);
      if (entry.isDirectory()) {
        copyRecursive(srcPath, destPath);
      } else {
        const resolved = resolve(destPath);
        if (!resolved.startsWith(destResolved + sep)) {
          throw new Error("Theme folder contains path-traversal entry");
        }
        writeFileSync(destPath, readFileSync(srcPath));
      }
    }
  };
  copyRecursive(srcResolved, destResolved);

  return id;
}

// --- ThemeEngine (public API) ---

export const ThemeEngine = {
  /** List all installed themes. */
  list: (): ThemeInfo[] => {
    let ids: string[] = [];
    try { ids = readdirSync(themesDir()).filter((d) => statSync(join(themesDir(), d)).isDirectory()); } catch { /* no themes dir */ }
    const out: ThemeInfo[] = [];
    for (const id of ids.sort()) {
      const m = readManifest(id);
      if (m) out.push({ id, name: String(m.name ?? id), author: String(m.author ?? "") });
    }
    return out;
  },

  /** Get theme CSS by ID. */
  get: (id: string): { css: string } | null => {
    const m = readManifest(id);
    const f = m && themeFile(id, typeof m.css === "string" ? m.css : "theme.css");
    try { return f ? { css: readFileSync(f, "utf-8") } : null; } catch { return null; }
  },

  /** No-op; renderer handles CSS injection. */
  apply: (_id: string): void => { /* renderer handles injection */ },

  /** Clear active theme. */
  clear: (): void => { /* renderer handles removal */ },

  /** Import a .theme/.zip file; returns the installed theme ID. */
  importZip: (zipPath: string): Promise<string> => importThemeZip(zipPath),

  /** Import a theme folder; returns the installed theme ID. */
  importFolder: (folderPath: string): Promise<string> => importThemeFolder(folderPath),

  /** Register theme IPC handlers. */
  registerIpc: (): void => {
    // Copy bundled themes to config dir so they appear in listThemes().
    initBundledThemes();
    ipcMain.handle("theme:list", () => ThemeEngine.list());
    ipcMain.handle("theme:get", (_e, id: string) => ThemeEngine.get(id));
    ipcMain.handle("theme:import", async (_e, path: string) => {
      const ext = extname(path).toLowerCase();
      if (ext === ".theme" || ext === ".zip") return ThemeEngine.importZip(path);
      return ThemeEngine.importFolder(path);
    });
    app.whenReady().then(() => {
      protocol.handle(SCHEME, (req) => {
        const u = new URL(req.url);
        const file = themeFile(decodeURIComponent(u.hostname), decodeURIComponent(u.pathname).replace(/^\/+/, ""));
        return file && existsSync(file)
          ? net.fetch(pathToFileURL(file).toString())
          : new Response("not found", { status: 404 });
      });
    });
  },
};

// Must run before app ready.
export function registerThemeScheme(): void {
  protocol.registerSchemesAsPrivileged([
    { scheme: SCHEME, privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true } },
  ]);
}
