#!/usr/bin/env python3
"""Responsive help layout and pager controls in real terminals."""
import fcntl
import os
from pathlib import Path
import pty
import re
import select
import shutil
import signal
import struct
import subprocess
import tempfile
import termios
import time

ROOT = Path(__file__).resolve().parents[1]
HELP = ROOT / 'scripts/help'


def main():
    env = dict(os.environ)
    for name in ('TMUX', 'TMUX_PANE', 'TMUX_CANOPY_HELP_TEST', 'TMUX_CANOPY_CLIENT'):
        env.pop(name, None)
    for width in (12, 24, 30, 42, 59, 60, 80, 100):
        result = subprocess.run([str(HELP), '--print', str(width)], env=env,
                                text=True, capture_output=True, check=True)
        assert all(len(line) <= width for line in result.stdout.splitlines()), (width, result.stdout)
        assert '\x1b' not in result.stdout
        compact = re.sub(r'\s', '', result.stdout)
        for text in ('[Ctrl-r]', '[Enter]', '@tmux-canopy-density', 'prefix+T', 'Navigation', 'Create'):
            assert text in compact, (width, text)
        if width >= 60:
            assert '[Enter]               Focus the selected object' in result.stdout
        elif width >= 24:
            assert '  [Enter]\n    Focus' in result.stdout
    custom = subprocess.check_output([str(HELP), '--print', '24'], text=True,
                                     env=env | {'TMUX_CANOPY_KEY': 'a' * 50,
                                                'TMUX_CANOPY_LAST_KEY': 'off'})
    assert all(len(line) <= 24 for line in custom.splitlines())
    assert 'Return to the last window' not in custom
    print('ok - narrow/wide layouts, complete command text, custom keys and bounded line widths')

    for width in (12, 24, 42, 60, 80):
        legend = subprocess.check_output([str(HELP), '--legend', '--print', str(width)],
                                         text=True, env=env)
        assert all(len(line) <= width for line in legend.splitlines()), (width, legend)
        assert '\x1b' not in legend
        compact = re.sub(r'\s+', ' ', legend)
        if width >= 24:
            for phrase in ('Sidebar legend', 'Selected row', 'current content pane', 'grouped by working directory',
                           'Unread terminal output', 'does not mean an agent needs input', 'Session and window names',
                           'Recognized apps have icons', 'Working directory', 'Window-name / pane-title'):
                assert phrase in compact, (width, phrase)
    print('ok - responsive legend explains selection, location, pane details, notices and filters')

    with tempfile.TemporaryDirectory(prefix='tree-help-', ignore_cleanup_errors=True) as directory:
        temp = Path(directory)
        wrapper = temp / 'tmux'
        wrapper.write_text('#!/bin/sh\nprintf "%s\\n" "$HELP_THEME"\n')
        wrapper.chmod(0o755)
        env['PATH'] = str(temp) + ':' + env['PATH']
        for width, theme in ((24, 'ansi'), (42, 'mono'), (88, 'ansi')):
            pid, master = pty.fork()
            if pid == 0:
                fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack('HHHH', 18, width, 0, 0))
                os.execve(str(HELP), [str(HELP), '--render'], env | {'HELP_THEME': theme})
            output = bytearray()

            def wait_for(text):
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if text in output:
                        return
                    if select.select([master], [], [], .05)[0]:
                        output.extend(os.read(master, 65536))
                raise AssertionError((width, text, output.decode(errors='replace')))

            def send(keys):
                output.clear()
                os.write(master, keys)

            try:
                wait_for(b'q close   1-14')
                assert b'SIDEBAR HELP' in output and b'[j / Down]' in output
                assert b'\x1b[?1000h\x1b[?1006h' in output, 'mouse reporting not enabled'
                assert (b'\x1b[1;36m' in output) == (theme == 'ansi')
                send(b'\x1b[<65;12;8M')  # SGR wheel down
                wait_for(b'q close   4-17')
                send(b'\x1b[<64;12;8M')  # SGR wheel up
                wait_for(b'q close   1-14')
                send(b'\x1b[Ma99')  # X10 wheel down, including its three data bytes
                wait_for(b'q close   4-17')
                send(b'\x1b[M`bG')  # X10 wheel up; coordinates must not become keys
                wait_for(b'q close   1-14')
                send(b'\x1b[B')
                wait_for(b'q close   2-15')
                send(b' ')
                wait_for(b'q close   16-29')
                send(b'b')
                wait_for(b'q close   2-15')
                send(b'g')
                wait_for(b'q close   1-14')
                send(b'G')
                wait_for(b'Retained')
                send(b'g')
                wait_for(b'q close   1-14')
                output.clear()
                fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', 22, 65, 0, 0))
                os.kill(pid, signal.SIGWINCH)
                # A blocked read may resume on input after SIGWINCH. It must
                # reflow on the next interaction without losing pager state.
                os.write(master, b'g')
                wait_for(b'q close   1-18')
                wait_for(b'[Enter]')
                send(b'\x1b' if theme == 'mono' else b'q')
                wait_for(b'\x1b[?1049l')
                assert b'\x1b[?1006l\x1b[?1000l' in output, 'mouse reporting not restored'
                _, status = os.waitpid(pid, 0)
                assert os.waitstatus_to_exitcode(status) == 0
                pid = None
            finally:
                if pid:
                    os.kill(pid, signal.SIGTERM)
                    os.waitpid(pid, 0)
                os.close(master)
        pid, master = pty.fork()
        if pid == 0:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack('HHHH', 18, 42, 0, 0))
            os.execve(str(HELP), [str(HELP), '--legend', '--render'],
                      env | {'HELP_THEME': 'ansi'})
        try:
            output = bytearray()
            deadline = time.monotonic() + 5
            while b'Selected row' not in output and time.monotonic() < deadline:
                if select.select([master], [], [], .05)[0]:
                    output.extend(os.read(master, 65536))
            assert b'SIDEBAR LEGEND' in output and b'Selected row' in output, output
            os.write(master, b'q')
            deadline = time.monotonic() + 5
            while b'\x1b[?1049l' not in output and time.monotonic() < deadline:
                if select.select([master], [], [], .05)[0]:
                    output.extend(os.read(master, 65536))
            assert b'\x1b[?1049l' in output, output
            _, status = os.waitpid(pid, 0)
            assert os.waitstatus_to_exitcode(status) == 0
            pid = None
        finally:
            if pid:
                os.kill(pid, signal.SIGTERM)
                os.waitpid(pid, 0)
            os.close(master)
    print('ok - ANSI/mono pager, keyboard and mouse wheel, resize reflow, q/Esc and terminal restoration')

    # tmux must forward wheel events to the real attached popup, not only to
    # a pager invoked directly on a pty. This server never touches user panes.
    tmux = shutil.which('tmux')
    socket = f'canopy-help-mouse-{os.getpid()}'
    attached_env = os.environ.copy()
    attached_env.pop('TMUX', None)
    attached_env.pop('TMUX_PANE', None)

    def tm(*args):
        p = subprocess.run([tmux, '-L', socket, *args], env=attached_env,
                           text=True, capture_output=True, timeout=15)
        assert p.returncode == 0, (args, p.stderr)
        return p.stdout.strip()

    client_process = popup_process = master = None
    try:
        pane = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'help', '-x', '100', '-y', '35',
                  '-P', '-F', '#{pane_id}', 'sleep 600')
        tm('set-option', '-g', 'mouse', 'on')
        tm('set-option', '-g', 'status', 'off')
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 35, 100, 0, 0))
        client = os.ttyname(slave)
        client_process = subprocess.Popen([tmux, '-L', socket, 'attach-session', '-t', 'help'],
                                          env=attached_env | {'TERM': 'xterm-256color'},
                                          stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
        os.close(slave)
        deadline = time.monotonic() + 8
        while client not in tm('list-clients', '-F', '#{client_tty}').splitlines():
            assert time.monotonic() < deadline, 'private tmux client did not attach'
            time.sleep(.05)
        popup_process = subprocess.Popen([tmux, '-L', socket, 'display-popup', '-c', client,
                                          '-t', pane, '-w', '60', '-h', '20', '-E',
                                          str(HELP), '--render'], env=attached_env,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        def wait_for_screen(text):
            seen = bytearray()
            deadline = time.monotonic() + 6
            while text not in seen and time.monotonic() < deadline:
                if select.select([master], [], [], .05)[0]:
                    seen.extend(os.read(master, 65536))
            assert text in seen, (text, bytes(seen[-150:]))

        wait_for_screen(b'q close   1-14')
        os.write(master, b'\x1b[<65;30;15M')
        wait_for_screen(b'q close   4-17')
        os.write(master, b'q')
        _, stderr = popup_process.communicate(timeout=6)
        assert popup_process.returncode == 0, stderr
        print('ok - attached tmux Help popup accepts the mouse wheel without changing panes')
    finally:
        subprocess.run([tmux, '-L', socket, 'kill-server'], env=attached_env,
                       capture_output=True, timeout=10)
        if popup_process and popup_process.poll() is None:
            popup_process.terminate()
            popup_process.wait(timeout=3)
        if client_process:
            client_process.terminate()
            client_process.wait(timeout=3)
        if master is not None:
            os.close(master)


if __name__ == '__main__':
    main()
