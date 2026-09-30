#!/usr/bin/env bash
# Simple canopy demo: start tmux, split, open canopy.
# Usage: bash docs/demo/record-simple.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIR="$(mktemp -d /tmp/canopy-demo.XXXXXX)"
trap 'tmux -S "$SOCK" kill-server 2>/dev/null; rm -rf "$DIR"' EXIT

CAST="$ROOT/docs/assets/canopy-demo.cast"
GIF="$ROOT/docs/assets/canopy-demo.gif"
SOCK="$DIR/tmux.sock"
COLS=120 ROWS=34

HOME_ORIG="$HOME"
export HOME="$DIR/home"
mkdir -p "$HOME/.config" "$HOME/projects/webapp" "$HOME/projects/api"
export PATH="/usr/local/bin:/usr/bin:/bin"
export USER=demo LOGNAME=demo SHELL=/bin/bash
export TERM=xterm-256color LANG=C.UTF-8 LC_ALL=C.UTF-8
export XDG_CONFIG_HOME="$HOME/.config" XDG_DATA_HOME="$HOME/.local/share" XDG_CACHE_HOME="$HOME/.cache"
export PS1='\[\033[32m\]demo\[\033[0m\]:\[\033[34m\]\w\[\033[0m\]\$ '
export HOSTNAME=demo

# Create some realistic content
cat > "$HOME/projects/webapp/app.py" << 'PYEOF'
"""Web application entry point."""

from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/health")
def health():
    return jsonify(status="ok")

if __name__ == "__main__":
    app.run(debug=True)
PYEOF

cat > "$HOME/projects/api/server.go" << 'GOEOF'
package main

import (
    "fmt"
    "net/http"
)

func main() {
    http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
        fmt.Fprintf(w, "Hello, World!")
    })
    http.ListenAndServe(":8080", nil)
}
GOEOF

# Start a minimal tmux server for setup; the demo builds from here
tmux -S "$SOCK" -f /dev/null new-session -d -s dev -n editor -x "$COLS" -y "$ROWS" \
  -c "$HOME/projects/webapp"
export TMUX="$(tmux -S "$SOCK" display-message -p '#{socket_path},#{pid},0')"

tmux -S "$SOCK" set-option -g default-shell /bin/bash
tmux -S "$SOCK" set-environment -g PS1 "$PS1"
tmux -S "$SOCK" set-environment -g HOSTNAME demo
tmux -S "$SOCK" set-option -g status on
tmux -S "$SOCK" set-option -g status-style 'bg=#282a36,fg=#f8f8f2'
tmux -S "$SOCK" set-option -g status-left '#[bg=#50fa7b,fg=#282a36,bold]  #S #[bg=#282a36] '
tmux -S "$SOCK" set-option -g status-left-length 20
tmux -S "$SOCK" set-option -g status-right '#[fg=#6272a4]tmux-canopy '
tmux -S "$SOCK" set-option -g window-status-format '#[fg=#6272a4] #I:#W '
tmux -S "$SOCK" set-option -g window-status-current-format '#[bg=#44475a,fg=#bd93f9,bold] #I:#W '
tmux -S "$SOCK" set-option -g window-status-separator ''
tmux -S "$SOCK" set-option -g pane-border-style 'fg=#44475a'
tmux -S "$SOCK" set-option -g pane-active-border-style 'fg=#bd93f9'
tmux -S "$SOCK" set-option -g automatic-rename off
tmux -S "$SOCK" set-option -g allow-rename off
tmux -S "$SOCK" set-option -g '@tmux-canopy-icon-theme' nerdfont
tmux -S "$SOCK" set-option -g '@tmux-canopy-agents' on
tmux -S "$SOCK" set-option -g '@tmux-canopy-animate' on
tmux -S "$SOCK" set-option -g '@tmux-canopy-notifications' none
tmux -S "$SOCK" set-option -g '@tmux-canopy-preview' off

editor="$(tmux -S "$SOCK" list-panes -t dev:editor -F '#{pane_id}')"

# Load canopy before the demo starts
"$ROOT/tmux-canopy.tmux"

# Drive the demo - user types commands to build up the session
drive() {
  local client sidebar
  sleep 1.5
  client="$(tmux -S "$SOCK" list-clients -F '#{client_tty}')"

  # Flash a styled message in the tmux status line
  flash() {
    tmux -S "$SOCK" display-message -c "$client" -d 2000 " $1"
    sleep 0.3
  }

  # Show some code
  flash "Show project code"
  tmux -S "$SOCK" send-keys -t "$editor" "cat app.py" Enter
  sleep 2.5

  # Split the pane
  flash "Split pane vertically"
  tmux -S "$SOCK" send-keys -t "$editor" "tmux split-window -v -l 10" Enter
  sleep 1.5

  # Create a second window
  flash "Create api window"
  tmux -S "$SOCK" send-keys "tmux new-window -n api -c ~/projects/api" Enter
  sleep 1.5

  # Create a third window
  flash "Create logs window"
  tmux -S "$SOCK" send-keys "tmux new-window -n logs" Enter
  sleep 1.5

  # Create a second session
  flash "Create infra session"
  tmux -S "$SOCK" send-keys "tmux new-session -d -s infra -n cluster" Enter
  sleep 1.5

  # Go back to editor window
  tmux -S "$SOCK" send-keys "tmux select-window -t dev:editor" Enter
  sleep 0.5
  tmux -S "$SOCK" send-keys "tmux select-pane -t top" Enter
  sleep 1

  # Open Canopy to see everything
  flash "Open Canopy  (prefix + T)"
  "$ROOT/scripts/toggle" "$client" "$editor" 36 global T Tab slot
  sleep 3

  sidebar="$(tmux -S "$SOCK" list-panes -a -F '#{pane_id}|#{@tmux_canopy}' | awk -F'|' '$2==1{print $1;exit}')"
  sk() { tmux -S "$SOCK" send-keys -t "$sidebar" "$1"; sleep "${2:-0.4}"; }

  # Navigate the tree
  flash "Navigate the tree"
  for _ in $(seq 1 5); do sk Down 0.3; done
  sleep 1.5

  # Collapse all
  flash "Collapse all  (H)"
  sk H 2

  # Expand all
  flash "Expand all  (L)"
  sk L 2

  # Search for api
  flash "Search  (/)"
  sk / 0.5
  sk a 0.15; sk p 0.15; sk i 0.15
  sleep 2
  sk Escape 0.3; sk Escape 1.5

  # Window navigation - sidebar follows
  flash "Next window  (prefix + n)"
  tmux -S "$SOCK" send-keys -t "$client" C-b n
  sleep 2

  flash "Next window  (prefix + n)"
  tmux -S "$SOCK" send-keys -t "$client" C-b n
  sleep 2

  flash "Previous window  (prefix + p)"
  tmux -S "$SOCK" send-keys -t "$client" C-b p
  sleep 2

  flash "Previous window  (prefix + p)"
  tmux -S "$SOCK" send-keys -t "$client" C-b p
  sleep 2

  # Close sidebar
  flash "Close sidebar  (Ctrl-q)"
  sk C-q 2

  tmux -S "$SOCK" kill-server
}

drive &

asciinema rec --window-size "${COLS}x${ROWS}" --overwrite \
  --command "tmux -S '$SOCK' attach-session -t dev" \
  "$CAST"

"${AGG:-agg}" --font-dir "$HOME_ORIG/.local/share/fonts/Hack" \
  --font-family "Hack Nerd Font Mono" --font-size 14 \
  --theme dracula --speed 1 --last-frame-duration 3 \
  "$CAST" "$GIF"

echo "Wrote: $GIF ($(du -h "$GIF" | cut -f1))"
