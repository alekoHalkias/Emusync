# Plan: #600 Standalone skill runner with isolated context per step

Issue: #600
Branch: feature/600-skill-runner-minimal
PR: none
Status: implementing
Fix attempts: 0

## Goal
One ~60 line script, scripts/run-skill.sh <N>, that reads the handoff Status and runs each next skill in a fresh `claude -p` process until shipped or blocked.

## Steps
- [ ] 1. Add scripts/run-skill.sh. Loop: read `- Status:` from plans/<N>-handoff.md, map to a skill, run `claude -p "/<skill> <N>. Run only this skill; do not invoke the next one." $CLAUDE_FLAGS`, re-read Status. Mapping: created->design, designed->plan, planned->(prompt y/N approval, or APPROVE=1) implement, implementing->implement, implemented->review if handoff "### Findings: TBD" else ship, shipped|blocked->print and exit. Stop if Status is unchanged after a run (no infinite loop) or after MAX_RUNS (default 12). CLAUDE_FLAGS defaults to `--permission-mode acceptEdits`.
  - Files: scripts/run-skill.sh
  - Reuses: handoff `Status:` values flow from .claude/skills/SKILLS_OVERVIEW.md; each skill already reads the handoff first and writes back to it, so the handoff is the per-skill snapshot and `claude -p` is the fresh context. No SKILL.md changes.
  - New: the script - nothing in the repo spawns skills in separate processes.
- [ ] 2. Tests: tests/test_run_skill.py, stdlib only. Put a fake `claude` script on PATH that rewrites Status in a temp handoff; assert the sequence created->designed->planned->(APPROVE=1)implementing->implemented->shipped invokes design, plan, implement, ship in order; assert a no-progress run stops with non-zero exit; assert `blocked` exits non-zero. No mocks of product code, no DB involved (script touches none).
- [ ] 3. Docs: CLAUDE.md Commands list gets one line `scripts/run-skill.sh <N>`; docs/ARCHITECTURE.md none needed (not product code).

## Checklist
Schema bump: no. New IPC channel (+ emusync.d.ts): no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
- Per-skill compressed context snapshots / prompt templates / config files / lib modules (the rolled-back attempt had 18 files, 1700+ lines). Handoff file + fresh process already bounds context; add snapshots only if a skill measurably overflows.
- fplan/bplan/merge/tplan as separate runner stages: `plan` covers them. Add stages if split planning is wanted.
- Deleting old branch feature/600-standalone-skill-runner (needs user approval) and untracked scripts/skill-runner/.

## Log
