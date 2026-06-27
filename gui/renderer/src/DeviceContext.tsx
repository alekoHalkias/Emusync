/**
 * Shared device state — polls /devices + /whoami every 30 seconds so every
 * component that needs the device list (DevicesPanel in the Server modal, the
 * per-game devices tab) reads from one shared fetch instead of each making
 * independent calls.
 *
 * On error it retries after 5 seconds; after a successful retry it goes back
 * to the 30-second interval. This means a brief server blip recovers quickly
 * without hammering the server.
 */

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { listDevices, whoami, type Device } from "./api";

type DeviceContextValue = {
  devices: Device[];
  currentDeviceId: string | null;
  /** The server's LAN IP — devices whose last_ip matches this are the host. */
  serverIp: string | null;
  /** True if a device's IP matches the server IP (or it is the current device on a server install). */
  isServerDevice: (d: Device) => boolean;
  /** True only during the very first load (before any data has been received). */
  initialLoading: boolean;
  /** Force an immediate refresh (e.g. after removing a device). */
  refresh: () => Promise<void>;
};

const DeviceContext = createContext<DeviceContextValue>({
  devices: [],
  currentDeviceId: null,
  serverIp: null,
  isServerDevice: () => false,
  initialLoading: true,
  refresh: async () => {},
});

const POLL_INTERVAL_MS = 30_000;
const RETRY_INTERVAL_MS = 5_000;

export function DeviceProvider({ children }: { children: React.ReactNode }): React.ReactElement {
  const [devices, setDevices] = useState<Device[]>([]);
  const [currentDeviceId, setCurrentDeviceId] = useState<string | null>(null);
  const [serverIp, setServerIp] = useState<string | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  // Load server IP once on mount: prefer server_host from config (client path),
  // fall back to this machine's LAN IP (server path where server_host is blank).
  useEffect(() => {
    (async () => {
      try {
        const cfg = await window.emusync.config.load();
        const host: string = cfg?.server_host || "";
        if (host && host !== "localhost" && host !== "127.0.0.1") {
          setServerIp(host);
        } else {
          const ip = await window.emusync.server.localIp();
          if (ip) setServerIp(ip);
        }
      } catch {}
    })();
  }, []);

  const scheduleNext = useCallback((delayMs: number) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => fetchDevices(), delayMs);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const fetchDevices = useCallback(async () => {
    try {
      const [devs, me] = await Promise.all([listDevices(), whoami()]);
      if (!mountedRef.current) return;
      setDevices(devs);
      setCurrentDeviceId(me.device_id);
      setInitialLoading(false);
      scheduleNext(POLL_INTERVAL_MS);
    } catch {
      if (!mountedRef.current) return;
      // Don't clear existing data on transient error — keep showing last known values.
      setInitialLoading(false);
      scheduleNext(RETRY_INTERVAL_MS);
    }
  }, [scheduleNext]);

  // Kick off the first fetch immediately on mount.
  useEffect(() => {
    mountedRef.current = true;
    fetchDevices();
    return () => {
      mountedRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [fetchDevices]);

  const refresh = useCallback(async () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    await fetchDevices();
  }, [fetchDevices]);

  const isServerDevice = useCallback((d: Device): boolean => {
    if (!serverIp) return false;
    // Match by last_ip (client view: server_host matches device IP)
    if (d.last_ip === serverIp) return true;
    // Match by current device being the server (server view: localIp = serverIp)
    if (d.id === currentDeviceId && d.last_ip && serverIp &&
        (d.last_ip === "127.0.0.1" || d.last_ip === "::1")) return true;
    return false;
  }, [serverIp, currentDeviceId]);

  return (
    <DeviceContext.Provider value={{ devices, currentDeviceId, serverIp, isServerDevice, initialLoading, refresh }}>
      {children}
    </DeviceContext.Provider>
  );
}

export function useDevices(): DeviceContextValue {
  return useContext(DeviceContext);
}
