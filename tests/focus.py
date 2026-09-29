#!/usr/bin/env python3
"""Real-client active-location, pointer return, and debounce regressions."""
import fcntl
from support import install_fzf_probe
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

ROOT = Path(__file__).resolve().parents[1]


def main():
    socket = f'tree-focus-test-{os.getpid()}'
    executable = shutil.which('tmux')
    env = os.environ.copy()
    env.pop('TMUX', None)
    env.pop('TMUX_PANE', None)
    env['TERM'] = 'xterm-256color'
    processes, terminals = [], []
    with tempfile.TemporaryDirectory(prefix='tree-focus-', ignore_cleanup_errors=True) as directory:
        temp = Path(directory)
        selected, deliveries, state = (temp / name for name in ('selected', 'deliveries', 'state'))
        deliveries.touch()
        state.touch()

        def tm(*args):
            p = sp.run([executable, '-L', socket, *args], env=env, text=True, capture_output=True, timeout=15)
            assert p.returncode == 0, (args, p.stderr)
            return p.stdout.strip()

        def run(script, *args):
            p = sp.run([str(ROOT / 'scripts' / script), *args], env=script_env, text=True,
                       capture_output=True, timeout=15)
            assert p.returncode == 0, (script, p.stderr)
            return p.stdout

        def display(pane, fmt):
            return tm('display-message', '-p', '-t', pane, fmt)

        def wait(predicate, message):
            until = time.monotonic() + 6
            while time.monotonic() < until:
                if predicate():
                    return
                time.sleep(.025)
            raise AssertionError((message, tm('list-clients', '-F', '#{client_tty}|#{session_id}|#{window_id}|#{pane_id}'), tm('list-panes', '-a', '-F', '#{pane_id}|#{pane_last}|#{@tmux_canopy}|#{@tmux_canopy_target}|#{@tmux_canopy_focus_location}|#{@tmux_canopy_focus_pending}')))

        def attach(session):
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 44, 160, 0, 0))
            tty = os.ttyname(slave)
            processes.append(sp.Popen([executable, '-L', socket, 'attach-session', '-t', session],
                                      stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True))
            os.close(slave)
            terminals.append(master)

            def drain():
                try:
                    while os.read(master, 65536):
                        pass
                except OSError:
                    pass
            threading.Thread(target=drain, daemon=True).start()
            wait(lambda: tty in tm('list-clients', '-F', '#{client_tty}').splitlines(), 'client attach')
            return master, tty

        def location(sidebar):
            return tm('show-option', '-pqv', '-t', sidebar, '@tmux_canopy_focus_location')

        def active_rows():
            # The pane has the single green dot; its session and window are bold.
            return [line.split('\t')[0] for line in run('sidebar-source', '--stable').splitlines()
                    if '●' in line.split('\t')[1] or '▶' in line.split('\t')[1] or '\x1b[1m' in line.split('\t')[1]]

        def probe(sidebar):
            selected.unlink(missing_ok=True)
            def poll():
                if selected.exists() and selected.stat().st_size:
                    return True
                tm('send-keys', '-t', sidebar, 'M-z')
                time.sleep(.08)
                return False
            wait(poll, 'selection probe')
            return selected.read_text().strip()

        def pointer_line(sidebar):
            lines = tm('capture-pane', '-e', '-p', '-t', sidebar).splitlines()
            return next(i for i, line in enumerate(lines) if '[7m' in line or '[1;7m' in line or '48;5;236' in line)

        try:
            pane_a = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'one', '-x', '160', '-y', '44', '-P', '-F', '#{pane_id}', 'sleep 600')
            peer = tm('split-window', '-d', '-h', '-t', pane_a, '-P', '-F', '#{pane_id}', 'sleep 600')
            pane_b = tm('new-window', '-d', '-t', 'one:', '-n', 'beta', '-P', '-F', '#{pane_id}', 'sleep 600')
            session = display(pane_a, '#{session_id}')
            wa, wb = (display(pane, '#{window_id}') for pane in (pane_a, pane_b))
            for index in range(16):
                last = tm('new-window', '-d', '-t', 'one:', '-n', f'extra-{index}', '-P', '-F', '#{pane_id}', 'sleep 600')
            pane_c = tm('new-session', '-d', '-s', 'two', '-x', '160', '-y', '44', '-P', '-F', '#{pane_id}', 'sleep 600')
            session_two = display(pane_c, '#{session_id}')
            tm('link-window', '-s', wb, '-t', 'two:5')
            tm('set-option', '-g', 'default-shell', '/bin/bash')
            tm('set-option', '-g', 'status', 'off')
            tm('set-option', '-g', 'mouse', 'on')
            tm('set-option', '-g', 'escape-time', '10')
            for option, value in [('scope', 'global'), ('transition', 'slot'), ('theme', 'ansi'),
                                  ('appearance', 'classic'),
                                  ('preview', 'off'), ('notifications', 'none')]:
                tm('set-option', '-g', '@tmux-canopy-' + option, value)
            script_env = env.copy()
            script_env.update(TMUX=display(pane_a, '#{socket_path},#{pid},0'), TMUX_PANE=pane_a,
                              TMUX_CANOPY_STATE=str(state))
            sp.run([str(ROOT / 'tmux-canopy.tmux')], env=script_env, check=True, timeout=15)
            initial = [line.split('\t') for line in run('sidebar-source', '--stable').splitlines()]
            pos = next(i for i, row in enumerate(initial) if row[0] == 'P:' + last)
            bindings = [f'alt-a:pos({pos})', f"alt-z:execute-silent(printf '%s|%s|%s\\n' {{1}} {{3}} {{q}} > {selected})"]
            install_fzf_probe(temp, bindings, script_env)
            wrapper = temp / 'tmux'
            wrapper.write_text('#!/bin/bash\nif [[ "$1" == if-shell && "$*" == *tmux_canopy_focus_pending* && "$*" == *send-keys* ]]; then printf "%s\\n" "$6" >> ' + shlex.quote(str(deliveries)) + '; fi\nexec ' + shlex.join([executable, '-L', socket]) + ' "$@"\n')
            wrapper.chmod(0o755)
            tm('set-environment', '-g', 'PATH', str(temp) + ':' + env['PATH'])
            master, client = attach('one')
            script_env['TMUX_CANOPY_CLIENT'] = client
            run('toggle', client, pane_a, '42', 'global', 'T', 'Tab', 'slot')
            sidebar = next(row.split('|')[0] for row in tm('list-panes', '-a', '-F', '#{pane_id}|#{@tmux_canopy}').splitlines() if row.endswith('|1'))
            script_env['TMUX_PANE'] = sidebar
            wait(lambda: location(sidebar) == f'{session}|{wa}|{pane_a}', 'initial remembered content')
            time.sleep(.3)
            tm('send-keys', '-t', sidebar, 'M-a')
            before, row_before = probe(sidebar), pointer_line(sidebar)
            assert before.startswith('P:' + last + '|')

            # Actual client keystrokes retain client identity even with another
            # attached client. No global "most recent client" assumptions.
            tm('bind-key', '-n', 'F5', 'select-pane', '-t', pane_a)
            tm('bind-key', '-n', 'F6', 'select-pane', '-t', peer)
            tm('bind-key', '-n', 'F7', 'select-window', '-t', wb)
            tm('bind-key', '-n', 'F8', 'select-window', '-t', wa)
            tm('bind-key', '-n', 'F9', 'select-pane', '-t', sidebar)
            # Browse to a distant row, then leave the sidebar for the pane
            # already active beneath it. The arrow must follow that pane even
            # though the active-location value itself has not changed.
            os.write(master, b'\x1b[15~')
            wait(lambda: probe(sidebar).startswith('P:' + pane_a + '|'), 'same-pane departure selects active row')
            assert pointer_line(sidebar) != row_before
            os.write(master, b'\x1b[17~')
            wait(lambda: location(sidebar) == f'{session}|{wa}|{peer}', 'native pane focus marker')
            assert display(sidebar, '#{@tmux_canopy_target}') == peer
            assert set(active_rows()) == {'S:' + session, f'W:{wa}:{session}', 'P:' + peer}
            wait(lambda: probe(sidebar).startswith('P:' + peer + '|'), 'native pane focus selects active row')
            print('ok - native pane focus updates hierarchy and selects active row')

            # Real SGR mouse click selects the other content pane.
            x, y = map(int, display(pane_a, '#{pane_left}|#{pane_top}').split('|'))
            os.write(master, f'\x1b[<0;{x+2};{y+2}M\x1b[<0;{x+2};{y+2}m'.encode())
            wait(lambda: location(sidebar) == f'{session}|{wa}|{pane_a}', 'mouse pane focus marker')
            wait(lambda: probe(sidebar).startswith('P:' + pane_a + '|'), 'mouse pane focus selects active row')
            # Entering the sidebar remembers content and causes no extra reload.
            time.sleep(.2)
            count = len(deliveries.read_text().splitlines())
            os.write(master, b'\x1b[20~')
            wait(lambda: probe(sidebar).startswith('P:' + pane_a + '|'), 'return selects current pane')
            assert location(sidebar) == f'{session}|{wa}|{pane_a}'
            assert len(deliveries.read_text().splitlines()) == count
            print('ok - mouse focus and returning to sidebar selects the current content pane')

            os.write(master, b'\x1b[17~')
            wait(lambda: location(sidebar) == f'{session}|{wa}|{peer}', 'prepare pane burst')
            time.sleep(.2)
            count = len(deliveries.read_text().splitlines())
            os.write(master, (b'\x1b[15~\x1b[17~' * 4) + b'\x1b[15~')
            wait(lambda: location(sidebar) == f'{session}|{wa}|{pane_a}', 'rapid pane burst')
            time.sleep(.25)
            assert len(deliveries.read_text().splitlines()) == count + 1
            print('ok - rapid real pane switches publish only the settled target')

            # Collapse the active window in the *actual* UI state file.
            # Use the existing window row and h, not a filesystem side channel.
            tm('send-keys', '-t', sidebar, 'Home')
            # A search selects the window by name; clear it after collapse.
            tm('rename-window', '-t', wa, 'focus-collapse')
            time.sleep(.2)
            # Rename refresh is asynchronous; wait for search mode to be
            # visibly entered rather than typing across an in-flight reload.
            def enter_search():
                tm('send-keys', '-t', sidebar, '/')
                time.sleep(.08)
                return tm('capture-pane', '-p', '-t', sidebar).startswith('search ›')
            wait(enter_search, 'search mode after rename refresh')
            tm('send-keys', '-t', sidebar, '-l', 'focus-collapse')
            time.sleep(.15)
            filtered = probe(sidebar)
            assert filtered.split('|')[2] == 'focus-collapse', filtered
            os.write(master, b'\x1b[17~')
            wait(lambda: location(sidebar) == f'{session}|{wa}|{peer}', 'filtered focus refresh')
            wait(lambda: probe(sidebar).startswith('P:' + peer + '|'), 'filtered focus selects active pane')
            assert probe(sidebar).split('|')[-1] == ''
            print('ok - leaving a filtered sidebar clears search and selects the active pane')
            wait(enter_search, 'search mode before collapsing active window')
            tm('send-keys', '-t', sidebar, '-l', 'focus-collapse')
            time.sleep(.15)
            assert probe(sidebar).split('|')[2] == 'focus-collapse'
            tm('send-keys', '-t', sidebar, 'Escape')
            time.sleep(.3)
            tm('send-keys', '-t', sidebar, 'h')
            time.sleep(.15)
            os.write(master, b'\x1b[18~')
            wait(lambda: location(sidebar) == f'{session}|{wb}|{pane_b}', 'native window focus marker')
            os.write(master, b'\x1b[19~')
            wait(lambda: location(sidebar) == f'{session}|{wa}|{peer}', 'return to collapsed window')
            capture = tm('capture-pane', '-p', '-t', sidebar)
            assert '▸ 0:focus-collapse' in capture, capture
            print('ok - window switches update markers without expanding collapsed branches')

            # Coalesce concurrent duplicate/stale requests and ignore a stale
            # hook pane. Only one delivery is needed for the final target.
            tm('set-option', '-pu', '-t', sidebar, '@tmux_canopy_focus_location')
            time.sleep(.2)
            count = len(deliveries.read_text().splitlines())
            jobs = [sp.Popen([str(ROOT / 'scripts/refresh-sidebar'), '%999999', client], env=script_env) for _ in range(12)]
            for job in jobs:
                assert job.wait(timeout=10) == 0
            wait(lambda: location(sidebar) == f'{session}|{wa}|{peer}', 'coalesced stale requests')
            time.sleep(.2)
            assert len(deliveries.read_text().splitlines()) == count + 1
            count = len(deliveries.read_text().splitlines())
            for _ in range(3):
                run('refresh-sidebar', '%999999', client)
            time.sleep(.2)
            assert len(deliveries.read_text().splitlines()) == count
            print('ok - stale requests coalesce and unchanged locations do not reload')

            tm('set-option', '-p', '-t', sidebar, '@tmux_canopy_focus_pending', '1.1.1')
            tm('set-option', '-p', '-t', sidebar, '@tmux_canopy_focus_deadline', '1')
            tm('set-option', '-pu', '-t', sidebar, '@tmux_canopy_focus_location')
            run('refresh-sidebar', peer, client)
            wait(lambda: location(sidebar) == f'{session}|{wa}|{peer}', 'expired focus worker recovery')
            assert display(sidebar, '#{@tmux_canopy_focus_pending}') == ''
            print('ok - an expired focus-worker claim recovers automatically')

            # A linked pane must mark only the session occurrence the client uses.
            tm('bind-key', '-n', 'F9', 'switch-client', '-t', f'{session_two}:{wb}')
            os.write(master, b'\x1b[20~')
            wait(lambda: location(sidebar) == f'{session_two}|{wb}|{pane_b}', 'linked session focus')
            assert f'W:{wb}:{session_two}' in active_rows()
            assert f'W:{wb}:{session}' not in active_rows()
            # Restore the first client's session before attaching another owner.
            tm('switch-client', '-c', client, '-t', f'{session}:{wa}')
            wait(lambda: location(sidebar) == f'{session}|{wa}|{peer}', 'restore first owner')
            tm('bind-key', '-n', 'F10', 'new-window', '-n', 'fresh', 'sleep 600')
            os.write(master, b'\x1b[21~')
            def first_client_location():
                return next(row.split('|', 1)[1] for row in tm('list-clients', '-F', '#{client_tty}|#{session_id}|#{window_id}|#{pane_id}').splitlines() if row.startswith(client + '|'))
            wait(lambda: first_client_location().split('|')[1] != wa, 'native new-window command')
            wait(lambda: location(sidebar) == first_client_location(), 'new-window marker')
            tm('switch-client', '-c', client, '-t', f'{session}:{wa}')
            wait(lambda: location(sidebar) == f'{session}|{wa}|{peer}', 'restore after new window')
            print('ok - newly created windows receive the active marker')

            _second_master, second_client = attach('two')
            tm('select-window', '-t', display(pane_c, '#{window_id}'))
            run('toggle', second_client, pane_c, '42', 'global', 'T', 'Tab', 'slot')
            other = next(row.split('|')[0] for row in tm('list-panes', '-a', '-F', '#{pane_id}|#{@tmux_canopy_client}').splitlines() if row.endswith('|' + second_client))
            wait(lambda: location(other) != '', 'second sidebar initialization')
            time.sleep(.2)
            count_other = sum(f"-t '{other}'" in line for line in deliveries.read_text().splitlines())
            os.write(master, b'\x1b[18~')
            wait(lambda: location(sidebar) == f'{session}|{wb}|{pane_b}', 'first owner window switch')
            time.sleep(.2)
            assert sum(f"-t '{other}'" in line for line in deliveries.read_text().splitlines()) == count_other
            print('ok - linked-session markers and refresh delivery are owner-specific')
        finally:
            sp.run([executable, '-L', socket, 'kill-server'], env=env, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            for process in processes:
                process.wait(timeout=5)
            for fd in terminals:
                os.close(fd)
    print('all active-location tests passed')


if __name__ == '__main__':
    main()
