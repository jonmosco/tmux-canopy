#!/usr/bin/env python3
"""Stock macOS Bash 3.2 gets one clear message, not a wall of syntax errors."""
import os
from pathlib import Path
import re
import subprocess as sp

ROOT = Path(__file__).resolve().parents[1]
OLD = '/bin/bash'


def version(path):
    result = sp.run([path, '-c', 'echo "${BASH_VERSINFO[0]} ${BASH_VERSINFO[1]}"'], capture_output=True, text=True)
    major, minor = (int(part) for part in result.stdout.split())
    return major, minor


def main():
    if not os.path.exists(OLD) or version(OLD) >= (4, 4):
        print(f'skip - {OLD} is Bash 4.4 or newer here; only macOS ships an old one')
        return
    socket = f'canopy-old-bash-{os.getpid()}'
    env = {k: v for k, v in os.environ.items() if k not in ('TMUX', 'TMUX_PANE')}
    try:
        sp.run(['tmux', '-L', socket, '-f', '/dev/null', 'new-session', '-d', '-s', 'one'], env=env, check=True)
        tmux = sp.run(['tmux', '-L', socket, 'display-message', '-p', '#{socket_path},#{pid},0'],
                      env=env, capture_output=True, text=True, check=True).stdout.strip()
        result = sp.run([OLD, str(ROOT / 'tmux-canopy.tmux')], env=env | {'TMUX': tmux},
                        capture_output=True, text=True, timeout=30)
        assert result.returncode != 0, 'an unsupported Bash must not look like a successful load'
        assert 'Bash 4.4' in result.stderr and 'brew install bash' in result.stderr, result.stderr
        assert len(result.stderr.strip().splitlines()) == 1, result.stderr
        assert not re.search(r'declare|syntax error|invalid option', result.stderr), result.stderr
        keys = sp.run(['tmux', '-L', socket, 'list-keys'], env=env, capture_output=True, text=True).stdout
        assert 'scripts/navigate' not in keys, 'a refused load must not install bindings'
        print('ok - Bash 3.2 prints one clear message, fails, and installs nothing')
    finally:
        sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)


if __name__ == '__main__':
    main()
