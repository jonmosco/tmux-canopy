#!/usr/bin/env python3
"""Read-only captures, real fzf clipping/toggling, and the native popup."""
import fcntl
from support import install_fzf_probe
import os
from pathlib import Path
import pty
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
    socket = f'tree-preview-test-{os.getpid()}'
    executable = shutil.which('tmux')
    env = os.environ.copy()
    for name in ('TMUX', 'TMUX_PANE', 'FZF_DEFAULT_OPTS', 'FZF_DEFAULT_OPTS_FILE', 'TMUX_CANOPY_PREVIEW_EXPANDED'):
        env.pop(name, None)
    env['TERM'] = 'xterm-256color'
    master = None
    client_process = None
    with tempfile.TemporaryDirectory(prefix='tree-preview-') as directory:
        temp = Path(directory)
        signals, selected, state = (temp / name for name in ('signals', 'selected', 'state'))
        for path in (signals, state):
            path.touch()

        def tm(*args):
            result = sp.run([executable, '-L', socket, *args], env=env, text=True, capture_output=True, timeout=10)
            assert result.returncode == 0, (args, result.stderr)
            return result.stdout.rstrip('\n')

        def display(pane, fmt):
            return tm('display-message', '-p', '-t', pane, fmt)

        def wait(predicate, message):
            end = time.monotonic() + 8
            while time.monotonic() < end:
                if predicate():
                    return
                time.sleep(.04)
            raise AssertionError(message)

        def run(script, *args, extra=None):
            result = sp.run([str(ROOT / 'scripts' / script), *args], env=script_env | (extra or {}),
                            text=True, capture_output=True, timeout=15)
            assert result.returncode == 0, (script, result.stderr)
            return result.stdout

        def capture():
            return tm('capture-pane', '-p', '-t', sidebar)

        def probe():
            selected.unlink(missing_ok=True)
            tm('send-keys', '-t', sidebar, 'M-z')
            wait(lambda: selected.exists() and selected.stat().st_size, 'selection probe')
            return selected.read_text()

        def descendants():
            rows = [line.split(None, 2) for line in sp.check_output(['ps', '-eo', 'pid=,ppid=,comm='], text=True).splitlines()]
            pids = {server_pid}
            for _ in range(12):
                pids.update(int(pid) for pid, parent, _ in rows if int(parent) in pids)
            return {(int(pid), command) for pid, _, command in rows if int(pid) in pids}

        fixture = temp / 'terminal.py'
        fixture.write_text('''import os, signal, sys, tty
signal.signal(signal.SIGWINCH, lambda *_: open(sys.argv[1], 'a').write('resize\\n'))
tty.setraw(0)
def draw(key):
    width, height = os.get_terminal_size()
    if key == b't':
        out = '\\033[?1049h\\033[2J'
        for row in range(height):
            text = 'TUI%02d | columns aligned | ' % row
            out += '\\033[%d;1H' % (row + 1) + text.ljust(width - 10, '-') + 'RIGHTEND'
        out += '\\033[%d;1H' % (height // 2)
    else:
        out = '\\033[?1049l\\033[2J\\033[H'
        for row in range(80):
            text = 'ROW%03d 界🙂 | ' % row
            out += '\\033[31m' + text.ljust(width - 15, '-') + 'RIGHTEND\\033[0m\\r\\n'
        out += 'DONE'
    os.write(1, out.encode())
draw(b'n')
while True:
    key = os.read(0, 1)
    if key in (b'n', b't'): draw(key)
''')
        try:
            pane = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'preview', '-x', '160', '-y', '44',
                      '-P', '-F', '#{pane_id}', shlex.join(['python3', str(fixture), str(signals)]))
            server_pid = int(display(pane, '#{pid}'))
            tm('set-option', '-g', 'status', 'off')
            tm('set-option', '-g', 'default-shell', '/bin/bash')
            for option, value in [('scope', 'global'), ('transition', 'slot'), ('theme', 'mono'), ('preview', 'off')]:
                tm('set-option', '-g', '@tmux-canopy-' + option, value)
            script_env = env | {'TMUX': display(pane, '#{socket_path},#{pid},0'), 'TMUX_PANE': pane,
                                'TMUX_CANOPY_STATE': str(state), 'FZF_PREVIEW_LINES': '12', 'FZF_PREVIEW_COLUMNS': '40'}
            bindings = ['alt-t:pos(3)', 'alt-w:pos(2)',
                        f"alt-z:execute-silent(printf '%s|%s\\n' {{1}} {{q}} > {selected})"]
            install_fzf_probe(temp, bindings, script_env)
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 44, 160, 0, 0))
            client = os.ttyname(slave)
            client_process = sp.Popen([executable, '-L', socket, 'attach-session', '-t', 'preview'],
                                     stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True)
            os.close(slave)

            terminal_output = bytearray()
            def drain():
                try:
                    while data := os.read(master, 65536):
                        terminal_output.extend(data)
                        if len(terminal_output) > 2_000_000:
                            del terminal_output[:1_000_000]
                except OSError:
                    pass
            threading.Thread(target=drain, daemon=True).start()
            wait(lambda: client in tm('list-clients', '-F', '#{client_tty}'), 'client attach')
            script_env['TMUX_CANOPY_CLIENT'] = client
            run('toggle', client, pane, '42', 'global', 'T', 'Tab', 'slot')
            sidebar = next(row.split('|')[0] for row in tm('list-panes', '-a', '-F', '#{pane_id}|#{@tmux_canopy}').splitlines() if row.endswith('|1'))
            script_env['TMUX_PANE'] = sidebar
            wait(lambda: any(command == 'fzf' for _, command in descendants()), 'fzf running')
            time.sleep(.2)
            tm('send-keys', '-t', pane, '-l', 'n')
            wait(lambda: 'DONE' in tm('capture-pane', '-p', '-t', pane), 'normal screen drawn')
            time.sleep(.1)
            geometry = display(pane, '#{pane_width}|#{pane_height}')
            signal_count = signals.read_text()
            fzf_pids = {pid for pid, command in descendants() if command == 'fzf'}
            normal = run('sidebar-preview', 'P:' + pane)
            assert len(normal.splitlines()) <= 12 and 'ROW079' in normal and 'DONE' in normal
            assert '[recent crop]' in normal and '\x1b[' in normal and '界🙂' in normal
            for rows in ('1', '2', '3', '6'):
                assert len(run('sidebar-preview', 'P:' + pane, extra={'FZF_PREVIEW_LINES': rows}).splitlines()) <= int(rows)
            for token in ('Q:' + pane, f'X:{server_pid}:{pane}'):
                assert len(run('sidebar-preview', token).splitlines()) <= 12
            assert 'no longer available' in run('sidebar-preview', 'P:%999999')
            print('ok - compact row budgets, latest shell output, color/Unicode, and missing panes')
            tm('set-option', '-g', '@tmux_canopy_notifications', 'all')
            for provider in ('activity', 'bell', 'silence'):
                tm('set-option', '-p', '-t', pane, '@tmux_canopy_notice_pane_' + provider, '1')
            for rows in ('1', '2', '3', '6', '12'):
                flagged = run('sidebar-preview', 'P:' + pane, extra={'FZF_PREVIEW_LINES': rows})
                assert flagged.startswith('Unread: activity, bell, silence\n'), flagged
                assert len(flagged.splitlines()) <= int(rows)
            window = display(pane, '#{window_id}')
            session = display(pane, '#{session_id}')
            for provider in ('activity', 'bell', 'silence'):
                tm('set-option', '-w', '-t', window, '@tmux_canopy_notice_' + provider, '1')
            for token in ('W:' + window, 'S:' + session):
                assert 'unread: activity bell silence' in run('sidebar-preview', token)
            tm('set-option', '-g', '@tmux_canopy_notifications', 'none')
            for token in ('P:' + pane, 'W:' + window, 'S:' + session):
                assert 'unread:' not in run('sidebar-preview', token).lower()
            tm('set-option', '-g', '@tmux_canopy_notifications', 'all')
            for provider in ('activity', 'bell', 'silence'):
                tm('set-option', '-wu', '-t', window, '@tmux_canopy_notice_' + provider)
                tm('set-option', '-pu', '-t', pane, '@tmux_canopy_notice_pane_' + provider)
            print('ok - preview lists all notification types without exceeding its row budget')


            tm('send-keys', '-t', sidebar, 'M-t')
            before = probe()
            assert before.startswith('P:' + pane + '|')
            assert ' Preview ' not in capture()
            tm('send-keys', '-t', sidebar, 'p')
            wait(lambda: 'ROW079' in capture(), 'drawer shown')
            assert 'RIGHTEND' not in capture(), capture()
            assert '界🙂' in capture()
            border = next(i for i, line in enumerate(capture().splitlines()) if ' Preview ' in line)
            tm('send-keys', '-t', sidebar, 'M-w')
            wait(lambda: 'Window: preview' in capture(), 'window preview')
            assert border == next(i for i, line in enumerate(capture().splitlines()) if ' Preview ' in line)
            tm('send-keys', '-t', sidebar, 'M-t')
            wait(lambda: 'ROW079' in capture(), 'pane preview restored')
            for _ in range(2):
                tm('send-keys', '-t', sidebar, 'p')
                wait(lambda: ' Preview ' not in capture(), 'drawer hidden')
                tm('send-keys', '-t', sidebar, 'p')
                wait(lambda: 'ROW079' in capture(), 'drawer reshown')
            assert probe() == before
            tm('send-keys', '-t', sidebar, 'i')
            wait(lambda: 'No Codex or Claude process found' in capture(), 'agent drawer shown')
            assert probe() == before
            tm('send-keys', '-t', sidebar, 'i')
            wait(lambda: 'ROW079' in capture(), 'terminal drawer restored')
            assert probe() == before
            print('ok - real fzf clips wide rows, keeps drawer height steady, and toggles with p and i')

            tm('send-keys', '-t', pane, '-l', 't')
            wait(lambda: display(pane, '#{alternate_on}') == '1', 'alternate screen')
            tui = run('sidebar-preview', 'P:' + pane)
            assert '[screen crop]' in tui and 'TUI' in tui and 'ROW' not in tui
            assert len(tui.splitlines()) <= 12
            expanded = run('sidebar-preview', 'P:' + pane, extra={'TMUX_CANOPY_PREVIEW_EXPANDED': '1'})
            assert 'TUI00' in expanded and f'TUI{int(geometry.split("|")[1]) - 1:02d}' in expanded
            assert 'ROW' not in expanded
            print('ok - TUI captures use only the active screen; enlarged snapshots include all screen rows')

            tm('send-keys', '-t', sidebar, 'P')
            wait(lambda: any(command == 'less' for _, command in descendants()), 'enlarged native popup')
            os.write(master, b'q')
            wait(lambda: not any(command == 'less' for _, command in descendants()), 'popup closed')
            time.sleep(.15)
            assert probe() == before
            # A hostile buffer name must remain data, including in the popup.
            sentinel = temp / 'must-not-exist'
            name = "odd'$(touch " + str(sentinel) + ")"
            tm('set-buffer', '-b', name, 'safe buffer content')
            popup = sp.Popen([str(ROOT / 'scripts/preview-popup'), 'B:' + name], env=script_env,
                             stdout=sp.DEVNULL, stderr=sp.PIPE)
            wait(lambda: any(command == 'less' for _, command in descendants()), 'buffer popup')
            os.write(master, b'q')
            popup.communicate(timeout=10)
            assert popup.returncode == 0 and not sentinel.exists()
            assert display(pane, '#{pane_width}|#{pane_height}') == geometry
            assert signals.read_text() == signal_count
            assert {pid for pid, command in descendants() if command == 'fzf'} == fzf_pids
            print('ok - Shift-p popup, safe buffer names, selection/fzf identity, and zero application SIGWINCH')

            # Help is an overlay: the sidebar must keep its current display
            # throughout, rather than handing its terminal over to the helper.
            dock_geometry = display(sidebar, '#{pane_left}|#{pane_top}|#{pane_width}|#{pane_height}')
            sidebar_screen = capture()
            terminal_output.clear()
            tm('send-keys', '-t', sidebar, '?')
            wait(lambda: b'SIDEBAR HELP' in terminal_output, 'help popup opens')
            assert capture() == sidebar_screen, 'Help replaced the sidebar display'
            assert display(sidebar, '#{pane_left}|#{pane_top}|#{pane_width}|#{pane_height}') == dock_geometry
            assert display(pane, '#{pane_width}|#{pane_height}') == geometry
            terminal_output.clear()
            os.write(master, b'G')
            wait(lambda: b'Retained' in terminal_output, 'help scrolls to the last section')
            os.write(master, b'q')
            assert probe() == before
            assert capture() == sidebar_screen, 'Help changed the sidebar display on exit'
            assert display(sidebar, '#{pane_left}|#{pane_top}|#{pane_width}|#{pane_height}') == dock_geometry
            assert signals.read_text() == signal_count
            assert {pid for pid, command in descendants() if command == 'fzf'} == fzf_pids
            print('ok - readable scrollable Help preserves selection, fzf, pane sizes and application SIGWINCH count')

            terminal_output.clear()
            tm('send-keys', '-t', sidebar, 'g')
            wait(lambda: b'SIDEBAR LEGEND' in terminal_output, 'legend popup opens')
            assert capture() == sidebar_screen, 'Legend replaced the sidebar display'
            assert display(sidebar, '#{pane_left}|#{pane_top}|#{pane_width}|#{pane_height}') == dock_geometry
            os.write(master, b'q')
            assert probe() == before
            assert capture() == sidebar_screen, 'Legend changed the sidebar display on exit'
            assert {pid for pid, command in descendants() if command == 'fzf'} == fzf_pids
            print('ok - Legend opens with g and preserves the sidebar and pane geometry')

            # Exercise the actual prefix binding with the same persistent fzf.
            for _ in range(3):
                tm('split-window', '-d', '-v', '-l', '6', '-t', pane, 'sleep 600')
            sp.run([str(ROOT / 'tmux-canopy.tmux')], env=script_env, check=True, timeout=15)
            tm('set-option', '-g', 'prefix', 'C-a')
            dock_geometry = display(sidebar, '#{pane_left}|#{pane_top}|#{pane_width}|#{pane_height}')
            seen = set()
            for index in range(7):
                os.write(master, b'\x01 ')
                wait(lambda: display(pane, '#{@tmux_canopy_content_layout}') not in seen, 'Ctrl-a Space changes content layout')
                seen.add(display(pane, '#{@tmux_canopy_content_layout}'))
                assert display(sidebar, '#{pane_left}|#{pane_top}|#{pane_width}|#{pane_height}') == dock_geometry
                assert display(sidebar, '#{pane_active}') == '1'
            assert len(seen) == 7
            assert {pid for pid, command in descendants() if command == 'fzf'} == fzf_pids
            assert probe() == before
            print('ok - real Ctrl-a Space cycles seven content layouts without moving/restarting the sidebar')

            tm('send-keys', '-t', sidebar, '4')
            wait(lambda: '[4 Agents]' in capture(), 'Agents view header')
            wait(lambda: 'No Codex or Claude agents detected' in capture(), 'Agents empty view')
            assert {pid for pid, command in descendants() if command == 'fzf'} == fzf_pids
            tm('send-keys', '-t', sidebar, '1')
            wait(lambda: '[1 Tree]' in capture(), 'Tree view restored')
            assert {pid for pid, command in descendants() if command == 'fzf'} == fzf_pids
            print('ok - 4 opens Agents view and 1 returns to Tree in the same fzf process')
        finally:
            sp.run([executable, '-L', socket, 'kill-server'], env=env, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            if client_process:
                client_process.wait(timeout=5)
            if master is not None:
                os.close(master)
    print('all preview tests passed')


if __name__ == '__main__':
    main()
