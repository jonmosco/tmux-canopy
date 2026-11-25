#!/usr/bin/env bash
# One release gate, shared by developers and CI. Each suite owns its tmux socket.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export PYTHONDONTWRITEBYTECODE=1
for file in tmux-canopy.tmux scripts/* tests/*.sh; do bash -n "$file"; done
shellcheck tmux-canopy.tmux scripts/* tests/*.sh
# Canopy writes plain dashes. An em dash (U+2014) arrives easily from an editor
# or pasted prose, and the count crept back up twice before this check existed.
# En dashes (U+2013) are left alone: they carry number ranges such as 6-7 and
# the placeholder in the README's capability matrix. Needs the index, so it is
# skipped (loudly) outside a checkout, as the TPM check below is.
# The pattern comes from its codepoint so this file does not trip its own check.
em_dash=$'\u2014'
if git rev-parse --git-dir >/dev/null 2>&1; then
  if em_dash_files="$(git ls-files -z | xargs -0 grep -lF -- "$em_dash" 2>/dev/null)" \
    && [[ -n "$em_dash_files" ]]; then
    printf 'em dash (U+2014) in tracked text; use a plain dash:\n%s\n' "$em_dash_files" >&2
    exit 1
  fi
  printf 'ok - no em dash in tracked text\n'
else
  echo "skip - em dash check: not a git checkout"
fi
bash tests/integration.sh
for suite in configuration hook_gating monitor_hook setup buffers navigation rendering stability git_context quiet quiet_layout labels details view_headers focus icons icon_alignment notifications attention jump_agent alerts subagents codex_subagents codex_daemon agent_no_pane agent_actions orphans agent_reporting agent_detection processes help preview codex_panel claude_lifecycle harnesses layout layout_scaling multiline directories filters prompt_targets quick_switch widths launch lifecycle create_refresh directory_refresh session_names theme animate footer mouse status_mouse old_bash wide_text popup; do
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
