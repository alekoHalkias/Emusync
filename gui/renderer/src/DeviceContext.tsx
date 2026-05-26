/**
 * Shared device state — polls /devices + /whoami every 30 seconds so every
 * component that needs the device list (DevicesButton count, GameList device
 * modal) reads from one shared fetch instead of each making independent calls.
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
  /** True only during the very first load (before any data has been received). */
  initialLoading: boolean;
  /** Force an immediate refresh (e.g. after removing a device). */
  refresh: () => Promise<void>;
};

const DeviceContext = createContext<DeviceContextValue>({
  devices: [],
  currentDeviceId: null,
  initialLoading: true,
  refresh: async () => {},
});

const POLL_INTERVAL_MS = 30_000;
const RETRY_INTERVAL_MS = 5_000;

export function DeviceProvider({ children }: { children: React.ReactNode }): React.ReactElement {
  const [devices, setDevices] = useState<Device[]>([]);
  const [currentDeviceId, setCurrentDeviceId] = useState<string | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

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

  return (
    <DeviceContext.Provider value={{ devices, currentDeviceId, initialLoading, refresh }}>
      {children}
    </DeviceContext.Provider>
  );
}

export function useDevices(): DeviceContextValue {
  return useContext(DeviceContext);
}
