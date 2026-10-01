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

            # Server-wide hooks are gated inside tmux: splits with no sidebar and
            # resizes of ordinary panes start no shell.
            hook_lines = tm('show-hooks', '-g').splitlines()
            for name in ('after-split-window[9003]', 'after-resize-pane[9001]', 'after-resize-pane[9006]'):
                line = next((line for line in hook_lines if line.startswith(name)), '')
                assert line.startswith(name + ' if-shell -F '), line
            marker = temp / 'split-ran'
            tm('set-hook', '-g', 'after-split-window[9003]',
               f"if-shell -F '#{{S:#{{W:#{{P:#{{?#{{==:#{{@tmux_canopy}},1}},1,}}}}}}}}' 'run-shell \"touch {marker}\"'")
            tm('set-option', '-pu', '-t', sidebar, '@tmux_canopy')
            tm('kill-pane', '-t', tm('split-window', '-d', '-t', pane, '-P', '-F', '#{pane_id}', 'sleep 600'))
            assert not marker.exists(), 'split hook ran with no sidebar on the server'
            tm('set-option', '-p', '-t', sidebar, '@tmux_canopy', '1')
            tm('kill-pane', '-t', tm('split-window', '-d', '-t', pane, '-P', '-F', '#{pane_id}', 'sleep 600'))
            assert marker.exists(), 'split hook skipped although a sidebar exists'
            print('ok - split and resize hooks are gated inside tmux')

            # A burst of pane-command events (zsh -> ls -> zsh ...) shares one
            # delayed worker and one reload per agent-mode sidebar.
            import time
            tm('set-option', '-g', '@tmux-canopy-agents', 'on')
            tm('set-environment', '-g', 'PATH', wrapped['PATH'])
            before = sum(sidebar in line and 'C-r' in line for line in deliveries.read_text().splitlines())
            for _ in range(6):
                sp.run([str(ROOT / 'scripts/agent-refresh')], env=wrapped, check=True, timeout=15)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and tm('show-option', '-gqv', '@tmux_canopy_agent_refresh_pending'):
                time.sleep(.05)
            time.sleep(.2)
            after = sum(sidebar in line and 'C-r' in line for line in deliveries.read_text().splitlines())
            assert after - before == 1, deliveries.read_text()
            assert tm('show-option', '-gqv', '@tmux_canopy_agent_refresh_pending') == ''
            # A later event after the claim is released starts a new refresh.
            sp.run([str(ROOT / 'scripts/agent-refresh')], env=wrapped, check=True, timeout=15)
            time.sleep(.5)
            assert sum(sidebar in line and 'C-r' in line for line in deliveries.read_text().splitlines()) - after == 1
            print('ok - pane-command refresh bursts coalesce into one reload')
        finally:
            sp.run(['tmux', '-L', socket, 'kill-server'], capture_output=True)


if __name__ == '__main__':
    main()
