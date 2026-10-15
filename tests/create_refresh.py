#!/usr/bin/env python3
"""Pane-create refresh hook and transition-guarded sidebar reloads."""
import os
from pathlib import Path
import shlex
import subprocess as sp
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    socket = f'canopy-create-refresh-{os.getpid()}'
    env = os.environ.copy()
    env.pop('TMUX', None)
    env.pop('TMUX_PANE', None)
    executable = 'tmux'

    def tm(*args):
        result = sp.run([executable, '-L', socket, *args], env=env, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, (args, result.stderr)
        return result.stdout.strip()

    with tempfile.TemporaryDirectory(prefix='canopy-create-refresh-') as directory:
        temp = Path(directory)
        deliveries = temp / 'deliveries'
        deliveries.touch()
        release_gate = temp / 'release-agent'
        release_ready = temp / 'agent-ready'
        gate_enabled = temp / 'gate-enabled'
        os.mkfifo(release_gate)
        try:
            pane = tm('-f', '/dev/null', 'new-session', '-d', '-x', '120', '-y', '40', '-P', '-F', '#{pane_id}', 'sleep 600')
            env['TMUX'] = tm('display-message', '-p', '-t', pane, '#{socket_path},#{pid},0')
            load = sp.run(['bash', str(ROOT / 'tmux-canopy.tmux')], env=env, capture_output=True, text=True, timeout=30)
            assert load.returncode == 0 and not load.stderr, load.stderr

            sidebar = tm('split-window', '-d', '-h', '-l', '42', '-t', pane, '-P', '-F', '#{pane_id}', 'sleep 600')
            tm('set-option', '-p', '-t', sidebar, '@tmux_canopy', '1')
            tm('set-option', '-p', '-t', sidebar, '@tmux_canopy_client', '/dev/test')

            real_tmux = sp.run(['bash', '-c', 'command -v tmux'], capture_output=True, text=True, check=True).stdout.strip()
            wrapper = temp / 'tmux'
            wrapper.write_text(
                '#!/bin/bash\n'
                'if [[ "$1" == send-keys ]]; then\n'
                f'  printf "%s\\n" "$*" >> {shlex.quote(str(deliveries))}\n'
                'fi\n'
                f'if [[ -e {shlex.quote(str(gate_enabled))} && "$1" == if-shell && "$*" == *"set-option -gu @tmux_canopy_agent_refresh_pending"* ]]; then\n'
                f'  printf x > {shlex.quote(str(release_ready))}\n'
                f'  IFS= read -r _ < {shlex.quote(str(release_gate))}\n'
                'fi\n'
                f'exec {shlex.quote(real_tmux)} -L {shlex.quote(socket)} "$@"\n'
            )
            wrapper.chmod(0o755)
            wrapped = env | {'PATH': str(temp) + ':' + env['PATH']}
            tm('set-environment', '-g', 'PATH', wrapped['PATH'])

            sp.run([str(ROOT / 'scripts/cleanup'), 'split'], env=wrapped, check=True, timeout=15)
            assert any(sidebar in line and 'C-r' in line for line in deliveries.read_text().splitlines()), \
                deliveries.read_text()

            sp.run([str(ROOT / 'scripts/cleanup'), 'refresh'], env=wrapped, check=True, timeout=15)
            assert sum(sidebar in line and 'C-r' in line for line in deliveries.read_text().splitlines()) == 2, \
                deliveries.read_text()

            guard = sp.run(
                ['bash', '-c',
                 f'source "{ROOT}/scripts/lib.sh"; sidebar_transition_option "/dev/test"'],
                capture_output=True, text=True, check=True).stdout.strip()
            tm('set-option', '-g', guard, '1')
            mid = deliveries.read_text()
            sp.run([str(ROOT / 'scripts/cleanup'), 'refresh'], env=wrapped, check=True, timeout=15)
            assert deliveries.read_text() == mid, deliveries.read_text()
            tm('set-option', '-gu', guard)

            print('ok - split refresh hook installed; refresh_sidebars respects transition guards')

            # Exercise the installed split hook rather than replacing it with
            # a copy of its condition. Disable unrelated kill refreshes here.
            tm('set-hook', '-gu', 'after-kill-pane[9003]')
            tm('set-option', '-pu', '-t', sidebar, '@tmux_canopy')
            before_split = deliveries.stat().st_size
            created = tm('split-window', '-d', '-t', pane, '-P', '-F', '#{pane_id}', 'sleep 600')
            assert deliveries.stat().st_size == before_split, 'a split with no sidebar requested a reload'
            tm('kill-pane', '-t', created)
            tm('set-option', '-p', '-t', sidebar, '@tmux_canopy', '1')
            created = tm('split-window', '-d', '-t', pane, '-P', '-F', '#{pane_id}', 'sleep 600')
            assert deliveries.stat().st_size > before_split, 'the installed split hook did not refresh the sidebar'
            tm('kill-pane', '-t', created)
            print('ok - the installed split hook refreshes only when a sidebar exists')

            # Hold the real worker at its release point so this is one pending
            # burst regardless of process startup/scheduler speed. Sequential
            # calls can legitimately span multiple 120ms refresh windows.
            tm('set-option', '-g', '@tmux-canopy-agents', 'on')
            gate_enabled.touch()
            sp.run([str(ROOT / 'scripts/agent-refresh')], env=wrapped, check=True, timeout=15)
            deadline = time.monotonic() + 5
            while not release_ready.exists() and time.monotonic() < deadline:
                time.sleep(.02)
            assert release_ready.exists(), 'the pending worker did not reach its release gate'
            # The worker is artificially paused; freeze claim expiry as well.
            tm('set-option', '-g', '@tmux_canopy_agent_refresh_deadline', '9999999999')
            before = sum(sidebar in line and 'C-r' in line for line in deliveries.read_text().splitlines())
            jobs = [sp.Popen([str(ROOT / 'scripts/agent-refresh')], env=wrapped,
                             stdout=sp.DEVNULL, stderr=sp.PIPE) for _ in range(6)]
            for job in jobs:
                _, err = job.communicate(timeout=15)
                assert job.returncode == 0, err
            gate_enabled.unlink()
            with release_gate.open('w') as stream:
                stream.write('release\n')
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and (
                tm('show-option', '-gqv', '@tmux_canopy_agent_refresh_pending') or
                sum(sidebar in line and 'C-r' in line for line in deliveries.read_text().splitlines()) == before
            ):
                time.sleep(.02)
            after = sum(sidebar in line and 'C-r' in line for line in deliveries.read_text().splitlines())
            assert after - before == 1, deliveries.read_text()
            assert tm('show-option', '-gqv', '@tmux_canopy_agent_refresh_pending') == ''
            sp.run([str(ROOT / 'scripts/agent-refresh')], env=wrapped, check=True, timeout=15)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and (
                tm('show-option', '-gqv', '@tmux_canopy_agent_refresh_pending') or
                sum(sidebar in line and 'C-r' in line for line in deliveries.read_text().splitlines()) == after
            ):
                time.sleep(.02)
            assert sum(sidebar in line and 'C-r' in line for line in deliveries.read_text().splitlines()) - after == 1
            print('ok - concurrent requests share one pending refresh; a later event starts another')
        finally:
            sp.run(['tmux', '-L', socket, 'kill-server'], capture_output=True)


if __name__ == '__main__':
    main()
