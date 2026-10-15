#!/usr/bin/env python3
"""A sidebar whose terminal is gone closes when a terminal attaches, even when
Canopy missed the detach. Sidebars of attached terminals, and old ones with no
recorded owner, stay."""
import fcntl
import os
from pathlib import Path
import pty
import shlex
import signal
import shutil
import struct
import subprocess as sp
import tempfile
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


def ownership_scenarios():
    """Attached owners compete through the real toggle, split and popup paths."""
    binary, fzf = shutil.which('tmux'), shutil.which('fzf')
    socket = f'canopy-dock-owners-{os.getpid()}'
    clients, pending = [], []
    with tempfile.TemporaryDirectory(prefix='canopy-dock-owners-') as directory:
        temp = Path(directory)
        commands = temp / 'messages'
        bin_dir = temp / 'bin'
        bin_dir.mkdir()
        selections = temp / 'selections'
        selections.mkdir()
        wrapper = bin_dir / 'tmux'
        wrapper.write_text(f'''#!/bin/bash
if [[ "$1" == display-message && " $* " != *" -p "* ]]; then
  printf '%s\\n' "$*" >> {shlex.quote(str(commands))}
fi
if [[ "$1" == split-window && -n "${{CANOPY_TEST_SPLIT_GATE:-}}" ]]; then
  gate=$CANOPY_TEST_SPLIT_GATE
elif [[ "$1" == if-shell && "${{3:-}}" == '#{{!:#{{@tmux_canopy_dock_opening}}}}' && -n "${{CANOPY_TEST_CLAIM_GATE:-}}" ]]; then
  gate=$CANOPY_TEST_CLAIM_GATE
fi
if [[ -n "${{gate:-}}" ]]; then
  {shlex.quote(binary)} "$@"
  result=$?
  printf x > "$gate.ready"
  IFS= read -r _ < "$gate"
  exit "$result"
fi
exec {shlex.quote(binary)} "$@"
''')
        wrapper.chmod(0o755)
        probe_command = '''printf '%s|%s|%s|%s\\n' {1} {q} "$TMUX_CANOPY_CLIENT" "${TMUX_CANOPY_POPUP:-0}" > "$CANOPY_TEST_SELECTION_DIR/${TMUX_CANOPY_CLIENT##*/}"'''
        wrapper = bin_dir / 'fzf'
        wrapper.write_text(f'''#!/bin/bash
exec {shlex.quote(fzf)} --bind {shlex.quote('alt-z:execute-silent(' + probe_command + ')')} "$@"
''')
        wrapper.chmod(0o755)

        def tm(*args, check=True):
            result = sp.run([binary, '-L', socket, *args], env=env, capture_output=True, text=True, timeout=15)
            assert not check or result.returncode == 0, (args, result.stderr)
            return result.stdout.strip()

        def fmt(pane, value):
            return tm('display-message', '-p', '-t', pane, value)

        def sidebars():
            return tm('list-panes', '-a', '-f', '#{==:#{@tmux_canopy},1}', '-F', '#{pane_id}').splitlines()

        def attach(session):
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 44, 180, 0, 0))
            tty = os.ttyname(slave)
            process = sp.Popen([binary, '-L', socket, 'attach-session', '-t', session],
                               env=env, stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
            os.close(slave)
            clients.append((process, master, tty))

            def drain():
                try:
                    while os.read(master, 65536):
                        pass
                except OSError:
                    pass
            threading.Thread(target=drain, daemon=True).start()
            wait(lambda: tty in tm('list-clients', '-F', '#{client_tty}'), 'attached owner')
            return tty

        def toggle(client, target, width='42', extra=None, background=False):
            process = sp.Popen([str(ROOT / 'scripts/toggle'), client, target, width, 'global', 'T', 'Tab', 'slot'],
                               env=script_env | {'TMUX_PANE': target} | (extra or {}),
                               stdout=sp.PIPE, stderr=sp.PIPE, text=True, start_new_session=True)
            if background:
                pending.append(process)
                return process
            stdout, stderr = process.communicate(timeout=20)
            assert process.returncode == 0, (stdout, stderr)

        def probe(client, sidebar=None):
            selection = selections / client.rsplit('/', 1)[-1]
            selection.unlink(missing_ok=True)
            master = next(master for _, master, tty in clients if tty == client)

            def ready():
                if selection.exists() and selection.stat().st_size:
                    return True
                if sidebar:
                    tm('send-keys', '-t', sidebar, 'M-z')
                else:
                    os.write(master, b'\x1bz')
                return False
            wait(ready, 'fzf selection probe')
            return selection.read_text().strip()

        def snapshot():
            return (tm('list-panes', '-a', '-F',
                       '#{pane_id}|#{window_id}|#{pane_width}|#{pane_height}|#{pane_left}|#{pane_top}|#{pane_active}|#{window_layout}|#{window_zoomed_flag}|#{@tmux_canopy_client}'),
                    tm('list-clients', '-F', '#{client_tty}|#{pane_id}'),
                    fmt(first, '#{@tmux-canopy-width}|#{@tmux-canopy-min-width}|#{@tmux-canopy-max-width}|#{@tmux-canopy-min-content-width}|#{@tmux-canopy-position}|#{@tmux-canopy-zoom-action}|#{@tmux_canopy_runtime_width}'))

        def open_dock(client, target, width='42'):
            toggle(client, target, width)
            wait(lambda: len(sidebars()) == 1, 'one live dock')
            sidebar = sidebars()[0]
            assert fmt(sidebar, '#{@tmux_canopy_client}') == client
            probe(client, sidebar)
            return sidebar

        def close_dock(client, target):
            toggle(client, target)
            wait(lambda: not sidebars(), 'owner toggle closes')
            wait(lambda: not tm('show-option', '-gqv', '@tmux_canopy_runtime_width'), 'closed dock width cleanup')

        def gate(name):
            path = temp / name
            os.mkfifo(path)
            return path

        try:
            first = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'owner', '-x', '180', '-y', '44',
                       '-P', '-F', '#{pane_id}', 'sleep 600')
            second = tm('new-session', '-d', '-s', 'guest', '-x', '180', '-y', '44',
                        '-P', '-F', '#{pane_id}', 'sleep 600')
            tm('set-option', '-g', 'status', 'off')
            for option, value in [('preview', 'off'), ('scope', 'global'), ('transition', 'slot'),
                                  ('zoom-action', 'unzoom'), ('notifications', 'none')]:
                tm('set-option', '-g', '@tmux-canopy-' + option, value)
            script_env = env | {'TMUX': fmt(first, '#{socket_path},#{pid},0'),
                                'PATH': str(bin_dir) + ':' + env['PATH'],
                                'CANOPY_TEST_SELECTION_DIR': str(selections)}
            for key in ('PATH', 'CANOPY_TEST_SELECTION_DIR'):
                tm('set-environment', '-g', key, script_env[key])
            sp.run([str(ROOT / 'tmux-canopy.tmux')], env=script_env, check=True, timeout=20)
            owner, guest = attach('owner'), attach('guest')
            sidebar = open_dock(owner, first)
            def selection_settled():
                previous = probe(owner, sidebar)
                time.sleep(.2)
                return probe(owner, sidebar) == previous
            wait(selection_settled, 'initial focus reload settles')
            initial_selection = probe(owner, sidebar).split('|')[0]
            tm('send-keys', '-t', sidebar, 'Up')
            wait(lambda: probe(owner, sidebar).split('|')[0] != initial_selection, 'owner chooses another row')
            selection = probe(owner, sidebar)
            tm('split-window', '-d', '-v', '-t', second, 'sleep 600')
            tm('resize-pane', '-Z', '-t', second)
            before = snapshot()
            toggle(guest, second, '58')
            assert snapshot() == before, 'refusal changed layout, focus, zoom, ownership or runtime width'
            assert probe(owner, sidebar) == selection, 'refusal displaced the owner selection'
            assert 'close it there or set @tmux-canopy-mode popup' in commands.read_text()
            print('ok - a second attached dock owner is refused without geometry, focus, zoom, width or selection changes')

            tm('set-option', '-g', '@tmux-canopy-mode', 'popup')
            popup = toggle(guest, second, background=True)
            key = sp.check_output(['cksum'], input=guest.encode()).decode().split()[0]
            popup_option = '@tmux_canopy_popup_' + key
            wait(lambda: tm('show-option', '-gqv', popup_option) == '1', 'guest popup owns its terminal')
            assert probe(guest).endswith('|' + guest + '|1')
            assert snapshot() == before
            assert probe(owner, sidebar) == selection
            toggle(guest, second)
            popup.communicate(timeout=10)
            wait(lambda: tm('show-option', '-gqv', popup_option) != '1', 'popup owner cleanup')
            assert sidebars() == [sidebar] and fmt(sidebar, '#{@tmux_canopy_client}') == owner
            tm('set-option', '-g', '@tmux-canopy-mode', 'sidebar')
            legacy = tm('split-window', '-d', '-v', '-t', second, '-P', '-F', '#{pane_id}', 'sleep 600')
            tm('set-option', '-p', '-t', legacy, '@tmux_canopy', '1')
            legacy_before = snapshot()
            toggle(guest, second, '58')
            assert snapshot() == legacy_before and fmt(legacy, '#{@tmux_canopy_client}') == ''
            tm('kill-pane', '-t', legacy)
            close_dock(owner, first)
            sidebar = open_dock(owner, first)
            close_dock(owner, first)
            print('ok - another terminal popup is independently owned, and the dock owner still closes/reopens normally')
            legacy = tm('split-window', '-d', '-v', '-t', first, '-P', '-F', '#{pane_id}', 'sleep 600')
            tm('set-option', '-p', '-t', legacy, '@tmux_canopy', '1')
            toggle(owner, first)
            wait(lambda: not sidebars(), 'standalone legacy dock can still be adopted/closed')
            print('ok - legacy unowned adoption remains available only without a competing live owner')

            # Hold the winning claim until the competing request returns.
            # Both requests overlap, with no scheduling-dependent race window.
            path = gate('concurrent')
            opening = toggle(owner, first, '47', {'CANOPY_TEST_CLAIM_GATE': str(path)}, background=True)
            wait(lambda: Path(str(path) + '.ready').exists(), 'concurrent opener holds claim')
            before = snapshot()
            toggle(guest, second, '59')
            assert snapshot() == before and not sidebars()
            with path.open('w') as stream:
                stream.write('\n')
            stdout, stderr = opening.communicate(timeout=20)
            assert opening.returncode == 0, (stdout, stderr)
            wait(lambda: len(sidebars()) == 1, 'one dock after concurrent opens')
            assert fmt(sidebars()[0], '#{@tmux_canopy_client}|#{pane_width}') == owner + '|47'
            assert tm('show-option', '-gqv', '@tmux_canopy_runtime_width') == '47'
            close_dock(owner, first)
            print('ok - overlapping attached opens yield one dock and only its requested runtime width')

            path = gate('killed-before-split')
            opening = toggle(owner, first, extra={'CANOPY_TEST_CLAIM_GATE': str(path)}, background=True)
            wait(lambda: Path(str(path) + '.ready').exists(), 'killable claim holder')
            os.killpg(opening.pid, signal.SIGKILL)
            wait(lambda: sp.run(['ps', '-p', str(opening.pid), '-o', 'stat='],
                                capture_output=True, text=True).stdout.strip().startswith('Z'),
                 'terminated opener awaits reaping')
            sidebar = open_dock(guest, second)
            opening.communicate(timeout=10)
            close_dock(guest, second)
            print('ok - SIGKILL before split leaves no forever-stale opening claim')

            path = gate('killed-after-split')
            opening = toggle(owner, first, extra={'CANOPY_TEST_SPLIT_GATE': str(path)}, background=True)
            wait(lambda: Path(str(path) + '.ready').exists(), 'split completed before opener termination')
            os.killpg(opening.pid, signal.SIGKILL)
            opening.communicate(timeout=10)
            wait(lambda: len(sidebars()) == 1, 'pane publishes ownership after opener termination')
            sidebar = sidebars()[0]
            before = snapshot()
            toggle(guest, second, '59')
            assert snapshot() == before and sidebars() == [sidebar]
            close_dock(owner, first)
            print('ok - SIGKILL after split cannot strand an unmarked dock or admit a competing dock')

            sidebar = open_dock(owner, first)
            def exit_ui():
                if not sidebars():
                    return True
                tm('send-keys', '-t', sidebar, 'C-q')
                return False
            wait(exit_ui, 'owner UI exit frees dock')
            sidebar = open_dock(guest, second)
            tm('detach-client', '-t', guest)
            wait(lambda: not sidebars(), 'owner detach frees dock')
            sidebar = open_dock(owner, first)
            close_dock(owner, first)
            print('ok - UI exit and owner detach both permit the next attached dock owner')
        finally:
            for process in pending:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate(timeout=5)
            sp.run([binary, '-L', socket, 'kill-server'], env=env, capture_output=True, timeout=10)
            for process, master, _ in clients:
                process.wait(timeout=5)
                os.close(master)


ownership_scenarios()
