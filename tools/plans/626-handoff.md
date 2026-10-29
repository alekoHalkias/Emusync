# Handoff: #626 Offer bulk move and network upload of local-only games on Refresh locations

## Metadata
- Issue: #626
- Branch: feature/626-bulk-local-to-network
- PR: none
- Status: shipped
- Created: 2026-10-29
- Fix attempts: 0
- Base: stacked on feature/624-upload-local-rom-to-network (PR #625)

## 1. Issue
See issue #626.

## 2. Design
### Scope: ui (renderer only)
### Plan Target: fplan

## 12. Log
- 2026-10-29 issue: workflow initialized
- 2026-10-29 design: scope=ui, plan_target=fplan, difficulty=4/10, breaking=no
- 2026-10-29 fplan/tplan: 6 steps, tests manual

## 8. Implementation Steps
1 localToNetwork.ts helper
2 useBrokenRoms candidates
3 LocalToNetworkModal
4 GameGrid wiring
5 tests none
6 docs
- 2026-10-29 implement: steps 1-6 done
