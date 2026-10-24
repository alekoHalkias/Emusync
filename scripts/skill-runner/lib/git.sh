#!/usr/bin/env bash
# lib/git.sh — Git operations for the skill runner.
#
# Handles: branch create/checkout, commit, push.

source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

# ── Create and checkout a feature branch ───────────────────────────
create_branch() {
  local issue_num="$1"
  local slug="${2:-step}"
  local branch="feature/${issue_num}-${slug}"

  if git rev-parse --verify "$branch" &>/dev/null; then
    log "Branch '$branch' already exists, using it"
    git checkout "$branch" 2>/dev/null
    return 0
  fi

  local current
  current="$(current_branch)"
  log "Creating branch '$branch' from '$current'"
  git checkout "$current" 2>/dev/null
  git checkout -b "$branch" 2>/dev/null || die "Failed to create branch '$branch'"
}

# ── Commit handoff/plan changes ────────────────────────────────────
commit_handoff() {
  local handoff_file="$1"
  local message="${2:-skill-runner: update handoff}"

  local repo
  repo="$(repo_root)"
  local rel_path="${handoff_file#$repo/}"

  git add "$rel_path" 2>/dev/null
  local plan_files
  plan_files="$(git ls-files "plans/*" | grep -v handoff || true)"
  if [[ -n "$plan_files" ]]; then
    git add $plan_files 2>/dev/null
  fi

  if ! git diff --cached --quiet 2>/dev/null; then
    git commit -m "$message" 2>/dev/null
    log "Committed: $message"
  else
    log "Nothing to commit"
  fi
}

# ── Push branch to remote ──────────────────────────────────────────
push_branch() {
  local branch="${1:-$(current_branch)}"
  local remote="${2:-origin}"

  log "Pushing branch '$branch' to '$remote'"
  git push -u "$remote" "$branch" 2>/dev/null || \
    die "Failed to push branch '$branch'"
}
