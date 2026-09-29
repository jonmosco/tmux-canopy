#!/usr/bin/env python3
"""Reload restores owned configuration without clobbering later user edits."""
import os
from pathlib import Path
import subprocess as sp
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    socket = f'canopy-config-test-{os.getpid()}'
    env = os.environ.copy()
    env.pop('TMUX', None)
    env.pop('TMUX_PANE', None)

    def tm(*args):
        result = sp.run(['tmux', '-L', socket, *args], env=env, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, (args, result.stderr)
        return result.stdout.strip()

    def binding(key):
        lines = tm('list-keys', '-T', 'prefix', '-F', '#{key_string}|#{key_repeat}|#{key_note}|#{key_command}')
        return next((line for line in lines.splitlines() if line.startswith(key+'|')), '')

    def load():
        result = sp.run(['bash', str(ROOT/'tmux-canopy.tmux')], env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0 and not result.stderr, result.stderr

    try:
        pane = tm('-f', '/dev/null', 'new-session', '-d', '-P', '-F', '#{pane_id}', 'sleep 180')
        env['TMUX'] = tm('display-message', '-p', '-t', pane, '#{socket_path},#{pid},0')
        tm('bind-key', '-r', '-N', 'my "navigation" $note', 'n', 'display-message', 'original; #{version} $literal')
        tm('bind-key', 'T', 'display-message', 'original T')
        tm('unbind-key', 'Tab')
        original_n, original_t = binding('n'), binding('T')
        tm('set-window-option', '-g', 'monitor-activity', 'off')
        tm('set-window-option', '-g', 'monitor-bell', 'on')
        tm('set-window-option', '-g', 'monitor-silence', '17')
        tm('set-window-option', '-g', 'window-status-activity-style', 'fg=blue')
        tm('set-option', '-g', '@tmux-canopy-notifications', 'all')
        load()
        with tempfile.TemporaryDirectory(prefix='canopy-agent-option-') as directory:
            state = Path(directory) / 'state'
            state.touch()
            source_env = env | {'TMUX_PANE': pane, 'TMUX_CANOPY_STATE': str(state),
                                'TMUX_CANOPY_HEADER': '1'}

            def source(*args):
                result = sp.run([str(ROOT / 'scripts/tree-source'), *args], env=source_env,
                                capture_output=True, text=True, timeout=15)
                assert result.returncode == 0, result.stderr
                return result.stdout

            def ui_options():
                result = sp.run(['bash', '-c',
                                 'source "$1"; sidebar_ui_options "$2"; printf "%s\\n" "${SIDEBAR_FZF_ARGS[@]}"',
                                 'bash', str(ROOT / 'scripts/ui-options.sh'), pane],
                                env=source_env, capture_output=True, text=True, timeout=15)
                assert result.returncode == 0, result.stderr
                return result.stdout

            assert 'Agents' not in source() and 'Agents' not in source('--agents')
            assert source('--needs-input') == ''
            binds = ui_options()
            assert '--bind=4:' in binds and '--bind=n:' in binds and '--bind=A:' in binds
            tm('set-option', '-g', '@tmux-canopy-agents', 'on')
            load()
            assert 'Agents' in source() and '[Agents]' in source('--agents')
            client = '/dev/ttys-agent-test'
            key = sp.check_output(['cksum'], input=client.encode()).split()[0].decode()
            tm('set-option', '-g', '@tmux_canopy_agents_' + key, 'off')
            hidden = sp.run([str(ROOT / 'scripts/tree-source')], env=source_env | {'TMUX_CANOPY_CLIENT': client},
                            capture_output=True, text=True, timeout=15)
            assert hidden.returncode == 0 and 'Agents' not in hidden.stdout, hidden.stderr
            tm('set-option', '-g', '@tmux_canopy_agents_' + key, 'on')
            tm('set-option', '-g', '@tmux-canopy-agents', 'off')
            load()
            shown = sp.run([str(ROOT / 'scripts/tree-source')], env=source_env | {'TMUX_CANOPY_CLIENT': client},
                           capture_output=True, text=True, timeout=15)
            assert shown.returncode == 0 and 'Agents' in shown.stdout, shown.stderr
            assert 'Agents' not in source()
            print('ok - agent mode follows the client toggle and the global default')
        assert tm('show-option', '-gqv', '@tmux_canopy_icon_theme') == 'unicode'
        tm('set-option', '-g', '@tmux-canopy-icon-theme', 'nerdfont')
        load()
        assert tm('show-option', '-gqv', '@tmux_canopy_icon_theme') == 'nerdfont'
        tm('set-option', '-g', '@tmux-canopy-icon-theme', 'auto')
        load()
        assert tm('show-option', '-gqv', '@tmux_canopy_icon_theme') == 'unicode'
        assert tm('show-option', '-gqv', '@tmux_canopy_appearance') == 'places'
        tm('set-option', '-g', '@tmux-canopy-appearance', 'ascii')
        load()
        assert tm('show-option', '-gqv', '@tmux_canopy_appearance') == 'places'
        assert tm('show-option', '-gqv', '@tmux_canopy_icon_theme') == 'ascii'
        tm('set-option', '-g', '@tmux-canopy-icon-theme', 'auto')
        tm('set-option', '-g', '@tmux-canopy-appearance', 'default')
        load()
        assert tm('show-option', '-gqv', '@tmux_canopy_icon_theme') == 'unicode'
        assert tm('show-option', '-gqv', '@tmux_canopy_appearance') == 'places'
        tm('set-option', '-g', '@tmux-canopy-appearance', 'unexpected')
        load()
        assert tm('show-option', '-gqv', '@tmux_canopy_appearance') == 'places'
        tm('set-option', '-g', '@tmux-canopy-appearance', 'nope')
        load()
        assert tm('show-option', '-gqv', '@tmux_canopy_appearance') == 'places'
        assert tm('show-option', '-gqv', '@tmux_canopy_animate') == 'on'
        tm('set-option', '-g', '@tmux-canopy-animate', 'off')
        load()
        assert tm('show-option', '-gqv', '@tmux_canopy_animate') == 'off'
        tm('set-option', '-g', '@tmux-canopy-animate', 'maybe')
        load()
        assert tm('show-option', '-gqv', '@tmux_canopy_animate') == 'on'
        assert 'navigate' in binding('n') and 'toggle' in binding('T')
        assert 'global' in binding('T') and 'slot' in binding('T')
        installed = binding('n')
        load()
        assert binding('n') == installed
        tm('set-option', '-g', '@tmux-canopy-smooth-navigation', 'off')
        tm('set-option', '-g', '@tmux-canopy-last-window-key', 'off')
        tm('set-option', '-g', '@tmux-canopy-key', 'Y')
        tm('set-option', '-g', '@tmux-canopy-notifications', 'none')
        load()
        assert binding('n') == original_n, (binding('n'), original_n)
        assert binding('T') == original_t
        assert binding('Tab') == ''
        assert 'toggle' in binding('Y')
        assert tm('show-window-option', '-gv', 'monitor-activity') == 'off'
        assert tm('show-window-option', '-gv', 'monitor-bell') == 'on'
        assert tm('show-window-option', '-gv', 'monitor-silence') == '17'
        assert tm('show-window-option', '-gv', 'window-status-activity-style') == 'fg=blue'
        print('ok - original commands, notes, repeat flags and absent keys restore on disable/key change')
        tm('set-option', '-g', '@tmux-canopy-smooth-navigation', 'on')
        tm('set-option', '-g', '@tmux-canopy-notifications', 'all')
        load()
        tm('bind-key', 'n', 'display-message', 'later user command')
        tm('set-window-option', '-g', 'monitor-silence', '42')
        tm('set-window-option', '-g', 'window-status-activity-style', 'fg=red')
        later = binding('n')
        load()
        assert binding('n') == later
        assert tm('show-window-option', '-gv', 'monitor-silence') == '42'
        assert tm('show-window-option', '-gv', 'window-status-activity-style') == 'fg=red'
        tm('set-option', '-g', '@tmux-canopy-smooth-navigation', 'off')
        tm('set-option', '-g', '@tmux-canopy-notifications', 'none')
        load()
        assert binding('n') == later
        assert tm('show-window-option', '-gv', 'monitor-silence') == '42'
        assert tm('show-window-option', '-gv', 'window-status-activity-style') == 'fg=red'
        print('ok - later user bindings and monitor settings survive reload and disable')
    finally:
        sp.run(['tmux', '-L', socket, 'kill-server'], env=env, stdout=sp.DEVNULL, stderr=sp.DEVNULL)


if __name__ == '__main__':
    main()
