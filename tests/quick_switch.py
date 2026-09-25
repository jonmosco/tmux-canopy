#!/usr/bin/env python3
"""Real popup navigation, independent of tree folds, query and pending operations."""
import fcntl
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
from support import install_fzf_probe

ROOT = Path(__file__).resolve().parents[1]


def main():
    executable = shutil.which('tmux')
    socket = f'canopy-switch-test-{os.getpid()}'
    env = {k: v for k, v in os.environ.items() if k not in ('TMUX', 'TMUX_PANE')}
    env['TERM'] = 'xterm-256color'
    master = process = None
    with tempfile.TemporaryDirectory(prefix='canopy-switch-test-') as directory:
        temp = Path(directory)
        selected, state_path, started = (temp / name for name in ('selected', 'state-path', 'started'))

        def tm(*args):
            result = sp.run([executable, '-L', socket, *args], env=env, capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, (args, result.stderr)
            return result.stdout.strip()

        def wait(predicate, description):
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                if predicate():
                    return
                time.sleep(.04)
            raise AssertionError(description)

        def display(pane, fmt):
            return tm('display-message', '-p', '-t', pane, fmt)

        def probe(popup=False):
            selected.unlink(missing_ok=True)
            if popup:
                os.write(master, b'\x1bz')
            else:
                tm('send-keys', '-t', sidebar, 'M-z')
            wait(lambda: selected.exists() and selected.stat().st_size, 'selection probe')
            return selected.read_text().split('|')

        def open_switch():
            started.unlink(missing_ok=True)
            tm('send-keys', '-t', sidebar, 'C-g')
            wait(lambda: started.exists(), 'Ctrl-g opens popup fzf')
            time.sleep(.15)

        def run(name, *args):
            result = sp.run([str(ROOT / 'scripts' / name), *args], env=script_env,
                            capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, (name, result.stderr)
            return result.stdout

        try:
            first = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'one', '-x', '160', '-y', '44',
                       '-P', '-F', '#{pane_id}', 'sleep 600')
            target = tm('new-window', '-d', '-t', 'one:', '-n', 'agent-target', '-P', '-F', '#{pane_id}', 'sleep 600')
            target_window = display(target, '#{window_id}')
            second = tm('new-session', '-d', '-s', 'two', '-x', '160', '-y', '44', '-P', '-F', '#{pane_id}', 'sleep 600')
            sid = display(second, '#{session_id}')
            tm('link-window', '-s', target_window, '-t', 'two:5')
            tm('set-option', '-g', 'default-shell', '/bin/bash')
            tm('set-option', '-g', 'status', 'off')
            for key, value in [('scope', 'global'), ('transition', 'slot'), ('preview', 'off'), ('theme', 'mono'),
                               ('compact-single-panes', 'on'), ('notifications', 'none')]:
                tm('set-option', '-g', '@tmux-canopy-' + key, value)
            script_env = env | {'TMUX': display(first, '#{socket_path},#{pid},0'), 'TMUX_PANE': first}
            install_fzf_probe(temp, [
                f"alt-z:execute-silent(printf '%s|%s|%s' {{1}} {{3}} {{q}} > {selected})",
                f'''alt-y:execute-silent(printf '%s' "$TMUX_CANOPY_STATE" > {state_path})''',
                f'start:execute-silent(touch {started})'], script_env)
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 44, 160, 0, 0))
            client = os.ttyname(slave)
            process = sp.Popen([executable, '-L', socket, 'attach-session', '-t', 'one'], env=env,
                               stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
            os.close(slave)

            def drain():
                try:
                    while os.read(master, 65536):
                        pass
                except OSError:
                    pass
            threading.Thread(target=drain, daemon=True).start()
            wait(lambda: client in tm('list-clients', '-F', '#{client_tty}'), 'attached client')
            script_env['TMUX_CANOPY_CLIENT'] = client
            sp.run([str(ROOT / 'tmux-canopy.tmux')], env=script_env, check=True, timeout=15)
            run('toggle', client, first, '42', 'global', 'T', 'Tab', 'slot')
            sidebar = next(row.split('|')[0] for row in tm('list-panes', '-a', '-F', '#{pane_id}|#{@tmux_canopy}').splitlines() if row.endswith('|1'))
            script_env['TMUX_PANE'] = sidebar
            wait(lambda: started.exists(), 'sidebar loaded')
            time.sleep(.3)
            tm('send-keys', '-t', sidebar, 'M-y')
            wait(lambda: state_path.exists() and state_path.stat().st_size, 'live state location')
            state = Path(state_path.read_text())
            script_env['TMUX_CANOPY_STATE'] = str(state)
            sidebar_pid = display(sidebar, '#{pane_pid}')
            ui_pid = sp.check_output(['pgrep', '-P', sidebar_pid, '-x', 'fzf'], text=True).strip()
            tm('send-keys', '-t', sidebar, 'H')
            time.sleep(.2)
            tm('send-keys', '-t', sidebar, '/')
            tm('send-keys', '-t', sidebar, '-l', 'one')
            time.sleep(.2)
            before = probe()
            folds = state.read_bytes()
            geometry = tm('list-panes', '-a', '-F', '#{pane_id}|#{window_id}|#{pane_width}|#{pane_height}')
            open_switch()
            os.write(master, b'two:5 sleep')
            wait(lambda: probe(True)[1] == f'P:{target}:{sid}', 'collapsed linked pane found')
            os.write(master, b'\x1b')
            time.sleep(.7)
            assert probe() == before
            assert state.read_bytes() == folds
            assert tm('list-panes', '-a', '-F', '#{pane_id}|#{window_id}|#{pane_width}|#{pane_height}') == geometry
            print('ok - Ctrl-g searches collapsed panes in compact mode; cancel preserves query, selection, folds and geometry')

            # Pending move/link state must never turn quick-switch into a mutation.
            state.write_bytes(folds + f'MOVE\tP:{first}\nLINK\tW:{target_window}:{sid}\n'.encode())
            saved = state.read_bytes()
            first_window = display(first, '#{window_id}')
            open_switch()
            os.write(master, b'two:5 sleep')
            wait(lambda: probe(True)[1] == f'P:{target}:{sid}', 'linked target selected')
            os.write(master, b'\r')
            wait(lambda: tm('list-clients', '-F', '#{session_id}|#{pane_id}') == f'{sid}|{target}', 'correct linked occurrence focused')
            assert display(first, '#{window_id}') == first_window
            assert state.read_bytes() == saved
            assert sp.check_output(['pgrep', '-P', sidebar_pid, '-x', 'fzf'], text=True).strip() == ui_pid
            assert probe() == before
            print('ok - Enter targets the linked session after closing popup, bypasses pending move/link, and retains the sidebar/fzf')

            # Stale inventory must not redirect to an unrelated active object.
            stale = tm('new-window', '-d', '-t', 'two:', '-n', 'ephemeral-target', '-P', '-F', '#{pane_id}', 'sleep 600')
            open_switch()
            os.write(master, b'ephemeral-target sleep')
            wait(lambda: probe(True)[0] == f'P:{stale}', 'stale candidate selected')
            tm('kill-pane', '-t', stale)
            os.write(master, b'\r')
            time.sleep(.6)
            assert tm('list-clients', '-F', '#{session_id}|#{pane_id}') == f'{sid}|{target}'
            assert state.read_bytes() == saved
            print('ok - deleted popup targets do not change focus or consume pending operations')
        finally:
            sp.run([executable, '-L', socket, 'kill-server'], env=env, capture_output=True)
            if process is not None:
                process.wait(timeout=10)
            if master is not None:
                os.close(master)


if __name__ == '__main__':
    main()
