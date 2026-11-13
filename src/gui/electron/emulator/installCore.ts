// Install a missing RetroArch core from the libretro buildbot (#744).
import { copyFileSync, mkdirSync, mkdtempSync, renameSync, rmSync, statSync } from "fs";
import { execFile } from "child_process";
import { promisify } from "util";
import { tmpdir } from "os";
import { join } from "path";
import { download } from "../art";
import { PYTHON } from "../runtime";
import { coreInstallTargets } from "./detect";

const BUILDBOT = "https://buildbot.libretro.com/nightly/linux/x86_64/latest";

export async function installCore(
  home: string, consoleKey: string, coresDir: string, lib: string,
): Promise<{ ok: true } | { ok: false; error: string }> {
  // Renderer input: only a seeded core into a detected RetroArch cores dir.
  const t = coreInstallTargets(home, consoleKey);
  if (!t.cores.some(c => c.lib === lib) || !t.retroarch.some(r => r.coresDir === coresDir)) {
    return { ok: false, error: "Unknown core or RetroArch install" };
  }
  const tmp = mkdtempSync(join(tmpdir(), "emusync-core-"));
  try {
    const zip = join(tmp, `${lib}.so.zip`);
    await download(`${BUILDBOT}/${lib}.so.zip`, zip);
    // Stdlib unzip via the bundled Python; adm-zip was removed (#679).
    await promisify(execFile)(PYTHON, ["-m", "zipfile", "-e", zip, tmp], { timeout: 60_000 });
    const so = join(tmp, `${lib}.so`);
    if (statSync(so).size === 0) throw new Error("Downloaded core is empty");
    mkdirSync(coresDir, { recursive: true });
    const part = join(coresDir, `${lib}.so.part`);
    copyFileSync(so, part);
    renameSync(part, join(coresDir, `${lib}.so`));
    return { ok: true };
  } catch (e) {
    rmSync(join(coresDir, `${lib}.so.part`), { force: true });
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
}
