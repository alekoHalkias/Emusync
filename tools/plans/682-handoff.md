# Handoff: #682 Update Vite and @vitejs/plugin-react to current majors

## Metadata
- Issue: #682
- Branch: feature/682-update-vite
- PR: none
- Status: shipped
- Created: 2026-11-01
- Fix attempts: 0

## 1. Issue
Bump Vite 5 -> 8 and @vitejs/plugin-react 4 -> 6 (split from #679).

## 2. Design
### Scope: backend/build manifests only (no code, schema, IPC, config change)
### Plan Target: bplan
### Difficulty: 3/10 after findings below
### Backwards Compatibility: not breaking
### Findings
- electron-vite 2.3.0 (installed) peers vite ^4 || ^5 only. Vite 6/7/8 needs electron-vite 4/5/6, which is #681 scope.
- @vitejs/plugin-react 6.x requires vite ^8; 5.2.0 supports vite ^5..^8 and node ^20.19 || >=22.12 (CI uses node 20, resolves to >=20.19).
- Result: Vite stays on 5.x (latest 5.4.x); plugin-react goes 4.7.0 -> 5.2.0. Vite 6+ and plugin-react 6 blocked on #681.

## 4. Backend Plan
Manifest-only.

## 8. Implementation Steps
1. package.json/lock: plugin-react ^5.2.0; npm install. Reuses npm.
2. Verify make lint, build-gui, test.
3. Comment on #682 about the blocker on #681.

## 12. Log
- 2026-11-01 issue/design/bplan/tplan: plugin-react only; Vite blocked on #681
- 2026-11-01 implement/review/ship: plugin-react 5.2.0, Vite held at 5.4.21; lint/build/test pass (594 passed); review 0 findings; server sync skipped by directive
