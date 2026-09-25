#!/usr/bin/env python3
"""NUL-framed entries: shared directories, multiline selection and stable identities."""
import fcntl
from support import install_fzf_probe
import os
from pathlib import Path
import pty
import re
import shlex
import shutil
import struct
import subprocess as sp
import tempfile
import termios
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    executable = shutil.which('tmux')
    socket = f'tree-multiline-test-{os.getpid()}'
    env = os.environ.copy()
    for key in ('TMUX', 'TMUX_PANE', 'FZF_DEFAULT_OPTS', 'FZF_DEFAULT_OPTS_FILE', 'TMUX_CANOPY_RECORD_FORMAT'):
        env.pop(key, None)
    env['TERM'] = 'xterm-256color'
    master = None
    attached = None
    with tempfile.TemporaryDirectory(prefix='tree-multiline-') as directory:
        temp = Path(directory)
        state, selected = temp / 'state', temp / 'selected'
        state.touch()
        dirs = [temp / realm / 'hcm-gitops' for realm in ('commercial', 'fedramp')]
        for path in dirs:
            path.mkdir(parents=True)

        def tm(*args):
            result = sp.run([executable, '-L', socket, *args], env=env, text=True, capture_output=True, timeout=10)
            assert result.returncode == 0, (args, result.stderr)
            return result.stdout.rstrip('\n')

        def display(pane, fmt):
            return tm('display-message', '-p', '-t', pane, fmt)

        def source(*args):
            return sp.check_output([str(ROOT / 'scripts/sidebar-source'), '--stable', *args], env=script_env, timeout=10).decode()

        def records():
            return [record.split('\t') for record in source('--read0').rstrip('\0').split('\0')]

        def wait(predicate, message):
            until = time.monotonic() + 7
            while time.monotonic() < until:
                if predicate():
                    return
                time.sleep(.035)
            raise AssertionError(message)

        def probe():
            selected.unlink(missing_ok=True)
            def poll():
                if selected.exists() and selected.stat().st_size:
                    return True
                tm('send-keys', '-t', sidebar, 'M-z')
                time.sleep(.08)
                return False
            wait(poll, 'selection probe')
            return selected.read_text().rstrip('\n').split('|')

        def screen():
            return tm('capture-pane', '-p', '-t', sidebar).splitlines()

        try:
            first = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'multiline', '-n', 'main', '-x', '160', '-y', '44',
                       '-c', str(dirs[0]), '-P', '-F', '#{pane_id}', 'sleep 600')
            second = tm('split-window', '-d', '-v', '-c', str(dirs[1]), '-t', first, '-P', '-F', '#{pane_id}', 'sleep 600')
            tm('set-option', '-g', 'status', 'off')
            tm('set-option', '-g', 'mouse', 'on')
            tm('set-option', '-g', 'escape-time', '10')
            tm('set-option', '-g', 'default-shell', '/bin/bash')
            for option, value in [('density', 'normal'), ('theme', 'ansi'), ('preview', 'off'), ('scope', 'window')]:
                tm('set-option', '-g', '@tmux-canopy-' + option, value)
            tm('set-option', '-g', '@tmux_canopy_icon_theme', 'unicode')
            script_env = env | {'TMUX': display(first, '#{socket_path},#{pid},0'), 'TMUX_PANE': first,
                                'TMUX_CANOPY_STATE': str(state)}
            rows = records()
            assert all(len(row) == 3 for row in rows)
            assert len({row[2] for row in rows}) == len(rows)
            for token, text, _ in rows:
                assert text.count('\n') == (1 if token.startswith('P:') else 0)
                if token.startswith('P:'):
                    assert '\x1b[2m…/' in text.split('\n')[1]
            assert all(len(row.split('\t')) == 3 for row in source().splitlines())
            assert '\0' not in source()
            for view in ('processes', 'buffers'):
                state.write_text(f'VIEW\t{view}\n')
                assert all(len(row) == 3 and '\n' not in row[1] for row in records())
            state.write_text('')
            print('ok - one stable identity per multiline pane; legacy and other-view framing preserved')

            binding = f"alt-z:execute-silent(printf '%s|%s|%s\\n' {{1}} {{3}} {{q}} > {selected})"
            install_fzf_probe(temp, [binding], script_env)
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 44, 160, 0, 0))
            client = os.ttyname(slave)
            attached = sp.Popen([executable, '-L', socket, 'attach-session', '-t', 'multiline'], stdin=slave,
                                stdout=slave, stderr=slave, env=env, start_new_session=True)
            os.close(slave)
            def drain():
                try:
                    while os.read(master, 65536):
                        pass
                except OSError:
                    pass
            threading.Thread(target=drain, daemon=True).start()
            wait(lambda: client in tm('list-clients', '-F', '#{client_tty}'), 'client attach')
            script_env['TMUX_CANOPY_CLIENT'] = client
            sp.run([str(ROOT / 'scripts/toggle'), client, first, '42', 'window'], env=script_env, check=True, timeout=15)
            sidebar = next(row.split('|')[0] for row in tm('list-panes', '-a', '-F', '#{pane_id}|#{@tmux_canopy}').splitlines() if row.endswith('|1'))
            script_env['TMUX_PANE'] = sidebar
            wait(lambda: any('…/fedramp/hcm-gitops' in line for line in screen()), 'two-line view rendered')
            tm('send-keys', '-t', sidebar, 'Home', 'j', 'j')
            assert probe()[0] == 'P:' + first
            frame = screen()
            assert not any(line.startswith('▌') for line in frame), 'gutter must not form a block bar'
            a = next(i for i, line in enumerate(frame) if '…/commercial/hcm-gitops' in line)
            b = next(i for i, line in enumerate(frame) if '…/fedramp/hcm-gitops' in line)
            assert b == a + 2 and 'sleep' in frame[a-1] and 'sleep' in frame[b-1]
            assert frame[a].index('…/') == frame[a-1].index('sleep')
            assert frame[b].index('…/') == frame[b-1].index('sleep')
            # tmux's SGR capture lets us check that the whole logical entry,
            # not just its first line, receives fzf's selection background.
            bg = None
            highlighted = set()
            chunks = re.split(r'\x1b\[([0-9;]*)m', tm('capture-pane', '-ep', '-t', sidebar))
            for index, chunk in enumerate(chunks):
                if index % 2:
                    codes = [int(code or 0) for code in chunk.split(';')]
                    offset = 0
                    while offset < len(codes):
                        code = codes[offset]
                        if code in (0, 49):
                            bg = None
                        if code in (38, 48) and offset + 2 < len(codes) and codes[offset+1] == 5:
                            if code == 48:
                                bg = codes[offset+2]
                            offset += 3
                        else:
                            offset += 1
                elif bg == 236:
                    for label in ('sleep', '…/commercial/hcm-gitops'):
                        if label in chunk:
                            highlighted.add(label)
            assert highlighted == {'sleep', '…/commercial/hcm-gitops'}, highlighted
            tm('send-keys', '-t', sidebar, 'j')
            assert probe()[0] == 'P:' + second
            tm('send-keys', '-t', sidebar, 'k')
            assert probe()[0] == 'P:' + first
            # Click the directory, not the command. It must select the pane item.
            x = int(display(sidebar, '#{pane_left}')) + 15
            y = int(display(sidebar, '#{pane_top}')) + b + 1
            os.write(master, f'\x1b[<0;{x};{y}M\x1b[<0;{x};{y}m'.encode())
            wait(lambda: probe()[0] == 'P:' + second, 'second-line mouse selection')
            print('ok - aligned paths, no spacer rows, one j/k step per pane, and second-line mouse selection')

            tm('send-keys', '-t', sidebar, '/')
            tm('send-keys', '-t', sidebar, '-l', 'fedramp')
            time.sleep(.15)
            before = probe()
            assert before[0] == 'P:' + second and before[2] == 'fedramp'
            tm('rename-window', '-t', first, 'renamed')
            tm('send-keys', '-t', sidebar, 'C-r')
            time.sleep(.2)
            assert probe() == before
            tm('send-keys', '-t', sidebar, 'Escape')
            time.sleep(.3)
            identity = probe()[:2]
            geometry = display(first, '#{pane_width}|#{pane_height}')
            tm('set-option', '-g', '@tmux-canopy-density', 'compact')
            tm('send-keys', '-t', sidebar, 'C-r')
            wait(lambda: any('sleep' in line and '…/hcm-gitops' in line for line in screen()), 'compact view')
            assert probe()[:2] == identity
            tm('set-option', '-g', '@tmux-canopy-density', 'normal')
            tm('send-keys', '-t', sidebar, 'C-r')
            wait(lambda: any('…/fedramp/hcm-gitops' in line and 'sleep' not in line for line in screen()), 'normal view restored')
            assert probe()[:2] == identity
            assert display(first, '#{pane_width}|#{pane_height}') == geometry
            print('ok - path search, reload tracking, and compact/normal changes preserve the pane identity')

            # Enter from a selected two-line object must use its original token.
            tm('send-keys', '-t', sidebar, 'End')
            assert probe()[0] == 'P:' + second
            time.sleep(.15)
            tm('send-keys', '-t', sidebar, 'Enter')
            wait(lambda: display(second, '#{pane_active}') == '1', 'pane activation')
            print('ok - multiline Enter activates the correct real content pane')

            # A directory-only refresh may change row heights, but never IDs.
            identity = probe()[:2]
            geometry = display(first, '#{pane_width}|#{pane_height}')
            tm('respawn-pane', '-k', '-t', second, '-c', str(dirs[0]), 'sleep 600')
            tm('send-keys', '-t', sidebar, 'C-r')
            wait(lambda: sum('…/commercial/hcm-gitops' in line for line in screen()) == 1
                 and not any('…/fedramp/hcm-gitops' in line for line in screen()), 'shared directory grouped')
            assert probe()[:2] == identity
            rows = records()
            window = next(row for row in rows if row[0].startswith('W:'))
            assert window[1].count('\n') == 1
            assert all('\n' not in row[1] for row in rows if row[0].startswith('P:'))
            tm('send-keys', '-t', sidebar, '/')
            tm('send-keys', '-t', sidebar, '-l', 'commercial')
            wait(lambda: probe()[0] == window[0], 'shared directory search targets its window')
            tm('send-keys', '-t', sidebar, 'Escape')
            wait(lambda: sum('sleep' in line for line in screen()) == 2, 'Escape restores all grouped panes')
            assert probe()[0] == window[0], (probe(), screen())
            tm('send-keys', '-t', sidebar, 'j')
            observed = probe()
            assert observed[0] == 'P:' + first, (observed, screen())
            tm('send-keys', '-t', sidebar, 'j')
            assert probe()[0] == 'P:' + second
            tm('respawn-pane', '-k', '-t', second, '-c', str(dirs[1]), 'sleep 600')
            tm('send-keys', '-t', sidebar, 'C-r')
            wait(lambda: any('…/fedramp/hcm-gitops' in line for line in screen()), 'distinct directories restored')
            assert probe()[:2] == identity
            assert display(first, '#{pane_width}|#{pane_height}') == geometry
            print('ok - shared directories group and ungroup with stable selection, search, navigation and geometry')
        finally:
            sp.run([executable, '-L', socket, 'kill-server'], env=env, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            if attached:
                attached.wait(timeout=5)
            if master is not None:
                os.close(master)
    print('all multiline appearance tests passed')


if __name__ == '__main__':
    main()
