#!/usr/bin/env python3
"""A sidebar whose terminal is gone closes when a terminal attaches, even when
Canopy missed the detach. Sidebars of attached terminals, and old ones with no
recorded owner, stay."""
import fcntl
import os
from pathlib import Path
import pty
import shutil
import struct
import subprocess as sp
import termios
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
socket = f'canopy-orphans-{os.getpid()}'
env = {k: v for k, v in os.environ.items() if k not in ('TMUX', 'TMUX_PANE')}
env['TERM'] = 'xterm-256color'


def tm(*args):
    result = sp.run(['tmux', '-L', socket, *args], env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, (args, result.stderr)
    return result.stdout.strip()


def wait(condition, message, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(.05)
    raise AssertionError(message)


def panes():
    return set(tm('list-panes', '-a', '-F', '#{pane_id}').split())


def fake_sidebar(owner):
    """A pane that identifies itself as a sidebar owned by owner."""
    pane = tm('split-window', '-d', '-h', '-t', 'one:', '-P', '-F', '#{pane_id}', 'sleep 600')
    tm('set-option', '-p', '-t', pane, '@tmux_canopy_client', owner)
    tm('set-option', '-p', '-t', pane, '@tmux_canopy', '1')
    return pane


clients = []
try:
    tm('-f', '/dev/null', 'new-session', '-d', '-s', 'one', '-x', '160', '-y', '40', 'sleep 600')
    base = env | {'TMUX': tm('display-message', '-p', '#{socket_path},#{pid},0')}
    assert sp.run(['bash', str(ROOT / 'tmux-canopy.tmux')], env=base).returncode == 0

    def attach():
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 40, 160, 0, 0))
        client = sp.Popen([shutil.which('tmux'), '-L', socket, 'attach', '-t', 'one'], stdin=slave, stdout=slave,
                          stderr=slave, env=base, start_new_session=True)
        os.close(slave)

        def drain():
            try:
                while os.read(master, 65536):
                    pass
            except OSError:
                pass
        threading.Thread(target=drain, daemon=True).start()
        clients.append((client, master))
        before = len(clients)
        wait(lambda: len(tm('list-clients', '-F', '#{client_tty}').split()) >= before, 'client attached')
        return tm('list-clients', '-F', '#{client_tty}').split()[-1]

    live_owner = attach()
    orphan = fake_sidebar('/dev/ttys-gone')
    owned = fake_sidebar(live_owner)
    unowned = fake_sidebar('')
    attach()
    wait(lambda: orphan not in panes(), 'a terminal attaching closes the orphan')
    time.sleep(.5)
    assert {owned, unowned} <= panes(), (owned, unowned, panes())
    print('ok - a terminal attaching closes sidebars whose terminal is gone, and keeps the rest')
finally:
    sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True, timeout=10)
    for client, master in clients:
        client.wait(timeout=5)
        os.close(master)
