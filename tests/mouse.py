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
            # Long enough that the tree scrolls, even with one row per
            # single-pane window.
            for _ in range(48):
                tm('new-window', '-d', '-t', 'one:')
            tm('set-option', '-g', 'mouse', 'on')
            # Every new shell's prompt is activity, and each alert reloads the
            # sidebar, which drops wheel input mid-reload. This test is about
            # the mouse, so keep notifications out of it.
            tm('set-option', '-g', '@tmux-canopy-notifications', 'none')
            tm('set-option', '-g', 'status', 'off')
            base = script_env | {'TMUX': tm('display-message', '-p', '-t', first, '#{socket_path},#{pid},0')}
            tm('set-environment', '-g', 'PATH', script_env['PATH'])
            assert sp.run(['bash', str(ROOT / 'tmux-canopy.tmux')], env=base).returncode == 0
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 120, 0, 0))
            client = sp.Popen(['tmux', '-L', socket, 'attach', '-t', 'one'], stdin=slave, stdout=slave,
                              stderr=slave, env=base, start_new_session=True)
            os.close(slave)
            output = bytearray()

            def drain():
                try:
                    while data := os.read(master, 65536):
                        output.extend(data)
                        del output[:-65536]
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
                return next((line for line in tm('capture-pane', '-p', '-t', sidebar).splitlines()[1:] if line.strip()), '')

            left = int(tm('display-message', '-p', '-t', sidebar, '#{pane_left}'))

            def mouse(code, row, release=False):
                os.write(master, f'\x1b[<{code};{left + 12};{row + 1}M'.encode())
                if release:
                    os.write(master, f'\x1b[<{code};{left + 12};{row + 1}m'.encode())

            tm('select-pane', '-t', sidebar)
            # Focusing the sidebar moves the pointer in the background; a
            # click must come after that lands, or the jump can undo it.
            def settled():
                first_seen = selected()
                time.sleep(.6)
                return first_seen not in (None, '') and selected() == first_seen
            wait(settled, 'pointer settles after focus')
            start = selected()
            mouse(0, 8, release=True)
            wait(lambda: selected() not in (None, '', start), 'click selects a row')
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

            def post(action):
                with unix_socket.socket(unix_socket.AF_UNIX, unix_socket.SOCK_STREAM) as connection:
                    connection.settimeout(2)
                    connection.connect(str(fzf_socket))
                    connection.sendall(f'POST / HTTP/1.1\r\nHost: localhost\r\nContent-Length: {len(action)}\r\n'
                                       f'Connection: close\r\n\r\n{action}'.encode())
                    connection.recv(65536)

            # Leaving the sidebar moves the pointer to the live content row.
            tm('select-pane', '-t', first)
            wait(lambda: selected() != clicked, 'pointer follows content focus')
            time.sleep(.5)
            live = selected()
            # Clicking a row from outside is an explicit choice: it enters the
            # sidebar and keeps the clicked row instead of jumping to the live one.
            for row in (12, 6, 14, 9, 16):
                tm('select-pane', '-t', first)
                wait(lambda: selected() == live, 'pointer returns to the live row')
                time.sleep(.3)
                mouse(0, row, release=True)
                wait(lambda: tm('display-message', '-p', '#{pane_id}') == sidebar, 'click focuses the sidebar')
                wait(lambda: selected() != live, 'click selects the clicked row')
                chosen = selected()
                time.sleep(.8)
                assert selected() == chosen, (row, chosen, selected())
            print('ok - clicking a row from another pane keeps the clicked row')

            # Keyboard entry still lands on the live content row.
            tm('select-pane', '-t', first)
            wait(lambda: selected() == live, 'pointer returns to the live row')
            time.sleep(.3)
            post('down+down+down')
            wait(lambda: selected() != live, 'pointer moved away')
            tm('select-pane', '-t', sidebar)
            wait(lambda: selected() == live, 'keyboard entry jumps to the live row')
            print('ok - entering the sidebar from the keyboard selects the live row')

            # fzf pauses its screen when a command keeps it waiting over a
            # second, and resuming leaves mouse tracking off and the tty
            # echoing the keys Canopy sends the sidebar. A prompt waits on the
            # user, so it must not keep fzf waiting.
            tm('set-option', '-g', 'status-keys', 'emacs')
            tm('set-option', '-g', 'escape-time', '10')
            # Rename needs a session or window row; a pane row has no prompt.
            # Entering the sidebar moved the pointer in the background: let
            # that land before choosing the row.
            wait(lambda: selected() == live, 'pointer settles on the live row')
            time.sleep(1)
            post('first')
            wait(lambda: (selected() or '').startswith('S:'), 'session row selected')
            time.sleep(.5)
            assert (selected() or '').startswith('S:'), selected()
            output.clear()
            os.write(master, b'r')
            wait(lambda: b'Rename ' in output, 'rename prompt opens')
            time.sleep(1.5)
            tm('send-keys', '-t', sidebar, 'C-t')
            time.sleep(.3)
            os.write(master, b'\x1b')
            time.sleep(1)
            assert tm('display-message', '-p', '-t', sidebar, '#{mouse_any_flag}') == '1', 'mouse tracking survives a prompt'
            assert '^T' not in tm('capture-pane', '-p', '-t', sidebar), 'keys sent during a prompt are not echoed'
            top = top_row()
            for _ in range(3):
                mouse(65, 10)
                time.sleep(.08)
            wait(lambda: top_row() != top, 'wheel scrolls after a prompt')
            print('ok - a prompt from the sidebar leaves the mouse working and echoes nothing')
        finally:
            if client is not None:
                client.kill()
            if master is not None:
                os.close(master)
            sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)


if __name__ == '__main__':
    main()
