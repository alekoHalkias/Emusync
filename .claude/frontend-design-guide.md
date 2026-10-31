# EmuSync Frontend Design Guide

## Colors
- Danger: `var(--color-danger, #e5484d)` — used for error states, delete buttons
- Muted text: `var(--text-muted)` — secondary info, timestamps
- Accent per console: `CONSOLE_ACCENT` record in GameGrid.tsx (e.g. `#7c3aed` for SNES)
- Default accent: `#374151`

## Badges / Overlays
- Class: `game-card-badge` — 16x16 icon, border-radius pill, top-right corner overlay on card art
- Variants: `game-card-badge-net` (network), `game-card-badge-locked`, `game-card-badge-offline`, `game-card-badge-other`
- Layout: absolute positioned in `game-card-badges` div; stacked vertically
- Icon style: inline SVG or component from icons.tsx, white fill on colored background

## Buttons
- Primary action: `btn` class
- Ghost/secondary: `btn btn-ghost` class
- Danger: `btn btn-danger` class
- Header buttons: `btn btn-ghost game-grid-header-btn` — small, icon-only, in game-grid-header
- Disabled state: `disabled` attribute

## Modals
- Wrapper: `Modal.tsx` — accepts `children`, `busy`, `onClose` props
- Title: `<h3>` inside modal body
- Actions: `<div className="modal-actions">` with two buttons (cancel + confirm)
- Cancel: `btn btn-ghost`, Confirm: `btn btn-danger` or `btn`
- Spinner: `<span className="spinner" />` inside button text for busy state

## Inputs
- Search: `game-grid-search` class, placeholder "Search..."
- Select: `game-grid-art-type` class, styled `<select>`
- Text input: standard `<input>` with placeholder

## Layout
- GameGrid: header row (`game-grid-header`) + body (`game-grid-body`)
- Card grid: `game-grid-cards` div, CSS grid layout
- Section label: `game-grid-section-label` — small text divider between "On this device" and "On other devices"
- Empty state: `empty-state` div with padding and centered text

## Toast / Status
- Inline status line: `<div>` with `fontSize: 12`, `padding: "4px 16px"`, color by `isError`
- Clickable to dismiss
- Error color: `var(--color-danger, #e5484d)`, success: `var(--text-muted)`

## Icons
- Defined in `src/gui/renderer/src/components/icons.tsx`
- Pattern: functional components returning SVG with `currentColor` fill
- Standard size: 16x16 viewBox
- Usage: `<IconName />` inline in JSX

## Types
- GameRow: extends Game, adds `isLocal`, `lastPush`, `lastSave`, `locked`, `savePath`, `statePath`, `romSource`, `hasLocalCopy`, `offline`
- Defined in `src/gui/renderer/src/components/game-list/types.ts`

## Settings forms (modal editors, #629)
- Fields are `input-group` blocks: `<label>` above, text input with a `btn btn-ghost` Browse beside it for folders
- Conditional fields render only when their trigger value is set; helper text is muted 12px under the form
- Choice fields use a plain `<select>` including a blank "Not set" option and the stored value when it is not in the list
- List editors: one row per item (text + `btn btn-ghost` Remove), `Add` ghost button below, saved by the form's single Save

## Locations block and status chip (#644)
- Optional sources are rows in one block (label, path, `btn btn-ghost` Choose, clear), never a radio toggle; secondary lists collapse behind an "N items" disclosure.
- Status chip: small inline span after the path; neutral muted, match uses the accent, mismatch `var(--color-danger, #e5484d)`. Outcome text uses the inline status line, not a modal.

