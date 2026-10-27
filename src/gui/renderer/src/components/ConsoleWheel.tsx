import React, { useEffect, useRef, useState } from "react";

export type WheelItem = {
  key: string;
  label: string;
  abbr: string;
  totalGames: number;
  localGames: number;
  color: string;
};

type Props = {
  items: WheelItem[];
  renderIcon: (item: WheelItem) => React.ReactNode;
  onSelect: (item: WheelItem) => void;
};

// Big Picture console home (#503): consoles on a rotating 3D ring, selected one
// at the front. Rotation arrives as a "wheel-rotate" event (D-pad/stick/LB/RB
// via useGamepadNav) or ←/→ here.
const FULL_RING_MIN = 9; // fewer items than this form a fixed-step arc, not a closed ring
const ARC_STEP = 40;
const RADIUS = 520;

export default function ConsoleWheel({ items, renderIcon, onSelect }: Props): React.ReactElement {
  const n = items.length;
  const [rawSel, setSel] = useState(0);
  const sel = Math.min(rawSel, n - 1); // list can shrink while mounted
  const frontRef = useRef<HTMLDivElement | null>(null);
  const prevAngles = useRef<number[]>([]);
  const mounted = useRef(false);

  const rotate = (step: number) => setSel((s) => (s + step + n) % n);

  useEffect(() => {
    const onRotate = (e: Event) => rotate((e as CustomEvent<number>).detail);
    const onKey = (e: KeyboardEvent) => {
      if (document.querySelector(".modal-overlay")) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT")) return;
      if (e.key === "ArrowLeft") rotate(-1);
      else if (e.key === "ArrowRight") rotate(1);
    };
    window.addEventListener("wheel-rotate", onRotate);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("wheel-rotate", onRotate);
      window.removeEventListener("keydown", onKey);
    };
  }, [n]);

  // Tint the Big Picture backdrop with the front console's accent.
  const front = items[sel];
  useEffect(() => {
    document.documentElement.style.setProperty("--bp-accent", front.color);
    return () => { document.documentElement.style.removeProperty("--bp-accent"); };
  }, [front.color]);

  // Keep focus on the front console after a rotation (skip first mount so we
  // don't steal focus from the topbar).
  useEffect(() => {
    if (mounted.current && document.activeElement?.closest(".console-wheel")) frontRef.current?.focus();
    mounted.current = true;
  }, [sel]);

  const closed = n >= FULL_RING_MIN;
  const step = closed ? 360 / n : ARC_STEP;

  return (
    <div className="console-wheel-stage">
      <div className="console-wheel">
        <div className="console-wheel-ring" style={{ transform: `translateZ(-${RADIUS}px)` }}>
          {items.map((c, i) => {
            let d = i - sel;
            if (closed) {
              d = ((d % n) + n) % n;
              if (d > n / 2) d -= n;
            }
            let angle = d * step;
            // Keep each item's angle continuous across the ring's wrap point so
            // the CSS transition never sweeps an item through the front.
            if (closed && prevAngles.current[i] !== undefined) {
              angle = prevAngles.current[i] + ((((angle - prevAngles.current[i]) % 360) + 540) % 360) - 180;
            }
            prevAngles.current[i] = angle;
            const cos = Math.cos((angle * Math.PI) / 180);
            const isFront = i === sel;
            return (
              <div
                key={c.key}
                ref={isFront ? frontRef : undefined}
                role="button"
                tabIndex={isFront ? 0 : -1}
                className={`console-card wheel-item${isFront ? " wheel-item-front" : ""}`}
                data-console-key={c.key}
                style={{
                  "--console-accent": c.color,
                  transform: `rotateY(${angle}deg) translateZ(${RADIUS}px)`,
                  opacity: cos > 0 ? cos ** 1.5 : 0,
                  pointerEvents: cos > 0.3 ? "auto" : "none",
                } as React.CSSProperties}
                onClick={() => (isFront ? onSelect(c) : setSel(i))}
                onFocus={() => { if (!isFront) setSel(i); }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); (e.currentTarget as HTMLElement).click(); }
                }}
              >
                <div className="console-card-icon-wrap">{renderIcon(c)}</div>
              </div>
            );
          })}
        </div>
      </div>
      <div className="console-wheel-caption">
        <div className="console-wheel-label">{front.label}</div>
        <div className="console-wheel-count">
          {front.localGames > 0 && front.localGames < front.totalGames
            ? `${front.localGames} / ${front.totalGames}`
            : front.totalGames}{" "}
          game{front.totalGames !== 1 ? "s" : ""}
        </div>
      </div>
    </div>
  );
}
