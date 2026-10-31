# Plan: #640 Fix malformed auto-update feed URL

Issue: #640
Branch: feature/640-update-feed-owner
PR: none
Status: implementing
Fix attempts: 0

## Goal
Make the generated app-update.yml point at alekoHalkias/Emusync so the update check succeeds.

## Design Alignment
- **Backend Pattern**: none; build config only.
- **Recommendations**: none

## Steps
- [ ] 1. Split the publish target into owner and repo.
  - Files: src/gui/package.json
  - Reuses: existing `build.publish` block
  - New: none; add `"owner": "alekoHalkias"` and set `"repo": "Emusync"`.
- [ ] 2. Tests: none needed - config only. Verify by building an unpacked app (`npx electron-builder --dir --publish never` in src/gui) and checking `dist/linux-unpacked/resources/app-update.yml` shows owner alekoHalkias, repo Emusync.
- [ ] 3. Docs: none needed - CLAUDE.md already describes the updater; no rule changes.

## Testing
- **Test File**: none
- **Test Cases**:
  - app-update.yml in an unpacked build contains the correct owner and repo.
- **Edge Cases**:
  - v0.7.0 installs keep the bad config and need one manual upgrade to v0.7.1.
- **Integration Points**:
  - electron-updater reads app-update.yml at runtime.

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Cutting v0.7.1 (after merge).

## Log
