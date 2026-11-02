#!/usr/bin/env python3
"""Focus hooks start no shell while no sidebar exists, and run once one does."""
import os
from pathlib import Path
import shutil
import subprocess as sp
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    socket = f'canopy-hook-gating-{os.getpid()}'
    env = os.environ.copy()
    env.pop('TMUX', None)
    env.pop('TMUX_PANE', None)

    def tm(*args):
        result = sp.run(['tmux', '-L', socket, *args], env=env, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, (args, result.stderr)
        return result.stdout.strip()

    try:
        with tempfile.TemporaryDirectory(prefix='canopy-hook-gating-') as directory:
            # Load the plugin from a copy whose follow and refresh-sidebar only
            # record that they ran, so the test sees every shell the hooks start.
            plugin = Path(directory) / 'plugin'
            shutil.copytree(ROOT, plugin, ignore=shutil.ignore_patterns(
                '.git', 'docs', 'tests', '__pycache__', '*.png', '*.gif'))
            log = Path(directory) / 'ran'
            log.touch()
            for name in ('follow', 'refresh-sidebar'):
                stub = plugin / 'scripts' / name
                stub.write_text(f'#!/usr/bin/env bash\nprintf "%s\\n" "{name}" >> "{log}"\n')
                stub.chmod(0o755)

            first = tm('-f', '/dev/null', 'new-session', '-d', '-P', '-F', '#{pane_id}', 'sleep 180')
            env['TMUX'] = tm('display-message', '-p', '-t', first, '#{socket_path},#{pid},0')
            tm('set-option', '-g', '@tmux-canopy-scope', 'global')
            loaded = sp.run(['bash', str(plugin / 'tmux-canopy.tmux')], env=env, capture_output=True,
                            text=True, timeout=30)
            assert loaded.returncode == 0 and not loaded.stderr, loaded.stderr

            def ran():
                return log.read_text().split()

            def churn():
                """Switch focus every way the hooks listen for."""
                second = tm('new-window', '-d', '-P', '-F', '#{pane_id}', 'sleep 180')
                tm('select-window', '-t', second)
                tm('split-window', '-d', '-t', second, 'sleep 180')
                tm('select-pane', '-t', second)
                tm('select-window', '-t', first)

            # The hooks are conditional in tmux itself, not just quiet when they run.
            for hook in ('after-select-pane', 'after-select-window', 'after-new-window'):
                shown = tm('show-hooks', '-g', hook)
                assert 'if-shell -F' in shown and '@tmux_canopy' in shown, (hook, shown)
            print('ok - follow and the focus refresh are guarded by a sidebar-exists condition')

            churn()
            time.sleep(1.0)
            assert ran() == [], f'a shell started with no sidebar anywhere: {ran()}'
            print('ok - with no sidebar, switching panes and windows starts no follow or refresh shell')

            # A sidebar anywhere turns them back on (each exits for clients that own none).
            tm('set-option', '-p', '-t', first, '@tmux_canopy', '1')
            churn()
            deadline = time.time() + 5
            while time.time() < deadline and not {'follow', 'refresh-sidebar'} <= set(ran()):
                time.sleep(0.1)
            assert {'follow', 'refresh-sidebar'} <= set(ran()), ran()
            print('ok - once a sidebar exists, the same switches run follow and the focus refresh')
    finally:
        sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)


if __name__ == '__main__':
    main()
