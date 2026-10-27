import { useEffect } from "react";

// Closes the topmost modal on Escape. Shared across all modal shells (#474).
export function useEscapeToClose(onClose: () => void): void {
  useEffect(() => {
    function handler(e: KeyboardEvent): void {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);
}

// Same, but for a component that stacks several independently-toggled popups
// on top of one another (e.g. a settings modal that opens sub-popups without
// closing itself) — closes only the first one in the given priority order
// (topmost/most-recently-opened first).
export function useEscapeToCloseTopmost(...popups: [isOpen: boolean, close: () => void][]): void {
  useEffect(() => {
    function handler(e: KeyboardEvent): void {
      if (e.key !== "Escape") return;
      const topmost = popups.find(([isOpen]) => isOpen);
      topmost?.[1]();
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  });
}
