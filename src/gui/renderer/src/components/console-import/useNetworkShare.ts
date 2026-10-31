// Share-identity check for the console import wizard (#644): reads/creates the
// network folder's marker file and compares it with the IDs other devices registered.
import { useEffect, useState } from "react";
import { getConsoleShares, getDeviceConsoles, getDeviceId, updateDeviceConsole, type ConsoleShare } from "../../api";
import { shareStatus, type ShareStatus } from "./helpers";

const emusync = window.emusync;

export type NetworkShare = { status: ShareStatus; shareId: string | null; peer?: ConsoleShare };

export function useNetworkShare(consoleAbbr: string, networkRoot: string) {
  const [share, setShare] = useState<NetworkShare>({ status: "none", shareId: null });

  useEffect(() => {
    if (!networkRoot || !consoleAbbr) { setShare({ status: "none", shareId: null }); return; }
    let cancelled = false;
    setShare({ status: "checking", shareId: null });
    (async () => {
      const marker = await emusync.files.ensureShareMarker(networkRoot).catch(() => ({ id: null }));
      const peers = await getConsoleShares(consoleAbbr).catch(() => null);
      if (!cancelled) setShare({ shareId: marker.id, ...shareStatus(marker.id, peers) });
    })();
    return () => { cancelled = true; };
  }, [consoleAbbr, networkRoot]);

  /** Record this share's ID on the device's console row (exists once a game is configured). */
  async function saveShareId(): Promise<void> {
    if (!share.shareId) return;
    try {
      const row = (await getDeviceConsoles(getDeviceId())).find(c => c.console_name === consoleAbbr);
      if (!row?.id || row.network_share_id === share.shareId) return;
      const { id: _id, console_name: _name, ...fields } = row;
      await updateDeviceConsole(getDeviceId(), row.id, { ...fields, network_share_id: share.shareId });
    } catch { /* non-fatal - the next import retries */ }
  }

  return { share, saveShareId };
}
