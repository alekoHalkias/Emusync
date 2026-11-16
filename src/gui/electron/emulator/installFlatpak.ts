// Install a missing standalone emulator as a user-level Flathub Flatpak (#745).
import { execFile } from "child_process";
import { promisify } from "util";
import { coreInstallTargets } from "./detect";

const FLATHUB = "https://dl.flathub.org/repo/flathub.flatpakrepo";
const run = promisify(execFile);

export async function installFlatpak(
  home: string, consoleKey: string, flatpakId: string,
): Promise<{ ok: true } | { ok: false; error: string }> {
  // Renderer input: only a not-yet-installed Flatpak from this console's standalones.
  if (!coreInstallTargets(home, consoleKey).standalones.some(s => s.flatpakId === flatpakId)) {
    return { ok: false, error: "Unknown emulator or already installed" };
  }
  try {
    // --user everywhere: never prompts for elevated privileges.
    await run("flatpak", ["remote-add", "--user", "--if-not-exists", "flathub", FLATHUB], { timeout: 60_000 });
    await run("flatpak", ["install", "--user", "-y", "--noninteractive", "flathub", flatpakId],
      { timeout: 15 * 60_000, maxBuffer: 10 * 1024 * 1024 });
    return { ok: true };
  } catch (e) {
    const stderr = (e as { stderr?: string }).stderr?.trim().split("\n").pop();
    return { ok: false, error: stderr || (e instanceof Error ? e.message : String(e)) };
  }
}
