#!/usr/bin/env bash
# lib/workflow.sh — Status-to-skill mapping and loop logic.
#
# The workflow pipeline is:
#   created → issue → designed → plan → implementing → implement → reviewed → review → shipped → ship → done
#
# Additional terminal states: blocked, aborted.

source "$(dirname "$0")/config.sh"

# ── Status → skill mapping ─────────────────────────────────────────
status_to_skill() {
  local status="$1"
  case "$status" in
    created|issue_pending)    echo "issue" ;;
    issue_done|designed)      echo "design" ;;
    design_done|planning)     echo "plan" ;;
    plan_done|implementing)   echo "implement" ;;
    implement_done|reviewing) echo "review" ;;
    review_done|shipping)     echo "ship" ;;
    blocked|aborted|done)     echo "" ;;
    *)                        echo "" ;;
  esac
}

# ── Skill → next status mapping ────────────────────────────────────
skill_to_next_status() {
  local skill="$1"
  case "$skill" in
    issue)     echo "issue_done" ;;
    design)    echo "design_done" ;;
    plan)      echo "plan_done" ;;
    implement) echo "implement_done" ;;
    review)    echo "review_done" ;;
    ship)      echo "shipped" ;;
    *)         echo "" ;;
  esac
}

# ── Read current handoff status ────────────────────────────────────
handoff_status() {
  local handoff_file="$1"
  [[ -f "$handoff_file" ]] || die "Handoff file not found: $handoff_file"
  grep -m1 '^- Status:' "$handoff_file" | sed 's/^- Status: *//' | xargs
}

# ── Read handoff issue number ──────────────────────────────────────
handoff_issue() {
  local handoff_file="$1"
  grep -m1 '^- Issue:' "$handoff_file" | sed 's/^- Issue: *//' | xargs
}

# ── Read handoff branch ────────────────────────────────────────────
handoff_branch() {
  local handoff_file="$1"
  grep -m1 '^- Branch:' "$handoff_file" | sed 's/^- Branch: *//' | xargs
}

# ── Update handoff status ──────────────────────────────────────────
update_handoff_status() {
  local handoff_file="$1"
  local new_status="$2"
  local timestamp
  timestamp="$(date '+%Y-%m-%d')"

  if [[ "$(uname)" == "Darwin" ]]; then
    sed -i '' "s/^- Status: .*/- Status: $new_status/" "$handoff_file"
  else
    sed -i "s/^- Status: .*/- Status: $new_status/" "$handoff_file"
  fi

  echo "- ${timestamp} ${new_status}: skill completed" >> "$handoff_file"
}

# ── Main loop ──────────────────────────────────────────────────────
# Runs skills in sequence until terminal state or user interrupt.
run_pipeline() {
  local handoff_file="$1"
  local max_iterations="${MAX_ITERATIONS:-50}"
  local iteration=0

  while true; do
    iteration=$((iteration + 1))

    if (( iteration > max_iterations )); then
      log "Reached max iterations ($max_iterations). Stopping."
      return 1
    fi

    local status
    status="$(handoff_status "$handoff_file")"
    local skill
    skill="$(status_to_skill "$status")"

    if [[ -z "$skill" ]]; then
      log "Terminal or unknown status: $status. Pipeline complete."
      return 0
    fi

    log "Iteration $iteration: status=$status → skill=$skill"

    if ! "$run_skill_fn" "$skill" "$handoff_file"; then
      log "Skill '$skill' failed. Updating status to blocked."
      update_handoff_status "$handoff_file" "blocked"
      return 1
    fi

    local next_status
    next_status="$(skill_to_next_status "$skill")"
    if [[ -n "$next_status" ]]; then
      update_handoff_status "$handoff_file" "$next_status"
      log "Status updated: $status → $next_status"
    fi

    if [[ -n "$commit_fn" ]]; then
      "$commit_fn" "$handoff_file"
    fi
  done
}
