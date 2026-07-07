// Local `.bak` backup recovery IPC (issue #285).
// Surface the on-disk `.bak` losers (a save's `<save>.bak`, a state folder's
// `*.bak`) for the recovery view, and restore one back into place. These are
// copies that may never have reached the server (e.g. the loser of an offline
// conflict), so they're only recoverable locally.
import { ipcMain } from "electron";
import { existsSync, readFileSync, writeFileSync, mkdirSync, readdirSync, unlinkSync, renameSync, statSync } from "fs";
import { join, dirname, basename } from "path";

/** A `.bak` loser found on local disk (issue #285). */
interface LocalBak {
  path: string;
  kind: "save" | "state";
  size: number;
  mtime: string;
  fileName: string;
}

export function registerRecoveryIpc(): void {
  ipcMain.handle(
    "recovery:listLocalBackups",
    async (_event, savePath: string, stateFolder: string): Promise<{ saves: LocalBak[]; states: LocalBak[] }> => {
      const saves: LocalBak[] = [];
      const states: LocalBak[] = [];
      // Every fs touch is guarded so a dead network mount yields an empty list
      // instead of throwing/hanging; no recursive traversal.
      if (savePath) {
        const bak = `${savePath}.bak`;
        try {
          if (existsSync(bak)) {
            const st = statSync(bak);
            saves.push({ path: bak, kind: "save", size: st.size, mtime: st.mtime.toISOString(), fileName: basename(bak) });
          }
        } catch { /* unreachable path → skip */ }
      }
      if (stateFolder) {
        try {
          for (const f of readdirSync(stateFolder)) {
            if (!f.endsWith(".bak")) continue;
            try {
              const p = join(stateFolder, f);
              const st = statSync(p);
              states.push({ path: p, kind: "state", size: st.size, mtime: st.mtime.toISOString(), fileName: f });
            } catch { /* skip this entry */ }
          }
        } catch { /* unreachable folder → skip */ }
      }
      return { saves, states };
    }
  );

  ipcMain.handle(
    "recovery:restoreLocalBackup",
    async (_event, bakPath: string, targetPath: string): Promise<{ ok: boolean; error?: string }> => {
      try {
        if (!bakPath.endsWith(".bak")) return { ok: false, error: "Not a .bak file" };
        if (!existsSync(bakPath)) return { ok: false, error: "Backup file no longer exists" };
        if (!targetPath) return { ok: false, error: "No restore target given" };
        // Read the backup bytes BEFORE writing anything: for a save the backup is
        // `<target>.bak`, so writing the target via a temp must not race the source.
        const data = readFileSync(bakPath);
        mkdirSync(dirname(targetPath), { recursive: true });
        // Atomic + Windows-safe: write to .part, unlink any stale temp, rename.
        const tmp = `${targetPath}.restore.part`;
        try { if (existsSync(tmp)) unlinkSync(tmp); } catch {}
        writeFileSync(tmp, data);
        try { if (existsSync(targetPath)) unlinkSync(targetPath); } catch {}
        renameSync(tmp, targetPath);
        return { ok: true };
      } catch (e: any) {
        return { ok: false, error: e.message || "Restore failed" };
      }
    }
  );
}
