// Save-state folder push/pull IPC (tar.gz archives, one folder per game).
// Routes through the CLI (`emusync game push-state`/`pull-state`, #479)
// instead of reimplementing the tar.gz pack/backup logic here — see save.ts
// for the full rationale (#456/#478); this file had the identical problem,
// just for states instead of saves/memcards.
import { ipcMain } from "electron";
import { spawn } from "child_process";
import { SCRIPT, PYTHON } from "../runtime";

// Exit codes from `emusync game push-state`/`pull-state`: 0 = success, 1 =
// real error, 2 = pull found nothing on the server yet (not an error).
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

export function registerStateIpc(): void {
  ipcMain.handle("state:push", async (_event, slug: string, statePath: string): Promise<{ ok: boolean; error?: string }> => {
    const { code, output } = await runCliTransfer(["game", "push-state", slug, statePath]);
    return code === 0 ? { ok: true } : { ok: false, error: output || "Push failed" };
  });

  ipcMain.handle("state:pull", async (_event, slug: string, statePath: string): Promise<{ ok: boolean; pulled: boolean; error?: string }> => {
    const { code, output } = await runCliTransfer(["game", "pull-state", slug, statePath]);
    if (code === 0) return { ok: true, pulled: true };
    if (code === 2) return { ok: true, pulled: false };
    return { ok: false, pulled: false, error: output || "Pull failed" };
  });
}
