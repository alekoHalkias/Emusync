import React from "react";

/**
 * Human-friendly timestamp rendering (issue #216).
 *
 * Every timestamp EmuSync produces is UTC: the server uses
 * `datetime.now(timezone.utc).isoformat()` (carries a `+00:00` offset) and the
 * Electron file handlers use `Date.toISOString()` but slice off the trailing
 * `Z`. Per the ECMAScript spec a date-time string with NO timezone designator
 * parses as *local* time — which would be wrong for our UTC values — so
 * `parseUtc` appends `Z` whenever an offset/`Z` is absent.
 */
export function parseUtc(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const hasTz = /(Z|[+-]\d{2}:?\d{2})$/.test(iso);
  const d = new Date(hasTz ? iso : iso + "Z");
  return isNaN(d.getTime()) ? null : d;
}

const REL_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 31536000],
  ["month", 2592000],
  ["week", 604800],
  ["day", 86400],
  ["hour", 3600],
  ["minute", 60],
];

const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

/** Exact local time, 12-hour clock — e.g. "Jun 16, 2026, 9:25 PM". */
export function exactLocal(d: Date): string {
  return d.toLocaleString(undefined, {
    year: "numeric", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit", hour12: true,
  });
}

/**
 * Returns `{ text, title }` where `text` is a relative phrase ("2 hours ago",
 * "yesterday", "just now") and `title` is the exact local timestamp for a
 * tooltip. Both are empty strings when `iso` is missing/unparseable.
 */
export function formatRelative(iso: string | null | undefined): { text: string; title: string } {
  const d = parseUtc(iso);
  if (!d) return { text: "", title: "" };
  const secFromNow = (d.getTime() - Date.now()) / 1000;
  const title = exactLocal(d);
  if (Math.abs(secFromNow) < 45) return { text: "just now", title };
  for (const [unit, s] of REL_UNITS) {
    if (Math.abs(secFromNow) >= s) {
      return { text: rtf.format(Math.round(secFromNow / s), unit), title };
    }
  }
  return { text: "just now", title };
}

/**
 * Renders a relative time with the exact local time in a hover tooltip.
 * Shows `fallback` (plain text, no tooltip) when the timestamp is absent.
 */
export function RelTime(
  { iso, fallback = "—", className, style }:
  { iso: string | null | undefined; fallback?: string; className?: string; style?: React.CSSProperties },
): React.ReactElement {
  const { text, title } = formatRelative(iso);
  if (!text) return <span className={className} style={style}>{fallback}</span>;
  return <span className={className} style={style} title={title}>{text}</span>;
}
