// Answer a network-upload request (#660) on this device. The upload itself lives
// in Python (cli/netrom.py:upload_to_network); this only shells out to the CLI, like
// save.ts does for manual push/pull (#479).
import { ipcMain } from "electron";
import { runCliTransfer } from "./save";

export function registerNetUploadIpc(): void {
  ipcMain.handle("rom:fulfillNetworkUpload", async (_event, requestId: string, approve: boolean): Promise<{ ok: boolean; error?: string }> => {
    const { code, output } = await runCliTransfer(["rom", "fulfill-network-upload", requestId, ...(approve ? [] : ["--decline"])]);
    return code === 0 ? { ok: true } : { ok: false, error: output || "Upload failed" };
  });
}
