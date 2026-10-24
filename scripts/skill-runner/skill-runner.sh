#!/usr/bin/env bash
# skill-runner.sh — Main entry point for the standalone skill runner.
#
# Usage:
#   scripts/skill-runner/skill-runner.sh <issue-number> [options]
#
# Options:
#   --model <backend>     local | openai | claude-code (default: local)
#   --step <slug>         Branch slug (default: step)
#   --no-commit           Skip git commit after each skill
#   --no-push             Skip git push
#   --dry-run             Build prompt and exit (for testing)
#   --max-iterations <N>  Max loop iterations (default: 50)
#
# Sets up:
#   1. Config loading
#   2. Branch management
#   3. Pipeline loop (read handoff → build prompt → call LLM → parse → write → commit)

set -euo pipefail

# ── Resolve paths ──────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/config.sh"
source "$SCRIPT_DIR/lib/workflow.sh"
source "$SCRIPT_DIR/lib/context.sh"
source "$SCRIPT_DIR/lib/model.sh"
source "$SCRIPT_DIR/lib/response.sh"
source "$SCRIPT_DIR/lib/git.sh"
source "$SCRIPT_DIR/lib/github.sh"

# ── Parse arguments ────────────────────────────────────────────────
ISSUE_NUM=""
ISSUE_DESC=""
STEP_SLUG="step"
DRY_RUN=false
NO_COMMIT=false
NO_PUSH=false
MAX_ITERATIONS=50

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model)        EMUSYNC_MODEL="$2"; shift 2 ;;
    --step)         STEP_SLUG="$2"; shift 2 ;;
    --no-commit)    NO_COMMIT=true; shift ;;
    --no-push)      NO_PUSH=true; shift ;;
    --dry-run)      DRY_RUN=true; shift ;;
    --max-iterations) MAX_ITERATIONS="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: $0 <issue-number|description> [options]"
      echo "Options:"
      echo "  --model <backend>       local | openai | claude-code"
      echo "  --step <slug>           Branch slug (default: step)"
      echo "  --no-commit             Skip git commit"
      echo "  --no-push               Skip git push"
      echo "  --dry-run               Build prompt and exit"
      echo "  --max-iterations <N>    Max loop iterations (default: 50)"
      exit 0
      ;;
    *)
      if [[ -z "$ISSUE_NUM" ]]; then
        ISSUE_NUM="$1"
      else
        die "Unknown argument: $1"
      fi
      shift
      ;;
  esac
done

[[ -n "$ISSUE_NUM" ]] || die "Usage: $0 <issue-number|description>"

# ── Validate dependencies ──────────────────────────────────────────
validate_deps

# ── Locate (or create) handoff file ────────────────────────────────
REPO_ROOT="$(repo_root)"
HANDOFF_FILE="$REPO_ROOT/plans/${ISSUE_NUM}-handoff.md"

if [[ ! -f "$HANDOFF_FILE" ]]; then
  # No handoff exists — this is a fresh issue description.
  # Create the handoff with Status: created so the issue skill runs first.
  log "No handoff file — creating initial handoff for issue description"
  mkdir -p "$REPO_ROOT/plans"

  # Sanitize the issue description for use as a filename/branch slug
  ISSUE_SLUG="$(echo "$ISSUE_NUM" | tr ' :/' '---' | sed 's/--*/-/g; s/^-//; s/-$//')"
  HANDOFF_FILE="$REPO_ROOT/plans/${ISSUE_SLUG}-handoff.md"

  cat > "$HANDOFF_FILE" <<HEOF
# Handoff: $ISSUE_NUM

## Metadata
- Issue: $ISSUE_NUM
- Branch: feature/${ISSUE_SLUG}-step
- PR: none
- Status: created
- Created: $(date '+%Y-%m-%d')
- Fix attempts: 0

## 1. Issue
### Summary
TBD

### Motivation
TBD

### Steps to reproduce / expected behavior
TBD

### Affected area
TBD

### Acceptance criteria
- [ ] TBD

## 2. Design
### Scope: TBD
### Backend Changes: TBD
### UI Changes: TBD
### Sub-issues: TBD
### Difficulty: TBD/10
### Backwards Compatibility: TBD

## 3. Frontend Plan
### Design Alignment: TBD
### Visual Pattern: TBD
### Recommendations: TBD

## 4. Backend Plan
### Design Alignment: TBD
### Backend Pattern: TBD
### Recommendations: TBD

## 5. Merged Plan
### Conflicts Resolved: none
### Unresolved Conflicts: none

## 6. Testing Plan
### Test File: TBD
### Test Cases: TBD
### Edge Cases: TBD
### Integration Points: TBD

## 7. Test Design
### Test Scope: TBD
### Test Types: TBD
### Test Cases: TBD
### Affected Existing Tests: TBD
### Implementation Checklist: TBD

## 8. Implementation Steps
### Steps: TBD

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
- $(date '+%Y-%m-%d %H:%M') handoff created (fresh issue)
HEOF

  log "Created handoff: $HANDOFF_FILE"
fi

# ── Set up git branch ──────────────────────────────────────────────
BRANCH="feature/${ISSUE_SLUG:-$ISSUE_NUM}-${STEP_SLUG}"
git checkout "$BRANCH" 2>/dev/null || create_branch "${ISSUE_SLUG:-$ISSUE_NUM}" "$STEP_SLUG"

# ── Commit function for the pipeline ───────────────────────────────
do_commit() {
  if ! $NO_COMMIT; then
    commit_handoff "$HANDOFF_FILE" "skill-runner: update handoff"
    if ! $NO_PUSH; then
      push_branch
    fi
  fi
}

# ── Skill runner function ──────────────────────────────────────────
# Runs a single skill: build prompt, call LLM, parse response.
run_skill() {
  local skill_name="$1"
  local handoff_file="$2"
  local response_file
  response_file="$(mktemp)"

  log "Building prompt for skill: $skill_name"

  # Build the prompt and save to temp file
  local prompt_file
  prompt_file="$(mktemp)"
  build_prompt "$skill_name" "$handoff_file" > "$prompt_file"

  if $DRY_RUN; then
    log "DRY RUN — prompt saved to $prompt_file"
    log "Prompt size: $(wc -l < "$prompt_file") lines"
    # Copy first prompt to a known location for inspection
    if [[ ! -f /tmp/skill-runner-dry-run-prompt.md ]]; then
      cp "$prompt_file" /tmp/skill-runner-dry-run-prompt.md
      log "First prompt saved to /tmp/skill-runner-dry-run-prompt.md"
    fi
    rm -f "$response_file" "$prompt_file"
    return 0
  fi

  log "Calling LLM ($EMUSYNC_MODEL)..."
  local prompt_content
  prompt_content="$(cat "$prompt_file")"
  call_model "$prompt_content" "$response_file"

  local rc=$?
  if [[ $rc -ne 0 || ! -s "$response_file" ]]; then
    log "LLM call failed (exit code: $rc)"
    if [[ -s "$response_file" ]]; then
      log "Partial response:"
      head -20 "$response_file" >&2
    fi
    rm -f "$response_file" "$prompt_file"
    return 1
  fi

  log "LLM response received ($(wc -l < "$response_file") lines)"

  # Parse the response
  local response
  response="$(cat "$response_file")"
  parse_response "$response" "$handoff_file"

  rm -f "$response_file" "$prompt_file"
  return 0
}

# ── Wire up the pipeline ───────────────────────────────────────────
run_skill_fn="run_skill"
commit_fn="do_commit"

log "Starting pipeline for issue #$ISSUE_NUM"
log "Handoff: $HANDOFF_FILE"
log "Branch: $BRANCH"
log "Model: $EMUSYNC_MODEL ($EMUSYNC_MODEL_NAME)"
log "API: $EMUSYNC_API_URL"

run_pipeline "$HANDOFF_FILE"
