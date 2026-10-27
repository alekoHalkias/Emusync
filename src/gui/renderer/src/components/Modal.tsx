import React, { useEffect, useId, useRef } from "react";

// Shared modal shell (#530): overlay + dialog semantics + focus in/restore +
// a single Escape/backdrop path that is ignored while `busy` and only ever
// closes the topmost open Modal (stacked modals used to close together).
// useGamepadNav's B button dispatches a synthetic Escape, so it gets this too.
export type ModalSize = "sm" | "md" | "lg" | "xl" | "wizard";

type Props = {
  onClose: () => void;
  busy?: boolean;
  size?: ModalSize;
  style?: React.CSSProperties;
  zIndex?: number;
  children: React.ReactNode;
};

const stack: symbol[] = [];

export default function Modal({ onClose, busy = false, size = "sm", style, zIndex, children }: Props): React.ReactElement {
  const ref = useRef<HTMLDivElement>(null);
  const latest = useRef({ onClose, busy });
  latest.current = { onClose, busy };
  const titleId = useId();

  useEffect(() => {
    const token = Symbol("modal");
    stack.push(token);
    const prev = document.activeElement as HTMLElement | null;
    const el = ref.current;
    const title = el?.querySelector("h3");
    if (title) { title.id ||= titleId; el?.setAttribute("aria-labelledby", title.id); }
    if (el && !el.contains(document.activeElement)) el.focus({ preventScroll: true });

    function onKey(e: KeyboardEvent): void {
      if (e.key !== "Escape" || stack[stack.length - 1] !== token) return;
      if (!latest.current.busy) latest.current.onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      stack.splice(stack.indexOf(token), 1);
      if (prev?.isConnected) prev.focus({ preventScroll: true });
    };
  }, [titleId]);

  return (
    <div
      className="modal-overlay"
      style={zIndex ? { zIndex } : undefined}
      onClick={() => { if (!busy) onClose(); }}
    >
      <div
        ref={ref}
        className={`modal modal-${size}`}
        style={style}
        role="dialog"
        aria-modal="true"
        aria-busy={busy || undefined}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}
