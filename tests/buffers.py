#!/usr/bin/env python3
"""Lossless buffer identities across source, preview, paste and deletion."""
import os
from pathlib import Path
import shlex
import subprocess as sp
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    socket = f'canopy-buffers-test-{os.getpid()}'
    env = os.environ.copy()
    env.pop('TMUX', None)
    env.pop('TMUX_PANE', None)

    def tm(*args):
        result = sp.run(['tmux', '-L', socket, *args], env=env, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, (args, result.stderr)
        return result.stdout

    def run(script, *args):
        return sp.check_output([str(ROOT/'scripts'/script), *args], env=env, text=True, timeout=10)

    def delete(token):
        # Buffer deletion arms on the first x and confirms on the second.
        run('sidebar-action', 'delete', token)
        run('sidebar-action', 'delete', token)

    with tempfile.TemporaryDirectory(prefix='canopy-buffers-', ignore_cleanup_errors=True) as directory:
        try:
            pane = tm('-f', '/dev/null', 'new-session', '-d', '-P', '-F', '#{pane_id}', 'cat').strip()
            env['TMUX'] = tm('display-message', '-p', '-t', pane, '#{socket_path},#{pid},0').strip()
            env['TMUX_PANE'] = pane
            state = Path(directory)/'state'
            state.write_text('VIEW\tbuffers\n')
            env['TMUX_CANOPY_STATE'] = str(state)
            tm('set-option', '-g', '@tmux-canopy-theme', 'mono')
            tm('set-option', '-p', '-t', pane, '@tmux_canopy_target', pane)
            marker = Path(directory)/'must-not-exist'
            names = ['release', 'release|notes', 'B2:6162', 'hex:ab', 'slash\\path', 'spaced name',
                     'quote\'"$`', '#{version}', '#(touch '+str(marker)+')', '日本語-🪴']
            expected = {name: f'payload-{i:02d}' for i,name in enumerate(names)}
            for name,content in expected.items(): tm('set-buffer', '-b', name, content)
            # tmux canonicalizes backslashes when naming a buffer at creation.
            expected = {name.replace('\\', '\\\\'): value for name,value in expected.items()}
            names = list(expected)
            rows = [row.split('\t') for row in run('sidebar-source','--stable','--read0').rstrip('\0').split('\0')]
            tokens = {bytes.fromhex(row[0][3:]).decode(): row[0] for row in rows if row[0].startswith('B2:')}
            assert set(tokens) == set(names) and all(len(row)==3 for row in rows), (tokens, names, rows)
            assert len({row[2] for row in rows}) == len(rows)
            assert not marker.exists()
            for name, token in tokens.items():
                assert expected[name] in run('sidebar-preview', token)
                run('sidebar-action', 'activate', token)
                deadline = time.monotonic()+3
                while expected[name] not in tm('capture-pane','-p','-t',pane):
                    assert time.monotonic()<deadline, name
                    time.sleep(.03)
            before = tm('list-buffers','-F','#{buffer_name}')
            for token in ('B2:', 'B2:1', 'B2:gg', 'B2:00', 'B2:610062'):
                run('sidebar-action','delete',token)
                assert run('sidebar-preview',token) == ''
            assert tm('list-buffers','-F','#{buffer_name}') == before
            # One x only arms; arming another buffer moves the pending delete.
            run('sidebar-action','delete',tokens['release|notes'])
            assert 'release|notes' in tm('list-buffers','-F','#{buffer_name}').splitlines()
            assert 'DELETE\t' + tokens['release|notes'] + '\t' in state.read_text()
            run('sidebar-action','delete',tokens['spaced name'])
            run('sidebar-action','delete',tokens['release|notes'])
            assert {'release|notes', 'spaced name'} <= set(tm('list-buffers','-F','#{buffer_name}').splitlines())
            run('sidebar-action','delete',tokens['release|notes'])
            assert 'release|notes' not in tm('list-buffers','-F','#{buffer_name}').splitlines()
            assert 'DELETE\t' not in state.read_text()
            assert tm('show-buffer','-b','release').strip() == expected['release']
            # An expired arm does not confirm.
            state.write_text('VIEW\tbuffers\nDELETE\t' + tokens['spaced name'] + '\t1\n')
            run('sidebar-action','delete',tokens['spaced name'])
            assert 'spaced name' in tm('list-buffers','-F','#{buffer_name}').splitlines()
            print('ok - buffer deletion needs a second x within the confirmation window')
            names.remove('release|notes')
            for name in names:
                delete(tokens[name])
                assert name not in tm('list-buffers','-F','#{buffer_name}').splitlines()
            assert not marker.exists()
            # Yank pipes buffer bytes through the configured clipboard command,
            # bypassing the OS clipboard cascade so the test is deterministic.
            clip_marker = Path(directory)/'clipboard-output'
            tm('set-option', '-g', '@tmux-canopy-copy-command', f'cat > {shlex.quote(str(clip_marker))}')
            tm('set-buffer', '-b', 'clip-source', 'yanked-payload')
            rows = [row.split('\t') for row in run('sidebar-source','--stable','--read0').rstrip('\0').split('\0')]
            clip_token = next(row[0] for row in rows
                               if row[0].startswith('B2:') and bytes.fromhex(row[0][3:]).decode() == 'clip-source')
            run('sidebar-action', 'yank', clip_token)
            deadline = time.monotonic()+3
            while not clip_marker.exists():
                assert time.monotonic()<deadline, 'yank did not run the configured clipboard command'
                time.sleep(.03)
            assert clip_marker.read_text() == 'yanked-payload'
            delete(clip_token)
            tm('set-option', '-gu', '@tmux-canopy-copy-command')
            print('ok - yank pipes a buffer through the configured clipboard command')
            # Samples cannot forge extra source records or ANSI styling.
            tm('set-buffer','-b','sample','tab\tnewline\nB:forged\x1b[31m')
            rows = [r.split('\t') for r in run('sidebar-source','--stable','--read0').rstrip('\0').split('\0')]
            assert len(rows)==2 and all(len(r)==3 and '\n' not in r[1] and '\x1b' not in r[1] for r in rows)
            delete('B:sample')
            assert tm('list-buffers') == ''
            print('ok - separator, quoting, Unicode and format-like buffer names round-trip through preview/paste/delete')
            print('ok - malformed tokens are rejected, samples cannot forge records, and legacy rows still work')
        finally:
            sp.run(['tmux','-L',socket,'kill-server'],env=env,stdout=sp.DEVNULL,stderr=sp.DEVNULL)


if __name__ == '__main__':
    main()
