#!/usr/bin/env bash
# lib/config.sh — Load and validate configuration for the skill runner.
#
# Sources (in priority order):
#   1. Environment variables (EMUSYNC_*)
#   2. Per-project config: .claude/skill-runner.conf
#   3. Built-in defaults
#
# All values are exported so downstream scripts can use them.

# ── Built-in defaults ───────────────────────────────────────────────
DEFAULT_MODEL="${DEFAULT_MODEL:-local}"
DEFAULT_API_URL="${DEFAULT_API_URL:-http://localhost:8080/v1}"
DEFAULT_API_KEY="${DEFAULT_API_KEY:-}"
DEFAULT_MAX_TOKENS="${DEFAULT_MAX_TOKENS:-4096}"
DEFAULT_TEMPERATURE="${DEFAULT_TEMPERATURE:-0.3}"
DEFAULT_MODEL_NAME="${DEFAULT_MODEL_NAME:-local}"

# ── Environment variable overrides ──────────────────────────────────
_model="${EMUSYNC_DEFAULT_MODEL:-$DEFAULT_MODEL}"
_api_url="${EMUSYNC_API_URL:-$DEFAULT_API_URL}"
_api_key="${EMUSYNC_API_KEY:-$DEFAULT_API_KEY}"
_max_tokens="${EMUSYNC_MAX_TOKENS:-$DEFAULT_MAX_TOKENS}"
_temperature="${EMUSYNC_TEMPERATURE:-$DEFAULT_TEMPERATURE}"
_model_name="${EMUSYNC_MODEL_NAME:-$DEFAULT_MODEL_NAME}"

# ── Per-project config file ────────────────────────────────────────
_project_config=""
for _candidate in \
  "$(git rev-parse --show-toplevel 2>/dev/null)/.claude/skill-runner.conf" \
  "$(git rev-parse --show-toplevel 2>/dev/null)/scripts/skill-runner.conf"; do
  if [[ -f "$_candidate" ]]; then
    _project_config="$_candidate"
    break
  fi
done

if [[ -n "$_project_config" ]]; then
  while IFS='=' read -r _key _val; do
    [[ "$_key" =~ ^[[:space:]]*# ]] && continue
    [[ -z "$_key" ]] && continue
    _key="$(echo "$_key" | xargs)"
    [[ "$_key" =~ ^EMUSYNC_ ]] || continue
    _val="$(echo "$_val" | xargs)"
    case "$_key" in
      EMUSYNC_DEFAULT_MODEL)  [[ -z "${EMUSYNC_DEFAULT_MODEL:-}" ]] && _model="$_val" ;;
      EMUSYNC_API_URL)        [[ -z "${EMUSYNC_API_URL:-}" ]] && _api_url="$_val" ;;
      EMUSYNC_API_KEY)        [[ -z "${EMUSYNC_API_KEY:-}" ]] && _api_key="$_val" ;;
      EMUSYNC_MAX_TOKENS)     [[ -z "${EMUSYNC_MAX_TOKENS:-}" ]] && _max_tokens="$_val" ;;
      EMUSYNC_TEMPERATURE)    [[ -z "${EMUSYNC_TEMPERATURE:-}" ]] && _temperature="$_val" ;;
      EMUSYNC_MODEL_NAME)     [[ -z "${EMUSYNC_MODEL_NAME:-}" ]] && _model_name="$_val" ;;
    esac
  done < "$_project_config"
fi

# ── Export final values ────────────────────────────────────────────
export EMUSYNC_MODEL="$_model"
export EMUSYNC_API_URL="$_api_url"
export EMUSYNC_API_KEY="$_api_key"
export EMUSYNC_MAX_TOKENS="$_max_tokens"
export EMUSYNC_TEMPERATURE="$_temperature"
export EMUSYNC_MODEL_NAME="$_model_name"

# ── Helpers ─────────────────────────────────────────────────────────

log()  { echo "[$(date '+%H:%M:%S')] [skill-runner] $*" >&2; }
die()  { echo "[$(date '+%H:%M:%S')] [skill-runner] ERROR: $*" >&2; exit 1; }

require_cmd() {
  command -v "$1" &>/dev/null || die "Required command '$1' not found in PATH"
}

repo_root() {
  git rev-parse --show-toplevel 2>/dev/null || die "Not in a git repository"
}

current_branch() {
  git rev-parse --abbrev-ref HEAD 2>/dev/null || die "Cannot determine current branch"
}

github_remote() {
  local remote
  for r in origin upstream; do
    remote="$(git remote get-url "$r" 2>/dev/null)" && break
  done
  [[ -n "$remote" ]] || die "No git remote found"
  echo "$remote" | sed 's|git@github.com:||; s|\.git$||; s|https://github.com/||'
}


validate_deps() {
  require_cmd "git"
  require_cmd "curl"
  if ! command -v gh &>/dev/null; then
    log "Warning: 'gh' CLI not found — GitHub operations will be skipped"
  fi
}
