#!/usr/bin/env python3
"""Attached-client navigation regressions; Python is a test-only dependency."""
import os
from pathlib import Path
import pty
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import threading
import time
import fcntl


def probe(path):
    def record(*_):
        size = os.get_terminal_size()
        with open(path, 'a') as stream:
            stream.write(f'{size.columns}x{size.lines}\n')
    signal.signal(signal.SIGWINCH, record)
    record()
    while True:
        time.sleep(60)


def main():
    root = Path(__file__).resolve().parents[1]
    real_tmux = shutil.which('tmux')
    socket = f'tree-navigation-test-{os.getpid()}'
    env = os.environ.copy()
    env.pop('TMUX', None)
    env.pop('TMUX_PANE', None)
    env['TERM'] = 'xterm-256color'
    client_process = other_process = None
    master = other_master = None
    with tempfile.TemporaryDirectory(prefix='tree-navigation-') as directory:
        temp = Path(directory)
        calls = temp / 'calls'
        state = temp / 'state'
        calls.touch()
        state.touch()

        def tm(*args):
            result = subprocess.run([real_tmux, '-L', socket, *args], env=env, text=True,
                                    capture_output=True, timeout=10)
            assert result.returncode == 0, (args, result.stderr)
            return result.stdout.strip()

        def run(name, *args):
            result = subprocess.run([str(root / 'scripts' / name), *args],
                                    env=action_env, capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, (name, result.stderr)

        def current():
            for row in tm('list-clients', '-F', '#{client_tty}|#{session_id}|#{window_id}|#{pane_id}').splitlines():
                tty, session, window, pane = row.split('|')
                if tty == client:
                    return session, window, pane
            raise AssertionError('test client disappeared')

        def display(pane, field):
            return tm('display-message', '-p', '-t', pane, field)

        def activate(pane):
            run('sidebar-action', 'activate', 'P:' + pane)

        def recorded_commands():
            return [shlex.split(line) for line in calls.read_text().splitlines()]

        def fzf_pid(sidebar):
            parent = int(display(sidebar, '#{pane_pid}'))
            rows = subprocess.check_output(['ps', '-eo', 'pid=,ppid=,comm='], text=True)
            descendants = {parent}
            processes = [line.split(None, 2) for line in rows.splitlines()]
            for _ in range(10):
                descendants.update(int(pid) for pid, ppid, _ in processes if int(ppid) in descendants)
            return next(int(pid) for pid, _, command in processes if int(pid) in descendants and command == 'fzf')

        try:
            command = lambda log: shlex.join([sys.executable, str(Path(__file__).resolve()), '--probe', str(log)])
            log_a, log_b = temp / 'a.winch', temp / 'b.winch'
            tm('-f', '/dev/null', 'new-session', '-d', '-s', 'one', '-x', '160', '-y', '44', command(log_a))
            tm('set-option', '-g', 'default-shell', '/bin/bash')
            tm('set-option', '-g', 'status', 'off')
            pane_a = tm('display-message', '-p', '#{pane_id}')
            window_a = display(pane_a, '#{window_id}')
            session_a = display(pane_a, '#{session_id}')
            peer = tm('split-window', '-d', '-h', '-t', pane_a, '-P', '-F', '#{pane_id}', 'sleep 600')
            pane_b = tm('new-window', '-d', '-t', 'one:', '-P', '-F', '#{pane_id}', command(log_b))
            window_b = display(pane_b, '#{window_id}')
            pane_c = tm('new-session', '-d', '-s', 'two', '-x', '160', '-y', '44', '-P', '-F', '#{pane_id}', 'sleep 600')
            session_c = display(pane_c, '#{session_id}')
            window_c = display(pane_c, '#{window_id}')

            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 44, 160, 0, 0))
            client_process = subprocess.Popen([real_tmux, '-L', socket, 'attach-session', '-t', 'one'],
                                              stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True)
            os.close(slave)

            def drain(fd):
                try:
                    while os.read(fd, 65536):
                        pass
                except OSError:
                    pass
            threading.Thread(target=drain, args=(master,), daemon=True).start()
            time.sleep(.2)
            client = tm('list-clients', '-F', '#{client_tty}')
            tm('select-pane', '-t', pane_a)
            action_env = env.copy()
            action_env['TMUX'] = tm('display-message', '-p', '#{socket_path},#{pid},0')
            action_env.update(TMUX_CANOPY_STATE=str(state), TMUX_CANOPY_CLIENT=client,
                              TMUX_CANOPY_SCOPE='global', TMUX_CANOPY_TRANSITION='slot')
            # Instrument foreground commands only. Server hooks use their normal PATH.
            wrapper = temp / 'tmux'
            wrapper.write_text('#!/bin/bash\nprintf -v line "%q " "$@"\nprintf "%s\\n" "$line" >> ' + shlex.quote(str(calls)) +
                               '\nexec ' + shlex.join([real_tmux, '-L', socket]) + ' "$@"\n')
            wrapper.chmod(0o755)
            action_env['PATH'] = str(temp) + ':' + env['PATH']
            tm('set-option', '-g', '@tmux-canopy-scope', 'global')
            tm('set-option', '-g', '@tmux-canopy-transition', 'slot')
            tm('set-option', '-g', '@tmux-canopy-notifications', 'none')
            subprocess.run([str(root / 'tmux-canopy.tmux')], env=action_env, check=True, timeout=10)
            run('toggle', client, pane_a, '42', 'global', 'T', 'Tab', 'slot')
            sidebar = next(row.split('|')[0] for row in tm('list-panes', '-a', '-F', '#{pane_id}|#{@tmux_canopy}').splitlines() if row.endswith('|1'))
            action_env['TMUX_PANE'] = sidebar
            time.sleep(.7)
            ui_pid = fzf_pid(sidebar)

            activate(pane_a)
            calls.write_text('')
            activate(pane_a)
            commands = recorded_commands()
            assert len(commands) == 1, commands
            assert not any(word in commands[0] for word in ('set-option', 'select-pane', 'select-window', 'switch-client', 'swap-pane'))
            print('ok - already-current pane performs one read and no mutations')

            calls.write_text('')
            activate(peer)
            commands = recorded_commands()
            assert len(commands) == 2, commands
            assert current()[2] == peer
            assert display(sidebar, '#{@tmux_canopy_target}') == peer
            assert not any('select-window' in row or 'switch-client' in row or 'swap-pane' in row for row in commands)
            print('ok - same-window focus only updates target and selects pane')

            activate(pane_b)
            activate(pane_a)
            time.sleep(.15)
            before = (log_a.read_text(), log_b.read_text())
            for _ in range(4):
                run('navigate', client, 'last', '42', 'global', 'slot')
                assert display(sidebar, '#{window_id}') == current()[1]
                assert display(sidebar, '#{pane_left}') == '0'
            time.sleep(.15)
            assert before == (log_a.read_text(), log_b.read_text()), 'warm switching delivered application SIGWINCH'
            assert fzf_pid(sidebar) == ui_pid
            print('ok - warm window switches preserve sidebar/fzf identity and deliver no application SIGWINCH')

            calls.write_text('')
            run('navigate', client, 'next', '42', 'global', 'slot')
            assert current()[1] == window_b
            assert not any('switch-client' in row for row in recorded_commands())
            run('navigate', client, 'previous', '42', 'global', 'slot')
            assert current()[1] == window_a
            run('navigate', client, 'index:1', '42', 'global', 'slot')
            assert current()[1] == window_b
            run('navigate', client, 'index:9', '42', 'global', 'slot')
            assert current()[1] == window_b, 'missing numeric target changed the client'
            run('navigate', client, 'previous', '42', 'global', 'slot')
            assert current()[1] == window_a
            print('ok - next/previous/index navigation avoids redundant session switches')

            activate(pane_c)
            assert current() == (session_c, window_c, pane_c)
            assert display(sidebar, '#{window_id}') == window_c
            # A deleted hook pane must not override a live client's destination.
            run('follow', client, '%999999999', '42', 'slot')
            assert display(sidebar, '#{window_id}') == window_c
            activate(pane_a)
            assert current()[0] == session_a
            print('ok - cross-session navigation and stale/deleted hook targets use the live client')

            tm('link-window', '-s', window_a, '-t', 'two:5')
            run('sidebar-action', 'activate', f'W:{window_a}:{session_c}')
            assert current()[0:2] == (session_c, window_a), current()
            run('sidebar-action', 'activate', f'W:{window_a}:{session_a}')
            assert current()[0:2] == (session_a, window_a), current()
            print('ok - linked-window occurrences retain their destination session')

            # Width correction is batched with the destination swap.
            slot = next(row.split('|')[0] for row in tm('list-panes', '-t', window_b, '-F', '#{pane_id}|#{@tmux_canopy_slot}').splitlines() if row.endswith('|1'))
            expected_width = display(sidebar, '#{pane_width}')
            tm('resize-pane', '-t', slot, '-x', str(int(expected_width) - 4))
            activate(pane_b)
            assert display(sidebar, '#{pane_width}') == expected_width
            assert display(sidebar, '#{pane_left}') == '0'
            print('ok - navigation corrects a stale destination slot width before swapping')

            # Normal native new-window still uses the fallback follow hook.
            pane_new = tm('new-window', '-t', 'one:', '-P', '-F', '#{pane_id}', 'sleep 600')
            assert display(sidebar, '#{window_id}') == display(pane_new, '#{window_id}')
            assert fzf_pid(sidebar) == ui_pid
            assert not any('transition_' in line for line in tm('show-options', '-g').splitlines())
            print('ok - native new-window fallback follows without leaking transition guards')
            activate(pane_a)

            # A newer client in another session must not affect relative targets.
            other_master, other_slave = pty.openpty()
            fcntl.ioctl(other_slave, termios.TIOCSWINSZ, struct.pack('HHHH', 44, 160, 0, 0))
            other_process = subprocess.Popen([real_tmux, '-L', socket, 'attach-session', '-t', 'two'],
                                             stdin=other_slave, stdout=other_slave, stderr=other_slave, env=env, start_new_session=True)
            os.close(other_slave)
            threading.Thread(target=drain, args=(other_master,), daemon=True).start()
            time.sleep(.2)
            other_client = next(tty for tty in tm('list-clients', '-F', '#{client_tty}').splitlines() if tty != client)
            run('navigate', client, 'next', '42', 'global', 'slot')
            assert current()[0:2] == (session_a, window_b), current()
            run('follow', other_client, pane_c, '42', 'slot')
            assert display(sidebar, '#{window_id}') == window_b
            print('ok - relative navigation is client-specific with two attached clients')

            # An unknown owner must not borrow this client's sidebar.
            run('follow', 'not-the-owner', pane_a, '42', 'slot')
            assert display(sidebar, '#{window_id}') == window_b
            print('ok - unrelated owners cannot pull the sidebar')

            action_env['TMUX_CANOPY_SCOPE'] = 'window'
            activate(pane_a)
            assert current()[1] == window_a
            assert display(sidebar, '#{window_id}') == window_b
            action_env['TMUX_CANOPY_SCOPE'] = 'global'
            activate(pane_b)
            print('ok - window-local navigation does not move the sidebar')

            run('toggle', client, pane_b, '42', 'global', 'T', 'Tab', 'slot')
            time.sleep(.5)
            activate(pane_a)
            assert current()[1] == window_a
            assert '1' not in tm('list-panes', '-a', '-F', '#{@tmux_canopy}').splitlines()
            print('ok - navigation still works with the sidebar closed')
        finally:
            subprocess.run([real_tmux, '-L', socket, 'kill-server'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for process in (client_process, other_process):
                if process:
                    process.wait(timeout=5)
            for fd in (master, other_master):
                if fd is not None:
                    os.close(fd)
    print('all attached navigation tests passed')


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--probe':
        probe(sys.argv[2])
    else:
        main()
