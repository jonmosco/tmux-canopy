#!/usr/bin/env python3
"""Reload restores owned configuration without clobbering later user edits."""
import os
from pathlib import Path
import subprocess as sp

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
