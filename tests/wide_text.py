#!/usr/bin/env python3
"""Rows with wide characters (CJK, fullwidth, emoji) fit the sidebar and keep their edge marks."""
import os
from pathlib import Path
import re
import subprocess as sp
import tempfile
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
socket = f'canopy-wide-{os.getpid()}'
env = {k: v for k, v in os.environ.items() if k not in ('TMUX', 'TMUX_PANE')}


def tm(*args):
    result = sp.run(['tmux', '-L', socket, *args], env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, (args, result.stderr)
    return result.stdout.strip()


def cells(text):
    return sum(2 if unicodedata.east_asian_width(char) in 'WF' else 1 for char in text)


def main():
    with tempfile.TemporaryDirectory(prefix='canopy-wide-') as directory:
        state = Path(directory) / 'state'
        try:
            tm('-f', '/dev/null', 'new-session', '-d', '-s', '作業セッション', '-x', '120', '-y', '30')
            names = {'作業セッション:0': '設定ページの修正作業', 'plain:0': 'settings-page-fix-work'}
            tm('new-session', '-d', '-s', 'plain')
            tm('new-window', '-d', '-t', 'plain:', '-n', 'ＦＵＬＬ 🚀 ローンチ')
            for target, name in names.items():
                tm('rename-window', '-t', target, name)
                tm('split-window', '-d', '-t', target)
            tm('split-window', '-d', '-t', 'plain:1')
            sidebar = tm('split-window', '-d', '-h', '-l', '42', '-t', 'plain:0', '-P', '-F', '#{pane_id}')
            tm('set-option', '-p', '-t', sidebar, '@tmux_canopy', '1')
            width = int(tm('display-message', '-p', '-t', sidebar, '#{pane_width}'))
            folds = []
            for target in ('作業セッション:0', 'plain:0', 'plain:1'):
                window, session = tm('display-message', '-p', '-t', target, '#{window_id} #{session_id}').split()
                folds.append(f'W:{window}:{session}')
            state.write_text('\n'.join(folds) + '\n')
            base = env | {'TMUX': tm('display-message', '-p', '-t', sidebar, '#{socket_path},#{pid},0'),
                          'TMUX_PANE': sidebar, 'TMUX_CANOPY_STATE': str(state), 'TMUX_CANOPY_NUL': '1',
                          'TMUX_CANOPY_HEADER': '1', 'TMUX_CANOPY_CLIENT': '/dev/none'}
            tm('set-option', '-g', '@tmux_canopy_appearance', 'classic')
            result = sp.run([str(ROOT / 'scripts/tree-source')], env=base, capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, result.stderr
            rows = {}
            for record in result.stdout.split('\0'):
                if record.startswith('W:'):
                    token, text = record.split('\t')[:2]
                    rows[token] = re.sub(r'\x1b\[[0-9;]*m', '', text)
            assert len(rows) == 3, rows
            for token, text in rows.items():
                # A folded window carries its pane count at the right edge.
                assert cells(text) <= width - 1, (cells(text), width, text)
                assert re.search(r'\b2p\b', text), text
            print('ok - wide-character names fit the sidebar and keep their edge counts')
        finally:
            sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)


if __name__ == '__main__':
    main()
