#!/usr/bin/env bash
# One release gate, shared by developers and CI. Each suite owns its tmux socket.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export PYTHONDONTWRITEBYTECODE=1
for file in tmux-canopy.tmux tmux-tree-sidebar.tmux scripts/* tests/*.sh; do bash -n "$file"; done
shellcheck tmux-canopy.tmux tmux-tree-sidebar.tmux scripts/* tests/*.sh
bash tests/integration.sh
for suite in configuration buffers navigation rendering focus icons notifications processes help preview layout layout_scaling multiline directories filters quick_switch widths launch lifecycle; do
  python3 "tests/$suite.py"
done
python3 tests/widths.py --right
python3 tests/lifecycle.py --right
