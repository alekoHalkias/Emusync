// State machine + async orchestration for the Add-Console wizard.
// The presentational step components consume the object this hook returns.
import { useEffect, useState } from "react";
import { addGame, setGameDevice, gamesOverview, type GameOverview } from "../../api";
import {
  annotateRoms,
  classifyByRoot,
  dedupeAndLink,
  existingLocalGamesForConsole,
  getConsoleAbbreviation,
  groupByDir,
  sanitizeFilename,
  usesSharedSaveLayout,
  usesSharedStateLayout,
  stepIndex,
} from "./helpers";
import { autoPush, prefetchArt, pullFromServerIfNewer } from "./postImport";
import { resolveImportPaths } from "./resolveRomPaths";
import type {
  ConsoleOption,
  EmulatorOption,
  ImportedEntry,
  Phase,
  Props,
  PushResult,
  RomEntry,
} from "./types";

// IPC bridge (typing deferred to the typed-bridge work in #228).
const emusync = window.emusync;

export function useConsoleImport({ onClose, onImported, initialConsole }: Props) {
  const [phase, setPhase]         = useState<Phase>(initialConsole ? "detecting" : "console");
  const [consoles, setConsoles]   = useState<ConsoleOption[]>([]);
  const [consoleSel, setConsoleSel] = useState(initialConsole ?? "");
  const [emulators, setEmulators] = useState<EmulatorOption[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [emuSel, setEmuSel]       = useState<EmulatorOption | null>(null);
  const [extraPaths, setExtraPaths] = useState<string[]>([]);
  const [romDirs, setRomDirs]     = useState<string[]>([]);
  const [removedDirs, setRemovedDirs] = useState<Set<string>>(new Set());
  const [roms, setRoms]           = useState<RomEntry[]>([]);
  const [selected, setSelected]   = useState<Set<string>>(new Set());
  const [names, setNames]         = useState<Record<string, string>>({});
  const [error, setError]         = useState("");
  const [progress, setProgress]   = useState({ done: 0, total: 0 });
  const [importErrors, setImportErrors] = useState<string[]>([]);
  const [savedFolders, setSavedFolders] = useState<string[]>([]);
  const [pushResults, setPushResults]   = useState<PushResult[]>([]);
  const [artProgress, setArtProgress]   = useState({ done: 0, total: 0 });
  const [pushSaves, setPushSaves]       = useState(true);
  const [pushStates, setPushStates]     = useState(true);
  // ROM source (issue #255): import from a local folder or a network share, and
  // where local copies should land when a network ROM is localized later.
  const [romSource, setRomSource]       = useState<"local" | "network">("local");
  const [localRomRoot, setLocalRomRoot] = useState("");
  const [existingGames, setExistingGames] = useState<GameOverview[]>([]);
  const [nameWarnings, setNameWarnings] = useState<string[]>([]);

  useEffect(() => {
    emusync.emulator.consoles().then(setConsoles);
  }, []);

  // If initialConsole was provided, auto-detect emulators for it
  useEffect(() => {
    if (initialConsole && consoleSel && phase === "detecting") {
      (async () => {
        try {
          const [{ options, suggestions: sugg }, saved, cfg] = await Promise.all([
            emusync.emulator.detect(consoleSel),
            emusync.config.getRecentFolders(consoleSel),
            emusync.config.load(),
          ]);
          setEmulators(options);
          setSuggestions(sugg);
          setSavedFolders(saved);
          setExtraPaths(saved);
          const lastSource = cfg?.import_rom_source?.[consoleSel];
          setRomSource(lastSource === "network" ? "network" : "local");
          setLocalRomRoot(cfg?.import_local_folder?.[consoleSel] ?? "");
          if (options.length === 1) setEmuSel(options[0]);
          setPhase("emulator");
        } catch {
          setEmulators([]);
          setPhase("emulator");
        }
      })();
    }
  }, [initialConsole, consoleSel, phase]);

  async function detectEmulators(): Promise<void> {
    setPhase("detecting");
    try {
      const [{ options, suggestions: sugg }, saved, cfg] = await Promise.all([
        emusync.emulator.detect(consoleSel),
        emusync.config.getRecentFolders(consoleSel),
        emusync.config.load(),
      ]);
      setEmulators(options);
      setSuggestions(sugg);
      setSavedFolders(saved);
      setExtraPaths(saved);
      // Remember the last source + local destination per console (issue #255).
      const lastSource = cfg?.import_rom_source?.[consoleSel];
      setRomSource(lastSource === "network" ? "network" : "local");
      setLocalRomRoot(cfg?.import_local_folder?.[consoleSel] ?? "");
      if (options.length === 1) setEmuSel(options[0]);
      setPhase("emulator");
    } catch {
      setEmulators([]);
      setPhase("emulator");
    }
  }

  async function scanRoms(paths: string[]): Promise<void> {
    if (!emuSel) return;
    setPhase("scanning");
    setError("");
    try {
      // Network import (issue #270): also scan the console's local-copy folder so
      // ROMs already on local disk are detected — local-only ones get uploaded to
      // the share, ones present in both are treated as already localized.
      const scanNetwork = romSource === "network";
      const scanPaths = scanNetwork && localRomRoot && !paths.includes(localRomRoot)
        ? [...paths, localRomRoot]
        : paths;
      const result = await emusync.emulator.scan(consoleSel, emuSel, scanPaths);
      let annotated = annotateRoms(result.roms, scanPaths, result.romDirs ?? []);

      // Tag each ROM network/local/both and merge net+local duplicates into one row.
      if (scanNetwork) {
        annotated = classifyByRoot(annotated, paths, localRomRoot);
      }

      // Dedup: filter already-imported ROMs; detect cross-device links.
      let newRoms = annotated;
      let existingLocal: RomEntry[] = [];
      try {
        // One batched call gives every game's slug/name/console plus this
        // device's rom_path (empty when the game isn't configured here),
        // replacing the old listGames() + per-game getGameDevice() fan-out.
        const overview = await gamesOverview();
        setExistingGames(overview);
        const thisDeviceConfigs = overview
          .filter(o => o.rom_path)
          .map(o => ({ slug: o.slug, romPath: o.rom_path }));

        const { roms: deduped, skipCount } = dedupeAndLink(annotated, overview, thisDeviceConfigs);
        newRoms = deduped;
        if (skipCount > 0 && deduped.length === 0) {
          setError(`${skipCount} ROM${skipCount !== 1 ? "s" : ""} found — all already imported on this device.`);
        }
        // Network import (issue #281): also surface this device's already-imported
        // local-source games for the console so they get copied UP to the share
        // and converted to network-source. They're pre-selected (see below).
        if (scanNetwork) {
          const consoleAbbr = getConsoleAbbreviation(consoleSel, consoles);
          existingLocal = existingLocalGamesForConsole(overview, consoleAbbr, newRoms);
          newRoms = [...newRoms, ...existingLocal];
        }
      } catch {
        // Dedup unavailable (server not reachable / not paired yet) — show all ROMs
      }

      setRoms(newRoms);
      setRomDirs(result.romDirs ?? []);
      // Start with nothing selected so importing a few from a large scan
      // doesn't mean unchecking dozens (issue #273) — but pre-select the existing
      // local games being migrated up to the share (issue #281).
      setSelected(new Set(existingLocal.map(r => r.romPath)));
      setPhase("results");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Scan failed.");
      setPhase("results");
    }
  }

  async function addExtraPath(): Promise<void> {
    const folder = await emusync.dialog.openFolder();
    if (!folder) return;
    if (extraPaths.includes(folder)) return;
    await emusync.config.addRecentFolder(consoleSel, folder);
    const updated = [...extraPaths, folder];
    setSavedFolders(updated);
    setExtraPaths(updated);
    scanRoms(updated);
  }

  async function removeExtraPath(path: string): Promise<void> {
    const updated = extraPaths.filter(p => p !== path);
    setSavedFolders(updated);
    setExtraPaths(updated);
    const cfg = (await emusync.config.load()) ?? {};
    if (!cfg.recent_import_folders) cfg.recent_import_folders = {};
    cfg.recent_import_folders[consoleSel] = updated;
    await emusync.config.save(cfg);
    scanRoms(updated);
  }

  function removeRomDir(path: string): void {
    // Normalize the path for matching
    const normalizedPath = path.replace(/\/$/, "");

    // Find which ROMs to remove (match exact folder or any subfolder)
    const romsToRemove = roms.filter(r => {
      const normalizedRomPath = r.romFolderPath.replace(/\/$/, "");
      return normalizedRomPath === normalizedPath ||
             normalizedRomPath.startsWith(normalizedPath + "/");
    });

    // Mark folder as removed (hides it from the folder list)
    setRemovedDirs(prev => new Set([...prev, path]));

    // Also remove from romDirs to prevent re-detection on next scan
    setRomDirs(prev => prev.filter(dir => dir !== path));

    // Remove ROMs from this folder and all subfolders
    setRoms(prev => {
      return prev.filter(r => {
        const normalizedRomPath = r.romFolderPath.replace(/\/$/, "");
        return !(normalizedRomPath === normalizedPath ||
                 normalizedRomPath.startsWith(normalizedPath + "/"));
      });
    });

    setSelected(prev => {
      const next = new Set(prev);
      romsToRemove.forEach(r => next.delete(r.romPath));
      return next;
    });
  }

  function toggleRom(romPath: string): void {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(romPath)) next.delete(romPath);
      else next.add(romPath);
      return next;
    });
  }

  function toggleAll(paths: string[]): void {
    const allOn = paths.every(p => selected.has(p));
    setSelected(prev => {
      const next = new Set(prev);
      if (allOn) paths.forEach(p => next.delete(p));
      else paths.forEach(p => next.add(p));
      return next;
    });
  }

  function setName(romPath: string, value: string): void {
    setNames(prev => ({ ...prev, [romPath]: value }));
  }

  function computeNameConflicts(toImport: RomEntry[]): string[] {
    const displayNames = toImport.map(r => (names[r.romPath] ?? r.name).trim());
    const lowerNames   = displayNames.map(n => n.toLowerCase());
    const conflicts    = new Set<string>();

    // Within-selection duplicates
    const seen = new Set<string>();
    for (const n of lowerNames) {
      if (seen.has(n)) conflicts.add(n);
      seen.add(n);
    }

    // Against existing server games
    const serverNames = new Set(existingGames.map(g => g.name.toLowerCase()));
    for (const n of lowerNames) {
      if (serverNames.has(n)) conflicts.add(n);
    }

    // Return original-case names, deduplicated
    return [...new Set(displayNames.filter(n => conflicts.has(n.toLowerCase())))];
  }

  async function _runImport(toImport: RomEntry[]): Promise<void> {
    setProgress({ done: 0, total: toImport.length });
    setImportErrors([]);
    setPushResults([]);
    setPhase("importing");
    const errs: string[] = [];
    const imported: ImportedEntry[] = [];
    const consoleAbbr = getConsoleAbbreviation(consoleSel, consoles);
    // Shared-save consoles (PS2/DC/GC/PSP) share one card across all games, so
    // the per-game save must not be renamed/moved on import (#294/#295/#402).
    // Only PS2 also shares its STATES — the rest keep per-game state handling.
    const sharedLayout = usesSharedSaveLayout(consoleSel);
    const sharedStateLayout = usesSharedStateLayout(consoleSel);
    const scanRoots = [...new Set([...romDirs, ...extraPaths])].map(p => p.replace(/\/$/, ""));
    // Persist the chosen source + local destination for next time (issue #255).
    try {
      const cfg = (await emusync.config.load()) ?? {};
      cfg.import_rom_source = { ...(cfg.import_rom_source ?? {}), [consoleSel]: romSource };
      if (localRomRoot) cfg.import_local_folder = { ...(cfg.import_local_folder ?? {}), [consoleSel]: localRomRoot };
      await emusync.config.save(cfg);
    } catch { /* non-fatal */ }
    for (let i = 0; i < toImport.length; i++) {
      const rom = toImport[i];
      try {
        const displayName = names[rom.romPath] ?? rom.name;
        // Filesystem-safe base name to rename on-disk artifacts to (issue #283).
        // The display name (with spaces/punctuation) is what the game stores.
        const safeBase    = sanitizeFilename(displayName);

        const scanRoot   = (rom.romFolderPath ?? "").replace(/\/$/, "");

        const { romPath, savePath, statePath, launchCmd, romRelPath, netRoot, localCopyPath, romSha } =
          await resolveImportPaths(rom, { romSource, localRomRoot, scanRoots, scanRoot, safeBase, sharedLayout, sharedStateLayout });

        const slug = rom.linkedSlug ?? (await addGame(displayName, consoleAbbr)).slug;
        await setGameDevice(slug, {
          rom_path: romPath,
          save_path: savePath,
          launch_command: launchCmd,
          state_path: statePath,
          rom_folder_path: scanRoot || rom.romFolderPath || "",
          rom_source: romSource,
          rom_rel_path: romRelPath,
          local_rom_path: localCopyPath,
          ...(romSha ? { rom_sha256: romSha } : {}),
          // Network root + chosen local-copy destination land on the console row
          // so `Copy for offline play` / `emusync rom localize` know where to put it.
          ...(romSource === "network" ? {
            device_network_folder: netRoot,
            device_local_folder: localRomRoot,
          } : {}),
        });
        imported.push({ slug, name: displayName, savePath, statePath });
      } catch (e: unknown) {
        const reason = e instanceof Error ? e.message : "import failed";
        errs.push(`${names[rom.romPath] ?? rom.name} (${reason})`);
      }
      setProgress({ done: i + 1, total: toImport.length });
    }
    setImportErrors(errs);
    setPhase("done");
    // Network ROMs live on a share every device reaches, so there's nothing to
    // copy — cross-device config broadcast is tracked as a follow-up (#255).
    // Local ROMs auto-push their bytes to peers as before.
    if (imported.length > 0 && romSource !== "network") {
      autoPush(imported, consoleAbbr, { pushSaves, pushStates }, setPushResults);
    }
    // If another device already has save/state data for these games (or, for a
    // shared-layout console, the console's memory card), pull it down to this
    // device now — otherwise a fresh import shows up empty until the first
    // EmuSync-wrapped launch (issue #316). Runs regardless of rom source: a
    // network import has no ROM to copy, but still benefits from an existing
    // save. Best-effort; a pull failure here shouldn't block the import.
    if (imported.length > 0) pullFromServerIfNewer(imported, sharedLayout, sharedStateLayout, consoleAbbr);
    // Pre-fetch all 5 artwork types for every imported game now, so the
    // console's art-type dropdown and each game's Artwork tab always have
    // something cached instead of triggering a fresh SGDB fetch on demand
    // (issue #327, extended to all types by #411).
    if (imported.length > 0) prefetchArt(imported, consoleAbbr, setArtProgress);
  }

  async function doImport(): Promise<void> {
    const toImport = roms.filter(r => selected.has(r.romPath));
    const conflicts = computeNameConflicts(toImport);
    if (conflicts.length > 0) {
      setNameWarnings(conflicts);
      return;
    }
    await _runImport(toImport);
  }

  async function forceImport(): Promise<void> {
    setNameWarnings([]);
    await _runImport(roms.filter(r => selected.has(r.romPath)));
  }

  function dismissNameWarnings(): void {
    setNameWarnings([]);
  }

  async function pickLocalRomRoot(): Promise<void> {
    const folder = await emusync.dialog.openFolder();
    if (folder) setLocalRomRoot(folder);
  }

  function backToConsole(): void {
    setEmulators([]); setEmuSel(null); setSuggestions([]); setPhase("console");
  }

  function backToEmulator(): void {
    setRoms([]); setNames({}); setExtraPaths(savedFolders); setRomDirs([]); setRemovedDirs(new Set()); setPhase("emulator");
  }

  // ── derived ──────────────────────────────────────────────────────────────
  const grouped = groupByDir(roms);
  const selectedCount = roms.filter(r => selected.has(r.romPath)).length;
  const consoleLabel  = consoles.find(c => c.key === consoleSel)?.label ?? "";
  const currentStep   = stepIndex(phase);
  const showStepper   = phase !== "importing" && phase !== "done";
  // Merge auto-detected + extra dirs for display (no dupes), minus removed ones.
  const allRomDirs = [...new Set([...romDirs, ...extraPaths])].filter(p => !removedDirs.has(p));

  return {
    onClose, onImported,
    // state
    phase, consoles, consoleSel, emulators, suggestions, emuSel,
    extraPaths, removedDirs, roms, selected, names, error, progress,
    importErrors, pushResults, pushSaves, pushStates, artProgress,
    romSource, localRomRoot, nameWarnings,
    // derived
    grouped, selectedCount, consoleLabel, currentStep, showStepper, allRomDirs,
    // setters used directly by steps
    setConsoleSel, setEmuSel, setPushSaves, setPushStates, setName,
    setRomSource, pickLocalRomRoot,
    // handlers
    detectEmulators, scanRoms, addExtraPath, removeExtraPath, removeRomDir,
    toggleRom, toggleAll, doImport, forceImport, dismissNameWarnings,
    backToConsole, backToEmulator,
  };
}

export type ConsoleImportVM = ReturnType<typeof useConsoleImport>;
