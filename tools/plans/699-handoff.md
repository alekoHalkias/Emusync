# Handoff: #699 Harden run signal handling, tar extraction and transfer timeouts

## Metadata
- Issue: #699
- Branch: feature/699-run-extract-safety
- PR: none
- Status: implementing
- Created: 2026-11-01
- Fix attempts: 0

## 1. Issue
Signals other than SIGTERM skip the post-game push; tar extraction lacks the data filter; whole-blob transfers time out at 30s.

## 2. Design
Backend only. Plan target: bplan. Difficulty 3/10. No schema or API change.

## 12. Log
- 2026-11-01 issue/design/plan/tplan: written in one pass
