#!/usr/bin/env python3
"""Theme inheritance: parse styles, inherit ansi, keep fixed/mono escapes."""
import os
from pathlib import Path
import subprocess as sp
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def test_parser():
    script = r'''
set -euo pipefail
source scripts/theme-lib.sh
fail=0
check() {
  local name="$1" got="$2" want="$3"
  if [[ "$got" != "$want" ]]; then
    printf 'FAIL %s: got %q want %q\n' "$name" "$got" "$want"
    fail=1
  fi
}
canopy_style_attr 'fg=green,bg=black' fg; check named-fg "$CANOPY_REPLY" green
canopy_style_attr 'fg=#cba6f4,bg=#1e1e2e' fg; check hex-fg "$CANOPY_REPLY" '#cba6f4'
canopy_style_attr 'fg=colour183,bg=default' fg; check colourN "$CANOPY_REPLY" '183'
canopy_style_attr 'fg=colour183,bg=default' bg; check default-bg "$CANOPY_REPLY" ''
canopy_style_attr 'default' fg; check whole-default "$CANOPY_REPLY" ''
canopy_style_attr '' fg; check empty "$CANOPY_REPLY" ''
canopy_color_to_fzf green; check fzf-green "$CANOPY_REPLY" '2'
canopy_color_to_fzf '#cba6f4'; check fzf-hex "$CANOPY_REPLY" '#cba6f4'
canopy_color_to_fzf 183; check fzf-183 "$CANOPY_REPLY" '183'
canopy_color_to_ansi green; check ansi-green "$CANOPY_REPLY" $'\033[1;32m'
canopy_color_to_ansi '#cba6f4'; check ansi-hex "$CANOPY_REPLY" $'\033[38;2;203;166;244m'
canopy_color_to_ansi 183; check ansi-183 "$CANOPY_REPLY" $'\033[38;5;183m'
exit "$fail"
'''
    result = sp.run(['bash', '-c', script], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    print('ok - theme style parser')


def test_inherit_and_escapes():
    socket = f'canopy-theme-test-{os.getpid()}'
    env = os.environ.copy()
    env.pop('TMUX', None)
    env.pop('TMUX_PANE', None)
    for key in list(env):
        if key.startswith('CANOPY_COLOR_') or key in ('CANOPY_THEME', 'CANOPY_THEME_FROZEN',
                                                       'CANOPY_SELECTION_EXPLICIT'):
            env.pop(key, None)

    def tm(*args):
        result = sp.run(['tmux', '-L', socket, *args], env=env, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, (args, result.stderr)
        return result.stdout.strip()

    try:
        pane = tm('-f', '/dev/null', 'new-session', '-d', '-P', '-F', '#{pane_id}', 'sleep 180')
        env['TMUX'] = tm('display-message', '-p', '-t', pane, '#{socket_path},#{pid},0')
        env['TMUX_PANE'] = pane
        tm('set-option', '-g', 'status-style', 'fg=#88c0d0,bg=#3b4252')
        tm('set-option', '-g', 'pane-active-border-style', 'fg=#a3be8c')
        tm('set-option', '-g', 'pane-border-style', 'fg=#4c566a')
        tm('set-option', '-g', 'mode-style', 'fg=#81a1c1,bg=#3b4252')
        tm('set-option', '-g', 'message-style', 'fg=#d08770,bg=#3b4252')
        tm('set-option', '-g', '@tmux-canopy-theme', 'ansi')
        tm('set-option', '-gu', '@tmux-canopy-selection-background')

        load = sp.run(['bash', str(ROOT / 'tmux-canopy.tmux')], env=env, capture_output=True, text=True, timeout=30)
        assert load.returncode == 0, load.stderr

        def resolve(extra=None):
            script = r'''
set -euo pipefail
source scripts/theme-lib.sh
canopy_theme_resolve
printf '%s\n' "$CANOPY_THEME"
printf '%s\n' "$CANOPY_COLOR_ACCENT_FZF"
printf '%s\n' "$CANOPY_COLOR_ACTIVE_FZF"
printf '%s\n' "$CANOPY_COLOR_ATTENTION_FZF"
printf '%s\n' "$CANOPY_COLOR_SELECTION_BG"
printf '%s\n' "$CANOPY_COLOR_BORDER_FZF"
printf '%s\n' "$CANOPY_COLOR_ACCENT_ANSI"
printf '%s\n' "$CANOPY_COLOR_ACTIVE_ANSI"
printf '%s\n' "$CANOPY_COLOR_ATTENTION_ANSI"
printf '%s\n' "$CANOPY_COLOR_MUTED_FZF"
'''
            run_env = env.copy()
            if extra:
                run_env.update(extra)
            for key in list(run_env):
                if key.startswith('CANOPY_COLOR_') or key in ('CANOPY_THEME', 'CANOPY_THEME_FROZEN',
                                                             'CANOPY_SELECTION_EXPLICIT'):
                    run_env.pop(key, None)
            result = sp.run(['bash', '-c', script], cwd=ROOT, env=run_env,
                            capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, result.stderr
            return result.stdout.splitlines()

        lines = resolve()
        assert lines[0] == 'ansi'
        assert lines[1] == '#a3be8c', lines  # active border, not mode fg
        assert lines[2] == '#a3be8c', lines  # active border
        assert lines[3] == '#d08770', lines  # message
        assert lines[4] == '#3b4252', lines  # status bg, bright enough to keep
        assert lines[5] == '#4c566a', lines  # border
        assert '\x1b[38;2;163;190;140m' in lines[6]
        assert '\x1b[38;2;163;190;140m' in lines[7]
        assert '\x1b[38;2;208;135;112m' in lines[8]
        assert lines[9] == '#e6e6e6', lines  # dark status bg → light secondary text

        fixed = resolve({'CANOPY_THEME': 'fixed'})
        # Force theme via option
        tm('set-option', '-g', '@tmux-canopy-theme', 'fixed')
        fixed = resolve()
        assert fixed[0] == 'fixed'
        assert fixed[1] == '6' and fixed[2] == '2' and fixed[3] == '3'
        assert fixed[4] == '236'
        assert fixed[6] == '\x1b[1;36m'
        assert fixed[7] == '\x1b[1;32m'
        assert fixed[8] == '\x1b[1;33m'

        tm('set-option', '-g', '@tmux-canopy-theme', 'ansi')
        tm('set-option', '-g', '@tmux-canopy-selection-background', '245')
        overridden = resolve()
        assert overridden[4] == '245', overridden

        tm('set-option', '-gu', '@tmux-canopy-selection-background')
        tm('set-option', '-g', '@tmux-canopy-theme', 'ansi')

        def ui_colors(theme):
            tm('set-option', '-g', '@tmux-canopy-theme', theme)
            script = r'''
set -euo pipefail
source scripts/lib.sh
source scripts/ui-options.sh
sidebar_ui_options "$TMUX_PANE"
for arg in "${SIDEBAR_FZF_ARGS[@]}"; do
  case "$arg" in
    --color=*) printf '%s\n' "${arg#--color=}" ;;
  esac
done
'''
            run_env = {k: v for k, v in env.items()
                       if not k.startswith('CANOPY_COLOR_')
                       and k not in ('CANOPY_THEME', 'CANOPY_THEME_FROZEN', 'CANOPY_SELECTION_EXPLICIT')}
            result = sp.run(['bash', '-c', script], cwd=ROOT, env=run_env,
                            capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, result.stderr
            return result.stdout.strip()

        ansi_colors = ui_colors('ansi')
        assert 'pointer:#a3be8c:bold' in ansi_colors, ansi_colors
        assert 'bg+:#3b4252' in ansi_colors, ansi_colors
        assert 'border:#4c566a' in ansi_colors or 'border:#4c566a:' in ansi_colors, ansi_colors

        fixed_colors = ui_colors('fixed')
        assert 'pointer:6:bold' in fixed_colors, fixed_colors
        assert 'bg+:236' in fixed_colors, fixed_colors

        mono_colors = ui_colors('mono')
        assert mono_colors == 'bw', mono_colors

        def ui_glyphs():
            script = r'''
set -euo pipefail
source scripts/lib.sh
source scripts/ui-options.sh
sidebar_ui_options "$TMUX_PANE"
for arg in "${SIDEBAR_FZF_ARGS[@]}"; do
  case "$arg" in
    --pointer=*|--gutter=*) printf '%s\n' "$arg" ;;
  esac
done
'''
            run_env = {k: v for k, v in env.items()
                       if not k.startswith('CANOPY_COLOR_')
                       and k not in ('CANOPY_THEME', 'CANOPY_THEME_FROZEN', 'CANOPY_SELECTION_EXPLICIT')}
            result = sp.run(['bash', '-c', script], cwd=ROOT, env=run_env,
                            capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, result.stderr
            return result.stdout.splitlines()

        tm('set-option', '-g', '@tmux-canopy-theme', 'ansi')
        tm('set-option', '-g', '@tmux_canopy_icon_theme', 'unicode')
        glyphs = ui_glyphs()
        assert '--pointer=▌' in glyphs, glyphs
        assert '--gutter= ' in glyphs, glyphs
        tm('set-option', '-g', '@tmux_canopy_icon_theme', 'ascii')
        glyphs = ui_glyphs()
        assert '--pointer=>' in glyphs, glyphs
        assert '--gutter= ' in glyphs, glyphs
        tm('set-option', '-g', '@tmux_canopy_icon_theme', 'unicode')

        # Dracula: mode fg is the dark background color (text on the purple
        # highlight). It must not become the sidebar accent, and a status
        # background that matches the terminal is lifted so the selection shows.
        tm('set-option', '-g', '@tmux-canopy-theme', 'ansi')
        tm('set-option', '-gu', '@tmux-canopy-selection-background')
        tm('set-option', '-g', 'status-style', 'bg=#282a36,none')
        tm('set-option', '-g', 'pane-active-border-style', 'fg=#bd93f9')
        tm('set-option', '-g', 'mode-style', 'fg=#282a36,bg=#bd93f9')
        tm('set-option', '-g', 'message-style', 'fg=#f8f8f2,bg=#44475a')
        dracula = resolve()
        assert dracula[1] == '#bd93f9', dracula
        assert dracula[4] == '#585a66', dracula
        assert dracula[9] == '#e6e6e6', dracula

        # Tree render picks up env accents when theme=ansi.
        with tempfile.TemporaryDirectory(prefix='theme-render-') as directory:
            state = Path(directory) / 'state'
            state.touch()
            records = [
                ['D', 'unicode', 'none', 'ansi', 'compact', '', '', '', '%0', '@0', '$0', '42', 'host'],
                ['S', '$0', 'acme', '0'],
                ['W', '$0', '@0', '0', 'server', '1', 'off', '', '', ''],
                ['P', '%0', '@0', '0', 'claude', '', '/tmp', '0', '', '', '', '', '', '', '', ''],
            ]
            snapshot = '\n'.join('\x1f'.join(r) for r in records) + '\n'
            render_env = os.environ.copy()
            render_env.update(
                TMUX_CANOPY_RENDER_CLIENT='',
                TMUX_CANOPY_RENDER_HOME='/tmp',
                CANOPY_COLOR_ACTIVE_ANSI='\033[38;2;163;190;140m',
                CANOPY_COLOR_ACCENT_ANSI='\033[38;2;129;161;193m',
                CANOPY_COLOR_ATTENTION_ANSI='\033[38;2;208;135;112m',
            )
            out = sp.run(['awk', '-v', 'stable=1', '-v', 'header=1', '-f',
                          str(ROOT / 'lib/tree-render.awk'), str(state), '-'],
                         input=snapshot, text=True, capture_output=True, env=render_env, check=True)
            assert '\x1b[38;2;163;190;140m' in out.stdout, out.stdout
            # fixed ignores env
            records[0][3] = 'fixed'
            snapshot = '\n'.join('\x1f'.join(r) for r in records) + '\n'
            out_fixed = sp.run(['awk', '-v', 'stable=1', '-v', 'header=1', '-f',
                                str(ROOT / 'lib/tree-render.awk'), str(state), '-'],
                               input=snapshot, text=True, capture_output=True, env=render_env, check=True)
            assert '\x1b[1;32m' in out_fixed.stdout
            assert '\x1b[38;2;163;190;140m' not in out_fixed.stdout

        print('ok - theme inherit, fixed, mono, selection override, tree env')
    finally:
        sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)


def main():
    test_parser()
    test_inherit_and_escapes()


if __name__ == '__main__':
    main()
