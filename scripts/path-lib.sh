#!/usr/bin/env bash
# Shared by the previews: a directory as people write it, with the home
# directory as ~, to leave room for the rest of the path.

# Sets the variable named by $1 to its value with $HOME shortened to ~.
canopy_home_path() {
  local -n canopy_path_ref="$1"
  [[ -n "${HOME:-}" && "$HOME" != / ]] || return 0
  # shellcheck disable=SC2088 # A literal tilde for display, not a path to expand.
  if [[ "$canopy_path_ref" == "$HOME" ]]; then canopy_path_ref='~'
  elif [[ "$canopy_path_ref" == "$HOME/"* ]]; then canopy_path_ref='~/'"${canopy_path_ref#"$HOME/"}"
  fi
}
