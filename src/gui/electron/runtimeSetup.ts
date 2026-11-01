// First-run provisioning of the bundled CLI for a packaged AppImage (#677).
// The AppImage mounts read-only at a random path, so src/ is copied to RUNTIME_DIR
// (laid out like a checkout: src/ + .cache/.venv) and a venv is built from system
// python3. Stamps make it idempotent; a failure writes no stamp, so the next call retries.
import { app } from "electron";
import { spawn } from "child_process";
import { createHash } from "crypto";
import { chmodSync, cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "fs";
import { join } from "path";
import { RUNTIME_DIR, USE_RUNTIME_DIR } from "./runtime";

type Result = { ok: boolean; error?: string };

const VERSION_STAMP = join(RUNTIME_DIR, ".version");
const HASH_STAMP = join(RUNTIME_DIR, ".requirements-hash");
const VENV = join(RUNTIME_DIR, ".cache/.venv");
const VENV_PYTHON = join(VENV, "bin/python");

const read = (p: string): string => { try { return readFileSync(p, "utf-8").trim(); } catch { return ""; } };

function run(cmd: string, args: string[]): Promise<{ code: number | null; err: string }> {
  return new Promise((resolve) => {
    const proc = spawn(cmd, args, { stdio: ["ignore", "ignore", "pipe"] });
    let err = "";
    proc.stderr?.on("data", (c: Buffer) => { err += c.toString(); });
    proc.on("error", (e) => resolve({ code: null, err: e.message }));
    proc.on("exit", (code) => resolve({ code, err: err.trim().split("\n").pop() ?? "" }));
  });
}

async function provision(): Promise<Result> {
  if (read(VERSION_STAMP) !== app.getVersion()) {
    rmSync(join(RUNTIME_DIR, "src"), { recursive: true, force: true });
    mkdirSync(RUNTIME_DIR, { recursive: true });
    cpSync(join(process.resourcesPath, "src"), join(RUNTIME_DIR, "src"), { recursive: true });
    chmodSync(join(RUNTIME_DIR, "src/emusync"), 0o755);
    writeFileSync(VERSION_STAMP, app.getVersion());
  }

  const reqs = join(RUNTIME_DIR, "src/requirements.txt");
  const hash = createHash("sha256").update(readFileSync(reqs)).digest("hex");
  if (existsSync(VENV_PYTHON) && read(HASH_STAMP) === hash) return { ok: true };

  if (!existsSync(VENV_PYTHON)) {
    const v = await run("python3", ["-m", "venv", VENV]);
    if (v.code !== 0) {
      return { ok: false, error: `Could not create the EmuSync Python environment (needs Python 3.10+ with venv; on Debian/Ubuntu: sudo apt install python3-venv). ${v.err}` };
    }
  }
  const p = await run(VENV_PYTHON, ["-m", "pip", "install", "-q", "-r", reqs]);
  if (p.code !== 0) return { ok: false, error: `Installing EmuSync's Python dependencies failed (network needed on first run). ${p.err}` };
  writeFileSync(HASH_STAMP, hash);
  return { ok: true };
}

let inflight: Promise<Result> | null = null;

// No-op outside a packaged AppImage (dev checkout, EMUSYNC_SCRIPT, Windows).
export function ensureRuntime(): Promise<Result> {
  if (!USE_RUNTIME_DIR) return Promise.resolve({ ok: true });
  inflight ??= provision()
    .catch((e: any) => ({ ok: false, error: `EmuSync runtime setup failed: ${e.message || e}` }))
    .finally(() => { inflight = null; });
  return inflight;
}
