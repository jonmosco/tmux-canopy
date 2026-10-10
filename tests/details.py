#!/usr/bin/env python3
"""Directory and branch details: settings, the canopy-branch and
canopy-directory tmux commands, and what the quiet tree shows for each."""
import os
from pathlib import Path
import re
import subprocess as sp
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SEP = '\x1f'
ANSI = re.compile(r'\x1b\[[0-9;]*m')
socket = f'canopy-details-{os.getpid()}'
env = os.environ.copy()
env.pop('TMUX', None)
env.pop('TMUX_PANE', None)


def tm(*args, check=True):
    result = sp.run(['tmux', '-L', socket, *args], env=env, text=True, capture_output=True, timeout=10)
    assert result.returncode == 0 or not check, (args, result.stderr)
    return result.stdout.strip()


def wait(condition, message, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.05)
    raise AssertionError(message)


def render(directory):
    """A mixed quiet session: the window in /work/api shows its detail."""
    with tempfile.TemporaryDirectory(prefix='canopy-details-render-') as folder:
        state = Path(folder) / 'state'
        state.write_text('')
        d = ['D', 'unicode', 'none', 'ansi', 'normal', '', '', '', '%0', '@0', '$0', '42', 'host']
        d.extend([''] * (39 - len(d)))
        d.extend(['quiet', 'branch', 'on'])
        pane = lambda pane_id, window, path: ['P', pane_id, window, '0', 'nvim', '', path, '0', '', '', '', '', '',
                                             '', '', '0', '10' + pane_id[1:]]
        records = [d, ['S', '$0', 'work', '1'],
                   ['W', '$0', '@0', '0', 'api', '1', 'off', '', '', '', '0'],
                   ['W', '$0', '@1', '1', 'web', '1', 'off', '', '', '', '0'],
                   pane('%0', '@0', '/work/api'), pane('%1', '@1', '/work/web'),
                   ['G', '%0', 'main'], ['G', '%1', 'main']]
        run = sp.run(['awk', '-v', 'stable=1', '-v', 'nul=1', '-v', f'details_directory={directory}',
                      '-f', str(ROOT / 'lib/tree-render.awk'), str(state), '-'],
                     input='\n'.join(SEP.join(r) for r in records) + '\n', text=True, capture_output=True, check=True,
                     env=os.environ | {'TMUX_CANOPY_RENDER_HOME': '/home/test'})
        return {row.split('\t')[2]: ANSI.sub('', row.split('\t')[1]).rstrip()
                for row in run.stdout.strip('\0').split('\0')}


def main():
    on, off = render('on'), render('off')
    assert on['W:@0:$0'].endswith('api ⎇ main'), on['W:@0:$0']
    assert off['W:@0:$0'].endswith(' ⎇ main') and 'api ⎇' not in off['W:@0:$0'], off['W:@0:$0']
    assert off['W:@1:$0'].endswith(' ⎇ main') and 'web ⎇' not in off['W:@1:$0'], off['W:@1:$0']
    print('ok - directory details hide on their own, leaving the branch')

    try:
        with tempfile.TemporaryDirectory(prefix='canopy-details-') as folder:
            work = Path(folder) / 'api'
            work.mkdir()
            first = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'work', '-x', '120', '-y', '30',
                       '-c', str(work), '-P', '-F', '#{pane_id}', 'sleep 600')
            # A stand-in sidebar echoes the Ctrl-r refresh it receives.
            sidebar = tm('split-window', '-d', '-h', '-t', first, '-P', '-F', '#{pane_id}', 'cat -v')
            tm('set-option', '-p', '-t', sidebar, '@tmux_canopy', '1')
            script_env = env | {'TMUX': tm('display-message', '-p', '#{socket_path},#{pid},0')}
            sp.run([str(ROOT / 'tmux-canopy.tmux')], env=script_env, check=True, timeout=30, capture_output=True)
            aliases = tm('show-options', '-s', 'command-alias')
            assert 'command-alias[9100] "canopy-branch=run-shell -b' in aliases, aliases
            assert 'command-alias[9101] "canopy-directory=run-shell -b' in aliases, aliases

            def option(name):
                return tm('show-option', '-gqv', name)

            # The tmux commands toggle; the setting starts at its default.
            tm('canopy-branch')
            wait(lambda: option('@tmux-canopy-git-context') == 'branch', 'canopy-branch shows branches')
            wait(lambda: '^R' in tm('capture-pane', '-p', '-t', sidebar), 'the open sidebar refreshes')
            tm('canopy-branch')
            wait(lambda: option('@tmux-canopy-git-context') == 'off', 'canopy-branch hides them again')
            tm('canopy-directory')
            wait(lambda: option('@tmux-canopy-directory') == 'off', 'canopy-directory hides directories')
            tm('canopy-directory')
            wait(lambda: option('@tmux-canopy-directory') == 'on', 'canopy-directory shows them again')

            def details(*args):
                return sp.run([str(ROOT / 'scripts/details'), *args], env=script_env, capture_output=True,
                              text=True, timeout=10)
            for args, value in ((('directory', 'off'), 'off'), (('directory', 'off'), 'off'),
                                (('branch', 'on'), 'branch'), (('directory', 'on'), 'on')):
                assert details(*args).returncode == 0
                setting = '@tmux-canopy-directory' if args[0] == 'directory' else '@tmux-canopy-git-context'
                assert option(setting) == value, (args, option(setting))
            for bad in (('folders',), ('branch', 'maybe'), ()):
                assert details(*bad).returncode == 2, bad

            # tree-source passes the setting to the renderer.
            tm('set-option', '-g', '@tmux_canopy_appearance', 'quiet')
            other = Path(folder) / 'web'
            other.mkdir()
            tm('new-window', '-d', '-t', 'work:', '-n', 'web', '-c', str(other), 'sleep 600')
            state = Path(folder) / 'state'
            state.write_text('')

            def tree():
                out = sp.run([str(ROOT / 'scripts/tree-source')], env=script_env | {
                    'TMUX_PANE': sidebar, 'TMUX_CANOPY_STATE': str(state)}, capture_output=True, text=True,
                    timeout=15, check=True).stdout
                return ANSI.sub('', out)
            detail = re.compile(r'1:web · sleep +web\b')
            assert detail.search(tree()), tree()
            details('directory', 'off')
            assert not detail.search(tree()), tree()
        print('ok - canopy-branch and canopy-directory toggle, refresh sidebars, and reach the tree')
    finally:
        sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True, timeout=10)


if __name__ == '__main__':
    main()
