#!/usr/bin/env python3
"""Theme resolution: parse styles, inherit ansi, named presets, role overrides, light/dark polarity, fixed/mono escapes."""
import os
from pathlib import Path
import subprocess as sp
import tempfile

ROOT = Path(__file__).resolve().parents[1]

THEME_ENV_KEYS = (
    'CANOPY_THEME',
    'CANOPY_THEME_LIGHT',
    'CANOPY_THEME_FROZEN',
    'CANOPY_SELECTION_EXPLICIT',
)


def strip_theme_env(mapping):
    return {
        k: v for k, v in mapping.items()
        if not k.startswith('CANOPY_COLOR_') and k not in THEME_ENV_KEYS
    }


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
canopy_style_attr 'fg=#cba6f4, bg=#1e1e2e' bg; check spaced-bg "$CANOPY_REPLY" '#1e1e2e'
canopy_style_attr 'fg=colour183,bg=default' fg; check colourN "$CANOPY_REPLY" '183'
canopy_style_attr 'fg=colour183,bg=default' bg; check default-bg "$CANOPY_REPLY" ''
canopy_style_attr 'default' fg; check whole-default "$CANOPY_REPLY" ''
canopy_style_attr '' fg; check empty "$CANOPY_REPLY" ''
canopy_color_to_fzf green; check fzf-green "$CANOPY_REPLY" '2'
canopy_color_to_fzf '#cba6f4'; check fzf-hex "$CANOPY_REPLY" '#cba6f4'
canopy_color_to_fzf 183; check fzf-183 "$CANOPY_REPLY" '183'
canopy_color_to_fzf colour183; check fzf-colour183 "$CANOPY_REPLY" '183'
canopy_color_to_fzf color42; check fzf-color42 "$CANOPY_REPLY" '42'
canopy_color_to_fzf colour256; check fzf-colour256 "$CANOPY_REPLY" ''
canopy_color_to_ansi green; check ansi-green "$CANOPY_REPLY" $'\033[1;32m'
canopy_color_to_ansi '#cba6f4'; check ansi-hex "$CANOPY_REPLY" $'\033[38;2;203;166;244m'
canopy_color_to_ansi 183; check ansi-183 "$CANOPY_REPLY" $'\033[38;5;183m'
canopy_color_to_ansi colour183; check ansi-colour183 "$CANOPY_REPLY" $'\033[38;5;183m'

# Luma & solid-selection foreground contrast
canopy_color_luma '#000000'; check luma-black "$CANOPY_REPLY" '0'
canopy_color_luma '#ffffff'; check luma-white "$CANOPY_REPLY" '1000'
canopy_color_luma 16; check luma-cube-black "$CANOPY_REPLY" '0'
canopy_color_luma 231; check luma-cube-white "$CANOPY_REPLY" '1000'
canopy_color_luma 255; check luma-gray-255 "$CANOPY_REPLY" '933'
canopy_solid_fg '#89b4fa'; check solid-bright-hex "$CANOPY_REPLY" '#000000'
canopy_solid_fg '#1e66f5'; check solid-dark-hex "$CANOPY_REPLY" '#ffffff'
canopy_solid_fg 183; check solid-bright-256 "$CANOPY_REPLY" '16'
canopy_solid_fg 25; check solid-dark-256 "$CANOPY_REPLY" '231'
CANOPY_THEME_LIGHT=0 canopy_solid_fg 6; check solid-fixed-cyan "$CANOPY_REPLY" '0'
CANOPY_THEME_LIGHT=1 canopy_solid_fg 6; check solid-light-cyan "$CANOPY_REPLY" '16'

# Dark lift and light shade
canopy_lift_dark_hex '#282a36'; check lift-dracula "$CANOPY_REPLY" '#585a66'
canopy_darken_light_hex '#eff1f5'; check darken-latte "$CANOPY_REPLY" '#cfd1d5'
canopy_darken_light_hex '#101520'; check darken-floor "$CANOPY_REPLY" '#000000'

# Theme normalization & every built-in preset
canopy_theme_normalize 'Catppuccin_Mocha'; check norm-mocha "$CANOPY_REPLY" 'catppuccin-mocha'
canopy_theme_normalize 'catppuccin'; check norm-alias-cat "$CANOPY_REPLY" 'catppuccin-mocha'
canopy_theme_normalize 'gruvbox'; check norm-alias-gruv "$CANOPY_REPLY" 'gruvbox-dark'
canopy_theme_normalize 'tokyo-night-light'; check norm-alias-tnl "$CANOPY_REPLY" 'tokyo-night-day'
if canopy_theme_normalize 'no-such-theme'; then
  printf 'FAIL expected unknown theme to return non-zero\n'; fail=1
fi
check norm-unknown-fallback "$CANOPY_REPLY" 'ansi'

dark_presets=(
  catppuccin-mocha catppuccin-macchiato catppuccin-frappe
  tokyo-night tokyo-night-storm dracula nord gruvbox-dark github-dark
  rose-pine rose-pine-moon kanagawa everforest one-dark solarized-dark
)
light_presets=(
  catppuccin-latte tokyo-night-day gruvbox-light github-light
  rose-pine-dawn solarized-light
)
for preset in "${dark_presets[@]}"; do
  canopy_theme_preset "$preset"
  check "$preset-light" "$CANOPY_THEME_LIGHT" '0'
  [[ "$CANOPY_COLOR_ACCENT_FZF" == \#* && "$CANOPY_COLOR_ERROR_FZF" == \#* && "$CANOPY_COLOR_SELECTION_BG" == \#* ]] || {
    printf 'FAIL %s missing hex slot\n' "$preset"; fail=1
  }
done
for preset in "${light_presets[@]}"; do
  canopy_theme_preset "$preset"
  check "$preset-light" "$CANOPY_THEME_LIGHT" '1'
  [[ "$CANOPY_COLOR_ACCENT_FZF" == \#* && "$CANOPY_COLOR_ERROR_FZF" == \#* && "$CANOPY_COLOR_SELECTION_BG" == \#* ]] || {
    printf 'FAIL %s missing hex slot\n' "$preset"; fail=1
  }
done
exit "$fail"
'''
    result = sp.run(['bash', '-c', script], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    print('ok - theme style parser, luma helpers, and built-in preset palettes')


def test_inherit_and_escapes():
    socket = f'canopy-theme-test-{os.getpid()}'
    env = strip_theme_env(os.environ)
    env.pop('TMUX', None)
    env.pop('TMUX_PANE', None)

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
printf '%s\n' "$CANOPY_COLOR_ERROR_FZF"
printf '%s\n' "$CANOPY_COLOR_ERROR_ANSI"
printf '%s\n' "$CANOPY_THEME_LIGHT"
printf '%s\n' "$CANOPY_SELECTION_EXPLICIT"
printf '%s\n' "$CANOPY_COLOR_FG_FZF"
printf '%s\n' "$CANOPY_COLOR_SELECTION_FG"
'''
            run_env = strip_theme_env(env)
            if extra:
                run_env.update(extra)
            result = sp.run(['bash', '-c', script], cwd=ROOT, env=run_env,
                            capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, result.stderr
            return result.stdout.split('\n')[:-1]

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
        assert lines[10] == '1' and lines[11] == '\x1b[1;31m', lines
        assert lines[12] == '0' and lines[13] == '0', lines
        assert lines[14] == '-1' and lines[15] == '', lines

        # Force theme via option: fixed ignores tmux styles and per-role overrides.
        tm('set-option', '-g', '@tmux-canopy-theme', 'fixed')
        tm('set-option', '-g', '@tmux-canopy-color-accent', '#ff00ff')
        fixed = resolve()
        assert fixed[0] == 'fixed'
        assert fixed[1] == '6' and fixed[2] == '2' and fixed[3] == '3'
        assert fixed[4] == '236'
        assert fixed[6] == '\x1b[1;36m'
        assert fixed[7] == '\x1b[1;32m'
        assert fixed[8] == '\x1b[1;33m'
        assert fixed[10] == '1' and fixed[11] == '\x1b[1;31m'
        tm('set-option', '-gu', '@tmux-canopy-color-accent')

        # Explicit selection-background overrides inherited bg, including dark
        # hex values (luma < 180) that must NOT be altered by canopy_lift_dark_hex.
        tm('set-option', '-g', '@tmux-canopy-theme', 'ansi')
        tm('set-option', '-g', '@tmux-canopy-selection-background', '245')
        overridden = resolve()
        assert overridden[4] == '245' and overridden[13] == '1', overridden

        tm('set-option', '-g', '@tmux-canopy-selection-background', '#181825')
        dark_explicit = resolve()
        assert dark_explicit[4] == '#181825' and dark_explicit[13] == '1', dark_explicit

        # @tmux-canopy-color-selection-bg takes precedence over @tmux-canopy-selection-background.
        tm('set-option', '-g', '@tmux-canopy-color-selection-bg', '#11111b')
        role_explicit = resolve()
        assert role_explicit[4] == '#11111b' and role_explicit[13] == '1', role_explicit
        tm('set-option', '-gu', '@tmux-canopy-color-selection-bg')
        tm('set-option', '-gu', '@tmux-canopy-selection-background')

        def ui_colors(theme, selection_style=None):
            tm('set-option', '-g', '@tmux-canopy-theme', theme)
            if selection_style is None:
                tm('set-option', '-gu', '@tmux-canopy-selection-style')
            else:
                tm('set-option', '-g', '@tmux-canopy-selection-style', selection_style)
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
            run_env = strip_theme_env(env)
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
        fixed_solid = ui_colors('fixed', 'solid')
        assert 'bg+:6,fg+:0,hl+:0:bold' in fixed_solid, fixed_solid

        mono_colors = ui_colors('mono')
        assert mono_colors == 'bw', mono_colors

        # Named presets + solid selection ink contrast + per-role overrides
        mocha = ui_colors('catppuccin-mocha', 'solid')
        assert 'pointer:#89b4fa:bold' in mocha, mocha
        assert 'bg+:#89b4fa,fg+:#000000,hl+:#000000:bold' in mocha, mocha

        latte_subtle = ui_colors('catppuccin-latte', 'subtle')
        assert 'pointer:#1e66f5:bold' in latte_subtle, latte_subtle
        assert 'bg+:#ccd0da,fg+:-1:regular' in latte_subtle, latte_subtle
        latte_solid = ui_colors('catppuccin-latte', 'solid')
        assert 'bg+:#1e66f5,fg+:#ffffff,hl+:#ffffff:bold' in latte_solid, latte_solid

        tm('set-option', '-g', '@tmux-canopy-theme', 'catppuccin-mocha')
        tm('set-option', '-g', '@tmux-canopy-color-accent', '#cba6f7')
        tm('set-option', '-g', '@tmux-canopy-color-error', '#ff3366')
        tm('set-option', '-g', '@tmux-canopy-color-fg', '#cdd6f4')
        tm('set-option', '-g', '@tmux-canopy-color-selection-fg', '#ffffff')
        mocha_ov = resolve()
        assert mocha_ov[0] == 'catppuccin-mocha'
        assert mocha_ov[1] == '#cba6f7' and mocha_ov[6] == '\x1b[38;2;203;166;247m', mocha_ov
        assert mocha_ov[2] == '#a6e3a1', mocha_ov  # non-overridden preset slot stays intact
        assert mocha_ov[10] == '#ff3366' and mocha_ov[11] == '\x1b[38;2;255;51;102m', mocha_ov
        assert mocha_ov[14] == '#cdd6f4' and mocha_ov[15] == '#ffffff', mocha_ov
        mocha_ov_ui = ui_colors('catppuccin-mocha', 'subtle')
        assert 'fg:#cdd6f4,' in mocha_ov_ui and 'preview-fg:#cdd6f4,' in mocha_ov_ui, mocha_ov_ui
        assert 'bg+:#313244,fg+:#ffffff:regular' in mocha_ov_ui, mocha_ov_ui
        for opt in ('@tmux-canopy-color-accent', '@tmux-canopy-color-error',
                    '@tmux-canopy-color-fg', '@tmux-canopy-color-selection-fg',
                    '@tmux-canopy-selection-style'):
            tm('set-option', '-gu', opt)

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
            run_env = strip_theme_env(env)
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
        assert dracula[9] == '#e6e6e6' and dracula[12] == '0', dracula

        # Light tmux theme under ansi (e.g. Catppuccin Latte styles):
        # status bg is shaded so selection is visible, light polarity is set,
        # muted becomes dark gray, and warm amber message fg (#df8e1d) is kept.
        tm('set-option', '-g', 'status-style', 'fg=#eff1f5,bg=#eff1f5')
        tm('set-option', '-g', 'pane-active-border-style', 'fg=#1e66f5')
        tm('set-option', '-g', 'mode-style', 'fg=#eff1f5,bg=#1e66f5')
        tm('set-option', '-g', 'message-style', 'fg=#df8e1d,bg=#eff1f5')
        light_ansi = resolve()
        assert light_ansi[1] == '#1e66f5', light_ansi
        assert light_ansi[3] == '#df8e1d', light_ansi
        assert light_ansi[4] == '#cfd1d5', light_ansi
        assert light_ansi[9] == '#3a3a3a' and light_ansi[12] == '1', light_ansi

        # 256-color light status background also triggers light polarity and shading.
        tm('set-option', '-g', 'status-style', 'fg=colour235,bg=colour255')
        light_256 = resolve()
        assert light_256[4] == '252' and light_256[12] == '1', light_256

        # Tree render picks up env accents, error slot, and light-theme icon contrast.
        with tempfile.TemporaryDirectory(prefix='theme-render-') as directory:
            state = Path(directory) / 'state'
            state.write_text('W:@1:$0\n')
            appearance_pad = [''] * 22
            records = [
                ['D', 'unicode', 'none', 'catppuccin-mocha', 'compact', '', '', '', '%0', '@0', '$0', '42', 'host',
                 'off', '', '', '', *appearance_pad, 'places', 'off', 'on'],
                ['S', '$0', 'acme', '0'],
                ['W', '$0', '@0', '0', 'server', '1', 'off', '', '', '', '0', '1'],
                ['W', '$0', '@1', '1', 'broken', '1', 'off', '', '', '', '0', '1'],
                ['P', '%0', '@0', '0', 'claude', '', '/tmp/proj', '0', '', '', '', '', '', '', '', '0',
                 '100', 'claude-hook', 'sess-1', '100', 'working', '1000', '', '', '', '0', '', ''],
                ['P', '%1', '@1', '0', 'codex', '', '/tmp/proj', '0', '', '', '', '', '', '', '', '0',
                 '101', 'codex-hook', 'sess-2', '101', 'interrupted', '1000', '', '', '', '0', 'boom', ''],
                ['V', '%0'],
                ['V', '%1'],
            ]
            snapshot = '\n'.join('\x1f'.join(r) for r in records) + '\n'
            render_env = strip_theme_env(os.environ)
            render_env.update(
                TMUX_CANOPY_RENDER_CLIENT='',
                TMUX_CANOPY_RENDER_HOME='/tmp',
                CANOPY_THEME_LIGHT='0',
                CANOPY_COLOR_ACTIVE_ANSI='\033[38;2;166;227;161m',
                CANOPY_COLOR_ACCENT_ANSI='\033[38;2;137;180;250m',
                CANOPY_COLOR_ATTENTION_ANSI='\033[38;2;249;226;175m',
                CANOPY_COLOR_ERROR_ANSI='\033[38;2;243;139;168m',
                CANOPY_COLOR_MUTED_ANSI='\033[38;2;166;173;200m',
            )
            out = sp.run(['awk', '-v', 'now=1005', '-v', 'stable=1', '-v', 'header=1', '-f',
                          str(ROOT / 'lib/tree-render.awk'), str(state), '-'],
                         input=snapshot, text=True, capture_output=True, env=render_env, check=True)
            assert '\x1b[38;2;166;227;161m' in out.stdout, out.stdout   # active
            assert '\x1b[38;2;243;139;168m✕' in out.stdout, out.stdout  # error rollup badge
            assert '\x1b[93m✳' in out.stdout, out.stdout                # dark-mode claude icon
            assert '\x1b[38;5;74m📂' in out.stdout, out.stdout          # dark-mode folder icon

            # Light polarity switches icons to dark-ink 256-color values
            records[0][3] = 'catppuccin-latte'
            snapshot = '\n'.join('\x1f'.join(r) for r in records) + '\n'
            light_env = {**render_env, 'CANOPY_THEME_LIGHT': '1'}
            out_light = sp.run(['awk', '-v', 'now=1005', '-v', 'stable=1', '-v', 'header=1', '-f',
                                str(ROOT / 'lib/tree-render.awk'), str(state), '-'],
                               input=snapshot, text=True, capture_output=True, env=light_env, check=True)
            assert '\x1b[38;5;130m✳' in out_light.stdout, out_light.stdout
            assert '\x1b[38;5;25m📂' in out_light.stdout, out_light.stdout
            assert '\x1b[93m' not in out_light.stdout, out_light.stdout

            # fixed ignores env (including error, muted, and light polarity)
            records[0][3] = 'fixed'
            snapshot = '\n'.join('\x1f'.join(r) for r in records) + '\n'
            out_fixed = sp.run(['awk', '-v', 'now=1005', '-v', 'stable=1', '-v', 'header=1', '-f',
                                str(ROOT / 'lib/tree-render.awk'), str(state), '-'],
                               input=snapshot, text=True, capture_output=True, env=light_env, check=True)
            assert '\x1b[1;32m' in out_fixed.stdout
            assert '\x1b[1;31m✕' in out_fixed.stdout
            assert '\x1b[93m✳' in out_fixed.stdout
            assert '\x1b[38;2;166;227;161m' not in out_fixed.stdout
            assert '\x1b[38;2;243;139;168m' not in out_fixed.stdout
            assert '\x1b[38;2;166;173;200m' not in out_fixed.stdout

        print('ok - theme inherit, presets, role overrides, light polarity, fixed/mono escapes')
    finally:
        sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)


def main():
    test_parser()
    test_inherit_and_escapes()


if __name__ == '__main__':
    main()
