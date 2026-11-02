# Handoff: #731 Improve network game matching and prevent duplicate games

## Metadata
- Issue: #731
- Branch: feature/731-network-game-matching
- PR: none
- Status: implementing
- Created: 2026-11-02
- Fix attempts: 0

## 1. Issue
### Summary
Network-drive games should link on every device that can see them, and the same ROM should never become two separate games.

### Motivation
Auto-link (#729) requires an exact `network_share_id` match plus a valid `rom_rel_path`; missing/unwritable markers or differing rel paths mean no link. Same ROM imported on two devices can yield two slugs, splitting saves/history.

### Proposed Behavior / Steps to Reproduce
User answers (2026-11-02):
- Symptoms: games not auto-linking; duplicate games.
- Fallback when share ID/rel path fails: filename + size within this device's console network folder.
- Confirmation: exact matches auto-link silently; fuzzy (filename+size) matches shown for confirmation.
- Duplicates: prevent at import/link (reuse game on filename+size match, same console) AND offer confirmed merge of existing duplicates (newest save wins, history from both kept).
- Surfaces: GameGrid auto-link on load, Refresh locations (#616/#650), console import wizard (#644), CLI `run` ROM resolution.
- No concrete repro case; general improvement.

### Affected Area
- `src/server/store/games.py` (`network_link_candidates`), `src/server/api/games.py`
- `src/gui/electron/sync/netplay.ts` (`rom:autoLinkNetworkGames`)
- `src/gui/renderer/src/components/game-list/useBrokenRoms.ts`, `console-import/scanNewRoms.ts`, `useNetworkShare.ts`, `useConsoleImport.ts`
- `src/cli/run.py`, `src/cli/netrom.py`
- Store: game merge across all `game_slug`-referencing tables

### Acceptance Criteria
- [ ] Exact share-ID + rel-path matches still auto-link silently.
- [ ] Fallback filename + size match in this device's console network folder, shown for confirmation.
- [ ] Never link by first ROM in a mount; same filename with different size is not a match.
- [ ] Import/link reuses an existing game on filename + size match (same console).
- [ ] (moved to #732) Existing duplicates detected and mergeable after confirmation; newest save wins, history preserved.
- [ ] All four surfaces use the same matching rules.
- [ ] Integration tests (real SQLite) for fallback candidates, duplicate prevention, merge.

## 2. Design
### Scope: backend + ui. Matching (exact + filename/size fallback) and duplicate prevention. Merging existing duplicates split to #732.
### Backend Changes:
- Schema v34 (`_migrate` `from_version < 34`, bump `_SCHEMA_VERSION`, add to `_SCHEMA`): `game_devices.rom_size INTEGER NOT NULL DEFAULT 0`. v34 verified free on all remote branches (main/727/729 at 33, 725 at 32).
- `rom_size` on models.GameDevice, api/games.py device request + response, sync_client GameDeviceConfig; set by CLI console import (`cli/console.py`) and `cli/netrom.py`.
- Store: lookup existing game by (console, ROM basename, rom_size > 0) for duplicate prevention; expose via API for import/scan.
- `network_link_candidates` (games.py:152): also return fuzzy rows where this device has the console's `device_network_folder` but share IDs differ/blank; include `rom_size`, `match` = exact|fuzzy.
- CLI `run`: missing stored ROM path -> unique filename + size hit in console network/local folders, used for this launch only, stderr note.
- Python matcher helper reused by CLI paths; never "first ROM in mount"; size mismatch = no match; size 0 = no fuzzy match.
### UI Changes:
- Electron main: TS filename + size matcher (same rules); `rom:autoLinkNetworkGames` (netplay.ts) links exact silently, returns fuzzy proposals (additive return field).
- GameGrid: confirm modal for fuzzy proposals (on load + Refresh locations).
- useBrokenRoms sibling relink: require size match when rom_size known.
- Console import (useConsoleImport/useNetworkShare) + scanNewRoms: reuse existing game on filename + size match instead of new slug.
- Device PUTs send `rom_size`; update emusync.d.ts.
### Plan Target: both
### Sub-issues: #732 Merge existing duplicate games
### Difficulty: 7/10
### Backwards Compatibility: non-breaking. Additive column + optional field; rom_size 0 rows never fuzzy-matched; IPC return extended only.

## 3. Frontend Plan
### Design Alignment: fuzzy proposals (network + relink) in one MatchConfirmModal following LocalToNetworkModal; on-load discovery via the bulkMsg status line with Review, Refresh opens the modal. Plan file: tools/plans/731-network-game-matching-ui.md (10 steps).
### Visual Pattern: existing Modal/modal-actions/checkbox list; guide gained a "match confirmation lists" rule.
### Recommendations: declined proposals session-only; scanNewRoms unchanged (wizard is the confirmation step); GameConfig manual add not deduped.

## 4. Backend Plan
### Design Alignment: additive schema v34 column + defaulted request fields; dedup in the single creation route POST /games; fuzzy candidates extend existing /games/network-link-candidates; CLI search reuses detect._scan_rom_dir.
### Backend Pattern: preserve-on-None extended to scalars (`rom_size: Optional[int] = None`); ROM identity = casefolded basename + rom_size, same console, size 0 / ambiguous never match. Guide updated.
### Recommendations: GUI must send rom_size on every device PUT and backfill on Refresh locations, else rows stay at 0 and never match. Plan file: tools/plans/731-network-game-matching.md (11 steps).

## 5. Merged Plan
### Conflicts Resolved:
- POST /games body: fplan {filename,size} -> rom_filename/rom_size (backend wins).
- network-link-candidates rows: fplan uses bplan filename/rom_size/match as-is.
- rom_size PUT preserve-on-None keeps untouched renderer callers safe.
- Docs from both plans folded into one step.
- Ordering: backend 1-9 before frontend 10-16.
- Single plan file tools/plans/731-network-game-matching.md; -ui file removed (require_plan.py reads first glob hit).
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: src/tests/test_network_matching.py (new); src/tests/test_network_autolink.py (extended, exact key-set assertion updated)
### Test Cases: 17 (see plan Testing section): v33 migration; rom_size round-trip + None-preserve; POST /games match / no-match x4 / casefold+backslash / rel-path; find_rom_by_name_size x5; _relocated_gd hit + none; candidates exact fields, fuzzy on mismatch, fuzzy on blank, size 0, no own folder, configured, exact wins.
### Edge Cases: old-client PUT keeps size; oldest slug wins among existing duplicates; folder ROMs (size 0) never match.
### Integration Points: SyncClient.add_game against live_server; GUI manual script (5 scenarios) since no JS runner.
### Outline:
Backend
- 1 Schema v34 `game_devices.rom_size`. [done]
- 2 Model/store round-trip incl. overview. [done]
- 3 Device PUT/GET + sync_client `rom_size` (None = keep). [done]
- 4 `store.find_game_by_rom` (casefolded basename + size, same console). [done]
- 5 POST /games returns existing game on ROM match (`matched`); CLI import sends filename/size. [done]
- 6 netrom upload records size. [done]
- 7 network-link-candidates adds `match`/`filename`/`rom_size` + fuzzy rows. [done]
- 8 Python `find_rom_by_name_size` over `_scan_rom_dir`. [done]
- 9 CLI run finds a moved ROM for this launch only (pure `_relocated_gd`).
Frontend
- 10 Types + `addGame` ROM arg.
- 11 IPC `files:size`.
- 12 IPC `rom:findByNameSize` over `scanRomDir`.
- 13 Auto-link: exact silent, fuzzy -> proposals; IPC `rom:confirmNetworkMatch`.
- 14 Refresh: size backfill, moved-ROM relink proposals, size-checked sibling relink.
- 15 MatchConfirmModal + status-line Review in GameGrid.
- 16 Import reuses matched game; "N linked to existing games".
Tests
- 17 test_network_matching.py (new) + test_network_autolink.py (extended); build/lint/tsc + manual GUI script.
- 18 Docs: CLAUDE.md, ARCHITECTURE.md, GOTCHAS.md.
### Summary: Records ROM size per device so games match across devices by filename + size: exact network links stay automatic, fuzzy ones are confirmed in a modal, imports stop creating duplicate games, and `emusync run` can launch a moved ROM.

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: merged, see tools/plans/731-network-game-matching.md (18 steps)
- 1 schema v34 rom_size: schema.py; reuses _try/_migrate. [done]
- 2 model/store round-trip: models.py, store/games.py; reuses inline column lists. [done]
- 3 device API + sync_client rom_size (None = preserve): api/games.py, sync_client.py; reuses set_game_device route. [done]
- 4 store.find_game_by_rom: store/games.py; new - no ROM-identity lookup exists. [done]
- 5 POST /games dedup + CLI import: api/games.py, sync_client.py, cli/console.py; reuses add_game route/client/import loop. [done]
- 6 netrom upload sets rom_size: cli/netrom.py; reuses gd update block. [done]
- 7 fuzzy candidates: store/games.py; reuses method/route; new second SELECT (GROUP BY would mix rows). [done]
- 8 find_rom_by_name_size: cli/netrom.py; reuses detect._scan_rom_dir. [done]
- 9 CLI run fallback, not persisted: cli/run.py; reuses _resolve_launch_command, get_device_consoles; new _relocated_gd.
- 10 renderer types + addGame rom arg: api.ts, types.ts, useGameList.ts; reuses _fetch.
- 11 files:size IPC: files.ts, preload.ts, d.ts; new - no size IPC.
- 12 findRomByNameSize + rom:findByNameSize: emulator/scan.ts, ipc.ts; reuses scanRomDir.
- 13 netplay exact/fuzzy + rom:confirmNetworkMatch: sync/netplay.ts; reuses linkNetworkGame; new confirm channel.
- 14 useBrokenRoms backfill/proposals/size-checked siblings: useBrokenRoms.ts; reuses refresh/sourceFor/updateRom.
- 15 MatchConfirmModal + GameGrid wiring: new component; reuses LocalToNetworkModal structure, bulkMsg.
- 16 import dedup: useConsoleImport.ts; reuses addGame/setGameDevice/gamesOverview.
- 17 tests + GUI verify.
- 18 docs.

## 9. Review
### Findings: TBD
### Blocked: TBD
### Blockers: TBD

## 10. Ship
### Status: pending
### PR: none
### Server Sync: pending
### Doc Sync: pending

## 11. Fix Attempts
### Attempt 1: none
### Attempt 2: none
### Attempt 3: none

## 12. Log
- 2026-11-02 issue: workflow initialized; clarified scope with user (filename+size fallback, confirm fuzzy, prevent+merge duplicates, all four surfaces)
- 2026-11-02 design: scope=backend+ui, plan_target=both, difficulty=7/10, breaking=no; split #732 (merge duplicates)
- 2026-11-02 bplan: 11 steps written, backend_pattern=additive v34 rom_size + dedup in POST /games + fuzzy candidates on existing route
- 2026-11-02 fplan: 10 steps written, visual_pattern=LocalToNetworkModal-style MatchConfirmModal + status-line Review
- 2026-11-02 merge: 6 conflicts resolved, 0 unresolved
- 2026-11-02 tplan: test_file=src/tests/test_network_matching.py (+ test_network_autolink.py), 17 test cases defined
- 2026-11-02 implement: step 1 done (schema v34 game_devices.rom_size)
- 2026-11-02 implement: step 2 done (rom_size in GameDevice and store queries)
- 2026-11-02 implement: step 3 done (rom_size on device PUT/GET and sync_client, None preserves)
- 2026-11-02 implement: step 4 done (store.find_game_by_rom + rom_basename)
- 2026-11-02 implement: step 5 done (POST /games reuses existing game on ROM match; CLI import sends filename/size)
- 2026-11-02 implement: step 6 done (upload_to_network records rom_size)
- 2026-11-02 implement: step 7 done (fuzzy network-link candidates with match/filename/rom_size)
- 2026-11-02 implement: step 8 done (find_rom_by_name_size over _scan_rom_dir)
