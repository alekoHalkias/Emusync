#!/usr/bin/env bash
# scripts/run-skill.sh - Standalone skill runner for EmuSync workflow

set -eu

ISSUE_NUM=${1:-}
MAX_RUNS=${MAX_RUNS:-12}
CLAUDE_FLAGS=${CLAUDE_FLAGS:-"--permission-mode acceptEdits"}

HANDOFF="plans/${ISSUE_NUM}-handoff.md"

# --- Auto-init: no handoff yet, create issue + branch + handoff ---
if [[ -z "$ISSUE_NUM" ]] || [[ ! -f "$HANDOFF" ]]; then
  echo "No existing handoff for #$ISSUE_NUM."
  echo ""

  if [[ -z "$ISSUE_NUM" ]]; then
    echo "This is a new issue. Describe what you want to build or fix:"
    echo "(One line summary, e.g. \"Add dark mode to the device list\")"
    read -r summary
  else
    echo "Issue #${ISSUE_NUM} has no handoff yet."
    echo "If the issue doesn't exist yet, enter a description to create it:"
    echo "(Press Enter to skip issue creation and use a placeholder number)"
    read -r summary
  fi

  # Create the issue if a summary was provided
  if [[ -n "$summary" ]]; then
    if [[ -z "$ISSUE_NUM" ]] || ! gh issue view "$ISSUE_NUM" >/dev/null 2>&1; then
      echo "Creating issue..."
      ISSUE_NUM=$(gh issue create \
        --title "EmuSync: $summary" \
        --label "workflow" \
        --body "Auto-created by run-skill.sh" \
        --json number | jq -r '.number')
      echo "Created issue #${ISSUE_NUM}"
    fi
  fi

  # Determine branch name
  BRANCH="feature/${ISSUE_NUM}-$(echo "$summary" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/^-//;s/-$//' | cut -c1-40)"
  BRANCH=${BRANCH:-"feature/${ISSUE_NUM}-auto"}

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
  cat > "$HANDOFF" <<EOF
# Handoff: #${ISSUE_NUM} $(echo "$summary" | sed 's/"/\\"/g')

## Metadata
- Issue: #${ISSUE_NUM}
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

  echo "Handoff written to $HANDOFF"
  echo "Branch $BRANCH is active. Running /issue to flesh out the details..."
  echo ""

  # Kick off /issue to populate the handoff properly
  if ! claude -p "/issue $ISSUE_NUM: $summary" $CLAUDE_FLAGS; then
    echo "Warning: /issue run failed. Handoff file was created but may need manual filling."
  fi
  echo ""
fi

get_status() {
  grep -m 1 "^- Status:" "$HANDOFF" | sed 's/^- Status: //' | xargs
}

map_skill() {
  local status=$1
  case "$status" in
    created)    echo "design" ;;
    designed)   echo "plan" ;;
    planned)    echo "implement" ;;  # Note: Implement requires approval or APPROVE=1
    implementing) echo "implement" ;;
    implemented)
      if grep -q "### Findings: TBD" "$HANDOFF"; then
        echo "review"
      else
        echo "ship"
      fi
      ;;
    shipped|blocked) echo "exit" ;;
    *)          echo "unknown" ;;
  esac
}

run_count=0
while [[ $run_count -lt $MAX_RUNS ]]; do
  STATUS=$(get_status)
  SKILL=$(map_skill "$STATUS")

  if [[ "$SKILL" == "exit" ]]; then
    echo "Workflow reached status: $STATUS. Exiting."
    exit 0
  fi

  if [[ "$SKILL" == "unknown" ]]; then
    echo "Error: Unknown status '$STATUS' in $HANDOFF."
    exit 1
  fi

  echo "--- Run $((run_count + 1))/$MAX_RUNS: Status='$STATUS', Next Skill='$SKILL' ---"

  if [[ "$STATUS" == "planned" ]]; then
     if [[ "${APPROVE:-0}" != "1" ]]; then
        echo "Status is 'planned'. Transitioning to 'implementing' requires user approval."
        echo "To automate, run with APPROVE=1: APPROVE=1 $0 $ISSUE_NUM"
        exit 0
     fi
  fi

  if ! claude -p "/$SKILL $ISSUE_NUM. Run only this skill; do not invoke the next one." $CLAUDE_FLAGS; then
    echo "Skill '$SKILL' failed or exited with error."
    exit 1
  fi

  NEW_STATUS=$(get_status)
  if [[ "$STATUS" == "$NEW_STATUS" ]]; then
    echo "No progress made (Status unchanged: $STATUS). Stopping to prevent infinite loop."
    exit 1
  fi

  ((run_count++))
done

echo "Reached MAX_RUNS ($MAX_RUNS). Stopping."
exit 1
