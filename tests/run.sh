#!/usr/bin/env bash
# One release gate, shared by developers and CI. Each suite owns its tmux socket.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export PYTHONDONTWRITEBYTECODE=1
for file in tmux-canopy.tmux scripts/* tests/*.sh; do bash -n "$file"; done
shellcheck tmux-canopy.tmux scripts/* tests/*.sh
bash tests/integration.sh
for suite in configuration setup buffers navigation rendering focus icons icon_alignment notifications attention jump_agent subagents codex_subagents agent_reporting agent_detection processes help preview codex_panel harnesses layout layout_scaling multiline directories filters quick_switch widths launch lifecycle create_refresh animate footer mouse; do
  python3 "tests/$suite.py"
done
python3 tests/widths.py --right
python3 tests/lifecycle.py --right
