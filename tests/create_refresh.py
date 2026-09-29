#!/usr/bin/env python3
"""Pane-create refresh hook and transition-guarded sidebar reloads."""
import os
from pathlib import Path
import shlex
import subprocess as sp
import tempfile

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
        try:
            pane = tm('-f', '/dev/null', 'new-session', '-d', '-x', '120', '-y', '40', '-P', '-F', '#{pane_id}', 'sleep 600')
            env['TMUX'] = tm('display-message', '-p', '-t', pane, '#{socket_path},#{pid},0')
            load = sp.run(['bash', str(ROOT / 'tmux-canopy.tmux')], env=env, capture_output=True, text=True, timeout=30)
            assert load.returncode == 0 and not load.stderr, load.stderr
            hooks = tm('show-hooks', '-g')
            split_hook = next((line for line in hooks.splitlines() if line.startswith('after-split-window[9003]')), '')
            assert split_hook and "cleanup' 'split'" in split_hook, hooks

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
                f'exec {shlex.quote(real_tmux)} -L {shlex.quote(socket)} "$@"\n'
            )
            wrapper.chmod(0o755)
            wrapped = env | {'PATH': str(temp) + ':' + env['PATH']}

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
        finally:
            sp.run(['tmux', '-L', socket, 'kill-server'], capture_output=True)


if __name__ == '__main__':
    main()
