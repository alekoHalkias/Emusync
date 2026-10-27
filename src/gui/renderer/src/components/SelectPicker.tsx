import React, { useEffect, useRef, useState } from "react";

// Gamepad stand-in for a native <select> popup (#500): useGamepadNav fires
// "pad-select" when A lands on a <select>; this lists its options as buttons
// in a .modal-overlay so the D-pad trap and B-to-close apply for free.
export default function SelectPicker(): React.ReactElement | null {
  const [sel, setSel] = useState<HTMLSelectElement | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const open = (e: Event) => setSel((e as CustomEvent<HTMLSelectElement>).detail);
    window.addEventListener("pad-select", open);
    return () => window.removeEventListener("pad-select", open);
  }, []);

  useEffect(() => {
    if (!sel) return;
    // Capture + stopImmediatePropagation so B closes only the picker, not the modal under it.
    function onKey(e: KeyboardEvent): void {
      if (e.key !== "Escape") return;
      e.stopImmediatePropagation();
      close();
    }
    window.addEventListener("keydown", onKey, true);
    ref.current?.querySelector<HTMLElement>(".btn-primary, button")?.focus();
    return () => window.removeEventListener("keydown", onKey, true);
  }, [sel]);

  function close(): void {
    sel?.focus();
    setSel(null);
  }

  function pick(value: string): void {
    if (!sel) return;
    sel.value = value;
    sel.dispatchEvent(new Event("change", { bubbles: true }));
    close();
  }

  if (!sel) return null;
  return (
    <div className="modal-overlay" style={{ zIndex: 1000 }} onClick={close}>
      <div ref={ref} className="modal" style={{ width: 360, maxWidth: "92vw", maxHeight: "80vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
        {Array.from(sel.options).map((o) => (
          <button
            key={o.value}
            className={`btn ${o.value === sel.value ? "btn-primary" : "btn-ghost"}`}
            style={{ display: "block", width: "100%", textAlign: "left" }}
            onClick={() => pick(o.value)}
          >
            {o.text}
          </button>
        ))}
      </div>
    </div>
  );
}
