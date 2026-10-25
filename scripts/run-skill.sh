#!/usr/bin/env bash
# Run the next skill in the EmuSync workflow pipeline for issue <N>
# Usage: scripts/run-skill.sh <issue-number> [APPROVE=1] [MAX_RUNS=12]
set -euo pipefail

ISSUE="${1:?Usage: run-skill.sh <issue-number> [APPROVE=1] [MAX_RUNS=12]}"
APPROVE="${APPROVE:-${2:-}}"
MAX_RUNS="${MAX_RUNS:-${3:-12}}"
HANDOFF="plans/${ISSUE}-handoff.md"
CLAUDE_FLAGS="${CLAUDE_FLAGS:---permission-mode acceptEdits}"

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

prev_status=""
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
  prev_status="$status"
  status="$new_status"
done
