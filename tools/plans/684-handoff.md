# Handoff: #684 Update TypeScript to 7

## Metadata
- Issue: #684
- Branch: feature/684-typescript-7
- PR: none
- Status: shipped
- Created: 2026-11-01
- Fix attempts: 0

## 1. Issue
TypeScript 5.9 to 7.0.2. Affected: src/gui/package.json, lockfile, renderer type declarations.

## 2. Design
### Scope: tooling only (manifest + one declaration file)
### Plan Target: bplan
### Difficulty: 2/10
### Backwards Compatibility: not breaking
Probe: tsc 7.0.2 reports the same 6 pre-existing type errors as 5.9.3 (files.ts x2, steam.ts, GameConfig, GameGrid, SyncConflictModal; not part of this issue) plus one new: renderer/src/index.tsx side-effect import './styles.css' has no declaration. electron-vite build passes.

## 6. Testing Plan
No new tests. make lint, make build-gui, make test; tsc error set must not grow beyond the 6 baseline errors.

## 8. Implementation Steps
1. package.json/lock: typescript ^7.0.2.
2. Add renderer/src/vite-env.d.ts with vite/client reference.
3. Verify.

## 12. Log
- 2026-11-01 issue/design/bplan/tplan: collapsed for a tooling-only change, plan_target=bplan, difficulty=2/10, breaking=no
- 2026-11-01 implement/review/ship: steps done; tsc 7.0.2 error set equals 5.9.3 baseline; pytest 594 passed; server sync skipped per directive
