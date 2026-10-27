// Console-scoped shared memory card push/pull IPC (issue #295). Routes
// through the CLI (`emusync console push-memcard`/`pull-memcard`, #479)
// instead of reimplementing the file-vs-folder tar/sniff transfer logic
// here — see save.ts for the full rationale (#456/#478). One card per
// console (PS2), shared across every game on that console. Pull is used by
// the import wizard to bring a newly-imported shared-layout console's card
// in from the server (issue #316); push backs the manual "Push memory card"
// button in GameConfig (issue #319).
import { ipcMain } from "electron";
import { spawn } from "child_process";
import { SCRIPT, PYTHON } from "../runtime";

// Exit codes from `emusync console push-memcard`/`pull-memcard`: 0 =
// success, 1 = real error, 2 = pull found nothing to pull (no card on the
// server yet, or — GC only — a Dolphin card-format mismatch, #428).
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

export function registerMemcardIpc(): void {
  ipcMain.handle("memcard:push", async (_event, consoleKey: string, cardPath: string): Promise<{ ok: boolean; error?: string }> => {
    const { code, output } = await runCliTransfer(["console", "push-memcard", consoleKey, cardPath]);
    return code === 0 ? { ok: true } : { ok: false, error: output || "Push failed" };
  });

  ipcMain.handle("memcard:pull", async (_event, consoleKey: string, cardPath: string): Promise<{ ok: boolean; pulled: boolean; error?: string }> => {
    const { code, output } = await runCliTransfer(["console", "pull-memcard", consoleKey, cardPath]);
    if (code === 0) return { ok: true, pulled: true };
    if (code === 2) return { ok: true, pulled: false };
    return { ok: false, pulled: false, error: output || "Pull failed" };
  });
}
