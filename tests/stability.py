#!/usr/bin/env python3
"""Attached-client regressions for refresh painting, selection and pane navigation."""
import argparse
import fcntl
import os
from pathlib import Path
import pty
import re
import shlex
import shutil
import struct
import signal
import subprocess as sp
import tempfile
import termios
import threading
import time

from support import install_fzf_probe

ROOT = Path(__file__).resolve().parents[1]


def wait(predicate, description):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.02)
    raise AssertionError(description)


class Sidebar:
    def __init__(self, directory, position='left', navigator=None):
        self.directory = directory
        self.socket = f'canopy-stability-{os.getpid()}-{position}'
        self.env = os.environ.copy()
        self.env.pop('TMUX', None)
        self.env.pop('TMUX_PANE', None)
        self.env['TERM'] = 'xterm-256color'
        self.master = None
        self.process = None
        self.workers = []
        self.loads = directory / 'loads'
        self.loads.touch()
        self.probe_file = directory / 'selection'
        self.state_path_file = directory / 'state-path'
        self.output = directory / 'terminal'
        self.output.touch()
        self.failure = directory / 'fail-source'
        self.delay = directory / 'delay-source'
        self.hold = directory / 'hold-source'
        self.held = directory / 'held-source'
        self.release = directory / 'release-source'
        os.mkfifo(self.release)
        self.hold2 = directory / 'hold-background'
        self.held2 = directory / 'held-background'
        self.release2 = directory / 'release-background'
        os.mkfifo(self.release2)
        self.binary = shutil.which('tmux')
        try:
            self.pane = self.tm('-f', '/dev/null', 'new-session', '-d', '-s', 'stability',
                                '-x', '120', '-y', '30', '-P', '-F', '#{pane_id}', 'sleep 600')
            self.tm('set-option', '-g', 'status', 'off')
            self.tm('set-option', '-g', 'automatic-rename', 'off')
            for option, value in (('agents', 'off'), ('notifications', 'none'), ('animate', 'off'),
                                  ('preview', 'off'), ('position', position), ('appearance', 'quiet'),
                                  ('compact-single-panes', 'off')):
                self.tm('set-option', '-g', '@tmux-canopy-' + option, value)
            script_env = self.env | {'TMUX': self.display(self.pane, '#{socket_path},#{pid},0'),
                                     'TMUX_PANE': self.pane}
            # Delay/fail the actual metadata provider, not the renderer or fzf.
            wrapper = directory / 'tmux'
            wrapper.write_text('#!/bin/bash\n'
                               'if [[ "$*" == *D$\'\\037\'* ]]; then\n'
                               f'  [[ ! -e {shlex.quote(str(self.failure))} ]] || exit 1\n'
                               f'  [[ ! -e {shlex.quote(str(self.delay))} ]] || sleep .15\n'
                               f'  if [[ -e {shlex.quote(str(self.hold))} && ! -e {shlex.quote(str(self.held))} ]]; then\n'
                               f'    held={shlex.quote(str(self.held))}; release={shlex.quote(str(self.release))}\n'
                               f'  elif [[ -e {shlex.quote(str(self.hold2))} && ! -e {shlex.quote(str(self.held2))} ]]; then\n'
                               f'    held={shlex.quote(str(self.held2))}; release={shlex.quote(str(self.release2))}\n'
                               '  fi\n'
                               '  if [[ -n "${held:-}" ]]; then\n'
                               f'    {shlex.quote(self.binary)} "$@"\n'
                               '    result=$?\n'
                               '    printf x > "$held"\n'
                               '    IFS= read -r _ < "$release"\n'
                               '    exit "$result"\n'
                               '  fi\n'
                               'fi\nexec ' + shlex.quote(self.binary) + ' "$@"\n')
            wrapper.chmod(0o755)
            script_env['PATH'] = str(directory) + ':' + script_env['PATH']
            install_fzf_probe(directory, [
                f'load:execute-silent(printf x >> {shlex.quote(str(self.loads))})',
                f"alt-z:execute-silent(printf '%s|%s|%s' {{1}} {{3}} {{q}} > {shlex.quote(str(self.probe_file))})",
                f"alt-e:execute-silent(printf '%s' \"$TMUX_CANOPY_STATE\" > {shlex.quote(str(self.state_path_file))})",
            ], script_env)
            self.tm('set-environment', '-g', 'PATH', script_env['PATH'])
            self.run(ROOT / 'tmux-canopy.tmux', env=script_env)
            if navigator:
                self.run(navigator, env=script_env)
            else:
                # The upstream navigator's real ps-based fzf/Vim routing, with
                # no mocked process decision: fzf receives Ctrl-h/l itself.
                pattern = r'(\S+/)?g?\.?(view|l?n?vim?x?|fzf)(diff)?(-wrapped)?'
                check = f"ps -o state= -o comm= -t '#{{pane_tty}}' | grep -iqE '^[^TXZ ]+ +{pattern}$'"
                for key, direction in (('C-h', '-L'), ('C-l', '-R')):
                    self.tm('bind-key', '-n', key, 'if-shell', check,
                            'send-keys ' + key, 'select-pane ' + direction)
            self.master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 120, 0, 0))
            self.client = os.ttyname(slave)
            self.process = sp.Popen([self.binary, '-L', self.socket, 'attach-session', '-t', 'stability'],
                                    stdin=slave, stdout=slave, stderr=slave, env=self.env,
                                    start_new_session=True)
            os.close(slave)
            def drain():
                try:
                    while os.read(self.master, 65536):
                        pass
                except OSError:
                    pass
            threading.Thread(target=drain, daemon=True).start()
            wait(lambda: self.client in self.tm('list-clients', '-F', '#{client_tty}').splitlines(), 'client attach')
            self.script_env = script_env | {'TMUX_CANOPY_CLIENT': self.client}
            self.run(ROOT / 'scripts/toggle', self.client, self.pane, '42', 'global', 'T', 'Tab', 'slot',
                     env=self.script_env)
            self.sidebar = next(row.split('|')[0] for row in
                                self.tm('list-panes', '-a', '-F', '#{pane_id}|#{@tmux_canopy}').splitlines()
                                if row.endswith('|1'))
            wait(lambda: 'sleep' in self.screen(), 'sidebar first paint')
            wait(lambda: self.loads.stat().st_size > 0, 'sidebar initial load')
            self.tm('pipe-pane', '-O', '-t', self.sidebar, 'cat >> ' + shlex.quote(str(self.output)))
            time.sleep(.3)
        except BaseException:
            self.close()
            raise

    def tm(self, *args):
        result = sp.run([self.binary, '-L', self.socket, *args], env=self.env,
                        capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, (args, result.stderr)
        return result.stdout.strip()

    def run(self, executable, *args, env=None):
        result = sp.run(['bash', str(executable), *args], env=env or self.script_env,
                        capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, (executable, result.stderr)
        return result.stdout

    def display(self, pane, fmt):
        return self.tm('display-message', '-p', '-t', pane, fmt)

    def screen(self, ansi=False):
        return self.tm('capture-pane', '-ep' if ansi else '-p', '-t', self.sidebar)

    def send(self, *keys):
        self.tm('send-keys', '-t', self.sidebar, *keys)

    def probe(self):
        self.probe_file.unlink(missing_ok=True)
        self.send('M-z')
        wait(lambda: self.probe_file.exists() and self.probe_file.stat().st_size > 0, 'selection probe')
        return self.probe_file.read_text().split('|')

    def reload(self):
        size = self.loads.stat().st_size
        self.send('C-r')
        wait(lambda: self.loads.stat().st_size > size, 'refresh load')
        time.sleep(.15)

    def close(self):
        for process in self.workers:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=3)
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except sp.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        sp.run([self.binary, '-L', self.socket, 'kill-server'], env=self.env, capture_output=True)
        if self.master is not None:
            os.close(self.master)
            self.master = None


def refresh(ui):
    original_pid = ui.display(ui.sidebar, '#{pane_pid}')
    ui.send('/')
    ui.send('-l', 'sleep')
    before = ui.probe()
    start = ui.output.stat().st_size
    ui.delay.touch()
    ui.reload()
    ui.delay.unlink()
    raw = ui.output.read_bytes()[start:]
    # ED2/ED0 at home erase the live terminal before re-painting its rows.
    assert not re.search(rb'\x1b\[H\r?\x1b\[(?:0|2)?J', raw), \
        f'refresh blanked the sidebar before data arrived ({len(raw)} terminal bytes)'
    assert ui.probe() == before, 'refresh lost selection or search'
    ui.send('Escape')
    time.sleep(.6)
    size = ui.loads.stat().st_size
    ui.send('3')
    wait(lambda: ui.loads.stat().st_size > size and 'Buffers' in ui.screen(), 'buffer header replacement')
    size = ui.loads.stat().st_size
    ui.send('1')
    wait(lambda: ui.loads.stat().st_size > size and 'Tree' in ui.screen(), 'tree header replacement')
    # Failure/recovery must replace the sticky header without restarting fzf.
    ui.failure.touch()
    ui.reload()
    failed = ui.screen()
    assert 'sleep' not in failed and 'Tree' not in failed.splitlines()[0], 'failure retained stale tree/header'
    ui.failure.unlink()
    ui.reload()
    assert 'Tree' in ui.screen().splitlines()[0] and 'sleep' in ui.screen(), 'recovery retained failure header'
    assert ui.display(ui.sidebar, '#{pane_pid}') == original_pid, 'refresh replaced sidebar process'
    print('ok - reload preserves painted rows, selection/query and headers through view changes and recovery')


def ordering(ui):
    ui.hold.touch()
    ui.send('C-o')
    wait(ui.held.exists, 'background snapshot held after reading old metadata')
    ui.tm('rename-window', '-t', ui.pane, 'fresh-marker')
    ui.reload()
    assert 'fresh-marker' in ui.screen(), 'new refresh did not paint new metadata'
    with ui.release.open('w') as stream:
        stream.write('release\n')
    fzf_pid = sp.check_output(['pgrep', '-P', ui.display(ui.sidebar, '#{pane_pid}'), '-x', 'fzf'], text=True).strip()
    wait(lambda: sp.run(['pgrep', '-P', fzf_pid], stdout=sp.DEVNULL, stderr=sp.DEVNULL).returncode == 1,
         'held background action finished')
    ui.probe()
    assert 'fresh-marker' in ui.screen(), 'a superseded background snapshot reverted the new tree'
    print('ok - a delayed focus snapshot cannot overwrite a newer refresh')
    ui.hold.unlink()
    ui.held.unlink()


def overlapping(ui):
    ui.send('M-e')
    wait(lambda: ui.state_path_file.exists() and ui.state_path_file.stat().st_size > 0, 'live source state')
    ui.hold.touch()
    size = ui.loads.stat().st_size
    ui.send('C-r')
    wait(ui.held.exists, 'direct reload held after metadata')
    ui.hold2.touch()
    # Run the same background command with the live UI environment. Its
    # scheduling may reach sidebar-source after an already-started reload.
    background_env = ui.script_env | {'TMUX_PANE': ui.sidebar, 'TMUX_CANOPY_UI_HEADER': '1',
                                     'TMUX_CANOPY_RECORD_FORMAT': 'nul',
                                     'TMUX_CANOPY_STATE': ui.state_path_file.read_text()}
    process = sp.Popen([str(ROOT / 'scripts/jump-current')], env=background_env,
                       stdout=sp.PIPE, stderr=sp.PIPE, start_new_session=True)
    ui.workers.append(process)
    wait(ui.held2.exists, 'later focus render held after metadata')
    with ui.release.open('w') as stream:
        stream.write('release\n')
    wait(lambda: ui.loads.stat().st_size > size, 'direct reload finished')
    assert 'sleep' in ui.screen(), 'an overlapping focus render made the direct reload publish an empty list'
    with ui.release2.open('w') as stream:
        stream.write('release\n')
    _, err = process.communicate(timeout=8)
    assert process.returncode == 0, err
    print('ok - a direct reload stays populated while a later focus render is pending')


def color_at(frame, label):
    fg = bg = None
    reverse = underline = False
    for chunk in re.split(r'\x1b\[([0-9;]*)m', frame):
        if label in chunk:
            return fg, bg, reverse, underline
        if not re.fullmatch(r'[0-9;]*', chunk):
            continue
        codes = [int(code or 0) for code in chunk.split(';')]
        i = 0
        while i < len(codes):
            code = codes[i]
            if code == 0:
                fg = bg = None
                reverse = underline = False
            elif code in (4, 24):
                underline = code == 4
            elif code == 7:
                reverse = True
            elif code == 27:
                reverse = False
            elif code == 39:
                fg = None
            elif code == 49:
                bg = None
            elif 30 <= code <= 37:
                fg = code - 30
            elif 90 <= code <= 97:
                fg = code - 90 + 8
            elif 40 <= code <= 47:
                bg = code - 40
            elif 100 <= code <= 107:
                bg = code - 100 + 8
            elif code in (38, 48) and i + 2 < len(codes):
                if codes[i + 1] == 5:
                    value = codes[i + 2]
                    i += 2
                elif codes[i + 1] == 2 and i + 4 < len(codes):
                    value = tuple(codes[i + 2:i + 5])
                    i += 4
                else:
                    i += 1
                    continue
                if code == 38:
                    fg = value
                else:
                    bg = value
            i += 1
    raise AssertionError(f'no rendered {label!r} in frame')


def selection(ui):
    # Keep the window title distinct from the command so the color probe
    # samples the selected pane, not an unselected parent with the same name.
    ui.tm('rename-window', '-t', ui.pane, 'selection-window')
    ui.reload()
    # The fixture has one session, window and pane. Use cursor movement here;
    # async Ctrl-o reload ordering has its own regression scenarios.
    ui.send('C-j', 'C-j')
    for name, foreground, background in (('dark', 15, 0), ('light', 0, 15)):
        ui.tm('select-pane', '-t', ui.sidebar, '-P',
              f'fg=colour{foreground},bg=colour{background}')
        ui.reload()
        # Reload tracking keeps the pointer on the fixture's content pane.
        wait(lambda: ui.probe()[0] == 'P:' + ui.pane, 'content pane selection')
        row = next(line for line in ui.screen(ansi=True).splitlines() if 'sleep' in line)
        _, bg, reverse, underline = color_at(row, 'sleep')
        assert bg is not None and bg != background, f'{name} selected row has no distinct background'
        assert not reverse and not underline, f'{name} selection uses reverse video or underlining'
        assert color_at(row, ' ')[1] == bg, f'{name} highlight does not cover the row indentation'
        ui.send('C-k')
        wait(lambda: ui.probe()[0] != 'P:' + ui.pane, 'selection moved to parent')
        wait(lambda: color_at(ui.screen(ansi=True), 'sleep')[1] != bg, 'old row highlight cleared')
        # The old row can lose its background a frame before the parent gains it.
        try:
            wait(lambda: color_at(ui.screen(ansi=True), 'selection-window')[1] == bg,
                 'the parent window did not gain the row highlight')
        except AssertionError:
            plain = re.sub(r'\x1b\[[0-9;]*m', '', ui.screen(ansi=True))
            rows = [line for line in plain.splitlines() if 'selection-window' in line or 'sleep' in line]
            raise AssertionError(f'the parent window did not gain the row highlight; probe={ui.probe()!r}; rows={rows!r}')
        ui.send('C-j')
        wait(lambda: ui.probe()[0] == 'P:' + ui.pane, 'selection returned to content pane')
        print(f'ok - {name} selection highlights the row background without underlining and follows the pointer')


def navigation(ui, position):
    # Use actual terminal input, so the navigator's root-table decision runs.
    direction = b'\x0c' if position == 'left' else b'\x08'
    os.write(ui.master, direction)
    wait(lambda: ui.display(ui.pane, '#{pane_active}') == '1', f'{position} sidebar navigator escape')
    ui.tm('select-pane', '-t', ui.sidebar)
    time.sleep(.3)
    ui.send('/')
    ui.send('-l', 'sleeps')
    os.write(ui.master, b'\x08')
    wait(lambda: ui.probe()[2] == 'sleep', 'Ctrl-h deletes a query character')
    assert ui.display(ui.sidebar, '#{pane_active}') == '1', 'search backspace left sidebar'
    ui.send('Escape')
    time.sleep(.6)
    os.write(ui.master, direction)
    wait(lambda: ui.display(ui.pane, '#{pane_active}') == '1', 'directional escape restored after search')
    print(f'ok - {position} navigator escape and search backspace preserve their distinct behavior')


def resize(ui):
    # Replay a native hook that was queued before the user's newer resize.
    ui.tm('set-hook', '-gu', 'after-resize-pane[9001]')
    ui.tm('resize-pane', '-t', ui.sidebar, '-x', '30')
    ui.tm('resize-pane', '-t', ui.sidebar, '-x', '42')
    ui.tm('set-option', '-g', '@tmux_canopy_runtime_width', '42')
    ui.run(ROOT / 'scripts/sync-width', ui.sidebar, '30')
    assert ui.display(ui.sidebar, '#{pane_width}') == '42', 'a stale resize hook restored the old physical width'
    assert ui.display(ui.sidebar, '#{@tmux_canopy_runtime_width}') == '42', 'a stale resize hook replaced the saved width'
    # A detached new-window hook can follow the unchanged owner while the
    # new native width has not yet reached its asynchronous persistence worker.
    ui.tm('set-option', '-g', '@tmux_canopy_runtime_width', '30')
    ui.run(ROOT / 'scripts/follow', ui.client, ui.pane, '42', 'slot')
    assert ui.display(ui.sidebar, '#{pane_width}') == '42', 'a no-transition follow reapplied an old width preference'
    deadline = time.monotonic() + .3
    while time.monotonic() < deadline:
        assert ui.display(ui.sidebar, '#{pane_width}') == '42', 'ordinary layout notifications reverted the live resize'
        time.sleep(.02)
    ui.run(ROOT / 'scripts/sync-width', ui.sidebar, '42')
    assert ui.display(ui.sidebar, '#{@tmux_canopy_runtime_width}') == '42', 'the current resize did not save its preference'
    print('ok - delayed native resize callbacks preserve the newer geometry and preference')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', choices=('refresh', 'selection', 'navigation', 'ordering', 'overlapping', 'resize'))
    parser.add_argument('--navigator-source', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='canopy-stability-', ignore_cleanup_errors=True) as directory:
        root = Path(directory)
        for position in ('left', 'right') if args.only in (None, 'navigation') else ('left',):
            work = root / position
            work.mkdir()
            ui = Sidebar(work, position, args.navigator_source)
            try:
                if position == 'left':
                    if args.only in (None, 'refresh'):
                        refresh(ui)
                    if args.only in (None, 'ordering'):
                        ordering(ui)
                    if args.only in (None, 'overlapping'):
                        overlapping(ui)
                    if args.only in (None, 'selection'):
                        selection(ui)
                    if args.only in (None, 'resize'):
                        resize(ui)
                if args.only in (None, 'navigation'):
                    navigation(ui, position)
            finally:
                ui.close()


if __name__ == '__main__':
    main()
