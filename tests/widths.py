#!/usr/bin/env python3
"""Attached-client sidebar widths when hidden windows retain old terminal sizes."""
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

ROOT = Path(__file__).resolve().parents[1]


def main():
    executable = shutil.which('tmux')
    socket = f'tree-width-test-{os.getpid()}'
    env = os.environ.copy()
    env.pop('TMUX', None)
    env.pop('TMUX_PANE', None)
    env['TERM'] = 'xterm-256color'
    master = None
    attached = None
    with tempfile.TemporaryDirectory(prefix='tree-width-') as directory:
        temp = Path(directory)
        state = temp / 'state'
        state.touch()

        def tm(*args):
            p = sp.run([executable, '-L', socket, *args], env=env, text=True, capture_output=True, timeout=15)
            assert p.returncode == 0, (args, p.stderr)
            return p.stdout.strip()

        def display(pane, fmt):
            return tm('display-message', '-p', '-t', pane, fmt)

        def run(name, *args):
            p = sp.run([str(ROOT / 'scripts' / name), *args], env=script_env, text=True, capture_output=True, timeout=20)
            assert p.returncode == 0, (name, p.stderr)

        def wait(predicate, message):
            until = time.monotonic() + 6
            while time.monotonic() < until:
                if predicate():
                    return
                time.sleep(.03)
            raise AssertionError((message, tm('list-panes', '-a', '-F', '#{window_id}|#{window_width}|#{window_height}|#{pane_id}|#{pane_width}|#{pane_height}|#{@tmux_canopy}|#{@tmux_canopy_slot}|#{pane_dead}|#{pane_dead_status}')))

        def check_width(expected):
            actual = display(sidebar, '#{pane_left}|#{pane_top}|#{pane_width}|#{pane_height}|#{window_height}')
            left, top, width, height, total = actual.split('|')
            assert display(sidebar, '#{pane_dead}') == '0', tm('capture-pane', '-p', '-t', sidebar)
            assert (left, top, width, height) == ('0', '0', str(expected), total), actual

        try:
            first = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'one', '-x', '510', '-y', '104', '-P', '-F', '#{pane_id}', 'sleep 600')
            tm('set-option', '-g', 'default-shell', '/bin/bash')
            tm('set-option', '-g', 'status', '2')
            tm('set-option', '-g', 'mouse', 'on')
            tm('set-option', '-gw', 'window-size', 'largest')
            tm('set-option', '-gw', 'aggressive-resize', 'on')
            second = tm('new-window', '-d', '-t', 'one:', '-P', '-F', '#{pane_id}', 'sleep 600')
            tm('split-window', '-d', '-h', '-t', second, 'sleep 600')
            native = tm('new-window', '-d', '-t', 'one:', '-P', '-F', '#{pane_id}', 'sleep 600')
            third = tm('new-session', '-d', '-s', 'two', '-x', '510', '-y', '104', '-P', '-F', '#{pane_id}', 'sleep 600')
            for option, value in [('width', '42'), ('scope', 'global'), ('transition', 'slot'), ('notifications', 'none')]:
                tm('set-option', '-g', '@tmux-canopy-' + option, value)
            script_env = env | {'TMUX': display(first, '#{socket_path},#{pid},0'), 'TMUX_PANE': first,
                                'TMUX_CANOPY_STATE': str(state), 'TMUX_CANOPY_SCOPE': 'global',
                                'TMUX_CANOPY_TRANSITION': 'slot'}
            sp.run([str(ROOT / 'tmux-canopy.tmux')], env=script_env, check=True, timeout=15)
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 67, 211, 0, 0))
            client = os.ttyname(slave)
            attached = sp.Popen([executable, '-L', socket, 'attach-session', '-t', 'one'], stdin=slave, stdout=slave,
                                stderr=slave, env=env, start_new_session=True)
            os.close(slave)
            def drain():
                try:
                    while os.read(master, 65536):
                        pass
                except OSError:
                    pass
            threading.Thread(target=drain, daemon=True).start()
            wait(lambda: client in tm('list-clients', '-F', '#{client_tty}'), 'client attach')
            script_env['TMUX_CANOPY_CLIENT'] = client
            run('toggle', client, first, '42', 'global', 'T', 'Tab', 'slot')
            sidebar = next(row.split('|')[0] for row in tm('list-panes', '-a', '-F', '#{pane_id}|#{@tmux_canopy}').splitlines() if row.endswith('|1'))
            script_env['TMUX_PANE'] = sidebar
            tm('set-option', '-p', '-t', sidebar, 'remain-on-exit', 'on')
            time.sleep(.3)
            assert display(second, '#{window_width}') == '510', 'fixture did not retain hidden-window dimensions'
            check_width(42)
            sidebar_pid = display(sidebar, '#{pane_pid}')
            def fzf_pids():
                return sp.check_output(['pgrep', '-P', sidebar_pid, '-x', 'fzf'], text=True).strip()
            ui_pid = fzf_pids()
            for pane in (second, first, third, first):
                run('sidebar-action', 'activate', 'P:' + pane)
                time.sleep(.15)
                check_width(42)
            print('ok - scripted same/cross-session switching keeps width across stale hidden-window dimensions')

            assert display(native, '#{window_width}') == '510'
            for pane in (native, first, second, first):
                tm('select-window', '-t', pane)
                time.sleep(.2)
                check_width(42)
            print('ok - native window selection keeps the same sidebar width')

            # Exercise actual border events: calling mouse-resize directly does
            # not verify the pane context used by tmux mouse bindings.
            def drag_width(desired, expected):
                previous = int(display(sidebar, '#{pane_width}'))
                border = previous + 1
                os.write(master, f'\x1b[<0;{border};10M'.encode())
                wait(lambda: display(sidebar, '#{@tmux_canopy_staged_sidebar}') == sidebar,
                     'mouse down stages sidebar')
                os.write(master, f'\x1b[<32;{border + 1};10M'.encode())
                time.sleep(.1)
                os.write(master, f'\x1b[<32;{desired + 1};10M'.encode())
                time.sleep(.1)
                check_width(previous)
                os.write(master, f'\x1b[<0;{desired + 1};10m'.encode())
                wait(lambda: tm('show-option', '-gqv', '@tmux_canopy_runtime_width') == str(expected),
                     'mouse drag saves the preferred width')
                wait(lambda: display(sidebar, '#{@tmux_canopy_staged_sidebar}') == '', 'drag marker cleared')
                check_width(expected)

            for width in (35, 46):
                drag_width(width, width)
                for pane in (second, first, third, first):
                    run('sidebar-action', 'activate', 'P:' + pane)
                    check_width(width)
                for pane in (second, first):
                    tm('select-window', '-t', pane)
                    wait(lambda: display(sidebar, '#{window_id}') == display(pane, '#{window_id}'),
                         'native switch after mouse drag')
                    check_width(width)
            print('ok - mouse drags in both directions commit on release and persist across windows/sessions')

            # An unrelated border keeps normal tmux dragging and must not alter
            # the sidebar preference or switch the client into our drag table.
            run('sidebar-action', 'activate', 'P:' + second)
            left, width = map(int, display(second, '#{pane_left}|#{pane_width}').split('|'))
            border = left + width + 1
            os.write(master, f'\x1b[<0;{border};10M'.encode())
            time.sleep(.15)
            assert display(sidebar, '#{@tmux_canopy_staged_sidebar}') == ''
            os.write(master, f'\x1b[<32;{border + 1};10M'.encode())
            time.sleep(.1)
            os.write(master, f'\x1b[<32;{border + 5};10M'.encode())
            time.sleep(.1)
            os.write(master, f'\x1b[<0;{border + 5};10m'.encode())
            wait(lambda: display(second, '#{pane_width}') != str(width), 'ordinary content border resize')
            check_width(46)
            assert tm('show-option', '-gqv', '@tmux_canopy_runtime_width') == '46'
            run('sidebar-action', 'activate', 'P:' + first)
            print('ok - ordinary content border drags preserve the sidebar preference')

            tm('set-option', '-g', '@tmux-canopy-resize-mode', 'preset')
            sp.run([str(ROOT / 'tmux-canopy.tmux')], env=script_env, check=True, timeout=15)
            drag_width(33, 30)
            run('sidebar-action', 'activate', 'P:' + second)
            check_width(30)
            run('sidebar-action', 'activate', 'P:' + first)
            check_width(30)
            tm('set-option', '-g', '@tmux-canopy-resize-mode', 'staged')
            sp.run([str(ROOT / 'tmux-canopy.tmux')], env=script_env, check=True, timeout=15)
            print('ok - preset mouse drags snap and retain their width after navigation')

            run('resize', 'commit', sidebar, '48')
            for pane in (second, first, third, first):
                run('sidebar-action', 'activate', 'P:' + pane)
                time.sleep(.1)
                check_width(48)
            print('ok - an explicitly committed width follows the sidebar')

            small = tm('new-window', '-d', '-t', 'one:', '-P', '-F', '#{pane_id}', 'sleep 600')
            tm('set-option', '-w', '-t', small, 'window-size', 'manual')
            tm('resize-window', '-t', small, '-x', '80', '-y', '65')
            run('sidebar-action', 'activate', 'P:' + small)
            time.sleep(.2)
            check_width(39)
            assert tm('show-option', '-gqv', '@tmux_canopy_runtime_width') == '48'
            run('sidebar-action', 'activate', 'P:' + first)
            time.sleep(.15)
            check_width(48)
            print('ok - a narrow window clamps temporarily without changing the preferred width')

            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', 44, 80, 0, 0))
            os.kill(attached.pid, signal.SIGWINCH)
            wait(lambda: display(sidebar, '#{pane_width}') == '39', 'terminal shrink width repair')
            assert tm('show-option', '-gqv', '@tmux_canopy_runtime_width') == '48'
            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', 67, 211, 0, 0))
            os.kill(attached.pid, signal.SIGWINCH)
            wait(lambda: display(sidebar, '#{pane_width}') == '48', 'terminal grow restores preferred width')
            small_slot = next(row.split('|')[0] for row in tm('list-panes', '-t', small, '-F', '#{pane_id}|#{@tmux_canopy_slot}').splitlines() if row.endswith('|1'))
            assert display(small_slot, '#{pane_width}') == '39'
            print('ok - terminal shrink/grow restores the preference and clamps each inactive slot independently')

            # The old source's measured width must never become the new preference.
            tm('resize-pane', '-t', sidebar, '-x', '1')
            run('sidebar-action', 'activate', 'P:' + second)
            time.sleep(.15)
            check_width(48)
            print('ok - navigation recovers an already-collapsed sidebar instead of propagating its width')

            guard = sp.check_output(['bash', '-c', 'source "$1"; sidebar_transition_option "$2"', '_', str(ROOT / 'scripts/lib.sh'), client], env=script_env, text=True).strip()
            tm('set-option', '-g', guard, '1')
            tm('resize-pane', '-t', sidebar, '-x', '1')
            run('responsive-width')
            assert display(sidebar, '#{pane_width}') == '1', 'resize worker ignored the navigation guard'
            tm('set-option', '-gu', guard)
            run('responsive-width')
            check_width(48)
            print('ok - terminal resize correction respects in-flight navigation')

            tm('set-option', '-g', '@tmux-canopy-width', '20%')
            run('responsive-width')
            check_width(42)
            for pane, expected in ((small, 24), (first, 42)):
                run('sidebar-action', 'activate', 'P:' + pane)
                check_width(expected)
            tiny = tm('new-window', '-d', '-t', 'one:', '-P', '-F', '#{pane_id}', 'sleep 600')
            tm('set-option', '-w', '-t', tiny, 'window-size', 'manual')
            tm('resize-window', '-t', tiny, '-x', '60', '-y', '65')
            parked = display(sidebar, '#{window_id}')
            run('sidebar-action', 'activate', 'P:' + tiny)
            assert display(sidebar, '#{window_id}') == parked
            assert display(tiny, '#{pane_active}') == '1'
            run('sidebar-action', 'activate', 'P:' + first)
            check_width(42)
            assert display(sidebar, '#{pane_pid}') == sidebar_pid and fzf_pids() == ui_pid
            print('ok - percentage widths use destination geometry; sidebar/fzf processes survive all resizes')

            # Compare native commit-time expressions against the shell clamp,
            # including widths crossing decimal digit boundaries (not strings).
            code = '''source "$1"
for total in 60 65 80 100 211 510; do
  for requested in 42 120 20% invalid; do
    for maximum in 48 128; do
      expected=$(clamp_sidebar_width_for_total "$total" "$requested" 24 "$maximum" 40) || expected=no-fit
      sidebar_width_expression "$requested" 24 "$maximum" 40
      expression="#{?$SIDEBAR_WIDTH_FITS_FORMAT,$SIDEBAR_WIDTH_FORMAT,no-fit}"
      expression="${expression//\\#\\{window_width\\}/$total}"
      printf '%s|%s\\n' "$expected" "$expression"
    done
  done
done'''
            rows = sp.check_output(['bash', '-c', code, '_', str(ROOT / 'scripts/lib.sh')], env=script_env, text=True).splitlines()
            expected, expressions = zip(*(row.split('|', 1) for row in rows))
            assert tm('display-message', '-p', '-t', first, '\n'.join(expressions)).splitlines() == list(expected)
            print('ok - native width expressions match numeric clamping across 48 boundary/configuration cases')

            tm('set-option', '-g', '@tmux-canopy-width', '42')
            run('toggle', client, first, '42', 'global', 'T', 'Tab', 'slot')
            time.sleep(.3)
            tm('select-window', '-t', small)
            run('toggle', client, small, '42', 'global', 'T', 'Tab', 'slot')
            sidebar = next(row.split('|')[0] for row in tm('list-panes', '-a', '-F', '#{pane_id}|#{@tmux_canopy}').splitlines() if row.endswith('|1'))
            script_env['TMUX_PANE'] = sidebar
            check_width(39)
            assert tm('show-option', '-gqv', '@tmux_canopy_runtime_width') == '42'
            run('sidebar-action', 'activate', 'P:' + first)
            check_width(42)
            print('ok - opening in a narrow window retains the requested width for later windows')

            fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', 44, 60, 0, 0))
            os.kill(attached.pid, signal.SIGWINCH)
            wait(lambda: sidebar not in tm('list-panes', '-a', '-F', '#{pane_id}').splitlines(), 'undersized terminal closes the dock')
            assert all(pane in tm('list-panes', '-a', '-F', '#{pane_id}').splitlines() for pane in (first, second, third, small, tiny))
            print('ok - impossible terminal widths close only the dock, preserving regular panes')
        finally:
            sp.run([executable, '-L', socket, 'kill-server'], env=env, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            if attached:
                attached.wait(timeout=5)
            if master is not None:
                os.close(master)
    print('all width transition tests passed')


if __name__ == '__main__':
    main()
