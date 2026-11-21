// Move a game's save/state files to a new emulator's locations (#753).
// Only node:* imports so src/tests/test_move_saves.py can run it with plain node.
// Never overwrites an existing destination (reported as skipped) and never
// removes a source before its copy is in place (#692).
import { cpSync, existsSync, mkdirSync, readdirSync, renameSync, rmSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

export type MoveSavesParams = { fromSave?: string; toSave?: string; fromState?: string; toState?: string };
export type MoveSavesResult = { ok: boolean; moved: string[]; skipped: string[]; error?: string };

function moveOne(src: string, dest: string, out: MoveSavesResult): void {
  if (!src || !dest || resolve(src) === resolve(dest) || !existsSync(src)) return;
  if (existsSync(dest)) { out.skipped.push(dest); return; }
  mkdirSync(dirname(dest), { recursive: true });
  try {
    renameSync(src, dest);
  } catch (e: any) {
    if (e?.code !== "EXDEV") throw e;
    // Cross-device: copy to a temp sibling, verify, swap in, then drop the source.
    const part = dest + ".part";
    try {
      cpSync(src, part, { recursive: true });
      const s = statSync(src);
      if (s.isFile() && statSync(part).size !== s.size) throw new Error(`Copy verification failed for ${src}`);
      renameSync(part, dest);
    } finally {
      if (existsSync(part)) rmSync(part, { recursive: true, force: true });
    }
    rmSync(src, { recursive: true, force: true });
  }
  out.moved.push(dest);
}

export function moveSaves({ fromSave = "", toSave = "", fromState = "", toState = "" }: MoveSavesParams): MoveSavesResult {
  const out: MoveSavesResult = { ok: true, moved: [], skipped: [] };
  try {
    moveOne(fromSave, toSave, out);
    // State folders hold several slots; move file by file so existing slots at
    // the destination are kept.
    if (fromState && toState && resolve(fromState) !== resolve(toState)
        && existsSync(fromState) && statSync(fromState).isDirectory()) {
      for (const name of readdirSync(fromState)) moveOne(join(fromState, name), join(toState, name), out);
    }
  } catch (e: any) {
    return { ...out, ok: false, error: e?.message || "Move failed" };
  }
  return out;
}
