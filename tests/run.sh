#!/usr/bin/env bash
# One release gate, shared by developers and CI. Each suite owns its tmux socket.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export PYTHONDONTWRITEBYTECODE=1
for file in tmux-canopy.tmux scripts/* tests/*.sh; do bash -n "$file"; done
shellcheck tmux-canopy.tmux scripts/* tests/*.sh
bash tests/integration.sh
for suite in configuration hook_gating setup buffers navigation rendering stability git_context quiet quiet_layout labels details view_headers focus icons icon_alignment notifications attention jump_agent alerts subagents codex_subagents codex_daemon agent_no_pane agent_actions orphans agent_reporting agent_detection processes help preview codex_panel claude_lifecycle harnesses layout layout_scaling multiline directories filters quick_switch widths launch lifecycle create_refresh directory_refresh session_names theme animate footer mouse status_mouse wide_text popup; do
  python3 "tests/$suite.py"
done
python3 tests/widths.py --right
python3 tests/lifecycle.py --right
# Real-TPM install check. Needs a TPM checkout, so it is skipped (loudly) where
# none exists; point TMUX_CANOPY_TPM at one to force it.
tpm_dir="${TMUX_CANOPY_TPM:-$HOME/.tmux/plugins/tpm}"
if [[ -f "$tpm_dir/tpm" ]]; then
  python3 tests/tpm_install.py "$tpm_dir"
else
  echo "skip - tpm_install: no TPM checkout at $tpm_dir (set TMUX_CANOPY_TPM)"
fi
