# Handoff: #624 Add per-game upload of a local ROM to the network drive

## Metadata
- Issue: #624
- Branch: feature/624-upload-local-rom-to-network
- PR: none
- Status: designed
- Created: 2026-10-29
- Fix attempts: 0
- Base: stacked on feature/622-move-local-rom (PR #623); touches MoveLocalRomPanel.tsx

## 1. Issue
See issue #624: per-game "Add to network drive" for local ROMs (reuse rom:uploadMaster), resulting in rom_source network with local copy.

## 2. Design
### Scope: ui (renderer only; reuse rom:uploadMaster, relPathUnder, setGameDevice)
### Plan Target: fplan

## 12. Log
- 2026-10-29 issue: workflow initialized
- 2026-10-29 design: scope=ui, plan_target=fplan, difficulty=3/10, breaking=no
