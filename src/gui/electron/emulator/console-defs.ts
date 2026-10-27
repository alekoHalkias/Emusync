// Lazily fetch console / system / folder-name definitions from the Python API
// and cache them on `rt`. This is the data that drives the import wizard.
import { existsSync, readFileSync } from "fs";
import { parse as parseTOML } from "smol-toml";
import { CONFIG_PATH, rt } from "../runtime";
import { httpGetJSON } from "../http";

export async function loadConsoleDefinitionsIfNeeded(): Promise<void> {
  if (rt.cachedConsoleDefs && rt.cachedSystemDefs && rt.cachedConsoleFolderNames) return;

  try {
    const cfg = existsSync(CONFIG_PATH) ? parseTOML(readFileSync(CONFIG_PATH, "utf-8")) as Record<string, unknown> : null;
    if (!cfg?.server_port) return;
    const host = (cfg.server_host as string) || "localhost";

    const base = `http://${host}:${cfg.server_port}`;
    const headers = {
      "Authorization": `Bearer ${cfg.server_pin || ""}`,
      "X-Device-ID": String(cfg.device_id || "electron"),
      "X-Device-Name": String(cfg.device_name || "GUI"),
    };

    // Load console, system, and folder name definitions from Python API
    const consoleRes = await httpGetJSON(`${base}/console-defs`, headers);
    if (consoleRes.status === 200 && consoleRes.body) {
      rt.cachedConsoleDefs = {};
      for (const def of consoleRes.body) {
        rt.cachedConsoleDefs[def.key] = def;
      }
    }

    const systemRes = await httpGetJSON(`${base}/system-defs`, headers);
    if (systemRes.status === 200 && systemRes.body) {
      rt.cachedSystemDefs = systemRes.body;
    }

    const folderRes = await httpGetJSON(`${base}/console-folder-names`, headers);
    if (folderRes.status === 200 && folderRes.body) {
      rt.cachedConsoleFolderNames = folderRes.body;
    }
  } catch (e) {
    console.error("Failed to load console definitions:", e);
  }
}
