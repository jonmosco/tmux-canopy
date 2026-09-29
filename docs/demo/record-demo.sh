#!/usr/bin/env bash
# Record the canopy demo with asciinema + agg.
# Usage: bash docs/demo/record-demo.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DIR="$(mktemp -d /tmp/canopy-demo.XXXXXX)"
trap 'tmux -S "$SOCK" kill-server 2>/dev/null; rm -rf "$DIR"' EXIT

CAST="$ROOT/docs/assets/canopy-demo.cast"
GIF="$ROOT/docs/assets/canopy-demo.gif"
SOCK="$DIR/tmux.sock"
COLS=120 ROWS=34 SW=36

export HOME="$DIR/home"
mkdir -p "$HOME/bin" "$HOME/workspace/web" "$HOME/workspace/api" "$HOME/workspace/handbook"
export PATH="$HOME/bin:$ROOT/scripts:/usr/local/bin:/usr/bin:/bin"
export USER=demo LOGNAME=demo SHELL=/bin/bash
export TERM=xterm-256color LANG=C.UTF-8 LC_ALL=C.UTF-8
export XDG_CONFIG_HOME="$HOME/.config" XDG_DATA_HOME="$HOME/.local/share" XDG_CACHE_HOME="$HOME/.cache"

cp "$(command -v sleep)" "$HOME/bin/codex"

cat > "$HOME/workspace/web/app.py" << 'PYEOF'
"""A tiny example application."""

from dataclasses import dataclass


@dataclass
class Project:
    name: str
    ready: bool = True


def greeting(project: Project) -> str:
    return f"Welcome to {project.name}"


project = Project("Canopy demo")
print(greeting(project))
PYEOF

cat > "$HOME/editor.vim" << 'VIMEOF'
set number nowrap noswapfile nobackup nowritebackup
set notermguicolors laststatus=0 noruler noshowcmd noshowmode
set shortmess+=I
syntax on
hi Normal ctermfg=7 ctermbg=NONE
hi LineNr ctermfg=8
hi Comment ctermfg=8
hi String ctermfg=2
hi Statement ctermfg=4
hi Type ctermfg=3
hi PreProc ctermfg=4
hi Constant ctermfg=3
VIMEOF

for name in tests api handbook; do
  cat > "$HOME/bin/$name" << SCRIPTEOF
#!/usr/bin/env bash
printf '\033[2J\033[H'
SCRIPTEOF
done

cat >> "$HOME/bin/tests" << 'EOF'
printf '\n  $ pytest -q\n\n  ......................          [100%%]\n  \033[32m22 passed in 0.38s\033[0m\n\n  $ '
while IFS= read -r line; do :; done
EOF

cat >> "$HOME/bin/api" << 'EOF'
printf '\n  $ python3 server.py\n\n  Development server\n  ------------------\n\n  Ready at http://localhost:8000\n\n  \033[32mGET /health       200 OK\n  GET /projects     200 OK\033[0m\n\n  Waiting for requests...'
while IFS= read -r line; do :; done
EOF

cat >> "$HOME/bin/handbook" << 'EOF'
printf '\n  HANDBOOK\n  ========\n\n  01  Getting started\n  02  Local development\n  03  Running tests\n  04  Release checklist\n\n  Everything you need, one pane away.'
while IFS= read -r line; do :; done
EOF

chmod +x "$HOME/bin/tests" "$HOME/bin/api" "$HOME/bin/handbook"

cat > "$HOME/bin/new-window" << 'EOF'
#!/usr/bin/env bash
printf '\033[2J\033[H'
printf '  Codex\n  Working on the release notes...\n\n  Reviewing changes and tests.\n'
exec "$HOME/bin/agent-pane"
EOF
chmod +x "$HOME/bin/new-window"

cat > "$HOME/bin/agent-pane" << 'AGENTEOF'
#!/usr/bin/env bash
set -euo pipefail
pane="${TMUX_PANE:?}"
codex 3600 &
agent_pid=$!
birth="$(awk '{print $22}' "/proc/$agent_pid/stat")"
pane_pid="$(tmux display-message -p -t "$pane" '#{pane_pid}')"
sa() { tmux set-option -pq -t "$pane" "@tmux_canopy_agent_$1" "$2"; }
set_state() {
  local now; now="$(date +%s)"
  sa source codex-hook; sa session demo-codex-1; sa pane_pid "$pane_pid"
  sa status "$1"; sa updated "$now"; sa process_pid "$agent_pid"; sa process_birth "$birth"
  if [[ "$1" == needs-input ]]; then
    sa tool shell; sa summary 'Confirm the release command'
    sa command 'make release-notes'; sa request demo-request
  fi
}
set_state working
while [[ ! -e "$HOME/.canopy-needs-input" ]]; do sleep .15; done
set_state needs-input
sb="$(tmux list-panes -a -F '#{pane_id}|#{@tmux_canopy}' | awk -F'|' '$2==1{print $1;exit}')"
[[ -z "$sb" ]] || tmux send-keys -t "$sb" C-r
wait "$agent_pid"
AGENTEOF
chmod +x "$HOME/bin/agent-pane"

# Build the tmux fixture
tmux -S "$SOCK" -f /dev/null new-session -d -s studio -n Frontend -x "$COLS" -y "$ROWS" \
  -c "$HOME/workspace/web" "nvim --clean -n -u '$HOME/editor.vim' app.py"
export TMUX="$(tmux -S "$SOCK" display-message -p '#{socket_path},#{pid},0')"

tmux -S "$SOCK" set-option -g default-shell /bin/bash
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
tmux -S "$SOCK" set-option -g '@tmux-canopy-icon-codex' C
tmux -S "$SOCK" set-option -g '@tmux-canopy-agents' on
tmux -S "$SOCK" set-option -g '@tmux-canopy-animate' on
tmux -S "$SOCK" set-option -g '@tmux-canopy-notifications' none
tmux -S "$SOCK" set-option -g '@tmux-canopy-preview' off
tmux -S "$SOCK" set-option -g '@tmux-canopy-density' normal
tmux -S "$SOCK" set-option -g default-command "$HOME/bin/new-window"

editor="$(tmux -S "$SOCK" list-panes -t studio:Frontend -F '#{pane_id}')"
tmux -S "$SOCK" split-window -d -v -l 9 -t "$editor" -c "$HOME/workspace/web" tests
tmux -S "$SOCK" new-window -d -t studio: -n API -c "$HOME/workspace/api" api
tmux -S "$SOCK" new-session -d -s docs -n Handbook -x "$COLS" -y "$ROWS" \
  -c "$HOME/workspace/handbook" handbook

tmux -S "$SOCK" set-option -p -t "$editor" allow-set-title off
tmux -S "$SOCK" select-pane -t "$editor" -T editor
tmux -S "$SOCK" set-buffer -b test-command 'pytest -q'
tmux -S "$SOCK" set-buffer -b health-check 'curl http://localhost:8000/health'
tmux -S "$SOCK" set-buffer -b release-notes 'Ready for the next release.'
tmux -S "$SOCK" select-window -t studio:Frontend
tmux -S "$SOCK" select-pane -t "$editor"
"$ROOT/tmux-canopy.tmux"

touch "$DIR/action-state"

# Background driver sends keys at timed intervals
drive_demo() {
  local client sidebar
  sleep 2
  client="$(tmux -S "$SOCK" list-clients -F '#{client_tty}')"

  # Open Canopy
  "$ROOT/scripts/toggle" "$client" "$editor" "$SW" global T Tab slot
  sleep 2
  sidebar="$(tmux -S "$SOCK" list-panes -a -F '#{pane_id}|#{@tmux_canopy}' | awk -F'|' '$2==1{print $1;exit}')"
  sk() { tmux -S "$SOCK" send-keys -t "$sidebar" "$1"; sleep "${2:-0.35}"; }

  # Navigate tree
  for _ in $(seq 1 6); do sk Down 0.25; done
  sk Up 0.25; sk Up 0.25
  sleep 1.5

  # Collapse/expand
  sk H 1.5
  sk L 1.5

  # Search
  sk / 0.4
  sk p 0.12; sk y 0.12
  sleep 2
  sk Escape 0.3; sk Escape 1

  # Buffers
  sk 3 0.5
  sk Up 0.25; sk Up 0.25
  sk p 2
  sk p 0.4

  # Back to tree
  sk 1 1

  # Create agent window
  TMUX_CANOPY_STATE="$DIR/action-state" \
    TMUX_CANOPY_CLIENT="$client" \
    TMUX_CANOPY_WIDTH="$SW" \
    TMUX_CANOPY_SCOPE=global \
    TMUX_CANOPY_TRANSITION=slot \
    TMUX_PANE="$sidebar" \
    "$ROOT/scripts/tree-action" create-window \
    "S:$(tmux -S "$SOCK" display-message -p -t studio '#{session_id}')" 2>/dev/null || true
  sleep 2

  # Agents view - show working animation
  sk 4 4

  # Trigger needs-input
  touch "$HOME/.canopy-needs-input"
  sleep 2.5

  # Back to tree
  sk 1 2

  # Close sidebar
  sk C-q 1.5

  # End recording
  tmux -S "$SOCK" kill-server
}

drive_demo &

# Record the tmux session with asciinema
asciinema rec --window-size "${COLS}x${ROWS}" --overwrite \
  --command "tmux -S '$SOCK' attach-session -t studio" \
  "$CAST"

# Convert to GIF
"${AGG:-agg}" --font-family "Hack Nerd Font Mono" --font-size 16 \
  --theme dracula --speed 1 \
  "$CAST" "$GIF"

echo "Wrote: $CAST and $GIF ($(du -h "$GIF" | cut -f1))"
