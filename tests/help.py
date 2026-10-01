#!/usr/bin/env python3
"""Responsive help layout and pager controls in real terminals."""
import fcntl
import os
from pathlib import Path
import pty
import re
import select
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
                assert (b'\x1b[1;36m' in output) == (theme == 'ansi')
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
    print('ok - ANSI/mono pager, arrows, paging, first/last, resize reflow, q/Esc and terminal restoration')


if __name__ == '__main__':
    main()
