#!/usr/bin/env python3
"""Mouse wheel and clicks in a real sidebar, driven by SGR mouse events."""
import fcntl
import json
import os
from pathlib import Path
import pty
import socket as unix_socket
import struct
import subprocess as sp
import tempfile
import termios
import threading
import time

from support import install_fzf_probe

ROOT = Path(__file__).resolve().parents[1]
socket = f'canopy-mouse-{os.getpid()}'
env = {k: v for k, v in os.environ.items() if k not in ('TMUX', 'TMUX_PANE')}
env['TERM'] = 'xterm-256color'


def tm(*args):
    result = sp.run(['tmux', '-L', socket, *args], env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, (args, result.stderr)
    return result.stdout.strip()


def wait(predicate, message, timeout=8):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if predicate():
            return
        time.sleep(.05)
    raise AssertionError(message)


def main():
    master = client = None
    with tempfile.TemporaryDirectory(prefix='canopy-mouse-') as directory:
        temp = Path(directory)
        fzf_socket = temp / 'fzf.sock'
        script_env = dict(env)
        install_fzf_probe(temp, [], script_env, extra_options=(f'--listen={fzf_socket}',))
        try:
            first = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'one', '-x', '120', '-y', '30',
                       '-P', '-F', '#{pane_id}')
            # Long enough that the tree scrolls.
            for _ in range(24):
                tm('new-window', '-d', '-t', 'one:')
            tm('set-option', '-g', 'mouse', 'on')
            tm('set-option', '-g', 'status', 'off')
            base = script_env | {'TMUX': tm('display-message', '-p', '-t', first, '#{socket_path},#{pid},0')}
            tm('set-environment', '-g', 'PATH', script_env['PATH'])
            assert sp.run(['bash', str(ROOT / 'tmux-canopy.tmux')], env=base).returncode == 0
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 120, 0, 0))
            client = sp.Popen(['tmux', '-L', socket, 'attach', '-t', 'one'], stdin=slave, stdout=slave,
                              stderr=slave, env=base, start_new_session=True)
            os.close(slave)
            def drain():
                try:
                    while os.read(master, 65536):
                        pass
                except OSError:
                    pass
            threading.Thread(target=drain, daemon=True).start()
            wait(lambda: tm('list-clients', '-F', '#{client_name}'), 'client attached')
            os.write(master, b'\x02T')
            sidebar = ''

            def find_sidebar():
                nonlocal sidebar
                sidebar = next((row.split('|')[0] for row in tm('list-panes', '-a', '-F', '#{pane_id}|#{@tmux_canopy}').splitlines()
                                if row.endswith('|1')), '')
                return sidebar and fzf_socket.exists()
            wait(find_sidebar, 'sidebar opened')
            time.sleep(1)

            def selected():
                with unix_socket.socket(unix_socket.AF_UNIX, unix_socket.SOCK_STREAM) as connection:
                    connection.settimeout(2)
                    connection.connect(str(fzf_socket))
                    connection.sendall(b'GET / HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
                    data = b''
                    while chunk := connection.recv(65536):
                        data += chunk
                current = json.loads(data.split(b'\r\n\r\n', 1)[1])['current']
                return current['text'].split('\t')[0] if current else None

            def top_row():
                return next(line for line in tm('capture-pane', '-p', '-t', sidebar).splitlines()[1:] if line.strip())

            left = int(tm('display-message', '-p', '-t', sidebar, '#{pane_left}'))

            def mouse(code, row, release=False):
                os.write(master, f'\x1b[<{code};{left + 12};{row + 1}M'.encode())
                if release:
                    os.write(master, f'\x1b[<{code};{left + 12};{row + 1}m'.encode())

            tm('select-pane', '-t', sidebar)
            time.sleep(.5)
            mouse(0, 8, release=True)
            wait(lambda: selected() not in (None, ''), 'click selects a row')
            time.sleep(.4)
            clicked, top = selected(), top_row()

            # The wheel scrolls the view; a visible selection stays where it is.
            for code in (65, 65, 65, 64, 65, 64):
                mouse(code, 10)
                time.sleep(.08)
            wait(lambda: top_row() != top, 'wheel scrolls the view')
            time.sleep(.3)
            assert selected() == clicked, (clicked, selected())
            for _ in range(2):
                mouse(64, 10)
                time.sleep(.08)
            wait(lambda: top_row() == top, 'wheel scrolls back')
            assert selected() == clicked, (clicked, selected())
            print('ok - the mouse wheel scrolls the tree without moving the selection')
        finally:
            if client is not None:
                client.kill()
            if master is not None:
                os.close(master)
            sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)


if __name__ == '__main__':
    main()
