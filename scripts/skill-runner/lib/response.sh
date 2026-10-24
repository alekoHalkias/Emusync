#!/usr/bin/env bash
# lib/response.sh — Parse LLM response and write to handoff/plan files.
#
# Expected response format:
#
#   ## Handoff Updates
#   <markdown content>
#
#   ## Plan Updates
#   <markdown content>
#
#   ## Code Changes
#   file: path/to/file.md
#   ```
#   <new content>
#   ```
#
#   ## Actions
#   - run: <command>
#   - read: <file path>

source "$(dirname "$0")/config.sh"

# ── Extract a section from response ────────────────────────────────
extract_section() {
  local response="$1"
  local section="$2"
  local in_section=false
  local output=""

  while IFS= read -r line; do
    if [[ "$line" =~ ^##[[:space:]]+$section[[:space:]]*$ ]]; then
      in_section=true
      continue
    fi
    if [[ "$line" =~ ^##[[:space:]] ]]; then
      if $in_section; then
        break
      fi
    fi
    if $in_section; then
      output+="$line"$'\n'
    fi
  done <<< "$response"

  echo "$output" | sed '/^$/d'
}

# ── Write handoff updates ──────────────────────────────────────────
write_handoff_updates() {
  local handoff_file="$1"
  local updates="$2"

  [[ -z "$updates" ]] && return 0

  {
    echo ""
    echo "$updates"
  } >> "$handoff_file"

  log "Wrote handoff updates to $(basename "$handoff_file")"
}

# ── Write plan file ────────────────────────────────────────────────
write_plan_updates() {
  local handoff_file="$1"
  local updates="$2"

  [[ -z "$updates" ]] && return 0

  local issue_num
  issue_num="$(handoff_issue "$handoff_file")"
  local repo
  repo="$(repo_root)"
  local plan_file="$repo/plans/${issue_num}-*.md"

  local target=""
  for f in $plan_file; do
    [[ "$(basename "$f")" != *"handoff"* ]] && target="$f" && break
  done

  if [[ -z "$target" ]]; then
    log "No plan file found for issue #$issue_num — skipping plan updates"
    return 0
  fi

  {
    echo ""
    echo "$updates"
  } >> "$target"

  log "Wrote plan updates to $(basename "$target")"
}

# ── Write code changes ─────────────────────────────────────────────
write_code_changes() {
  local changes="$1"

  [[ -z "$changes" ]] && return 0

  local current_file=""
  local in_code_block=false
  local code_content=""

  while IFS= read -r line; do
    if [[ "$line" =~ ^file:[[:space:]]*(.+)$ ]]; then
      current_file="${BASH_REMATCH[1]}"
      current_file="$(echo "$current_file" | xargs)"
      in_code_block=false
      code_content=""
      continue
    fi

    if [[ "$line" == '```'* ]]; then
      if $in_code_block; then
        if [[ -n "$current_file" && -n "$code_content" ]]; then
          local full_path
          full_path="$(repo_root)/$current_file"
          mkdir -p "$(dirname "$full_path")"
          printf '%s\n' "$code_content" > "$full_path"
          log "Wrote code change: $current_file"
        fi
        in_code_block=false
        code_content=""
      else
        in_code_block=true
      fi
      continue
    fi

    if $in_code_block; then
      code_content+="$line"$'\n'
    fi
  done <<< "$changes"
}

# ── Execute actions ────────────────────────────────────────────────
execute_actions() {
  local actions="$1"
  local read_files_file="$2"

  [[ -z "$actions" ]] && return 0

  while IFS= read -r line; do
    if [[ "$line" =~ ^-[[:space:]]run:[[:space:]]*(.+)$ ]]; then
      local cmd="${BASH_REMATCH[1]}"
      log "Running: $cmd"
      eval "$cmd" 2>&1 | tail -5 | while IFS= read -r l; do log "  $l"; done
    elif [[ "$line" =~ ^-[[:space:]]read:[[:space:]]*(.+)$ ]]; then
      local filepath="${BASH_REMATCH[1]}"
      filepath="$(echo "$filepath" | xargs)"
      log "Will read file next prompt: $filepath"
      if [[ -n "$read_files_file" ]]; then
        echo "$filepath" >> "$read_files_file"
      fi
    fi
  done <<< "$actions"
}

# ── Main parser ────────────────────────────────────────────────────
parse_response() {
  local response="$1"
  local handoff_file="$2"

  local handoff_updates plan_updates code_changes actions

  handoff_updates="$(extract_section "$response" "Handoff Updates")"
  plan_updates="$(extract_section "$response" "Plan Updates")"
  code_changes="$(extract_section "$response" "Code Changes")"
  actions="$(extract_section "$response" "Actions")"

  write_handoff_updates "$handoff_file" "$handoff_updates"
  write_plan_updates "$handoff_file" "$plan_updates"
  write_code_changes "$code_changes"

  local tmp_read_files
  tmp_read_files="$(mktemp)"
  execute_actions "$actions" "$tmp_read_files"
  rm -f "$tmp_read_files"
}
