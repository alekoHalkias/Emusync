# Handoff: #679 Audit and update dependencies

## Metadata
- Issue: #679
- Branch: feature/679-update-dependencies
- PR: none
- Status: shipped
- Created: 2026-11-01
- Fix attempts: 0

## 1. Issue
### Summary
Audit Python and npm dependencies, bump outdated, remove unused.
### Motivation
Drifted versions (Electron 31, Vite 5, electron-builder 24); unused packages bloat the runtime venv (#677).
### Proposed Behavior / Steps to Reproduce
Check real imports; remove unused; update the rest; refresh lockfiles.
### Affected Area
src/requirements*.txt, src/gui/package.json + lockfile, possibly electron modules and build config.
### Acceptance Criteria
- [ ] All remaining deps used
- [ ] Deps updated, held-back ones noted
- [ ] make test, make lint, make build-gui pass
- [ ] AppImage runtime setup works with trimmed requirements.txt

## 2. Design
### Scope: backend (dependency manifests and lockfiles); no schema/API/IPC/config change
### Backend Changes: remove adm-zip (zero imports in src/gui); bump smol-toml 1.6.1 -> 1.9.1 and other in-range deps; evaluate majors individually (electron 31 -> 45, electron-builder 24 -> 26, electron-vite 2 -> 6, vite 5 -> 8, @vitejs/plugin-react 4 -> 6, react 18 -> 19, typescript 5 -> 7). Python: pydantic, httpx used; verify pytest-asyncio is needed; raise stale lower bounds.
### UI Changes: none expected; Electron/React majors may force code fixes
### Plan Target: bplan
### Sub-issues: none (suggest holding Electron/React majors out if they prove invasive)
### Difficulty: 6/10
### Backwards Compatibility: not breaking; AppImage runtime stamp is keyed to requirements hash so venvs rebuild

## 12. Log
- 2026-11-01 issue: workflow initialized
- 2026-11-01 design: scope=backend, plan_target=bplan, difficulty=6/10, breaking=no
- 2026-11-01 bplan: 7 steps written, backend_pattern=manifest-only, majors deferred

## 4. Backend Plan (summary)
Design alignment: manifest-only change. Majors deferred to follow-ups.

## 8. Implementation Steps
1. Remove adm-zip: package.json/lock; reuses npm; no new code.
2. npm update in-range: package.json/lock; reuses semver; no new code.
3. Raise Python floors: requirements*.txt; no new code.
4. Verify lint/build/test: Makefile targets.
5-7. Tests none, docs none, file follow-up issues for majors.

## 6. Testing Plan (summary)
### Test File: none new; existing suite + test_bundle.py
### Outline
Backend: remove adm-zip; npm update in-range; raise Python floors; verify lint/build/test; file follow-ups for majors.
Tests: make test-changed / make test, make lint, make build-gui.
### Summary
Drop unused adm-zip and refresh in-range deps; major bumps deferred to follow-up issues.
- 2026-11-01 tplan: test_file=none new, 3 checks defined
- 2026-11-01 implement: steps 1-7 done except follow-up issues (deferred to ship; uvicorn[standard] kept)
