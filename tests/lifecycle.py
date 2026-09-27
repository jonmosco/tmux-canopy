#!/usr/bin/env python3
"""An internal dock/slot must not prevent native last-content window closure."""
import fcntl
import os
import sys
from pathlib import Path
import pty
import shutil
import struct
import subprocess as sp
import tempfile
import termios
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


def scenario(transition='slot', scope='global', position='left'):
    binary = shutil.which('tmux')
    socket = f'tree-lifetime-{os.getpid()}-{transition}-{scope}'
    env = os.environ.copy()
    env.pop('TMUX', None)
    env.pop('TMUX_PANE', None)
    env['TERM'] = 'xterm-256color'
    process = None
    master = None
    with tempfile.TemporaryDirectory(prefix='tree-lifetime-', ignore_cleanup_errors=True) as directory:
        state = Path(directory) / 'state'
        state.touch()

        def tm(*args, check=True):
            p = sp.run([binary, '-L', socket, *args], env=env, capture_output=True, text=True, timeout=15)
            assert not check or p.returncode == 0, (args, p.stderr)
            return p.stdout.strip()

        def fmt(pane, value):
            return tm('display-message', '-p', '-t', pane, value)

        def windows():
            return tm('list-windows', '-a', '-F', '#{window_id}').splitlines()

        def wait(test, label):
            end = time.monotonic() + 10
            while time.monotonic() < end:
                if test():
                    return
                time.sleep(.04)
            raise AssertionError((label, tm('list-panes', '-a', '-F', '#{session_name}|#{window_id}|#{pane_id}|#{pane_active}|#{pane_dead}|#{pane_width}|#{@tmux_canopy}|#{@tmux_canopy_slot}', check=False), tm('show-options', '-g', check=False)))

        def run(name, *args):
            p = sp.run([str(ROOT / 'scripts' / name), *args], env=script_env, text=True, capture_output=True, timeout=20)
            assert p.returncode == 0, (name, p.stderr)

        def live():
            rows = tm('list-clients', '-F', '#{client_tty}|#{pane_id}').splitlines()
            return next((row.split('|')[1] for row in rows if row.startswith(client + '|')), '')

        def check_dock(target):
            wait(lambda: fmt(sidebar, '#{window_id}') == fmt(target, '#{window_id}') and live() == target and fmt(sidebar, '#{pane_width}') == '42', 'dock follows native successor and focuses content')
            assert fmt(sidebar, '#{pane_pid}') == sidebar_pid
            assert sp.check_output(['pgrep', '-P', sidebar_pid, '-x', 'fzf'], text=True).strip() == fzf_pid
            left = '0' if position == 'left' else str(int(fmt(sidebar, '#{window_width}')) - int(fmt(sidebar, '#{pane_width}')))
            assert fmt(sidebar, '#{pane_left}|#{pane_top}|#{pane_height}') == left + '|0|' + fmt(sidebar, '#{window_height}')

        try:
            shell = ['/bin/bash', '--noprofile', '--norc']
            first = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'main', '-n', 'first', '-x', '160', '-y', '44', '-P', '-F', '#{pane_id}', *shell)
            tm('set-option', '-g', 'default-shell', '/bin/bash')
            tm('set-option', '-g', 'status', 'off')
            tm('set-option', '-g', 'renumber-windows', 'on')
            panes = [first]
            for name in ('second', 'third', 'fourth'):
                panes.append(tm('new-window', '-d', '-t', 'main:', '-n', name, '-P', '-F', '#{pane_id}', *shell))
            first, second, third, fourth = panes
            # Match a native no-sidebar control: return to third, NOT first.
            for pane in (first, third, fourth):
                tm('select-window', '-t', pane)
            for key, value in [('position', position), ('scope', scope), ('transition', transition), ('width', '42'), ('preview', 'off'), ('notifications', 'none')]:
                tm('set-option', '-g', '@tmux-canopy-' + key, value)
            script_env = env | {'TMUX': fmt(first, '#{socket_path},#{pid},0'), 'TMUX_PANE': fourth, 'TMUX_CANOPY_STATE': str(state), 'TMUX_CANOPY_SCOPE': scope, 'TMUX_CANOPY_TRANSITION': transition}
            sp.run([str(ROOT / 'tmux-canopy.tmux')], env=script_env, check=True, timeout=20)
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 44, 160, 0, 0))
            client = os.ttyname(slave)
            process = sp.Popen([binary, '-L', socket, 'attach-session', '-t', 'main'], stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True)
            os.close(slave)

            def drain():
                try:
                    while os.read(master, 65536):
                        pass
                except OSError:
                    pass
            threading.Thread(target=drain, daemon=True).start()
            wait(lambda: client in tm('list-clients', '-F', '#{client_tty}'), 'attach')
            script_env['TMUX_CANOPY_CLIENT'] = client
            run('toggle', client, fourth, '42', scope, 'T', 'Tab', transition)
            sidebar = tm('list-panes', '-a', '-f', '#{==:#{@tmux_canopy},1}', '-F', '#{pane_id}')
            script_env['TMUX_PANE'] = sidebar
            sidebar_pid = fmt(sidebar, '#{pane_pid}')
            time.sleep(.4)
            fzf_pid = sp.check_output(['pgrep', '-P', sidebar_pid, '-x', 'fzf'], text=True).strip()

            # Detaching a different terminal must not close this owner's dock.
            guest_master, guest_slave = pty.openpty()
            fcntl.ioctl(guest_slave, termios.TIOCSWINSZ, struct.pack('HHHH', 44, 160, 0, 0))
            guest_client = os.ttyname(guest_slave)
            guest = sp.Popen([binary, '-L', socket, 'attach-session', '-t', 'main'], stdin=guest_slave, stdout=guest_slave, stderr=guest_slave, env=env, start_new_session=True)
            os.close(guest_slave)
            def drain_guest():
                try:
                    while os.read(guest_master, 65536):
                        pass
                except OSError:
                    pass
            threading.Thread(target=drain_guest, daemon=True).start()
            try:
                wait(lambda: guest_client in tm('list-clients', '-F', '#{client_tty}'), 'guest attach')
                tm('detach-client', '-t', guest_client)
                guest.wait(timeout=5)
                time.sleep(.3)
                assert fmt(sidebar, '#{pane_pid}') == sidebar_pid
                assert sp.check_output(['pgrep', '-P', sidebar_pid, '-x', 'fzf'], text=True).strip() == fzf_pid
            finally:
                if guest.poll() is None:
                    tm('detach-client', '-t', guest_client, check=False)
                    guest.wait(timeout=5)
                os.close(guest_master)

            mate = ''
            if transition == 'slot' and scope == 'global':
                mate = tm('split-window', '-d', '-v', '-t', third, '-P', '-F', '#{pane_id}', *shell)
                run('sidebar-action', 'activate', 'P:' + mate)
                tm('select-pane', '-t', sidebar)
                run('sidebar-action', 'activate', 'P:' + fourth)
                warm_geometry = [fmt(p, '#{pane_width}|#{pane_height}') for p in (third, mate)]
            old = fmt(fourth, '#{window_id}')
            tm('select-pane', '-t', fourth)
            tm('send-keys', '-t', fourth, 'exit', 'Enter')
            wait(lambda: old not in windows(), 'natural shell exit closes content-empty window')
            check_dock(mate or third)
            if mate:
                assert [fmt(p, '#{pane_width}|#{pane_height}') for p in (third, mate)] == warm_geometry
                tm('kill-pane', '-t', mate)
                tm('select-pane', '-t', third)
            print(f'ok - {transition}/{scope}: natural shell exit preserves sidebar/fzf and native last-window selection')

            # A retained dead application pane is NOT an empty window.
            tm('set-option', '-p', '-t', third, 'remain-on-exit', 'on')
            tm('send-keys', '-t', third, 'exit', 'Enter')
            wait(lambda: fmt(third, '#{pane_dead}') == '1', 'retained dead pane')
            time.sleep(.25)
            assert fmt(sidebar, '#{window_id}') == fmt(third, '#{window_id}')
            tm('respawn-pane', '-k', '-t', third, *shell)
            tm('set-option', '-p', '-t', third, 'remain-on-exit', 'off')
            extra = tm('split-window', '-d', '-v', '-t', third, '-P', '-F', '#{pane_id}', *shell)
            old = fmt(third, '#{window_id}')
            tm('kill-pane', '-t', extra)
            time.sleep(.25)
            assert old in windows() and fmt(sidebar, '#{window_id}') == old
            print(f'ok - {transition}/{scope}: remaining and retained-dead content prevents premature closure')

            # Ctrl-D through the actual attached terminal, not a plugin action.
            tm('select-pane', '-t', third)
            time.sleep(.1)
            os.write(master, b'\x04')
            wait(lambda: old not in windows(), 'Ctrl-D closes the last content pane')
            check_dock(first)

            # Make an inactive window with a slot, and end its content in the
            # background. Neither its placeholder nor native history may stick.
            if transition == 'slot' and scope == 'global':
                run('sidebar-action', 'activate', 'P:' + second)
                run('sidebar-action', 'activate', 'P:' + first)
                background = fmt(second, '#{window_id}')
                assert tm('list-panes', '-t', second, '-f', '#{==:#{@tmux_canopy_slot},1}', '-F', '#{pane_id}')
                tm('select-pane', '-t', sidebar)
                geometry = fmt(first, '#{pane_width}|#{pane_height}')
                tm('send-keys', '-t', second, 'exit', 'Enter')
                wait(lambda: background not in windows(), 'inactive slot-only window closes')
                assert live() == sidebar, 'background exit stole browsing focus'
                assert fmt(first, '#{pane_width}|#{pane_height}') == geometry
                second = tm('new-window', '-d', '-t', 'main:', '-P', '-F', '#{pane_id}', *shell)

            # Confirmed sidebar deletion of a last pane must use the same path.
            tm('select-pane', '-t', first)
            old = fmt(first, '#{window_id}')
            run('tree-action', 'delete', 'P:' + first)
            run('tree-action', 'delete', 'P:' + first)
            wait(lambda: old not in windows(), 'confirmed last-pane deletion')
            check_dock(second)
            assert len(set(windows())) == 1
            print(f'ok - {transition}/{scope}: Ctrl-D and confirmed last-pane deletion retain the dock without ghost windows')

            # With detach-on-destroy off, let tmux choose another session too.
            spare = tm('new-session', '-d', '-s', 'spare', '-x', '160', '-y', '44', '-P', '-F', '#{pane_id}', *shell)
            tm('link-window', '-s', second, '-t', 'spare:')
            tm('set-option', '-g', 'detach-on-destroy', 'off')
            tm('kill-pane', '-t', second)
            wait(lambda: tm('list-sessions', '-F', '#{session_name}') == 'spare', 'native last-session destruction')
            check_dock(spare)
            print(f'ok - {transition}/{scope}: native session fallback keeps the same dock when detach-on-destroy is off')

            # Conversely, do not override native detach-on-destroy=on merely to
            # keep a dock alive. Preserve the unrelated session/application.
            winches, ready = Path(directory) / 'winches', Path(directory) / 'ready'
            watcher = 'trap \'printf x >> "$1"\' WINCH; : > "$2"; while :; do read -r line || :; done'
            tail = tm('new-session', '-d', '-s', 'tail', '-x', '160', '-y', '44', '-P', '-F', '#{pane_id}', '/bin/bash', '-c', watcher, '_', str(winches), str(ready))
            wait(ready.exists, 'unrelated application ready')
            tm('set-option', '-g', 'detach-on-destroy', 'on')
            tm('kill-pane', '-t', spare)
            wait(lambda: not tm('list-clients', '-F', '#{client_tty}'), 'native detach after final window')
            wait(lambda: not tm('list-panes', '-a', '-f', '#{||:#{==:#{@tmux_canopy},1},#{==:#{@tmux_canopy_slot},1}}', '-F', '#{pane_id}'), 'detached dock cleanup')
            assert fmt(tail, '#{pane_dead}') == '0'
            assert not winches.exists(), 'final-session detachment resized an unrelated application'
            assert tm('list-sessions', '-F', '#{session_name}') == 'tail'
            print(f'ok - {transition}/{scope}: unrelated detach preserves the dock; native final-session detach cleans only its internals')
        finally:
            sp.run([binary, '-L', socket, 'kill-server'], env=env, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            if process:
                process.wait(timeout=5)
            if master is not None:
                os.close(master)


def main():
    for transition, scope in [('slot', 'global'), ('move', 'global'), ('slot', 'window')]:
        scenario(transition, scope, "right" if "--right" in sys.argv else "left")
    print('all empty-window lifecycle tests passed')


if __name__ == '__main__':
    main()
