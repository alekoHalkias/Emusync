# Plan: #595 Design theme import and refactor theme engine

Issue: #595
Branch: feature/595-theme-import-refactor
PR: #596
Status: shipped
Fix attempts: 0

## Goal
Add a `.theme` ZIP import mechanism for Big Picture user themes and refactor the theme engine into a thin, self-contained module with a clear public API.

## Steps

- [x] 1. Add `ThemeImportModal` component to the renderer
  - Files: `gui/renderer/src/components/ThemeImportModal.tsx`
  - New: Theme import modal UI — file picker for `.theme` ZIP or theme folder, progress indicator, error display
  - IPC: `theme:import` handler in main process (see step 2)
  - Adds a "Themes" button in the topbar (next to Import button) that opens the modal when in Big Picture mode

- [x] 2. Add theme import logic to `gui/electron/themes.ts`
  - Files: `gui/electron/themes.ts`
  - Reuses: `themeFile()` for path validation (rejects `..` escapes)
  - New: `importThemeZip(zipPath: string): Promise<string>` — extracts ZIP, validates manifest (`name` required), generates a safe ID from the manifest name (slugify, deduplicate against existing IDs), writes to `<configDir>/themes/<id>/`, returns the ID
  - New: `importThemeFolder(folderPath: string): Promise<string>` — same validation, uses folder's basename as ID
  - New: `theme:import` IPC handler accepting a file path or folder path
  - ZIP extraction uses `adm-zip` (added as dependency; no built-in ZIP parser in Node)
  - Manifest schema: `{ name: string; author?: string; css?: string }` — `css` defaults to `"theme.css"`

- [x] 3. Refactor `gui/electron/themes.ts` to expose a clean public API
  - Files: `gui/electron/themes.ts`
  - Reuses: existing `listThemes()`, `getThemeCss()`, `themeFile()`, `registerThemeScheme()`
  - Refactor: extract the core logic into an exported object `ThemeEngine`:
    ```ts
    export const ThemeEngine = {
      list: () => ThemeInfo[],
      get: (id: string) => { css: string } | null,
      apply: (id: string) => void, // no-op; renderer handles injection
      clear: () => void,
      importZip: (zipPath: string) => Promise<string>,
      importFolder: (folderPath: string) => Promise<string>,
    };
    ```
  - IPC handlers delegate to `ThemeEngine` methods
  - `registerThemeIpc()` becomes `ThemeEngine.registerIpc()`
  - `registerThemeScheme()` stays standalone (protocol registration is Electron-specific)
  - `themeFile()` and `readManifest()` remain internal helpers

- [x] 4. Simplify renderer CSS injection in `App.tsx`
  - Files: `gui/renderer/src/App.tsx`
  - Reuses: `window.emusync.theme.get(id)` return value
  - No structural change to the CSS injection logic — the engine still returns `{ css: string }` which the renderer injects.

- [x] 5. Add `theme:import` type to `emusync.d.ts`
  - Files: `gui/renderer/src/emusync.d.ts`
  - Reuses: existing `theme` namespace
  - New: `import: (path: string) => Promise<string>` in `window.emusync.theme`

- [x] 6. Wire up the "Themes" button in the topbar
  - Files: `gui/renderer/src/App.tsx`
  - New: state for theme modal open/close
  - New: `<button className="btn btn-ghost" onClick={() => setThemeImportOpen(true)}>Themes</button>` in the topbar actions area (visible when `display.bigPicture`)

- [x] 7. Update `preload.ts` with the new `theme:import` channel
  - Files: `gui/electron/preload.ts`
  - Reuses: existing `theme` namespace in preload

- [x] 8. Tests for theme import and validation
  - No frontend test framework exists; theme import tested manually during QA
  - Manual test cases:
    - Valid ZIP with manifest → installed, returns ID
    - ZIP missing manifest → error shown in UI
    - ZIP with `..` in asset paths → rejected (path traversal protection)
    - Duplicate theme name → ID deduplicated (`my-theme`, `my-theme-1`, etc.)
    - Empty ZIP → error shown in UI
    - Folder import → installed, returns ID

- [x] 9. Docs: update ARCHITECTURE.md theme section
  - Files: `docs/ARCHITECTURE.md`, `CLAUDE.md`
  - Update: add `.theme` ZIP import format, `theme:import` IPC, `ThemeEngine` API

- [x] 10. Add bundled Solarized theme
  - Files: `gui/electron/themes/bundled/solarized/theme.json`, `gui/electron/themes/bundled/solarized/theme.css`
  - New: warm earthy Solarized Dark color palette overriding the default's cool blue tones
  - Bundled themes moved from `gui/renderer/src/themes/` to `gui/electron/themes/bundled/` and copied to `<configDir>/themes/` on startup so they appear in `listThemes()`

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): yes (`theme:import`). New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- Bundled themes (nebula, aurora) — handled by separate branches
- Theme editing/deletion UI
- Theme preview in the import modal
- Server-side theme management (themes are client-local)
- Moving theme engine out of Electron entirely

## Log
