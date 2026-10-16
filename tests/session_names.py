#!/usr/bin/env python3
"""S names a new session after the git repository, or session-N otherwise."""
import os
from pathlib import Path
import subprocess as sp
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    socket = f'canopy-session-names-{os.getpid()}'
    env = os.environ.copy()
    env.pop('TMUX', None)
    env.pop('TMUX_PANE', None)

    def tm(*args):
        result = sp.run(['tmux', '-L', socket, *args], env=env, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, (args, result.stderr)
        return result.stdout.strip()

    def create(pane):
        state = Path(temp) / 'state'
        state.touch()
        run_env = env | {
            'TMUX_PANE': pane,
            'TMUX_CANOPY_STATE': str(state),
            'TMUX_CANOPY_CLIENT': '',
            'TMUX_CANOPY_WIDTH': '42',
            'TMUX_CANOPY_SCOPE': 'window',
        }
        result = sp.run([str(ROOT / 'scripts/tree-action'), 'create-session', f'P:{pane}'],
                        env=run_env, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stderr
        names = tm('list-sessions', '-F', '#{session_name}').splitlines()
        return [name for name in names if name != 'origin']

    try:
        with tempfile.TemporaryDirectory(prefix='canopy-session-names-') as directory:
            global temp
            temp = Path(directory)
            repo = temp / 'my.project'
            repo.mkdir()
            sp.run(['git', 'init', '-q', str(repo)], check=True, capture_output=True)
            plain = temp / 'scratch'
            plain.mkdir()
            linked = temp / 'linked'
            linked.mkdir()
            (linked / '.git').write_text('gitdir: /nowhere\n')

            pane = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'origin', '-c', str(repo),
                      '-P', '-F', '#{pane_id}', 'sleep 180')
            env['TMUX'] = tm('display-message', '-p', '-t', pane, '#{socket_path},#{pid},0')

            assert create(pane) == ['my-project'], 'a repository session uses the root name, with . and : turned into -'

            again = create(pane)
            assert 'session-1' in again and 'my-project' in again, again

            tm('new-window', '-d', '-t', 'origin:', '-c', str(plain), '-n', 'plain')
            plain_pane = tm('display-message', '-p', '-t', 'origin:plain', '#{pane_id}')
            outside = create(plain_pane)
            assert 'session-2' in outside, outside

            tm('new-window', '-d', '-t', 'origin:', '-c', str(linked), '-n', 'linked')
            linked_pane = tm('display-message', '-p', '-t', 'origin:linked', '#{pane_id}')
            worktree = create(linked_pane)
            assert 'linked' in worktree, worktree
        print('ok - new sessions are named for the git repository, or session-N')
    finally:
        sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)


if __name__ == '__main__':
    main()
