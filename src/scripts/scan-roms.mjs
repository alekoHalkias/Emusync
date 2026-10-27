#!/usr/bin/env node
/**
 * scan-roms.mjs — standalone ROM scanner for debugging
 *
 * Usage:
 *   node scripts/scan-roms.mjs <folder> [--ext gba,sfc,smc] [--depth 3] [--verbose]
 *
 * Examples:
 *   node scripts/scan-roms.mjs ~/roms
 *   node scripts/scan-roms.mjs ~/roms --ext gba
 *   node scripts/scan-roms.mjs ~/roms --ext gba --depth 3 --verbose
 */

import { readdirSync, statSync } from "fs";
import { join, extname, basename } from "path";
import { homedir } from "os";

// ── same ROM_EXTENSIONS as gui/electron/main.ts ──────────────────────────────
const ROM_EXTENSIONS = new Set([
  "sfc", "smc",                        // SNES
  "gb", "gbc",                         // Game Boy / Color
  "gba",                               // Game Boy Advance
  "nes", "fds",                        // NES
  "n64", "z64", "v64",                 // Nintendo 64
  "nds",                               // Nintendo DS
  "md", "smd", "gen",                  // Sega Genesis / Mega Drive
  "sms", "gg",                         // Sega Master System / Game Gear
  "32x",                               // Sega 32X
  "pce",                               // PC Engine
  "ws", "wsc",                         // WonderSwan
  "ngp", "ngc",                        // Neo Geo Pocket
  "a26", "a52", "a78",                 // Atari
  "lnx",                               // Atari Lynx
  "iso", "cue", "bin", "chd", "pbp",   // Disc-based (PSX, Dreamcast, PSP…)
]);

// ── parse args ───────────────────────────────────────────────────────────────
const args = process.argv.slice(2);
if (args.length === 0 || args[0] === "--help" || args[0] === "-h") {
  console.log(`
Usage: node scripts/scan-roms.mjs <folder> [options]

Options:
  --ext <exts>    Comma-separated extensions to filter (e.g. gba,sfc).
                  Default: all ROM extensions.
  --depth <n>     Max subdirectory depth to recurse (default: 3).
  --verbose       Log every file and directory visited.
  --help          Show this message.

Supported extensions:
  ${[...ROM_EXTENSIONS].join(", ")}
`.trim());
  process.exit(0);
}

// Expand ~ in the root path
const rawRoot = args[0];
const root = rawRoot.startsWith("~/")
  ? join(homedir(), rawRoot.slice(2))
  : rawRoot === "~" ? homedir() : rawRoot;

let filterExts = null;        // null = use all ROM_EXTENSIONS
let maxDepth   = 3;
let verbose    = false;

for (let i = 1; i < args.length; i++) {
  if (args[i] === "--ext"     && args[i + 1]) { filterExts = new Set(args[++i].split(",").map(e => e.trim().toLowerCase())); }
  else if (args[i] === "--depth"  && args[i + 1]) { maxDepth = parseInt(args[++i], 10); }
  else if (args[i] === "--verbose") { verbose = true; }
}

// Validate filter extensions against the known set
if (filterExts) {
  for (const ext of filterExts) {
    if (!ROM_EXTENSIONS.has(ext)) {
      console.warn(`⚠  '${ext}' is not in the known ROM_EXTENSIONS set — it will never match.`);
    }
  }
}

const activeExts = filterExts ?? ROM_EXTENSIONS;

// ── counters ─────────────────────────────────────────────────────────────────
let dirsVisited  = 0;
let filesChecked = 0;
let dirsSkipped  = 0;   // depth-limited
let errCount     = 0;

const found = [];

// ── scanner ──────────────────────────────────────────────────────────────────
function scan(dir, depth) {
  if (depth > maxDepth) {
    dirsSkipped++;
    if (verbose) console.log(`  ${"  ".repeat(depth)}[depth limit] ${dir}`);
    return;
  }

  dirsVisited++;
  if (verbose) console.log(`${"  ".repeat(depth)}📂 ${dir}  (depth ${depth})`);

  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch (err) {
    errCount++;
    console.error(`  ${"  ".repeat(depth)}[ERROR reading dir] ${dir}: ${err.message}`);
    return;
  }

  for (const e of entries) {
    const fullPath = join(dir, e.name);

    if (e.isDirectory()) {
      scan(fullPath, depth + 1);
    } else if (e.isFile()) {
      filesChecked++;
      const ext = extname(e.name).slice(1).toLowerCase();
      const inRomSet    = ROM_EXTENSIONS.has(ext);
      const inActiveSet = activeExts.has(ext);

      if (verbose) {
        const tag = !inRomSet    ? "[not a rom ext]"
                  : !inActiveSet ? "[filtered by --ext]"
                  :                "[ROM ✓]";
        console.log(`  ${"  ".repeat(depth + 1)}${tag} ${e.name}  (.${ext})`);
      }

      if (inRomSet && inActiveSet) {
        found.push(fullPath);
      }
    } else {
      // symlinks, sockets, etc.
      if (verbose) console.log(`  ${"  ".repeat(depth + 1)}[skip] ${e.name}  (not file/dir)`);
    }
  }
}

// ── run ───────────────────────────────────────────────────────────────────────
console.log(`\nEmuSync ROM scanner`);
console.log(`Root       : ${root}`);
console.log(`Extensions : ${filterExts ? [...filterExts].join(", ") : "all (" + ROM_EXTENSIONS.size + " types)"}`);
console.log(`Max depth  : ${maxDepth}`);
console.log(`Verbose    : ${verbose}`);
console.log("─".repeat(60));

// Check root exists
let rootStat;
try {
  rootStat = statSync(root);
} catch (err) {
  console.error(`\n[FATAL] Cannot stat root directory: ${err.message}`);
  process.exit(1);
}
if (!rootStat.isDirectory()) {
  console.error(`\n[FATAL] ${root} is not a directory.`);
  process.exit(1);
}

scan(root, 0);

// ── results ───────────────────────────────────────────────────────────────────
console.log("─".repeat(60));
console.log(`Dirs visited : ${dirsVisited}`);
console.log(`Dirs skipped : ${dirsSkipped}  (exceeded depth ${maxDepth})`);
console.log(`Files checked: ${filesChecked}`);
console.log(`Read errors  : ${errCount}`);
console.log(`ROMs found   : ${found.length}`);

if (found.length === 0) {
  console.log("\nNo ROMs found.");
  if (!verbose) console.log("Re-run with --verbose to see every file visited.");
} else {
  console.log("");
  // Group by directory
  const byDir = {};
  for (const p of found) {
    const dir = p.replace(/[^/]+$/, "").replace(/\/$/, "") || "/";
    (byDir[dir] = byDir[dir] ?? []).push(basename(p));
  }
  for (const [dir, files] of Object.entries(byDir)) {
    console.log(`📁 ${dir}  (${files.length} ROM${files.length !== 1 ? "s" : ""})`);
    for (const f of files.sort()) {
      console.log(`   • ${f}`);
    }
  }
}
