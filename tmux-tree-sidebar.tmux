#!/usr/bin/env bash
# Compatibility entrypoint for installations using the previous project name.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$(tmux show-option -gqv @tmux_canopy_loaded_path 2>/dev/null)" == "$SCRIPT_DIR" ]]; then
  exit 0
fi
exec "$BASH" "$SCRIPT_DIR/tmux-canopy.tmux" "$@"
