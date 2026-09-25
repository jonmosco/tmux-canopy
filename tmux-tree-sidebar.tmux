#!/usr/bin/env bash
# Compatibility entrypoint for installations using the previous project name.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$BASH" "$SCRIPT_DIR/tmux-canopy.tmux" "$@"
