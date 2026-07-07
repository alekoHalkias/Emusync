// Filter popover for GameGrid's search row (issue #345): checkbox filters
// for artwork presence, save presence, and ROM source. Checkboxes combine
// OR-within-group, AND-across-groups — an empty group applies no filter.
import React, { useEffect, useRef, useState } from "react";

export type ArtworkFilterValue = "with" | "without";
export type SavesFilterValue = "on" | "off";
export type RomSourceFilterValue = "network" | "local";

export type GameFilters = {
  artwork: Set<ArtworkFilterValue>;
  saves: Set<SavesFilterValue>;
  romSource: Set<RomSourceFilterValue>;
};

export const EMPTY_FILTERS: GameFilters = {
  artwork: new Set(),
  saves: new Set(),
  romSource: new Set(),
};

export function activeFilterCount(filters: GameFilters): number {
  return filters.artwork.size + filters.saves.size + filters.romSource.size;
}

type Props = {
  filters: GameFilters;
  onChange: (filters: GameFilters) => void;
};

function toggle<T>(set: Set<T>, value: T): Set<T> {
  const next = new Set(set);
  next.has(value) ? next.delete(value) : next.add(value);
  return next;
}

export default function GameFilterButton({ filters, onChange }: Props): React.ReactElement {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const count = activeFilterCount(filters);

  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent): void {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  return (
    <div ref={ref} style={{ position: "relative", flexShrink: 0 }}>
      <button className="btn btn-ghost" onClick={() => setOpen((v) => !v)} style={{ fontSize: 13 }}>
        ⏷ Filter{count > 0 ? ` (${count})` : ""}
      </button>
      {open && (
        <div
          style={{
            position: "absolute", top: "calc(100% + 6px)", right: 0, zIndex: 20,
            background: "var(--surface, var(--bg))", border: "1px solid var(--border)",
            borderRadius: "var(--radius)", padding: 12, width: 220,
            boxShadow: "0 8px 24px rgba(0,0,0,0.35)",
          }}
        >
          <FilterGroup
            label="Artwork"
            options={[["with", "With artwork"], ["without", "Without artwork"]]}
            selected={filters.artwork}
            onToggle={(v) => onChange({ ...filters, artwork: toggle(filters.artwork, v as ArtworkFilterValue) })}
          />
          <FilterGroup
            label="Saves"
            options={[["on", "Saves on device"], ["off", "Saves not on device"]]}
            selected={filters.saves}
            onToggle={(v) => onChange({ ...filters, saves: toggle(filters.saves, v as SavesFilterValue) })}
          />
          <FilterGroup
            label="ROM source"
            options={[["network", "Network ROM"], ["local", "Local ROM"]]}
            selected={filters.romSource}
            onToggle={(v) => onChange({ ...filters, romSource: toggle(filters.romSource, v as RomSourceFilterValue) })}
          />
          {count > 0 && (
            <button className="btn btn-ghost" style={{ fontSize: 12, width: "100%", marginTop: 4 }} onClick={() => onChange(EMPTY_FILTERS)}>
              Clear filters
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function FilterGroup({ label, options, selected, onToggle }: {
  label: string;
  options: [string, string][];
  selected: Set<string>;
  onToggle: (value: string) => void;
}): React.ReactElement {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ fontSize: 11, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: 6 }}>
        {label}
      </div>
      {options.map(([value, optLabel]) => (
        <label key={value} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, marginBottom: 4, cursor: "pointer" }}>
          <input type="checkbox" checked={selected.has(value)} onChange={() => onToggle(value)} />
          {optLabel}
        </label>
      ))}
    </div>
  );
}

/** OR-within-group, AND-across-groups; an empty group applies no filter. */
export function matchesFilters(
  filters: GameFilters,
  hasSave: boolean,
  isNetworkRom: boolean,
  hasArt: boolean | undefined,
): boolean {
  if (filters.artwork.size > 0 && hasArt !== undefined) {
    const matches = (filters.artwork.has("with") && hasArt) || (filters.artwork.has("without") && !hasArt);
    if (!matches) return false;
  }
  if (filters.saves.size > 0) {
    const matches = (filters.saves.has("on") && hasSave) || (filters.saves.has("off") && !hasSave);
    if (!matches) return false;
  }
  if (filters.romSource.size > 0) {
    const matches = (filters.romSource.has("network") && isNetworkRom) || (filters.romSource.has("local") && !isNetworkRom);
    if (!matches) return false;
  }
  return true;
}
