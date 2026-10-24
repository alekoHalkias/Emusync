#!/usr/bin/env bash
# lib/context.sh — Build a minimal context snapshot for the LLM prompt.
#
# Assembles: issue body, handoff file, plan file (if exists),
# skill definition, and project docs (CLAUDE.md or equivalent).
#
# Output: a single markdown string written to stdout.

source "$(dirname "${BASH_SOURCE[0]}")/config.sh"

# ── Fetch issue body from GitHub ───────────────────────────────────
fetch_issue_body() {
  local repo="$1"
  local issue_num="$2"
  local body

  if command -v gh &>/dev/null; then
    body="$(gh issue view "$issue_num" --repo "$repo" --body 2>/dev/null)"
    if [[ -n "$body" ]]; then
      echo "$body"
      return 0
    fi
  fi

  # Fallback: try API
  body="$(curl -s "https://api.github.com/repos/$repo/issues/$issue_num" \
    -H "Authorization: token ${GITHUB_TOKEN:-}" 2>/dev/null \
    | grep '"body"' | head -1 | sed 's/.*"body": *"//; s/".*//')"

  if [[ -n "$body" ]]; then
    echo "$body"
    return 0
  fi

  echo "[Could not fetch issue body]"
  return 1
}

# ── Read plan file if it exists ────────────────────────────────────
read_plan_file() {
  local handoff_file="$1"
  local issue_num
  issue_num="$(handoff_issue "$handoff_file")"
  local repo
  repo="$(repo_root)"
  local issue_slug
  issue_slug="$(echo "$issue_num" | tr ' :/' '---' | sed 's/--*/-/g; s/^-//; s/-$//')"
  local plan_files
  plan_files="$(find "$repo/plans" -maxdepth 1 -name "${issue_slug}-*.md" ! -name "*handoff*" 2>/dev/null | head -1)"

  if [[ -n "$plan_files" && -f "$plan_files" ]]; then
    cat "$plan_files"
    return 0
  fi

  echo "[No plan file yet]"
  return 1
}

# ── Read skill definition ──────────────────────────────────────────
read_skill_file() {
  local skill_name="$1"
  local repo
  repo="$(repo_root)"
  local skill_file="$repo/.claude/skills/$skill_name/SKILL.md"

  if [[ -f "$skill_file" ]]; then
    cat "$skill_file"
    return 0
  fi

  # Fallback: use prompt template
  local script_dir
  script_dir="$(dirname "${BASH_SOURCE[0]}")"
  local prompt_file="$script_dir/../prompts/${skill_name}.prompt"
  if [[ -f "$prompt_file" ]]; then
    echo "Skill: $skill_name (using prompt template)"
    echo ""
    cat "$prompt_file"
    return 0
  fi

  echo "[No skill definition found for: $skill_name]"
  return 1
}

# ── Read project docs (CLAUDE.md or equivalent) ────────────────────
read_project_docs() {
  local project_docs="${PROJECT_DOCS:-CLAUDE.md}"
  local repo
  repo="$(repo_root)"
  local docs_file="$repo/$project_docs"

  if [[ -f "$docs_file" ]]; then
    local max_lines="${MAX_DOCS_LINES:-500}"
    head -n "$max_lines" "$docs_file"
    return 0
  fi

  echo "[No project docs found at $project_docs]"
  return 1
}

# ── Build the full prompt ──────────────────────────────────────────
# Usage: build_prompt <skill_name> <handoff_file>
# Output: markdown prompt string (written to stdout)
build_prompt() {
  local skill_name="$1"
  local handoff_file="$2"
  local repo
  repo="$(github_remote)"
  local issue_num
  issue_num="$(handoff_issue "$handoff_file")"
  local branch
  branch="$(handoff_branch "$handoff_file")"

  cat <<EOF
You are a workflow skill runner for this project. Follow the skill instructions below carefully.

## Skill: $skill_name
## Issue: #$issue_num
## Branch: $branch
## Repo: $repo

EOF

  echo "=== SKILL DEFINITION ==="
  # Substitute placeholders in skill definition
  local skill_def
  skill_def="$(read_skill_file "$skill_name")"
  skill_def="$(echo "$skill_def" | sed "s|<ISSUE_NUM>|$issue_num|g; s|<REPO>|$repo|g; s|<BRANCH>|$branch|g")"
  echo "$skill_def"
  echo ""
  echo ""

  echo "=== HANDOFF STATE ==="
  cat "$handoff_file"
  echo ""
  echo ""

  echo "=== PROJECT RULES ==="
  read_project_docs
  echo ""
  echo ""

  echo "=== GITHUB ISSUE ==="
  fetch_issue_body "$repo" "$issue_num"
  echo ""
  echo ""

  echo "=== PLAN FILE ==="
  read_plan_file "$handoff_file"
  echo ""
  echo ""

  cat <<'EOF'
=== YOUR TASK ===

Follow the skill definition above. Produce your output in this exact format:

## Handoff Updates
<markdown sections to write to the handoff file. Use the exact section headings
from the handoff file. If adding new content to an existing section, include the
full section content (not just the diff).>

## Plan Updates
<markdown sections to write to the plan file. Same format as above.>

## Code Changes
file: path/to/file.md
```
<new content>
```

## Actions
- run: <command to execute>
- read: <file path — I will include this in the next prompt>

Rules:
1. Be concise. Don't repeat the handoff or issue body.
2. Only include sections that need changes.
3. For code changes, use the format shown above.
4. If no changes are needed for a section, write "no changes".
EOF
}
