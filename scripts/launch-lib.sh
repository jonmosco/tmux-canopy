#!/usr/bin/env bash
# Quoting for two distinct interpreters: POSIX shell argv and tmux command text.
shell_join() {
  local argument separator=''
  for argument in "$@"; do
    printf "%s'%s'" "$separator" "${argument//\'/\'\\\'\'}"
    separator=' '
  done
}

tmux_quote() {
  local value="$1"
  value="${value//\\/\\\\}"
  value="${value//\"/\\\"}"
  value="${value//\$/\\\$}"
  value="${value//$'\n'/\\n}"
  value="${value//$'\r'/\\r}"
  value="${value//$'\t'/\\t}"
  printf '"%s"' "$value"
}

# run-shell performs one tmux format expansion before executing its shell.
tmux_shell() {
  local command
  command="$(shell_join "$@")"
  printf '%s' "${command//#/##}"
}

# display-menu expands command formats once more, before run-shell does.
sidebar_menu_job() {
  local job
  job="run-shell -b $(tmux_quote "$1")"
  printf '%s' "${job//#/##}"
}

# Fixed, bounded operational messages only. Never retain stderr, environment,
# source rows, previews, buffer samples, command output, or terminal contents.
sidebar_display_menu() {
  local owner="$1" pane="$2"
  shift 2
  [[ -n "$owner" ]] || return 0
  tmux display-menu -c "$owner" -t "$pane" "$@"
}

sidebar_failure() {
  local owner="${1:-}" code="$2" message="$3" key='' stamp candidate _rest
  [[ -n "$owner" ]] || { printf 'tmux-canopy: %s\n' "$message" >&2; return 0; }
  message="${message:0:256}"
  read -r key _rest < <(printf '%s' "$owner" | cksum 2>/dev/null) || true
  stamp="$(date -u +%FT%TZ 2>/dev/null || printf 'time-unavailable')"
  if [[ "$key" =~ ^[0-9]+$ ]]; then
    tmux set-option -gq "@tmux_canopy_failure_$key" "$stamp [$code] $message" 2>/dev/null || true
  fi
  # Never let an absent/stale owner redirect the message to another client.
  # Avoid awk/grep here so missing dependencies can still be reported.
  while IFS= read -r candidate; do
    if [[ "$candidate" == "$owner" ]]; then
      tmux display-message -c "$owner" -d 7000 "tmux-canopy: $message" 2>/dev/null || true
      break
    fi
  done < <(tmux list-clients -F '#{client_tty}' 2>/dev/null)
}

sidebar_clean_fzf() {
  env -u FZF_DEFAULT_OPTS -u FZF_DEFAULT_OPTS_FILE -u FZF_DEFAULT_COMMAND "$@"
}

sidebar_preflight() {
  local owner="${1:-}" target="${2:-}" dependency helper commands rc scratch
  if ((BASH_VERSINFO[0] < 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 4))); then
    sidebar_failure "$owner" bash-version 'Bash 4.4 or newer is required (NUL-delimited record handling).'
    return 1
  fi
  for dependency in tmux bash awk mktemp fzf grep cksum date rm env sort; do
    if ! command -v "$dependency" >/dev/null 2>&1; then
      sidebar_failure "$owner" dependency "Required executable is missing: $dependency. See scripts/doctor."
      return 1
    fi
  done
  SIDEBAR_FZF_BINARY="$(command -v fzf)"
  for helper in sidebar sidebar-source tree-source sidebar-action tree-action sidebar-preview tree-preview \
    view-header doctor help quick-switch preview-popup pane-preview info process-source buffer-source navigate follow \
    refresh-sidebar cleanup reap-empty resize sync-width responsive-width mouse-resize notify content-layout; do
    if [[ ! -f "$SCRIPT_DIR/$helper" || ! -r "$SCRIPT_DIR/$helper" || ! -x "$SCRIPT_DIR/$helper" ]]; then
      sidebar_failure "$owner" install "Required helper is missing or not executable: $helper. Restore the plugin installation."
      return 1
    fi
  done
  for helper in buffer-lib.sh config-lib.sh lib.sh navigation.sh notification-lib.sh launch-lib.sh ui-options.sh ../lib/tree-render.awk ../lib/content-layout.awk; do
    if [[ ! -f "$SCRIPT_DIR/$helper" || ! -r "$SCRIPT_DIR/$helper" ]]; then
      sidebar_failure "$owner" install "Required library is missing or unreadable: $helper. Restore the plugin installation."
      return 1
    fi
  done
  commands="$(tmux list-commands 2>/dev/null)" || {
    sidebar_failure "$owner" server 'Cannot query the tmux server. See scripts/doctor.'; return 1;
  }
  if ! grep -q '^run-shell .*\[-[^]]*C' <<< "$commands" ||
     ! grep -q '^split-window .*\[-[^]]*f' <<< "$commands" ||
     ! grep -q '^split-window .*\[-e ' <<< "$commands" ||
     ! grep -q '^display-popup .*\[-e ' <<< "$commands" ||
     ! grep -q '^display-menu ' <<< "$commands" ||
     ! grep -q '^command-prompt .*\[-[^]]*l' <<< "$commands" ||
     [[ "$(tmux display-message -p -t "$target" '#{e|>=:211,65}' 2>/dev/null)" != 1 ]]; then
    sidebar_failure "$owner" tmux-capabilities 'tmux lacks required commands/formats (tested with 3.7c). See scripts/doctor.'
    return 1
  fi
  # Parse the actual UI options/bindings with a fixed, non-sensitive input.
  # Filter mode does not start a terminal UI, preview, or key-bound command.
  sidebar_ui_options "$target"
  printf 'H:\theader\theader\0V:probe\tprobe\tprobe\0' | sidebar_clean_fzf "$SIDEBAR_FZF_BINARY" "${SIDEBAR_FZF_ARGS[@]}" --filter=probe >/dev/null 2>&1
  rc=$?
  if ((rc != 0)); then
    sidebar_failure "$owner" fzf-capabilities "fzf rejected the required UI options or configuration (exit $rc; tested with 0.74.4). See scripts/doctor."
    return 1
  fi
  scratch="$(mktemp "${TMPDIR:-/tmp}/tmux-canopy-preflight.XXXXXX" 2>/dev/null)" || {
    sidebar_failure "$owner" temporary-state 'Cannot create private temporary state. Check TMPDIR permissions.'; return 1;
  }
  rm -f -- "$scratch"
}
