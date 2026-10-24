#!/usr/bin/env bash
# lib/github.sh — GitHub operations via gh CLI.
#
# Handles: issue create, PR create, PR merge, status check.

source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

create_issue() {
  local repo="$1"
  local title="$2"
  local body="$3"

  if ! command -v gh &>/dev/null; then
    log "gh CLI not available — cannot create issue"
    return 1
  fi

  log "Creating issue: $title"
  gh issue create \
    --repo "$repo" \
    --title "$title" \
    --body "$body" \
    2>/dev/null
}

create_pr() {
  local repo="$1"
  local branch="$2"
  local title="$3"
  local body="$4"
  local base="${5:-main}"

  if ! command -v gh &>/dev/null; then
    log "gh CLI not available — cannot create PR"
    return 1
  fi

  log "Creating PR: $title (branch: $branch → $base)"
  gh pr create \
    --repo "$repo" \
    --head "$branch" \
    --base "$base" \
    --title "$title" \
    --body "$body" \
    2>/dev/null
}

pr_merged() {
  local repo="$1"
  local pr_num="$2"

  if ! command -v gh &>/dev/null; then
    log "gh CLI not available — cannot check PR status"
    return 1
  fi

  local merged
  merged="$(gh pr view "$pr_num" --repo "$repo" --json state --jq '.state' 2>/dev/null)"
  [[ "$merged" == "MERGED" ]]
}

merge_pr() {
  local repo="$1"
  local pr_num="$2"

  if ! command -v gh &>/dev/null; then
    log "gh CLI not available — cannot merge PR"
    return 1
  fi

  log "Merging PR #$pr_num"
  gh pr merge "$pr_num" --repo "$repo" --squash --delete-branch 2>/dev/null
}

check_duplicates() {
  local repo="$1"
  local query="$2"

  if ! command -v gh &>/dev/null; then
    log "gh CLI not available — cannot check for duplicates"
    return 1
  fi

  gh issue list \
    --repo "$repo" \
    --search "$query" \
    --state all \
    --json number,title \
    --jq '.[] | "#\(.number) \(.title)"' \
    2>/dev/null
}
