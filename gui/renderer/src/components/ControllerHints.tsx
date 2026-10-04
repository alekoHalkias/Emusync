import React from "react";
import { GlyphFamily, useInputMode } from "../useGamepadNav";

// Face-button labels per controller family. Only buttons useGamepadNav
// actually binds are listed — keep in sync with it.
const GLYPHS: Record<GlyphFamily, { a: string; b: string; x: string }> = {
  xbox: { a: "A", b: "B", x: "X" },
  deck: { a: "A", b: "B", x: "X" },
  generic: { a: "A", b: "B", x: "X" },
  playstation: { a: "✕", b: "○", x: "□" },
};

export default function ControllerHints(): React.ReactElement | null {
  const { mode, family } = useInputMode();
  if (mode !== "controller") return null;
  const g = GLYPHS[family];
  return (
    <footer className="controller-hints">
      <span><kbd>{g.a}</kbd> Select</span>
      <span><kbd>{g.b}</kbd> Back</span>
      <span><kbd>{g.x}</kbd> Play</span>
    </footer>
  );
}
