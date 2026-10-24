#!/usr/bin/env bash
# lib/model.sh — LLM API caller supporting multiple backends.
#
# Backends:
#   local       — OpenAI-compatible API (llama.cpp, llama-swap/Strata)
#   openai      — OpenAI API
#   claude-code — Claude Code CLI (interactive session)
#
# Usage: call_model "<prompt>" > <output_file>

source "$(dirname "$0")/config.sh"

# ── Local / OpenAI API caller ──────────────────────────────────────
call_openai_api() {
  local prompt="$1"
  local output_file="$2"

  # Build JSON payload using python3 for safe escaping
  local payload
  payload="$(python3 -c "
import json, sys
prompt = sys.stdin.read()
messages = [{'role': 'user', 'content': prompt}]
body = {
    'model': '${EMUSYNC_MODEL_NAME}',
    'messages': messages,
    'max_tokens': ${EMUSYNC_MAX_TOKENS},
    'temperature': ${EMUSYNC_TEMPERATURE}
}
print(json.dumps(body))
" <<< "$prompt")"

  local curl_headers=()
  curl_headers+=(-H "Content-Type: application/json")

  if [[ -n "$EMUSYNC_API_KEY" ]]; then
    curl_headers+=(-H "Authorization: Bearer $EMUSYNC_API_KEY")
  fi

  curl -s -X POST "$EMUSYNC_API_URL/chat/completions" \
    "${curl_headers[@]}" \
    -d "$payload" \
    | python3 -c "
import sys, json
d = json.load(sys.stdin)
if 'choices' in d and len(d['choices']) > 0:
    print(d['choices'][0]['message']['content'])
else:
    print(json.dumps(d), file=sys.stderr)
    sys.exit(1)
" > "$output_file"

  return $?
}

# ── Claude Code CLI caller ─────────────────────────────────────────
call_claude_code() {
  local prompt="$1"
  local output_file="$2"

  if command -v claude &>/dev/null; then
    log "Calling Claude Code CLI..."
    claude code -p "$prompt" --output-file "$output_file" 2>/dev/null
    local rc=$?
    if [[ $rc -eq 0 && -s "$output_file" ]]; then
      return 0
    fi
    log "Claude Code CLI failed, falling back to API"
  fi

  call_openai_api "$prompt" "$output_file"
}

# ── Main dispatcher ────────────────────────────────────────────────
# Usage: call_model "<prompt>" "<output_file>"
call_model() {
  local prompt="$1"
  local output_file="$2"

  case "$EMUSYNC_MODEL" in
    claude-code)
      call_claude_code "$prompt" "$output_file"
      ;;
    local|openai|*)
      log "Calling API: $EMUSYNC_API_URL (model: $EMUSYNC_MODEL_NAME)"
      call_openai_api "$prompt" "$output_file"
      ;;
  esac
}
