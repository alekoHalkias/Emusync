import React from "react";

// Shared inline-SVG icons for the handful of glyphs that were repeated as
// raw emoji (✕ close, ▶ play, ⏷ chevron) across many components — emoji
// render differently per OS/font, which worked against the uniform design
// pass in #470. Warning (⚠) and per-event-type glyphs (🟢/■/↑ in the
// activity log) are left as text: they're inline punctuation in prose or a
// small self-contained lookup, not a repeated "system icon".
type IconProps = { size?: number; className?: string };

export function CloseIcon({ size = 12, className }: IconProps): React.ReactElement {
  return (
    <svg width={size} height={size} viewBox="0 0 12 12" fill="none" className={className} aria-hidden="true">
      <path d="M1 1L11 11M11 1L1 11" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function PlayIcon({ size = 12, className }: IconProps): React.ReactElement {
  return (
    <svg width={size} height={size} viewBox="0 0 12 12" fill="currentColor" className={className} aria-hidden="true">
      <path d="M2 1.2v9.6L10.5 6z" />
    </svg>
  );
}

export function ChevronDownIcon({ size = 10, className }: IconProps): React.ReactElement {
  return (
    <svg width={size} height={size} viewBox="0 0 12 8" fill="none" className={className} aria-hidden="true">
      <path d="M1 1.5L6 6.5L11 1.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
