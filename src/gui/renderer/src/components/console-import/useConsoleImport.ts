// State machine + async orchestration for the Add-Console wizard.
// The presentational step components consume the object this hook returns.
import { useEffect, useRef, useState } from "react";
import { addGame, setGameDevice, gamesOverview, type GameOverview } from "../../api";
import {
  annotateRoms,
  classifyByRoot,
  dedupeAndLink,
  existingLocalGamesForConsole,
  getConsoleAbbreviation,
  groupByDir,
  relPathUnder,
  sanitizeFilename,
  usesSharedSaveLayout,
  usesSharedStateLayout,
  stepIndex,
} from "./helpers";
import { autoPush, backfillSwitchTitleIds, prefetchArt, pullFromServerIfNewer } from "./postImport";
import { resolveImportPaths } from "./resolveRomPaths";
import { useNetworkShare } from "./useNetworkShare";
import { filterIgnored, saveIgnoredRoms } from "./ignoredRoms";
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

/** Last network folder for a console (#644); older configs only stored a source flag, where the first saved folder was the share. */
function savedNetworkRoot(cfg: Record<string, any> | null, consoleKey: string, folders: string[]): string {
  const saved = cfg?.import_network_folder?.[consoleKey];
  if (saved !== undefined) return saved;
  return cfg?.import_rom_source?.[consoleKey] === "network" ? (folders[0] ?? "") : "";
}

export function useConsoleImport({ onClose, onImported, initialConsole, initialRomDirs, initialNetworkRoot, initialLocalRoot }: Props) {
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
  const [artProgress, setArtProgress]   = useState({ done: 0, total: 0, failed: 0 });
  const [pushSaves, setPushSaves]       = useState(true);
  const [pushStates, setPushStates]     = useState(true);
  // Locations (issues #255, #644): an optional network share and the local folder
  // (where copies of network ROMs land). The ROM source is derived: a network
  // folder means network-sourced ROMs, otherwise local.
  const [networkRoot, setNetworkRoot]   = useState("");
  const [localRomRoot, setLocalRomRoot] = useState("");
  const romSource: "local" | "network" = networkRoot ? "network" : "local";
  const [linkedCount, setLinkedCount]   = useState<number | null>(null);
  // ROM paths hidden from scans (#646); loaded with the config when detection finishes.
  const [ignored, setIgnored]           = useState<Set<string>>(new Set());
  const linkedFor = useRef("");
  const [existingGames, setExistingGames] = useState<GameOverview[]>([]);
  const [nameWarnings, setNameWarnings] = useState<string[]>([]);

  useEffect(() => {
    emusync.emulator.consoles().then(setConsoles);
  }, []);

  const { share, saveShareId } = useNetworkShare(getConsoleAbbreviation(consoleSel, consoles), networkRoot);

  // A matching share (#644): games another device already put on it get this
  // device's path with no file operations - the first device already named them.
  useEffect(() => {
    if (share.status !== "same" || phase !== "results" || linkedFor.current === networkRoot) return;
    linkedFor.current = networkRoot;
    void linkShareGames();
  }, [share.status, phase, networkRoot]);

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
          // A caller-provided folder (bulk-library import, #462) takes over
          // scanning entirely — union with unrelated recent folders would
          // silently widen the scan to leftovers from a past single-console import.
          const initial = initialRomDirs && initialRomDirs.length > 0 ? initialRomDirs : saved;
          setSavedFolders(initial);
          setExtraPaths(initial);
          setNetworkRoot(initialNetworkRoot ?? savedNetworkRoot(cfg, consoleSel, initial));
          setIgnored(new Set(cfg?.import_ignored_roms?.[consoleSel] ?? []));
          setLocalRomRoot(initialLocalRoot ?? cfg?.import_local_folder?.[consoleSel] ?? "");
          if (options.length === 1) setEmuSel(options[0]);
          setPhase("emulator");
        } catch {
          setEmulators([]);
          setPhase("emulator");
        }
      })();
    }
  }, [initialConsole, consoleSel, phase, initialRomDirs, initialNetworkRoot, initialLocalRoot]);

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
      // Remember the last network + local folder per console (issues #255, #644).
      setNetworkRoot(savedNetworkRoot(cfg, consoleSel, saved));
      setIgnored(new Set(cfg?.import_ignored_roms?.[consoleSel] ?? []));
      setLocalRomRoot(cfg?.import_local_folder?.[consoleSel] ?? "");
      if (options.length === 1) setEmuSel(options[0]);
      setPhase("emulator");
    } catch {
      setEmulators([]);
      setPhase("emulator");
    }
  }

  async function scanRoms(paths: string[], over: { networkRoot?: string; localRoot?: string } = {}): Promise<void> {
    if (!emuSel) return;
    const net = over.networkRoot ?? networkRoot;
    const loc = over.localRoot ?? localRomRoot;
    setPhase("scanning");
    setError("");
    try {
      // Network import (issue #270): also scan the console's local-copy folder so
      // ROMs already on local disk are detected — local-only ones get uploaded to
      // the share, ones present in both are treated as already localized.
      const scanNetwork = !!net;
      const withNet = net && !paths.includes(net) ? [net, ...paths] : paths;
      const scanPaths = loc && !withNet.includes(loc) ? [...withNet, loc] : withNet;
      const result = await emusync.emulator.scan(consoleSel, emuSel, scanPaths);
      let annotated = annotateRoms(filterIgnored(result.roms, ignored), scanPaths, result.romDirs ?? []);

      // Tag each ROM network/local/both and merge net+local duplicates into one row.
      if (scanNetwork) {
        annotated = classifyByRoot(annotated, withNet, loc);
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

  /** Hide ROMs from this and later scans (#646). A network+local pair ignores both paths. */
  function ignoreRoms(list: RomEntry[]): void {
    const gone = new Set(list.map(r => r.romPath));
    const next = new Set([...ignored, ...list.flatMap(r => [r.romPath, r.localRomPath ?? ""]).filter(Boolean)]);
    setIgnored(next);
    void saveIgnoredRoms(consoleSel, [...next]);
    setRoms(prev => prev.filter(r => !gone.has(r.romPath)));
    setSelected(prev => new Set([...prev].filter(p => !gone.has(p))));
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

    // Against existing server games — skip ROMs that already carry a
    // linkedSlug (dedupeAndLink matched them to a game that exists on
    // another device but isn't set up on this one yet): those import by
    // linking to the existing game, not by creating a new one, so sharing
    // its name isn't a duplicate.
    const serverNames = new Set(existingGames.map(g => g.name.toLowerCase()));
    toImport.forEach((r, i) => {
      if (r.linkedSlug) return;
      if (serverNames.has(lowerNames[i])) conflicts.add(lowerNames[i]);
    });

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
    const scanRoots = [...new Set([networkRoot, ...romDirs, ...extraPaths].filter(Boolean))].map(p => p.replace(/\/$/, ""));
    // Persist the chosen source + local destination for next time (issue #255).
    try {
      const cfg = (await emusync.config.load()) ?? {};
      cfg.import_rom_source = { ...(cfg.import_rom_source ?? {}), [consoleSel]: romSource };
      cfg.import_network_folder = { ...(cfg.import_network_folder ?? {}), [consoleSel]: networkRoot };
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
          ...(romSource === "network" ? { device_network_folder: netRoot } : {}),
          ...(localRomRoot ? { device_local_folder: localRomRoot } : {}),
        });
        imported.push({ slug, name: displayName, savePath, statePath });
      } catch (e: unknown) {
        const reason = e instanceof Error ? e.message : "import failed";
        errs.push(`${names[rom.romPath] ?? rom.name} (${reason})`);
      }
      setProgress({ done: i + 1, total: toImport.length });
    }
    setImportErrors(errs);
    if (imported.length > 0 && networkRoot) void saveShareId();
    setPhase("done");
    // Network ROMs live on a share every device reaches, so there's nothing to
    // copy — cross-device config broadcast is tracked as a follow-up (#255).
    // Local ROMs auto-push their bytes to peers as before.
    if (imported.length > 0 && romSource !== "network") {
      autoPush(imported, consoleAbbr, { pushSaves, pushStates }, setPushResults);
    }
    // Discover switch_title_id by name before the game is ever launched
    // (#448) — best-effort, doesn't block the rest of the import.
    if (imported.length > 0 && consoleAbbr === "Switch") {
      backfillSwitchTitleIds(imported);
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
    // (issue #327, extended to all types by #411). Uses the canonical
    // console key (consoleSel), not the stored abbreviation — they diverge
    // for GameCube ("gc" vs "gamecube"), which would silently cache art
    // under a folder the grid never reads from (issue #419).
    if (imported.length > 0) prefetchArt(imported, consoleSel, setArtProgress);
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

  // Location pickers rescan so presence (network / local / both) is reclassified.
  async function pickLocalRomRoot(): Promise<void> {
    const folder = await emusync.dialog.openFolder();
    if (!folder) return;
    setLocalRomRoot(folder);
    void scanRoms(extraPaths, { localRoot: folder });
  }

  async function pickNetworkRoot(): Promise<void> {
    const folder = await emusync.dialog.openFolder();
    if (!folder) return;
    setNetworkRoot(folder);
    setLinkedCount(null);
    void scanRoms(extraPaths, { networkRoot: folder });
  }

  function clearLocalRoot(): void {
    setLocalRomRoot("");
    void scanRoms(extraPaths, { localRoot: "" });
  }

  function clearNetworkRoot(): void {
    setNetworkRoot("");
    setLinkedCount(null);
    void scanRoms(extraPaths, { networkRoot: "" });
  }

  async function linkShareGames(): Promise<void> {
    // Only ROMs found on the share: a local-only file must not become a network master.
    const toLink = roms.filter(r => r.linkedSlug && !r.existingLocal && (r.presence === "network" || r.presence === "both"));
    let linked = 0;
    const done = new Set<string>();
    for (const rom of toLink) {
      try {
        await setGameDevice(rom.linkedSlug!, {
          rom_path: rom.romPath,
          save_path: rom.savePath,
          launch_command: rom.launchCommand,
          state_path: rom.statePath ?? "",
          rom_folder_path: rom.romFolderPath,
          rom_source: "network",
          rom_rel_path: relPathUnder(rom.romPath, [networkRoot]),
          local_rom_path: rom.presence === "both" ? (rom.localRomPath ?? "") : "",
          device_network_folder: networkRoot,
          ...(localRomRoot ? { device_local_folder: localRomRoot } : {}),
        });
        done.add(rom.romPath);
        linked++;
      } catch { /* left in the list to import manually */ }
    }
    if (done.size === 0) return;
    setRoms(prev => prev.filter(r => !done.has(r.romPath)));
    setSelected(prev => new Set([...prev].filter(p => !done.has(p))));
    setLinkedCount(linked);
    void saveShareId();
    onImported(); // grid must reload now; Done is not the only way to close the wizard (#664)
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
  const allRomDirs = [...new Set([...romDirs, ...extraPaths])]
    .filter(p => !removedDirs.has(p) && p !== networkRoot && p !== localRomRoot);

  return {
    onClose, onImported,
    // state
    phase, consoles, consoleSel, emulators, suggestions, emuSel,
    extraPaths, removedDirs, roms, selected, names, error, progress,
    importErrors, pushResults, pushSaves, pushStates, artProgress,
    romSource, networkRoot, localRomRoot, nameWarnings, share, linkedCount, ignoredCount: ignored.size,
    // derived
    grouped, selectedCount, consoleLabel, currentStep, showStepper, allRomDirs,
    // setters used directly by steps
    setConsoleSel, setEmuSel, setPushSaves, setPushStates, setName,
    pickLocalRomRoot, pickNetworkRoot, clearLocalRoot, clearNetworkRoot,
    // handlers
    detectEmulators, scanRoms, ignoreRoms, addExtraPath, removeExtraPath, removeRomDir,
    toggleRom, toggleAll, doImport, forceImport, dismissNameWarnings,
    backToConsole, backToEmulator,
  };
}

export type ConsoleImportVM = ReturnType<typeof useConsoleImport>;
