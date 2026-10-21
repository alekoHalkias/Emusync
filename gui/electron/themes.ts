// Big Picture user themes (#527): folders in <config dir>/themes/<id>/ holding
// theme.json ({name, author, css}), a CSS file and optional assets. Assets are
// served via emusync-theme://<id>/<path> (see registerThemeScheme).
import { app, ipcMain, net, protocol } from "electron";
import { existsSync, readdirSync, readFileSync, statSync } from "fs";
import { join, resolve, sep } from "path";
import { pathToFileURL } from "url";
import { configDir } from "./paths";

const SCHEME = "emusync-theme";
export const themesDir = (): string => join(configDir(), "themes");

export interface ThemeInfo { id: string; name: string; author: string }

/** Resolve rel inside the theme's folder; null if id/rel escape it. */
export function themeFile(id: string, rel: string): string | null {
  const root = resolve(themesDir());
  const dir = resolve(root, id);
  if (!dir.startsWith(root + sep)) return null;
  const file = resolve(dir, rel);
  return file.startsWith(dir + sep) ? file : null;
}

function readManifest(id: string): Record<string, unknown> | null {
  const f = themeFile(id, "theme.json");
  try {
    return f && existsSync(f) ? JSON.parse(readFileSync(f, "utf-8")) : null;
  } catch { return null; } // bad theme.json — skip the theme
}

export function listThemes(): ThemeInfo[] {
  let ids: string[] = [];
  try { ids = readdirSync(themesDir()).filter((d) => statSync(join(themesDir(), d)).isDirectory()); } catch { /* no themes dir */ }
  const out: ThemeInfo[] = [];
  for (const id of ids.sort()) {
    const m = readManifest(id);
    if (m) out.push({ id, name: String(m.name ?? id), author: String(m.author ?? "") });
  }
  return out;
}

export function getThemeCss(id: string): string | null {
  const m = readManifest(id);
  const f = m && themeFile(id, typeof m.css === "string" ? m.css : "theme.css");
  try { return f ? readFileSync(f, "utf-8") : null; } catch { return null; }
}

// Must run before app ready.
export function registerThemeScheme(): void {
  protocol.registerSchemesAsPrivileged([
    { scheme: SCHEME, privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true } },
  ]);
}

export function registerThemeIpc(): void {
  ipcMain.handle("theme:list", () => listThemes());
  ipcMain.handle("theme:get", (_e, id: string) => {
    const css = getThemeCss(id);
    return css === null ? null : { css };
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
}
