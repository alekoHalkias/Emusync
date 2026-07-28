// Save / state / ROM sync IPC — the handlers that move bytes between this
// device and the Python server. Split (issue #370) into one module per
// domain under sync/: save.ts, memcard.ts, state.ts, rom.ts, recovery.ts.
import { registerSaveIpc } from "./sync/save";
import { registerMemcardIpc } from "./sync/memcard";
import { registerStateIpc } from "./sync/state";
import { registerRomIpc } from "./sync/rom";
import { registerRecoveryIpc } from "./sync/recovery";

export function registerSyncIpc(): void {
  registerSaveIpc();
  registerMemcardIpc();
  registerStateIpc();
  registerRomIpc();
  registerRecoveryIpc();
}
