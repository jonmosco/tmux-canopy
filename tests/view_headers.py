#!/usr/bin/env python3
"""Every view names itself, counts what it holds, and exposes responsive
view-specific actions in the footer."""
import os
from pathlib import Path
import re
import subprocess as sp
import tempfile
import time

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

        def view(name, state_extra=''):
            state.write_text(f'VIEW\t{name}\n{state_extra}')
            out = sp.run([str(ROOT / 'scripts/sidebar-source'), '--stable', '--read0'], env=source_env,
                         capture_output=True, text=True, timeout=20).stdout
            header = next(r.split('\t')[1] for r in out.split('\0') if r.startswith('H:'))
            footer = Path(str(state) + '.footer')
            return ANSI.sub('', header).rstrip(), ANSI.sub('', footer.read_text()).strip() if footer.exists() else ''

        tm('set-option', '-g', '@tmux-canopy-agents', 'on')
        assert view('processes') == ('Processes                   2 processes', '↵ focus  a actions  p preview'), \
            view('processes')
        assert view('buffers') == ('Buffers                       2 buffers', '↵ paste  a actions  x delete  / search'), \
            view('buffers')
        assert view('processes', 'MOVE\tP:%0\n')[1] == 'Moving  ↵ move here  c cancel'
        assert view('buffers', f'DELETE\tB2:one\t{int(time.time())}\n')[1] == \
            'x again within 5 s to delete'
        assert view('tree')[0] == 'Tree · All', view('tree')
        assert view('agents')[0].startswith('Agents · All'), view('agents')
        tm('set-option', '-g', '@tmux-canopy-agents', 'off')
        assert view('tree') == ('Tree · All' + ' ' * 15 + 'agent mode off', '↵ focus  a actions  / search  ? help'), \
            view('tree')
        tm('delete-buffer', '-b', 'two')
        assert view('buffers')[0].endswith('1 buffer'), view('buffers')
        tm('resize-pane', '-t', sidebar, '-x', '26')
        assert view('processes') == ('Processes   2 processes', '↵ focus  a actions'), view('processes')
        tm('set-option', '-g', '@tmux_canopy_appearance', 'places')
        process_view = view('processes')
        assert process_view[0].startswith('╭─ Proc') and 'Buff' not in process_view[0], process_view
        assert process_view[1] == '↵ focus  a actions', process_view
        assert view('buffers', 'FOOTER\toff\n')[1] == ''
    print('ok - every view names itself and exposes responsive action footers')
finally:
    sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True, timeout=10)
