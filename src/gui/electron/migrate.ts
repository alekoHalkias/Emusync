// Moves a legacy ~/.emusync into the config/data/cache dirs (#564) by asking the
// CLI — the one implementation lives in src/server/paths.py. Imported first by
// main.ts so it finishes before any module reads a path. Best effort: a broken
// venv is reported by server:preflight, not here.
import { spawnSync } from "child_process";
import { PYTHON, SCRIPT } from "./runtime";

spawnSync(PYTHON, [SCRIPT, "migrate"], { stdio: "ignore", timeout: 120_000 });
