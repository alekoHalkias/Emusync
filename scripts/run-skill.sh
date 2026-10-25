#!/usr/bin/env bash
# Run the next skill in the EmuSync workflow pipeline for issue <N>
# Usage: scripts/run-skill.sh [issue-number] [APPROVE=1] [MAX_RUNS=12]
# If no issue number given (or no handoff exists), prompts to create one.
set -euo pipefail

ISSUE="${1:-}"
APPROVE="${APPROVE:-${2:-}}"
MAX_RUNS="${MAX_RUNS:-${3:-12}}"
CLAUDE_FLAGS="${CLAUDE_FLAGS:---permission-mode acceptEdits}"

# --- Auto-init: no handoff yet, create issue + branch + handoff ---
if [[ -z "$ISSUE" ]] || [[ ! -f "plans/${ISSUE}-handoff.md" ]]; then
  echo "No existing handoff for #$ISSUE."
  echo ""

  if [[ -z "$ISSUE" ]]; then
    echo "This is a new issue. Describe what you want to build or fix:"
    echo "(One line summary, e.g. \"Add dark mode to the device list\")"
    read -r summary
  else
    echo "Issue #${ISSUE} has no handoff yet."
    echo "If the issue doesn't exist yet, enter a description to create it:"
    echo "(Press Enter to skip issue creation and use a placeholder number)"
    read -r summary
  fi

  # Create the issue if a summary was provided
  if [[ -n "$summary" ]]; then
    if [[ -z "$ISSUE" ]] || ! gh issue view "$ISSUE" >/dev/null 2>&1; then
      echo "Creating issue..."
      ISSUE_URL=$(gh issue create \
        --title "EmuSync: $summary" \
        --body "Auto-created by run-skill.sh")
      ISSUE_NUM=$(echo "$ISSUE_URL" | sed 's|.*/issues/||')
      echo "Created issue #${ISSUE_NUM}"
      ISSUE="${ISSUE_NUM}"
    fi
  fi

  # Determine branch name
  BRANCH="feature/${ISSUE}-$(echo "$summary" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//;s/-$//' | cut -c1-40)"
  BRANCH=${BRANCH:-"feature/${ISSUE}-auto"}

  # Create and checkout the branch
  if ! git rev-parse --verify "$BRANCH" >/dev/null 2>&1; then
    echo "Creating branch $BRANCH from main..."
    git checkout -b "$BRANCH" main
  else
    echo "Branch $BRANCH already exists, checking out..."
    git checkout "$BRANCH"
  fi

  # Ensure plans/ exists
  mkdir -p plans

  # Write the handoff file
  cat > "plans/${ISSUE}-handoff.md" <<EOF
# Handoff: #${ISSUE} $(echo "$summary" | sed 's/"/\\"/g')

## Metadata
  - Issue: #${ISSUE}
  - Branch: ${BRANCH}
  - PR: none
  - Status: created
  - Created: $(date +%Y-%m-%d)
  - Last updated: $(date +%Y-%m-%d)
  - Fix attempts: 0

## 1. Issue
### Summary
$(echo "$summary")

### Motivation
TBD

### Proposed Behavior / Steps to Reproduce
TBD

### Affected Area
TBD

### Acceptance Criteria
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
### Log:
- $(date +%Y-%m-%d) init: handoff created by run-skill.sh

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
- $(date +%Y-%m-%d) init: handoff created by run-skill.sh

## Rollback
- **Last known good state:** main
- **Blocked at:** none
- **State at failure:** none
EOF

  echo "Handoff written to plans/${ISSUE}-handoff.md"
  echo "Branch $BRANCH is active. Running /issue to flesh out the details..."
  echo ""

  # Kick off /issue to populate the handoff properly
  if ! claude -p "/issue $ISSUE: $summary" $CLAUDE_FLAGS; then
    echo "Warning: /issue run failed. Handoff file was created but may need manual filling."
  fi
  echo ""
fi

HANDOFF="plans/${ISSUE}-handoff.md"

if [[ ! -f "$HANDOFF" ]]; then
  echo "ERROR: handoff not found: $HANDOFF" >&2
  exit 1
fi

read_status() {
  grep -m1 '^  - Status:' "$HANDOFF" | sed 's/.*- Status: *//'
}

SKILL_FOR_STATUS() {
  case "$1" in
    created)       echo "design" ;;
    designed)      echo "fplan" ;;
    planned)       echo "implement" ;;
    implementing)  echo "review" ;;
    implemented)   echo "ship" ;;
    shipped|blocked) echo "" ;;
    *)             echo "" ;;
  esac
}

run_skill() {
  local skill="$1"
  echo ">>> Running skill: $skill for issue #$ISSUE"
  claude -p "/${skill} ${ISSUE}. Run only this skill; do not invoke the next one." $CLAUDE_FLAGS
}

runs=0

while true; do
  status=$(read_status)

  # Terminal states
  if [[ "$status" == "shipped" ]]; then
    echo "Workflow shipped for issue #$ISSUE."
    exit 0
  fi
  if [[ "$status" == "blocked" ]]; then
    echo "Workflow blocked for issue #$ISSUE." >&2
    exit 1
  fi

  skill=$(SKILL_FOR_STATUS "$status")
  if [[ -z "$skill" ]]; then
    echo "ERROR: unknown or unhandled status '$status'" >&2
    exit 1
  fi

  # Approve gate for fplan -> implement transition
  if [[ "$status" == "planned" ]]; then
    if [[ "$APPROVE" == "1" ]]; then
      echo "[APPROVE] Skipping approval prompt for issue #$ISSUE."
    else
      read -r -p "Approve plan? [y/N] " ans
      if [[ "$ans" != [yY] ]]; then
        echo "Aborted (manual approval required)." >&2
        exit 1
      fi
    fi
  fi

  runs=$((runs + 1))
  if (( runs > MAX_RUNS )); then
    echo "ERROR: reached MAX_RUNS=$MAX_RUNS without progress (last status: $status)" >&2
    exit 1
  fi

  echo "[$runs/$MAX_RUNS] Status=$status → skill=$skill"

  run_skill "$skill"

  new_status=$(read_status)
  if [[ "$new_status" == "$status" ]]; then
    echo "WARNING: status unchanged ($status) after running $skill — stopping to avoid infinite loop." >&2
    exit 1
  fi
  status="$new_status"
done
