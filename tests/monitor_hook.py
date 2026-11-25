#!/usr/bin/env python3
"""The tmux 3.8 pane-command monitor installs once and ignores Canopy's panes.

tmux 3.8 added monitor hooks: `set-hook -B name:what:format` re-checks a format
once a second and runs the hook when its value changes. Canopy registers one so
the Agents view notices a pane's foreground command changing without polling.

`-B` takes the subscription as its own argument, so it cannot be bundled with
other flags. `-Bgu` made tmux read "gu" as the subscription and `-B -g` made it
read "-g" as the command; both failed behind `2>/dev/null` and the monitor was
never installed at all. Older tmux has no `-B`, where installing nothing is the
correct outcome.
"""
import os
from pathlib import Path
import shutil
import subprocess as sp
import sys

ROOT = Path(__file__).resolve().parents[1]
SOCKET = 'canopy-monitor-hook-%d' % os.getpid()
TMUX = shutil.which('tmux')


def tmux(*args):
    return sp.run([TMUX, '-L', SOCKET, *args], env=ENV, text=True,
                  capture_output=True, timeout=15)


def value(*args):
    result = tmux(*args)
    assert result.returncode == 0, (args, result.stderr)
    return result.stdout.strip()


ENV = {k: v for k, v in os.environ.items() if k not in ('TMUX', 'TMUX_PANE')}
ENV['TERM'] = 'xterm-256color'


def subscriptions():
    """The @tmux_canopy_command monitors tmux currently has registered."""
    result = tmux('show-hooks', '-g', '-B')
    assert result.returncode == 0, result.stderr
    return [line for line in result.stdout.splitlines()
            if line.startswith('@tmux_canopy_command:')]


def main():
    if TMUX is None:
        print('skip - monitor_hook: no tmux on PATH')
        return
    try:
        content = value('-f', '/dev/null', 'new-session', '-d', '-s', 'one',
                        '-x', '80', '-y', '24', '-P', '-F', '#{pane_id}', 'sleep 600')
        script_env = ENV | {
            'TMUX': value('display-message', '-p', '#{socket_path},#{pid},0')}

        # Probe the capability instead of parsing a version: tmux without
        # monitor hooks rejects the flag outright.
        supported = tmux('show-hooks', '-g', '-B').returncode == 0

        load = sp.run([str(ROOT / 'tmux-canopy.tmux')], env=script_env,
                      capture_output=True, text=True, timeout=30)
        assert load.returncode == 0, load.stderr

        if not supported:
            # The plugin must still load cleanly and complain about nothing.
            assert 'unknown flag' not in load.stderr, load.stderr
            print('skip - monitor_hook: this tmux has no set-hook -B '
                  '(monitor hooks arrived in 3.8)')
            return

        registered = subscriptions()
        assert len(registered) == 1, ('exactly one monitor should be registered',
                                      registered)

        # Loading again must not stack a second subscription: the plugin unsets
        # by name first, which covers any format registered by an older load.
        sp.run([str(ROOT / 'tmux-canopy.tmux')], env=script_env, check=True, timeout=30)
        assert subscriptions() == registered, ('a reload replaced, not stacked',
                                               subscriptions())
        print('ok - the pane-command monitor installs once and survives a reload')

        # Evaluate the format tmux actually stored, rather than matching its
        # text: it must report a content pane's command and nothing for the
        # sidebar and slot panes, so Canopy's own panes start no refresh.
        fmt = registered[0].split(':', 2)[2]
        assert value('display-message', '-p', '-t', content, fmt) == 'sleep', fmt

        sidebar = value('split-window', '-d', '-t', content, '-P', '-F', '#{pane_id}', 'sleep 600')
        slot = value('split-window', '-d', '-t', content, '-P', '-F', '#{pane_id}', 'sleep 600')
        tmux('set-option', '-p', '-t', sidebar, '@tmux_canopy', '1')
        tmux('set-option', '-p', '-t', slot, '@tmux_canopy_slot', '1')
        assert value('display-message', '-p', '-t', sidebar, fmt) == '', 'sidebar pane is ignored'
        assert value('display-message', '-p', '-t', slot, fmt) == '', 'slot pane is ignored'
        assert value('display-message', '-p', '-t', content, fmt) == 'sleep', 'content pane still reports'
        print('ok - the monitored format ignores sidebar and slot panes')

        # doctor is where a user would look to see whether it is active.
        doctor = sp.run([sys.executable, str(ROOT / 'canopy'), 'doctor'],
                        env=script_env, capture_output=True, text=True, timeout=30)
        assert doctor.returncode == 0, doctor.stderr
        line = next((row.strip() for row in doctor.stdout.splitlines()
                     if row.strip().startswith('monitor:')), None)
        assert line is not None and '@tmux_canopy_command' in line, doctor.stdout
        print('ok - canopy doctor reports the monitor')
    finally:
        sp.run([TMUX, '-L', SOCKET, 'kill-server'], env=ENV, capture_output=True)


if __name__ == '__main__':
    main()
