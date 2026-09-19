// Save-file push/pull IPC. Routes through the CLI (`emusync game push-save`/
// `pull-save`, #479) instead of reimplementing the file-vs-folder tar/sniff
// transfer logic here in TypeScript — that logic already lives once in
// server/sync_client.py (#478's transfer envelope), and a second, independent
// copy in this file was exactly the "two implementations of the same thing"
// problem #456 already bit us on once. Mirrors the existing save:pullSwitchSeed
// pattern below.
import { ipcMain } from "electron";
import { spawn } from "child_process";
import { SCRIPT, PYTHON } from "../runtime";

// Exit codes from `emusync game push-save`/`pull-save`: 0 = success, 1 = real
// error, 2 = pull found nothing on the server yet (not an error).
function runCliTransfer(args: string[]): Promise<{ code: number | null; output: string }> {
  return new Promise((resolve) => {
    const proc = spawn(PYTHON, [SCRIPT, ...args]);
    let output = "";
    proc.stdout.on("data", (d) => (output += d.toString()));
    proc.stderr.on("data", (d) => (output += d.toString()));
    proc.on("close", (code) => resolve({ code, output: output.trim() }));
    proc.on("error", (e: Error) => resolve({ code: 1, output: e.message }));
  });
}

export function registerSaveIpc(): void {
  ipcMain.handle("save:push", async (_event, slug: string, savePath: string): Promise<{ ok: boolean; error?: string }> => {
    const { code, output } = await runCliTransfer(["game", "push-save", slug, savePath]);
    return code === 0 ? { ok: true } : { ok: false, error: output || "Push failed" };
  });

  ipcMain.handle("save:pull", async (_event, slug: string, savePath: string): Promise<{ ok: boolean; pulled: boolean; error?: string }> => {
    const { code, output } = await runCliTransfer(["game", "pull-save", slug, savePath]);
    if (code === 0) return { ok: true, pulled: true };
    if (code === 2) return { ok: true, pulled: false };
    return { ok: false, pulled: false, error: output || "Pull failed" };
  });

  // A device with no local Switch save yet has no savePath to pull *into* —
  // save:pull above needs one. The destination (<Eden profile>/<title-id>)
  // is only knowable server-side (cli/run_switch.py's _seed_switch_save), so
  // this shells out to the CLI (mirrors switchmods.ts's "sync now") rather
  // than duplicating that profile-discovery logic here. On success it
  // persists save_path itself; the renderer re-fetches the device config
  // afterward to pick it up.
  ipcMain.handle("save:pullSwitchSeed", async (_event, slug: string): Promise<{ ok: boolean; error?: string }> => {
    const { code, output } = await runCliTransfer(["game", "pull-switch-save", slug]);
    return code === 0 ? { ok: true } : { ok: false, error: output || "Pull failed" };
  });
}
