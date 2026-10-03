#!/usr/bin/env python3
"""Popup mode behavior: ephemeral display-popup, auto-detection, and state caching."""
import fcntl
import os
from pathlib import Path
import pty
import shutil
import signal
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
    socket = f'canopy-popup-test-{os.getpid()}'
    env = {k: v for k, v in os.environ.items() if k not in ('TMUX', 'TMUX_PANE')}
    env['TERM'] = 'xterm-256color'
    master = process = None
    with tempfile.TemporaryDirectory(prefix='canopy-popup-test-', ignore_cleanup_errors=True) as directory:
        temp = Path(directory)
        started, loads = temp / 'started', temp / 'loads'

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
            raise AssertionError((description,
                                  tm('list-clients', '-F', '#{client_tty}|#{session_id}|#{pane_id}'),
                                  tm('list-panes', '-a', '-F', '#{session_id}|#{window_id}|#{pane_id}|#{pane_active}|#{@tmux_canopy}')))

        def display(pane, fmt):
            return tm('display-message', '-p', '-t', pane, fmt)

        def run(name, *args):
            result = sp.run([str(ROOT / 'scripts' / name), *args], env=script_env,
                            capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, (name, result.stderr)
            return result.stdout

        try:
            first = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'test', '-x', '120', '-y', '30',
                       '-P', '-F', '#{pane_id}', 'sleep 600')
            tm('new-window', '-d', '-t', 'test:', '-n', 'second', 'sleep 600')
            tm('set-option', '-g', 'default-shell', '/bin/bash')
            tm('set-option', '-g', 'status', 'off')
            tm('set-option', '-g', '@tmux-canopy-mode', 'popup')

            script_env = env | {'TMUX': display(first, '#{socket_path},#{pid},0'), 'TMUX_PANE': first}
            install_fzf_probe(temp, [
                f'start:execute-silent(touch {started})',
                f'load:+execute-silent(printf x >> {loads})'], script_env)

            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 120, 0, 0))
            client = os.ttyname(slave)
            process = sp.Popen([executable, '-L', socket, 'attach-session', '-t', 'test'], env=env,
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

            def toggle():
                tm('run-shell', '-b', f'{ROOT}/scripts/toggle "{client}" "{first}" 42 global T Tab slot')

            def is_popup_active():
                return any(line.startswith('@tmux_canopy_popup_') and line.endswith('1')
                           for line in tm('show-options', '-g').splitlines())

            # 1. Opening with mode=popup launches display-popup without splitting panes
            initial_panes = tm('list-panes', '-t', 'test:0', '-F', '#{pane_id}').splitlines()
            assert len(initial_panes) == 1, 'only one content pane initially'

            toggle()
            wait(is_popup_active, 'popup opened and active')
            panes_during_popup = tm('list-panes', '-t', 'test:0', '-F', '#{pane_id}').splitlines()
            assert len(panes_during_popup) == 1, 'no sidebar split pane created in popup mode'
            print('ok - popup mode opens via display-popup without altering window pane splits')

            # 2. Re-toggling while popup is active closes the popup
            toggle()
            wait(lambda: not is_popup_active(), 'popup closed by re-toggle')
            print('ok - re-toggle closes active popup via display-popup -C')

            # 3. Pressing 'q' inside popup closes it cleanly
            started.unlink(missing_ok=True)
            toggle()
            wait(is_popup_active, 'popup opened again')
            time.sleep(.3)
            os.write(master, b'q')
            wait(lambda: not is_popup_active(), 'popup closed via q')
            print('ok - pressing q inside popup exits and closes the popup')

            # 4. Pressing Enter inside popup activates target and closes popup
            started.unlink(missing_ok=True)
            toggle()
            wait(is_popup_active, 'popup opened for enter test')
            time.sleep(.3)
            os.write(master, b'\r')
            wait(lambda: not is_popup_active(), 'popup closed via Enter')
            print('ok - pressing Enter inside popup activates target and closes the popup')

            # 5. Adaptive auto mode threshold
            tm('set-option', '-g', '@tmux-canopy-mode', 'auto')
            tm('set-option', '-g', '@tmux-canopy-popup-threshold', '100')

            # Narrow terminal (80 cols < 100 threshold) -> opens as popup
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 80, 0, 0))
            os.kill(process.pid, signal.SIGWINCH)
            wait(lambda: display(first, '#{window_width}') == '80', 'terminal resized to 80')
            toggle()
            wait(is_popup_active, 'narrow window uses popup in auto mode')
            assert len(tm('list-panes', '-t', 'test:0', '-F', '#{pane_id}').splitlines()) == 1
            os.write(master, b'q')
            wait(lambda: not is_popup_active(), 'narrow popup closed')
            print('ok - auto mode selects popup when terminal width is below threshold')

            # Wide terminal (120 cols >= 100 threshold) -> opens as sidebar split pane
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 120, 0, 0))
            os.kill(process.pid, signal.SIGWINCH)
            wait(lambda: display(first, '#{window_width}') == '120', 'terminal resized to 120')
            toggle()
            wait(lambda: len(tm('list-panes', '-t', 'test:0', '-F', '#{pane_id}').splitlines()) == 2, 'wide window opens split sidebar')
            assert not is_popup_active(), 'no popup in wide auto mode'
            print('ok - auto mode selects sidebar when terminal width meets threshold')

            # Close the sidebar pane
            toggle()
            wait(lambda: len(tm('list-panes', '-t', 'test:0', '-F', '#{pane_id}').splitlines()) == 1, 'sidebar closed')

        finally:
            if master:
                os.close(master)
            if process:
                process.terminate()
            sp.run([executable, '-L', socket, 'kill-server'], env=env, capture_output=True)


if __name__ == '__main__':
    main()
