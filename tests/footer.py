#!/usr/bin/env python3
"""The Tree footer exposes actions, responds to width, and can be hidden."""
import os
from pathlib import Path
import re
import subprocess as sp
import tempfile

ROOT = Path(__file__).resolve().parents[1]
socket = f'canopy-footer-{os.getpid()}'
env = {k: v for k, v in os.environ.items() if k not in ('TMUX', 'TMUX_PANE')}


def tm(*args):
    result = sp.run(['tmux', '-L', socket, *args], env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, (args, result.stderr)
    return result.stdout.strip()


def main():
    with tempfile.TemporaryDirectory(prefix='canopy-footer-') as directory:
        state = Path(directory) / 'state'
        state.write_text('')
        try:
            wide = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'one', '-x', '160', '-y', '40',
                      '-P', '-F', '#{pane_id}')
            tm('split-window', '-d', '-t', 'one:')
            tm('new-window', '-d', '-t', 'one:')
            tm('new-session', '-d', '-s', 'two')
            tm('new-session', '-d', '-s', 'three')
            # A window linked into a second session is still one window.
            tm('link-window', '-s', tm('display-message', '-p', '-t', 'one:0', '#{window_id}'), '-t', 'two:5')
            # A Canopy sidebar pane is not a content pane.
            sidebar = tm('split-window', '-d', '-h', '-l', '30', '-t', 'one:1', '-P', '-F', '#{pane_id}')
            tm('set-option', '-p', '-t', sidebar, '@tmux_canopy', '1')
            base = env | {'TMUX': tm('display-message', '-p', '-t', wide, '#{socket_path},#{pid},0'),
                          'TMUX_CANOPY_STATE': str(state), 'TMUX_CANOPY_HEADER': '1', 'TMUX_CANOPY_NUL': '1'}

            def footer(pane, *args):
                result = sp.run([str(ROOT / 'scripts/tree-source'), *args], env=base | {'TMUX_PANE': pane},
                                capture_output=True, text=True, timeout=10)
                assert result.returncode == 0, result.stderr
                records = [r.split('\t') for r in result.stdout.split('\0') if r.startswith('F:\t')]
                return re.sub(r'\x1b\[[0-9;]*m', '', records[0][1]) if records else None

            expected = '↵ focus  a actions  / search  ? help'
            assert footer(wide) == expected, footer(wide)
            print('ok - the Tree footer exposes the actions available in the view')

            state.write_text('FILTER\tsession\n')
            assert footer(wide) == expected, footer(wide)
            state.write_text('')
            print('ok - filters do not replace the stable action rail')

            # A narrow sidebar keeps the highest-priority actions.
            narrow = tm('split-window', '-d', '-h', '-l', '24', '-t', 'three:', '-P', '-F', '#{pane_id}')
            assert footer(narrow) == '↵ focus  a actions', footer(narrow)
            print('ok - a narrow sidebar drops lower-priority actions')

            # f flips the footer for this sidebar through its private state.
            def toggle():
                result = sp.run([str(ROOT / 'scripts/sidebar-action'), 'toggle-footer'],
                                env=base | {'TMUX_PANE': wide}, capture_output=True, text=True, timeout=10)
                assert result.returncode == 0, result.stderr
            toggle()
            assert 'FOOTER\toff' in state.read_text() and footer(wide) is None
            toggle()
            assert 'FOOTER\ton' in state.read_text() and footer(wide) == expected
            assert state.read_text().count('FOOTER') == 1
            state.write_text('')
            print('ok - f hides and shows the footer for one sidebar')

            tm('set-option', '-g', '@tmux_canopy_icon_theme', 'ascii')
            assert footer(wide) == 'Enter focus  a actions  / search  ? help', footer(wide)
            print('ok - the ASCII footer uses an ASCII Enter label')

            tm('set-option', '-g', '@tmux-canopy-agents', 'on')
            assert footer(wide) == 'Enter focus  a actions  / search  ? help', footer(wide)
            assert footer(wide, '--agents') == 'Enter focus  n waiting  > reply  i summary'
            print('ok - Tree and Agents expose their own stable action rails')
        finally:
            sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)


if __name__ == '__main__':
    main()
