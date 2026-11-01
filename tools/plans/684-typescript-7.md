# Plan: #684 Update TypeScript to 7

Issue: #684
Branch: feature/684-typescript-7
PR: none
Status: shipped
Fix attempts: 0

## Goal
Bump TypeScript to 7.0.2 without growing the type error set.

## Design Alignment
- **Backend Pattern**: manifest change plus one ambient declaration.
- **Recommendations**: none

## Steps
- [x] 1. Set typescript ^7.0.2 in src/gui/package.json and lockfile.
  - Files: src/gui/package.json, src/gui/package-lock.json
  - Reuses: npm
  - New: none
- [x] 2. Add src/gui/renderer/src/vite-env.d.ts (`/// <reference types="vite/client" />`) so the css side-effect import type-checks under TS 7.
  - Files: src/gui/renderer/src/vite-env.d.ts
  - Reuses: vite/client types
  - New: one-line file - TS 7 rejects an undeclared side-effect import
- [x] 3. Verify: tsc both configs show only the 6 pre-existing errors; make lint, build-gui, test pass.
- [x] 4. Tests: none new. Docs: none needed.

## Testing
- **Test File**: none new; existing suite
- **Test Cases**: tsc error set equals the 5.9.3 baseline
- **Edge Cases**: none
- **Integration Points**: make build-gui

## Checklist
Schema bump: no. New IPC channel: no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
Fixing the 6 pre-existing type errors.

## Log
