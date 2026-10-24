# EmuSync Skills - Current State

This file documents all workflow skills and their responsibilities.

## Skills

### 1. issue (`/.claude/skills/issue/SKILL.md`)
- **Stage**: 1 of 4
- **Purpose**: File a GitHub issue or resume an existing one
- **Output**: GitHub issue + `plans/<N>-handoff.md` (workflow state carrier)
- **Next**: invokes `design`

### 2. design (`./.claude/skills/design/SKILL.md`)
- **Stage**: 1.5 of 4
- **Purpose**: Analyze issue scope, split into UI/Backend parts, propose sub-issues, assign difficulty
- **Output**: Appends `## Design Analysis` block to GitHub issue + rewrites `plans/<N>-handoff.md` section 2
- **Next**: Invokes `fplan` and/or `bplan` based on analysis, then `tplan`

### 3. fplan (`./.claude/skills/fplan/SKILL.md`)
- **Stage**: 2.1 of 4
- **Purpose**: Frontend-focused implementation planning
- **Design Guide**: `.claude/frontend-design-guide.md` (auto-created, auto-updated, auto-compressed at 100 lines)
- **Focus**: React, Electron, IPC, CSS
- **Output**: `plans/<N>-<slug>.md` + rewrites `plans/<N>-handoff.md` sections 3, 8
- **Next**: Invoke `tplan` (or `bplan` if backend-only; `merge` if both ran)

### 4. bplan (`./.claude/skills/bplan/SKILL.md`)
- **Stage**: 2.2 of 4
- **Purpose**: Backend-focused implementation planning
- **Design Guide**: `.claude/backend-design-guide.md` (auto-created, auto-updated, auto-compressed at 100 lines)
- **Focus**: Python, FastAPI, SQLite/Store, Click, mDNS
- **Output**: `plans/<N>-<slug>.md` + rewrites `plans/<N>-handoff.md` sections 4, 8
- **Next**: Invoke `tplan` (or `merge` if fplan also ran)

### 5. merge (`./.claude/skills/merge/SKILL.md`)
- **Stage**: 2.15 of 4
- **Purpose**: Reconcile two plan files (fplan + bplan) into one unified plan
- **Output**: Merged plan file + rewrites `plans/<N>-handoff.md` sections 5, 8
- **Next**: Invoke `tplan`

### 6. tplan (`./.claude/skills/tplan/SKILL.md`)
- **Stage**: 2.3 of 4
- **Purpose**: Testing-focused implementation planning
- **Test Guide**: `.claude/testing-guide.md` (auto-created, auto-updated, auto-compressed at 100 lines)
- **Focus**: Integration tests, SQLite usage, CLI testing, Electron IPC testing
- **Input**: Reads plan from `fplan` or `bplan`
- **Output**: Updated `plans/<N>-<slug>.md` with `## Testing` section + rewrites `plans/<N>-handoff.md` section 6
- **Next**: Invoke `implement`

### 7. test-design (`./.claude/skills/test-design/SKILL.md`)
- **Stage**: 2.5 of 4
- **Purpose**: Generates detailed test design document for high-impact test coverage
- **Output**: `plans/<N>-test-design.md` + rewrites `plans/<N>-handoff.md` section 7
- **Next**: Invoke `implement`

### 8. implement (`./.claude/skills/implement/SKILL.md`)
- **Stage**: 3 of 4
- **Purpose**: Execute the plan file step by step
- **Output**: Code changes + commits + updates `plans/<N>-handoff.md` sections 8, 11
- **Next**: Invoke `ship`

### 9. review (`./.claude/skills/review/SKILL.md`)
- **Stage**: pre-ship
- **Purpose**: PR/diff review against CLAUDE.md rules and GOTCHAS.md
- **Output**: `ReportFindings` + rewrites `plans/<N>-handoff.md` section 9
- **Next**: `ship` (blocks if gotcha-violation or correctness findings)

### 10. ship (`./.claude/skills/ship/SKILL.md`)
- **Stage**: 4 of 4
- **Purpose**: Create PR, run tests, handle fix-plans if needed
- **Output**: GitHub PR + rewrites `plans/<N>-handoff.md` sections 10, 11
- **Next**: done

## Handoff File (`plans/<N>-handoff.md`)

A single workflow-wide state document that every skill reads, updates with its section, and passes forward. It replaces reliance on conversation memory and carries state through the entire pipeline.

**Structure:**
```
# Handoff: #<N> <title>

## Metadata          ← Issue: #N, Branch, PR, Status, Created, Fix attempts
## 1. Issue          ← Written by /issue: summary, motivation, acceptance criteria
## 2. Design         ← Written by /design: scope, backend/UI changes, difficulty, compat
## 3. Frontend Plan  ← Written by /fplan: design alignment, visual pattern, recommendations
## 4. Backend Plan   ← Written by /bplan: design alignment, backend pattern, recommendations
## 5. Merged Plan    ← Written by /merge: conflicts resolved, unresolved
## 6. Testing Plan   ← Written by /tplan: test file, cases, edge cases, integration points
## 7. Test Design    ← Written by /test-design: scope, types, cases, affected tests, checklist
## 8. Implementation Steps ← Written by /plan skills, updated by /implement: steps with files/reuses/new
## 9. Review         ← Written by /review: findings, blocked status, blockers
## 10. Ship          ← Written by /ship: status, PR, server sync, doc sync
## 11. Fix Attempts  ← Written by /ship fix-loop: attempt details, root cause
## 12. Log           ← Every skill appends a timestamped entry
```

**Rules:**
- Created by `/issue`, read by every subsequent skill
- Each skill rewrites only its own section(s)
- The plan file (`plans/<N>-<slug>.md`) remains the executable checklist; the handoff carries the full workflow context
- The edit hook checks `plans/<N>-*.md` — both plan and handoff files are in scope
- Status values flow: `created` → `designed` → `planned` → `implementing` → `implemented` → `shipped` or `blocked`

## Workflow Diagram

```
┌─────────────┐
│   /issue    │  Stage 1: File or resume issue, create handoff.md
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   /design   │  Stage 1.5: Analyze scope, split UI/Backend, assign difficulty
└──────┬──────┘
       │
       ├── Backend changes? ────► /bplan ──► .claude/backend-design-guide.md
       │                              (Stage 2.2)
       │
       └── UI changes? ─────────► /fplan ──► .claude/frontend-design-guide.md
                                      (Stage 2.1)

       Both guides:
       - Auto-created on first run
       - Auto-updated with new patterns
       - Auto-compressed at 100+ lines

       ▼
┌─────────────┐
│   /merge    │  Stage 2.15: Reconcile fplan+bplan into one plan (if both ran)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   /tplan    │  Stage 2.3: Add testing guidelines and steps
└──────┬──────┘
       │
       └──► .claude/testing-guide.md (auto-created, auto-updated, auto-compressed)

       ▼
┌─────────────┐
│ /test-design│  Stage 2.5: Generate detailed test design doc (optional)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  /implement │  Stage 3: Execute plan step by step
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  /review    │  Pre-ship gate: review diff, block on gotcha-violation/correctness
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   /ship     │  Stage 4: Create PR, run tests, fix-plans if needed, server sync
└─────────────┘
```

## Design Guides

### Frontend Design Guide (`.claude/frontend-design-guide.md`)
- **Tracks**: Colors, spacing, typography, component patterns (buttons, inputs, modals, lists)
- **Updated by**: `fplan` when new UI patterns are introduced
- **Compressed at**: 100+ lines

### Backend Design Guide (`.claude/backend-design-guide.md`)
- **Tracks**: API routes, store methods, CLI commands, sync logic, auth, config handling
- **Updated by**: `bplan` when new backend patterns are introduced
- **Compressed at**: 100+ lines

### Testing Guide (`.claude/testing-guide.md`)
- **Tracks**: Test patterns, fixtures, integration test structure, SQLite testing
- **Updated by**: `tplan` when new testing patterns are introduced
- **Compressed at**: 100+ lines

## Plan File Template

The executable plan file (separate from the handoff) has this structure:
```
# Plan: #<N> <issue title>

Issue: #<N>
Branch: feature/<N>-<slug>
PR: none
Status: planned
Fix attempts: 0

## Goal
One sentence.

## Design Alignment
- **Visual Pattern** / **Backend Pattern**: <how this change fits existing patterns>
- **Recommendations**: <if any, or "none">

## Steps
- [ ] 1. <what changes, observable result>
  - Files: path/a.ts, path/b.tsx
  - Reuses: path/a.ts:existing_fn
  - New: <thing> - <why nothing existing fits>

## Testing
- **Test File**: <path to test file>
- **Test Cases**:
  - <case 1>: <description>
  - <case 2>: <description>
- **Edge Cases**:
  - <edge case 1>: <description>

## Checklist
Schema bump: no. New IPC channel: yes/no. New CLI subcommand: no. Config/data file change: no.

## Not in this plan
## Log
```
