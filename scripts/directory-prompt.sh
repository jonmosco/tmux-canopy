#!/usr/bin/env bash
# Opt-in Bash prompt hook: notify Canopy when this pane's working directory
# changes. Source from ~/.bashrc (or equivalent) after enabling
# @tmux-canopy-directory-refresh. Does not replace PS1 or other hooks.
#
#   set -g @tmux-canopy-directory-refresh 'on'
#   source /path/to/tmux-canopy/scripts/directory-prompt.sh
#
# Unchanged-directory prompts use only builtins. A change schedules the
# plugin helper asynchronously with the pane id alone — never $PWD.

# Allow tests (or a relocated helper) to override before sourcing.
if [[ -z ${_CANOPY_DIRECTORY_REFRESH:-} ]]; then
  _CANOPY_DIRECTORY_REFRESH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/directory-refresh"
fi

# Seed so the first prompt after install does not fire without a real cd.
_canopy_directory_prev=${PWD:-}

_canopy_directory_prompt() {
  local status=$?
  # Outside tmux, or without a pane id, stay silent.
  [[ -n ${TMUX:-} && -n ${TMUX_PANE:-} ]] || return "$status"
  # Builtins only on the hot path.
  [[ ${PWD:-} == "$_canopy_directory_prev" ]] && return "$status"
  _canopy_directory_prev=$PWD
  # Pane id only; the helper reads pane_current_path from tmux.
  if [[ -x $_CANOPY_DIRECTORY_REFRESH ]]; then
    "$_CANOPY_DIRECTORY_REFRESH" "$TMUX_PANE" </dev/null >/dev/null 2>&1 &
  fi
  return "$status"
}

_canopy_directory_prompt_install() {
  local entry='_canopy_directory_prompt' declared
  declared=$(declare -p PROMPT_COMMAND 2>/dev/null) || declared=
  # Already installed (string or array): leave the user's ordering alone.
  if [[ $declared == 'declare -a'* ]]; then
    local item
    for item in "${PROMPT_COMMAND[@]}"; do
      [[ $item == "$entry" || $item == "$entry;"* || $item == *";$entry" || $item == *";$entry;"* ]] && return 0
    done
    # Prepend so $? is still the interactive command's status.
    PROMPT_COMMAND=("$entry" "${PROMPT_COMMAND[@]}")
    return 0
  fi
  # String form (Bash default when unset or assigned as a scalar).
  # shellcheck disable=SC2178 # PROMPT_COMMAND is either an array or a string; this branch is string-only.
  local current=${PROMPT_COMMAND-}
  case $current in
    '' )
      # shellcheck disable=SC2178
      PROMPT_COMMAND=$entry
      ;;
    *"$entry"* ) ;;
    * )
      # shellcheck disable=SC2178
      PROMPT_COMMAND="$entry; $current"
      ;;
  esac
}

_canopy_directory_prompt_install
unset -f _canopy_directory_prompt_install
