#!/usr/bin/env python3
"""Native prompt blocks must not name a pane: tmux rewrites %1 as the response.

tmux parses a `{ ... }` block into argv once and then substitutes the prompt
response into *every* finished argv string (args_copy_copy_value). The response
to the first prompt is %1, which is also the pane id of the second pane a tmux
server ever creates, so a block holding `-t %1` had its target replaced by
whatever the user typed. The first sidebar opened on a fresh server is normally
that pane, which made the Tree filter's text prompts silently do nothing.
"""
import fcntl
import os
from pathlib import Path
import pty
import shutil
import struct
import subprocess as sp
import sys
import tempfile
import termios
import threading
import time

from support import TerminalAnswers

ROOT = Path(__file__).resolve().parents[1]
SOCKET = 'canopy-prompt-targets-%d' % os.getpid()
TMUX = shutil.which('tmux')


def tm(*args):
    return sp.run([TMUX, '-L', SOCKET, *args], capture_output=True,
                  text=True, timeout=15)


def value(*args):
    return tm(*args).stdout.strip()


def wait(predicate, message, limit=10.0):
    deadline = time.time() + limit
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(message)


def main():
    if TMUX is None:
        print('skip - prompt_targets: no tmux on PATH')
        return
    environment = os.environ | {'TERM': 'xterm-256color'}
    environment.pop('TMUX', None)
    attached = None
    with tempfile.TemporaryDirectory(prefix='canopy-prompt-targets-') as folder:
        temp = Path(folder)
        output = bytearray()
        try:
            first = value('-f', '/dev/null', 'new-session', '-d', '-s', 'one',
                          '-n', 'work', '-x', '100', '-y', '30',
                          '-P', '-F', '#{pane_id}', 'sleep 600')
            # The whole point of this test: a fresh server hands the sidebar the
            # pane id that collides with the first prompt response.
            assert first == '%0', ('unexpected first pane on a fresh server', first)
            tm('set-option', '-g', 'default-shell', '/bin/bash')
            tm('set-option', '-g', 'status', 'off')
            tm('set-option', '-g', 'escape-time', '10')
            # Native prompt key mode otherwise inherits EDITOR/VISUAL.
            tm('set-option', '-g', 'status-keys', 'emacs')
            for key, setting in (('scope', 'global'), ('transition', 'slot'),
                                 ('preview', 'off'), ('theme', 'mono'),
                                 ('appearance', 'classic')):
                tm('set-option', '-g', '@tmux-canopy-' + key, setting)

            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 100, 0, 0))
            client = os.ttyname(slave)
            attached = sp.Popen([TMUX, '-L', SOCKET, 'attach-session', '-t', 'one'],
                                env=environment, stdin=slave, stdout=slave,
                                stderr=slave, start_new_session=True)
            os.close(slave)
            answers = TerminalAnswers(master)

            def drain():
                try:
                    while data := os.read(master, 65536):
                        output.extend(data)
                        answers.feed(data)
                except OSError:
                    pass
            threading.Thread(target=drain, daemon=True).start()
            wait(lambda: client in value('list-clients', '-F', '#{client_tty}'),
                 'client attached')

            script_env = environment | {
                'TMUX': value('display-message', '-p', '-t', first,
                              '#{socket_path},#{pid},0'),
                'TMUX_PANE': first, 'TMUX_CANOPY_CLIENT': client}
            sp.run([str(ROOT / 'tmux-canopy.tmux')], env=script_env,
                   check=True, timeout=20)
            sp.run([str(ROOT / 'scripts' / 'toggle'), client, first, '42',
                    'global', 'T', 'Tab', 'slot'], env=script_env,
                   check=True, timeout=20)
            sidebar = next(row.split('|')[0] for row in
                           value('list-panes', '-a',
                                 '-F', '#{pane_id}|#{@tmux_canopy}').splitlines()
                           if row.endswith('|1'))
            assert sidebar == '%1', ('the sidebar should be the colliding pane', sidebar)

            state = temp / 'state'
            state.write_text('')
            filter_env = script_env | {'TMUX_CANOPY_STATE': str(state),
                                       'TMUX_PANE': sidebar}

            def prompt(action, label, keys, script='tree-filter', extra=()):
                output.clear()
                pending = sp.Popen([str(ROOT / 'scripts' / script), action, *extra],
                                   env=filter_env, stdout=sp.PIPE, stderr=sp.PIPE)
                try:
                    wait(lambda: label in bytes(output), f'{action} prompt opens')
                    os.write(master, keys)
                    _, error = pending.communicate(timeout=15)
                    assert pending.returncode == 0, error
                finally:
                    if pending.poll() is None:
                        pending.kill()
                        pending.wait(timeout=10)

            # Typed text must reach the sidebar's state, not tmux's -t target.
            prompt('window', b'Window name contains', b'orch\r')
            wait(lambda: 'FILTER_WINDOW\torch\n' in state.read_text(),
                 f'window text saved: {state.read_text()!r}')
            # An apostrophe is the character tmux 3.8 started escaping in %%.
            prompt('title', b'Pane title contains', b"it's x\r")
            wait(lambda: "FILTER_TITLE\tit's x\n" in state.read_text(),
                 f'literal title saved: {state.read_text()!r}')

            # The named-session prompt shares the placeholder and has no other
            # coverage. Its response becomes a session name, so check it lands
            # verbatim rather than escaped.
            prompt('create-session-prompt', b'New session name', b"it's mine\r",
                   script='tree-action', extra=('P:' + first,))
            wait(lambda: "it's mine" in value('list-sessions', '-F', '#{session_name}'),
                 f"named session created: {value('list-sessions', '-F', '#{session_name}')!r}")

            # The response must never be taken as a pane target or a command.
            assert tm('has-session', '-t', 'one').returncode == 0, \
                'the server survived the prompts'
            assert value('display-message', '-p', '-t', sidebar,
                         '#{@tmux_canopy}') == '1', 'the sidebar pane survived'
            leftovers = [row for row in value('show-options', '-g').splitlines()
                         if '@tmux_canopy_filter_' in row
                         or '@tmux_canopy_new_session_' in row]
            assert not leftovers, ('temporary response keys were cleaned up', leftovers)
            print('ok - prompts deliver literal text to a sidebar whose pane id collides with %1')
        finally:
            tm('kill-server')
            if attached is not None:
                attached.kill()


if __name__ == '__main__':
    main()
