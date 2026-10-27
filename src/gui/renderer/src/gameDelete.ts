// Tiered game-delete orchestration (issue #343), shared by the single-game
// delete button (GameConfig.tsx) and the multi-select bulk delete
// (GameGrid.tsx) so both stay in sync.
//
// Tier 1 (always): unlink the game from this device only — the game itself,
// its saves/states, and every other device's config are untouched.
// Tier 2 (opt-in, deleteLocalRom): also delete the ROM file from this
// device's disk (a network ROM's localized copy, or a local-source ROM).
// Tier 3 (opt-in, removeEverywhere): fully purge the game — every device,
// save/state history, blobs — via the existing full-delete route. Does NOT
// touch the network-share master; that's Tier 3b.
// Tier 3b (opt-in, deleteNetworkRom, independent of removeEverywhere): also
// delete the network-share master ROM for a network-sourced game (#376 — a
// user may want to fully unlink a game from EmuSync without touching the
// actual file sitting on the NAS).
import { getGameDevice, removeGame, removeGameDevice } from "./api";

export type DeleteGameOptions = {
  deleteLocalRom: boolean;
  removeEverywhere: boolean;
  deleteNetworkRom: boolean;
};

export async function deleteGame(slug: string, opts: DeleteGameOptions): Promise<void> {
  const gd = await getGameDevice(slug).catch(() => null);

  if (opts.deleteLocalRom && gd) {
    if (gd.rom_source === "network") {
      // Deletes local_rom_path only, cleans empty dirs, never touches the
      // master; "No local copy" is expected when nothing was localized.
      await window.emusync.rom.delocalize(slug).catch(() => {});
    } else if (gd.rom_path) {
      await window.emusync.rom.deleteFile(gd.rom_path).catch(() => {});
    }
  }

  if (opts.deleteNetworkRom && gd && gd.rom_source === "network" && gd.rom_path) {
    await window.emusync.rom.deleteFile(gd.rom_path).catch(() => {});
  }

  if (opts.removeEverywhere) {
    await removeGame(slug);
  } else {
    await removeGameDevice(slug);
  }
}
