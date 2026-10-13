// Shared transfer-speed estimate for DownloadProgressModal (#396, #520): a
// light EMA over >=500ms windows so the figure reads steady instead of
// jittering per chunk. Call with the cumulative byte count on every progress
// event; `reset(bytes)` re-bases when a new transfer starts.
export function createSpeedMeter(startBytes = 0): { update: (bytes: number) => number; reset: (bytes: number) => void } {
  const s = { lastT: Date.now(), lastBytes: startBytes, bps: 0 };
  return {
    update(bytes: number): number {
      const now = Date.now();
      const dt = now - s.lastT;
      if (dt >= 500) {
        const inst = ((bytes - s.lastBytes) / dt) * 1000;
        s.bps = s.bps > 0 ? s.bps * 0.7 + inst * 0.3 : inst;
        s.lastT = now;
        s.lastBytes = bytes;
      }
      return s.bps;
    },
    reset(bytes: number): void {
      s.lastT = Date.now();
      s.lastBytes = bytes;
    },
  };
}
