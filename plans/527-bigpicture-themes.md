# Plan: #527 Big Picture mode: user-installable themes (CSS + assets)

Issue: #527
Branch: feature/527-bigpicture-themes
PR: none
Status: shipped
Fix attempts: 0

## Goal
Users drop a folder (`theme.json`, `theme.css`, assets) in `<configDir>/themes/` and pick it in settings; Big Picture restyles live with no reload.

## Steps
- [x] 1. Main-process theme module: scan `<configDir>/themes/*/theme.json`, `theme:list` -> `[{id,name,author}]` (id = folder name, always plus bundled `default`), `theme:get(id)` -> `{css}` read from the file named by `theme.json` `css` (default `theme.css`; path must resolve inside the theme dir). Register `emusync-theme://<id>/<path>` protocol (privileged scheme before ready, `protocol.handle` after) serving files from the themes dir only, rejecting `..` escapes. Register IPC in main.ts.
  - Files: gui/electron/themes.ts (new), gui/electron/main.ts
  - Reuses: gui/electron/paths.ts:configDir, gui/electron/display.ts registerDisplayIpc pattern
  - New: themes.ts - no existing theme/protocol code; kept separate from display.ts (file size rule, ~300 lines)
- [x] 2. Persist selection: add `theme: string` (default `"default"`) to `Display` in display.json; `display:get` returns it, new `display:setTheme(id)` saves it. Not in emusync.toml (#499).
  - Files: gui/electron/display.ts
  - Reuses: display.ts load()/save()
- [x] 3. Preload + types: `theme.list/get`, `display.setTheme`, theme in `display.get` result type.
  - Files: gui/electron/preload.ts, gui/renderer/src/emusync.d.ts
- [x] 4. Move the `html[data-bigpicture]` colour/typography block (styles.css lines ~836-862) into `gui/renderer/src/themes/default.css`, imported by styles.css/App so it is the reference example (header comment documents the variables, selector scope, `emusync-theme://` asset URLs, `logos/<consoleKey>.svg`). It stays scoped `html[data-bigpicture]` (lower specificity than `[data-theme="<id>"]`) so partial user themes layer over it. Backdrop, wheel and gamepad focus rules stay in the base styles.css (#500: themes cannot break navigation).
  - Files: gui/renderer/src/styles.css, gui/renderer/src/themes/default.css (new)
  - New: default.css - issue asks the default to be a standalone reference file
- [x] 5. Renderer apply: in App.tsx, when `display.theme !== "default"`, `theme.get(id)` -> inject into `<style id="theme">`, set `documentElement.dataset.theme`; switching removes/replaces both. Applies only while Big Picture is on.
  - Files: gui/renderer/src/App.tsx
  - Reuses: existing data-bigpicture effect at App.tsx:45
- [x] 6. Theme picker in settings Display section (select fed by `theme.list`, calls `display.setTheme`, `onDisplay({theme})`); empty-list hint shows folder location via the existing data-folder row pattern.
  - Files: gui/renderer/src/components/ServerStatusButton.tsx
  - Reuses: ServerStatusButton display/onDisplay props
- [x] 7. Per-console logos: in `art:getConsoleLogo`, first check `<themes>/<selectedTheme>/logos/<consoleKey>.svg` (return data URL), else existing Carbon/ART_BOOK flow. ConsoleLogo refetches when theme changes (pass theme id as effect dep from App via ConsoleGrid prop).
  - Files: gui/electron/art.ts, gui/renderer/src/components/ConsoleGrid.tsx, gui/renderer/src/App.tsx
  - Reuses: art.ts getConsoleLogo toUrl pattern; themes.ts path-safe resolver from step 1
- [x] 8. Tests: no JS test harness exists (gui/package.json has none) and no Python/API/Store surface changes, so no automated tests; manual check: sample theme folder in themes dir, switch in settings, asset url loads, `..` traversal returns 404, bad theme.json skipped. `make test-changed` still run.
- [x] 9. Docs: docs/ARCHITECTURE.md (themes.ts module row, `theme` IPC group, `display.json` gains `theme`, themes dir under config); CLAUDE.md rule line (themes dir, GUI-only setting in display.json, focus styles in base layer). Pre-commit requires CLAUDE.md staged with main.ts/preload.ts.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): yes (theme:list, theme:get, display:setTheme). New CLI subcommand: no. Config/data file change: yes (display.json `theme`; new `<configDir>/themes/` dir).

## Not in this plan
- Layout changes (wheel orientation/scale, alternate views) - issue follow-up.
- Enforcing CSS scoping or sandboxing theme CSS; themes are trusted local files.
- Theme install UI / "open folder" button.
- Deviation from issue: themes live in `configDir()/themes/` not literal `~/.emusync/themes/` (CLAUDE.md: never hardcode paths, XDG via paths.ts).
- Default theme stays always-on as the base layer rather than a selectable overlay, so partial themes inherit it.

## Log
Step 9: docs were staged from HEAD blobs (CLAUDE.md, ARCHITECTURE.md) because the working copies hold unrelated uncommitted rewrites; the same additions were also applied to the working copies, which remain uncommitted.
Step 6: empty-list hint is generic text (no IPC to expose the config dir path; the plan said to show the folder location).
Step 1: CLAUDE.md rule line staged early (from HEAD blob, not the working copy which has unrelated uncommitted edits) to satisfy the pre-commit hook; step 9 still covers ARCHITECTURE.md.
