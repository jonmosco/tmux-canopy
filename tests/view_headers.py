#!/usr/bin/env python3
"""quiet names every view the same way, with what it holds on the right and a
footer to act and get back; agent mode off says so in the Tree."""
import os
from pathlib import Path
import re
import subprocess as sp
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ANSI = re.compile(r'\x1b\[[0-9;]*m')
socket = f'canopy-view-headers-{os.getpid()}'
env = {k: v for k, v in os.environ.items() if k not in ('TMUX', 'TMUX_PANE')}


def tm(*args):
    result = sp.run(['tmux', '-L', socket, *args], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, (args, result.stderr)
    return result.stdout.strip()


try:
    with tempfile.TemporaryDirectory(prefix='canopy-view-headers-') as directory:
        state = Path(directory) / 'state'
        tm('-f', '/dev/null', 'new-session', '-d', '-s', 'work', '-x', '120', '-y', '30', 'sleep 600')
        tm('split-window', '-d', 'sleep 601')
        tm('set-buffer', '-b', 'one', 'hello')
        tm('set-buffer', '-b', 'two', 'world')
        sidebar = tm('split-window', '-d', '-h', '-l', '42', '-P', '-F', '#{pane_id}', 'sleep 600')
        tm('set-option', '-p', '-t', sidebar, '@tmux_canopy', '1')
        tm('set-option', '-g', '@tmux_canopy_appearance', 'quiet')
        source_env = env | {'TMUX': tm('display-message', '-p', '#{socket_path},0,0'), 'TMUX_PANE': sidebar,
                            'TMUX_CANOPY_STATE': str(state)}

        def view(name):
            state.write_text(f'VIEW\t{name}\n')
            out = sp.run([str(ROOT / 'scripts/sidebar-source'), '--stable', '--read0'], env=source_env,
                         capture_output=True, text=True, timeout=20).stdout
            header = next(r.split('\t')[1] for r in out.split('\0') if r.startswith('H:'))
            footer = Path(str(state) + '.footer')
            return ANSI.sub('', header).rstrip(), ANSI.sub('', footer.read_text()).strip() if footer.exists() else ''

        tm('set-option', '-g', '@tmux-canopy-agents', 'on')
        assert view('processes') == ('Processes                   2 processes', 'Enter focus   1 tree   a actions'), \
            view('processes')
        assert view('buffers') == ('Buffers                       2 buffers', 'Enter paste   1 tree   a actions'), \
            view('buffers')
        assert view('tree')[0] == 'Tree · All', view('tree')
        assert view('agents')[0].startswith('Agents · All'), view('agents')
        tm('set-option', '-g', '@tmux-canopy-agents', 'off')
        assert view('tree') == ('Tree · All' + ' ' * 15 + 'agent mode off', '? keys   / search   2 proc   3 buff'), \
            view('tree')
        tm('delete-buffer', '-b', 'two')
        assert view('buffers')[0].endswith('1 buffer'), view('buffers')
        tm('resize-pane', '-t', sidebar, '-x', '26')
        assert view('processes') == ('Processes   2 processes', 'Enter focus   1 tree'), view('processes')
        tm('set-option', '-g', '@tmux_canopy_appearance', 'places')
        assert 'Proc' in view('processes')[0] and 'Buff' in view('processes')[0], 'other appearances keep tabs'
    print('ok - quiet views share one header with their counts, footers act and lead back, and agent mode off shows')
finally:
    sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True, timeout=10)
