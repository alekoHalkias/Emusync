import React from "react";
import { GlyphFamily, useInputMode } from "../useGamepadNav";

// Face-button labels per controller family. Only buttons useGamepadNav
// actually binds are listed — keep in sync with it.
const GLYPHS: Record<GlyphFamily, { a: string; b: string; x: string; y: string }> = {
  xbox: { a: "A", b: "B", x: "X", y: "Y" },
  deck: { a: "A", b: "B", x: "X", y: "Y" },
  generic: { a: "A", b: "B", x: "X", y: "Y" },
  playstation: { a: "✕", b: "○", x: "□", y: "△" },
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
      <span><kbd>{g.y}</kbd> Pick</span>
      <span><kbd>LB</kbd><kbd>RB</kbd> Tabs</span>
    </footer>
  );
}
