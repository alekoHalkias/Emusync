# Plan: #654 Remove Big Picture mode from the GUI

Issue: #654
Branch: feature/654-remove-big-picture
PR: none
Status: planned
Fix attempts: 0

## Goal
Delete Big Picture mode (wheel, themes, colour logos, display toggle) so the GUI is desktop-only, keeping fullscreen and gamepad navigation.

## Design Alignment
- **Visual Pattern**: no new UI. The desktop console grid branch in ConsoleGrid becomes the only path; the Settings popover loses the theme select, the topbar loses the Themes button.
- **Recommendations**: none. Design guide needs no change (pure removal).

## Steps
- [ ] 1. Electron main: drop theme engine and Big Picture display state. Old display.json keys are ignored because load() reads only known keys.
  - Files: src/gui/electron/main.ts, display.ts, art.ts, preload.ts, themes.ts (delete), themes/bundled/ (delete)
  - Reuses: display.ts load()/save()/applyDisplay (remove `bigPicture`/`theme` fields, `selectedTheme`, `display:setTheme`; `sync` saves and sends `{ fullscreen }` only); main.ts drops `registerThemeScheme`, `ThemeEngine.registerIpc`; art.ts drops `themeFile`/`selectedTheme` imports, `art:getConsoleLogo` handler, `CARBON_FOLDER`, `ART_BOOK_LOGO`, `CARBON_BASE`, `ART_BOOK_BASE` and helpers only they use; preload.ts drops `theme` namespace, `setTheme`, `getConsoleLogo`, `bigPicture` in types
  - New: none
- [ ] 2. Renderer types: drop the same members from emusync.d.ts.
  - Files: src/gui/renderer/src/emusync.d.ts
  - Reuses: existing declarations (delete lines only)
  - New: none
- [ ] 3. Renderer components: remove wheel, theme import and theme settings.
  - Files: components/ConsoleWheel.tsx (delete), components/ThemeImportModal.tsx (delete), ConsoleGrid.tsx, ServerStatusButton.tsx, App.tsx
  - Reuses: ConsoleGrid desktop branch (drop `bigPicture`/`theme` props, `ConsoleLogo`, `ConsoleWheel` import, now-unused helpers); ServerStatusButton (drop `themes` state/effect, theme select label, `theme` in DisplayState); App.tsx (display state becomes `{ scale, fullscreen, autoUpdateEnabled }`, drop data-bigpicture and theme effects, `bp-backdrop`, Themes button, ThemeImportModal state and render, `bigPicture`/`theme` props)
  - New: none
- [ ] 4. Gamepad nav and CSS: remove wheel handling and bp styles.
  - Files: src/gui/renderer/src/useGamepadNav.ts, styles.css
  - Reuses: useGamepadNav LB/RB handler becomes `if (inModal) cycleModalTab(+-1)`; delete `rotateWheel` and the `.console-wheel` branch in moveFocus; styles.css delete `.bp-backdrop`, `@keyframes bp-drift`, `.console-wheel*`, `.wheel-*`, reduced-motion wheel rules, and the Big Picture comment
  - New: none
- [ ] 5. Verify: `make build-gui`; grep for `bigpicture|bigPicture|ConsoleWheel|wheel|theme:|emusync-theme|getConsoleLogo` in src/gui returns nothing relevant (Steam's own "Big Picture" comment in steam.ts stays).
  - Files: none
  - Reuses: make build-gui
  - New: none
- [ ] 6. Tests: no new tests. The Python suite has no coverage of this GUI code (no Big Picture tests exist); run `make test-changed` to confirm nothing regressed. Regression for old display.json is covered by load() reading only known keys; verify manually by launching with a display.json containing `bigPicture` and `theme`.
  - Files: none
- [ ] 7. Docs: CLAUDE.md (remove Big Picture themes bullet, `getConsoleLogo`/`ART_BOOK_LOGO`/`CARBON_FOLDER` rule, Big Picture mentions in the display.json rule), src/docs/ARCHITECTURE.md (ConsoleWheel and ConsoleGrid rows, `getConsoleLogo`, "Big Picture themes" section, theme IPC list, display fields), src/docs/GOTCHAS.md (display.json entry, console image sources entry).
  - Files: CLAUDE.md, src/docs/ARCHITECTURE.md, src/docs/GOTCHAS.md
  - Reuses: existing sections (delete or trim)
  - New: none

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no (removals only, d.ts updated in step 2). New CLI subcommand: no. Config/data file change: no (display.json loses two keys; old files still load).

## Not in this plan
- Deleting user theme folders in the config dir.
- Removing fullscreen toggle, UI scale, or desktop gamepad navigation.
- Steam shortcut art (steam.ts mentions Steam's own Big Picture).

## Log
