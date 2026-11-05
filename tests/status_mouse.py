#!/usr/bin/env python3
"""Clicking or scrolling the status line moves the sidebar in one transition.

tmux's own status-line bindings switch windows first and leave the sidebar to a
follow hook, which shows as a blink. Canopy routes them through `navigate`
instead. The follow hooks are removed here, so the sidebar can only reach the
new window if the binding itself did the work.
"""
import fcntl
import os
from pathlib import Path
import pty
import struct
import subprocess as sp
import tempfile
import termios
import threading
import time

from support import TerminalAnswers

ROOT = Path(__file__).resolve().parents[1]
PREFIX = f'canopy-status-mouse-{os.getpid()}'
env = {k: v for k, v in os.environ.items() if k not in ('TMUX', 'TMUX_PANE')}
env['TERM'] = 'xterm-256color'
TAB = 8  # ' 0:aaaa ' is eight columns wide


def tmux(socket, *args, check=True):
    result = sp.run(['tmux', '-L', socket, *args], env=env, capture_output=True, text=True, timeout=15)
    if check:
        assert result.returncode == 0, (args, result.stderr)
    return result.stdout.strip()


def wait(predicate, message, timeout=8):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if predicate():
            return
        time.sleep(.05)
    raise AssertionError(message)


def load_plugin(socket, session_pane, extra=None):
    base = env | {'TMUX': tmux(socket, 'display-message', '-p', '-t', session_pane,
                               '#{socket_path},#{pid},0')}
    assert sp.run(['bash', str(ROOT / 'tmux-canopy.tmux')], env=base | (extra or {})).returncode == 0
    return base


def status_binding(socket, key):
    # `list-keys -T root KEY` lists nothing on some tmux versions; filter instead.
    return '\n'.join(line for line in tmux(socket, 'list-keys', '-T', 'root').splitlines()
                     if line.split()[3:4] == [key])


def untouched_cases():
    """Bindings that are not tmux's defaults, or that were asked off, stay put."""
    socket = PREFIX + '-keep'
    try:
        pane = tmux(socket, '-f', '/dev/null', 'new-session', '-d', '-s', 'one', '-P', '-F', '#{pane_id}')
        tmux(socket, 'bind-key', '-T', 'root', 'MouseDown1Status', 'display-message', 'my-own-click')
        load_plugin(socket, pane)
        assert 'my-own-click' in status_binding(socket, 'MouseDown1Status'), 'user binding was replaced'
        assert 'scripts/navigate' in status_binding(socket, 'WheelUpStatus')
        print('ok - a status-line binding of the user\'s is left alone')
    finally:
        sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)
    socket = PREFIX + '-off'
    try:
        pane = tmux(socket, '-f', '/dev/null', 'new-session', '-d', '-s', 'one', '-P', '-F', '#{pane_id}')
        tmux(socket, 'set-option', '-g', '@tmux-canopy-smooth-navigation', 'off')
        load_plugin(socket, pane)
        for key, default in (('MouseDown1Status', 'switch-client -t ='), ('WheelUpStatus', 'previous-window'),
                             ('WheelDownStatus', 'next-window')):
            assert default in status_binding(socket, key) and 'navigate' not in status_binding(socket, key), key
        print('ok - smooth-navigation off keeps tmux\'s status-line bindings')
    finally:
        sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)
    socket = PREFIX + '-restore'
    try:
        pane = tmux(socket, '-f', '/dev/null', 'new-session', '-d', '-s', 'one', '-P', '-F', '#{pane_id}')
        load_plugin(socket, pane)
        assert 'navigate' in status_binding(socket, 'MouseDown1Status')
        tmux(socket, 'set-option', '-g', '@tmux-canopy-smooth-navigation', 'off')
        load_plugin(socket, pane)
        for key, default in (('MouseDown1Status', 'switch-client -t ='), ('WheelUpStatus', 'previous-window'),
                             ('WheelDownStatus', 'next-window')):
            binding = status_binding(socket, key)
            assert binding.endswith(default) and 'navigate' not in binding, (key, binding)
        print('ok - turning smooth-navigation off restores tmux\'s status-line bindings')
    finally:
        sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)


def main():
    socket = PREFIX
    master = client = None
    try:
        first = tmux(socket, '-f', '/dev/null', 'new-session', '-d', '-s', 'one', '-x', '120', '-y', '30',
                     '-n', 'aaaa', '-P', '-F', '#{pane_id}')
        for name in ('bbbb', 'cccc', 'dddd'):
            tmux(socket, 'new-window', '-d', '-t', 'one:', '-n', name)
        for option, value in (('mouse', 'on'), ('status', 'on'), ('status-position', 'bottom'),
                              ('status-left', ''), ('status-right', ''), ('status-justify', 'left'),
                              ('window-status-format', ' #I:#W '), ('window-status-current-format', ' #I:#W '),
                              ('window-status-separator', ''), ('automatic-rename', 'off'),
                              ('allow-rename', 'off'), ('@tmux-canopy-notifications', 'none')):
            tmux(socket, 'set-option', '-g', option, value)
        base = load_plugin(socket, first)
        assert 'scripts/navigate' in status_binding(socket, 'MouseDown1Status')
        assert 'switch-client -t =' in status_binding(socket, 'MouseDown1Status'), 'non-tab clicks keep tmux\'s action'
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 120, 0, 0))
        client = sp.Popen(['tmux', '-L', socket, 'attach', '-t', 'one'], stdin=slave, stdout=slave,
                          stderr=slave, env=base, start_new_session=True)
        os.close(slave)
        answers = TerminalAnswers(master)

        def drain():
            try:
                while data := os.read(master, 65536):
                    answers.feed(data)
            except OSError:
                pass
        threading.Thread(target=drain, daemon=True).start()
        wait(lambda: tmux(socket, 'list-clients', '-F', '#{client_name}'), 'client attached')
        os.write(master, b'\x02T')

        def sidebar_pane():
            return next((row.split('|')[0] for row in tmux(socket, 'list-panes', '-a', '-F',
                         '#{pane_id}|#{@tmux_canopy}').splitlines() if row.endswith('|1')), '')
        wait(sidebar_pane, 'sidebar opened')
        sidebar = sidebar_pane()
        sidebar_pid = tmux(socket, 'display-message', '-p', '-t', sidebar, '#{pane_pid}')
        # Only the binding may move the sidebar from here on.
        for hook in ('after-select-window', 'client-session-changed', 'session-window-changed'):
            tmux(socket, 'set-hook', '-gu', hook + '[9001]', check=False)
        time.sleep(1)

        windows = tmux(socket, 'list-windows', '-t', 'one', '-F', '#{window_id}').splitlines()

        def current():
            return tmux(socket, 'list-clients', '-F', '#{window_id}')

        def sidebar_window():
            return tmux(socket, 'display-message', '-p', '-t', sidebar, '#{window_id}')

        def click(code, column, release=False):
            # Two button presses within a few hundred milliseconds are a
            # double click, a different (unbound) key.
            time.sleep(.5)
            os.write(master, f'\x1b[<{code};{column};30M'.encode())
            if release:
                os.write(master, f'\x1b[<{code};{column};30m'.encode())

        def settled_on(window):
            return current() == window and sidebar_window() == window
        assert settled_on(windows[0]), (current(), sidebar_window())

        click(0, TAB * 2 + 4, release=True)
        wait(lambda: settled_on(windows[2]), f'click on the third tab: {current()} / {sidebar_window()}')
        assert sidebar_pane() == sidebar and tmux(socket, 'display-message', '-p', '-t', sidebar, '#{pane_pid}') == sidebar_pid, \
            'the sidebar process was replaced'
        print('ok - a click on a window tab brings the sidebar along with the same process')

        click(0, TAB * 0 + 4, release=True)
        wait(lambda: settled_on(windows[0]), 'click on the first tab')
        click(0, TAB * 3 + 4, release=True)
        wait(lambda: settled_on(windows[3]), 'click on the last tab')
        print('ok - clicks move in both directions and to a distant tab')

        before = current()
        click(0, 100, release=True)
        time.sleep(.6)
        assert current() == before and sidebar_window() == before, 'a click off the tabs moved something'
        print('ok - a click that is not on a tab changes nothing')

        click(65, TAB + 4)  # wheel down: next window, wrapping to the first
        wait(lambda: settled_on(windows[0]), 'wheel down wraps to the next window')
        click(64, TAB + 4)  # wheel up: previous window, wrapping to the last
        wait(lambda: settled_on(windows[3]), 'wheel up wraps to the previous window')
        print('ok - the wheel over the status line moves the sidebar too')
    finally:
        if client is not None:
            client.kill()
        if master is not None:
            os.close(master)
        sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)
    untouched_cases()


if __name__ == '__main__':
    main()
