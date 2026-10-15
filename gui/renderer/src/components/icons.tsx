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

export function FilterIcon({ size = 14, className }: IconProps): React.ReactElement {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" className={className} aria-hidden="true">
      <path d="M2 3h12l-4.5 5.5V13l-3-1.5V8.5L2 3z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
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

// Replacements for the emoji / pictographic glyphs that used to stand in for
// icons (#559). Stroke icons on a 16px grid that inherit currentColor and
// default to 1em, so they occupy the same space as the glyph they replaced.
type SizedProps = { size?: number | string; className?: string };

function glyph(children: React.ReactNode, filled = false) {
  return function Icon({ size = "1em", className }: SizedProps): React.ReactElement {
    return (
      <svg
        width={size} height={size} viewBox="0 0 16 16" aria-hidden="true"
        className={className ? `icon ${className}` : "icon"}
        fill={filled ? "currentColor" : "none"} stroke={filled ? "none" : "currentColor"}
        strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
      >
        {children}
      </svg>
    );
  };
}

export const GamepadIcon = glyph(<><path d="M4.5 5h7a3.5 3.5 0 0 1 3.4 4.3l-.5 2.2a1.8 1.8 0 0 1-3 .9L10 11H6l-1.4 1.4a1.8 1.8 0 0 1-3-.9l-.5-2.2A3.5 3.5 0 0 1 4.5 5z" /><path d="M5 7v2M4 8h2M10.5 8h.01M12 7h.01" /></>);
export const TrashIcon = glyph(<path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.6 8.5h5.8l.6-8.5M7 7v4M9 7v4" />);
export const FolderIcon = glyph(<path d="M2 4.5A1.5 1.5 0 0 1 3.5 3h2.8l1.4 1.5h4.8A1.5 1.5 0 0 1 14 6v5.5a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 11.5z" />);
export const PlusIcon = glyph(<path d="M8 3v10M3 8h10" />);
export const LockIcon = glyph(<path d="M4 7h8v6H4zM5.5 7V5a2.5 2.5 0 0 1 5 0v2" />);
export const BoltIcon = glyph(<path d="M9 2L4 9h3.5L7 14l5-7H8.5z" />);
export const SaveIcon = glyph(<path d="M3 3h8l2 2v8H3zM5.5 3v3h4V3M5.5 13V9.5h5V13" />);
export const GlobeIcon = glyph(<><circle cx="8" cy="8" r="5.5" /><path d="M2.5 8h11M8 2.5c2 2 2 9 0 11M8 2.5c-2 2-2 9 0 11" /></>);
export const MonitorIcon = glyph(<path d="M2 3.5h12v7H2zM6 13h4M8 10.5V13" />);
export const CloudIcon = glyph(<path d="M4.5 12a3 3 0 0 1-.3-6 4 4 0 0 1 7.6 1A2.5 2.5 0 0 1 11.5 12z" />);
export const UploadIcon = glyph(<path d="M8 11V3M4.5 6.5L8 3l3.5 3.5M3 13h10" />);
export const DownloadIcon = glyph(<path d="M8 3v8M4.5 7.5L8 11l3.5-3.5M3 13h10" />);
export const WarningIcon = glyph(<path d="M8 2.5L14.5 13.5h-13zM8 6.5v3.5M8 12v.01" />);
export const CheckIcon = glyph(<path d="M3 8.5l3.5 3.5L13 4.5" />);
export const GearIcon = glyph(<><circle cx="8" cy="8" r="2.5" /><path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M3.4 12.6l1.4-1.4M11.2 4.8l1.4-1.4" /></>);
export const RefreshIcon = glyph(<path d="M13 8a5 5 0 1 1-1.5-3.5M13 2.5v3h-3" />);
export const SquareIcon = glyph(<path d="M3 3h10v10H3z" />);
export const CheckSquareIcon = glyph(<path d="M3 3h10v10H3zM5.5 8.2l1.8 1.8 3.2-3.6" />);
export const StopIcon = glyph(<path d="M4 4h8v8H4z" />, true);
export const DotIcon = glyph(<circle cx="8" cy="8" r="4" />, true);
