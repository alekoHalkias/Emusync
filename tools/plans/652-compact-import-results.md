# Plan: #652 Reduce vertical space in console import results step

Issue: #652
Branch: feature/652-compact-import-results
PR: none
Status: planned
Fix attempts: 0

## Goal
Make the console import results step shorter by merging stacked control rows into wrapping flex rows and tightening ROM rows.

## Design Alignment
- **Visual Pattern**: Keeps existing `btn btn-ghost` 12px controls and inline-style flex rows; only changes arrangement (wrapping `display:flex; flexWrap:wrap; gap`). No new CSS classes or tokens.
- **Recommendations**: none

## Steps
- [ ] 1. LocationsBlock: Local and Network folder rows share one wrapping flex line (each `flex: 1 1 280px`), with the "N folders scanned" toggle and the "N games linked from ..." note as additional items on that same wrapping container. Expanded folder list still renders below.
  - Files: src/gui/renderer/src/components/console-import/LocationsBlock.tsx
  - Reuses: existing `Row` and `btn` constant (change `Row` wrapper style: drop marginBottom/fixed 110px label width, add flex basis); existing `showFolders` state and chip.
  - New: none
- [ ] 2. ResultsStep: merge the search/filter row, title cleanup row and selection row into one wrapping row: search input (flex 1, min 140), status select, "Replace _ with space", Find, Replace with, Replace all, "N of M selected" (with "N ignored hidden" as muted suffix, full text in title), Ignore selected, Select all. Remove the standalone ignored-note div.
  - Files: src/gui/renderer/src/components/console-import/ResultsStep.tsx
  - Reuses: existing handlers (`doReplaceUnderscores`, `doFindReplace`, `vm.ignoreRoms`, `vm.toggleAll`) and existing button/input styles; only JSX containers merge.
  - New: none
- [ ] 3. ResultsStep: tighten ROM rows (row padding "10px 12px" to "6px 12px", inner column gap 4 to 2).
  - Files: src/gui/renderer/src/components/console-import/ResultsStep.tsx
  - Reuses: existing inline styles
  - New: none
- [ ] 4. ResultsStep: move "Push saves/states" checkboxes (or the network-ROMs note, shortened) into the `modal-actions` row between Back and Import; row wraps on narrow width.
  - Files: src/gui/renderer/src/components/console-import/ResultsStep.tsx
  - Reuses: `ci-check` labels, `modal-actions`
  - New: none
- [ ] 5. Verify: `cd src/gui && npx tsc --noEmit` (typecheck) and visually check the wizard at default and narrow widths.
- [ ] 6. Tests: none. Layout-only change in inline styles; repo has no renderer component tests (integration tests cover Python only).
- [ ] 7. Docs: none needed - no behavior, IPC, or config change.

## Testing
- **Test File**: none (no renderer component test infra; Python integration tests unaffected)
- **Test Cases**:
  - typecheck: `npx tsc --noEmit` in src/gui passes
  - manual: wizard at default and narrow width shows merged rows, all buttons still work
- **Edge Cases**:
  - network folder unset: no chip, row still aligned
  - network source: note shown in action row instead of checkboxes
  - zero ROMs: merged control row hidden as before
- **Integration Points**: `make test-changed` still passes (no backend change)

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Any change to scan, ignore, or import behavior; modal size changes.

## Log
