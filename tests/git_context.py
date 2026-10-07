#!/usr/bin/env python3
"""Optional Git labels use one lookup per repository on private tmux."""
import fcntl
import os
from pathlib import Path
import pty
import shlex
import shutil
import struct
import subprocess as sp
import tempfile
import termios
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
GIT = shutil.which('git')


def main():
    if not GIT:
        print('ok - git context skipped (git not installed)')
        return
    socket = f'canopy-git-test-{os.getpid()}'
    tmux = shutil.which('tmux')
    env = os.environ.copy()
    env.pop('TMUX', None)
    env.pop('TMUX_PANE', None)
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               GIT_AUTHOR_NAME='Test', GIT_AUTHOR_EMAIL='test@example.com',
               GIT_COMMITTER_NAME='Test', GIT_COMMITTER_EMAIL='test@example.com')
    with tempfile.TemporaryDirectory(prefix='canopy-git-') as folder:
        temp = Path(folder)
        first = temp / 'app space'
        other = temp / 'second'
        plain = temp / 'ordinary'
        nested = first / 'src'
        for path in (nested, other, plain):
            path.mkdir(parents=True)
        for repo, branch in ((first, 'feature/alpha'), (other, 'fix/beta')):
            sp.run([GIT, 'init', '-q', str(repo)], env=env, check=True)
            sp.run([GIT, '-C', str(repo), 'symbolic-ref', 'HEAD', f'refs/heads/{branch}'], env=env, check=True)
        sp.run([GIT, '-C', str(first), 'commit', '-q', '--allow-empty', '-m', 'init'], env=env, check=True)
        worktree = temp / 'linked worktree'
        sp.run([GIT, '-C', str(first), 'worktree', 'add', '-q', '-b', 'feature/wt', str(worktree)],
               env=env, check=True)
        log = temp / 'git-calls'
        fake = temp / 'bin'
        fake.mkdir()
        wrapper = fake / 'git'
        wrapper.write_text('#!/bin/sh\nprintf "call\\n" >> "$CANOPY_GIT_LOG"\nexec ' + shlex.quote(GIT) + ' "$@"\n')
        wrapper.chmod(0o755)
        env['CANOPY_GIT_LOG'] = str(log)
        env['PATH'] = str(fake) + ':' + env['PATH']
        # The sidebar's fzf load hook writes its ready marker under TMPDIR.
        # A painted row can precede that hook (especially on slower runners).
        env['TMPDIR'] = str(temp)
        state = temp / 'state'
        state.touch()

        def tm(*args):
            p = sp.run([tmux, '-L', socket, *args], env=env, capture_output=True, text=True, timeout=15)
            assert p.returncode == 0, (args, p.stderr)
            return p.stdout.strip()

        client_process = None
        master = None
        try:
            a = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'app', '-x', '120', '-y', '35',
                   '-c', str(nested), '-P', '-F', '#{pane_id}', 'sleep 600')
            b = tm('new-window', '-d', '-t', 'app:', '-c', str(other), '-P', '-F', '#{pane_id}', 'sleep 600')
            c = tm('new-window', '-d', '-t', 'app:', '-c', str(plain), '-P', '-F', '#{pane_id}', 'sleep 600')
            d = tm('new-window', '-d', '-t', 'app:', '-c', str(first), '-P', '-F', '#{pane_id}', 'sleep 600')
            e = tm('new-window', '-d', '-t', 'app:', '-c', str(worktree), '-P', '-F', '#{pane_id}', 'sleep 600')
            mixed = tm('split-window', '-d', '-h', '-t', a, '-c', str(other),
                       '-P', '-F', '#{pane_id}', 'sleep 600')
            for pane, path in ((a, nested), (b, other), (c, plain), (d, first), (e, worktree),
                               (mixed, other)):
                assert tm('display-message', '-p', '-t', pane, '#{pane_current_path}') == str(path)
            script_env = env | {'TMUX': tm('display-message', '-p', '#{socket_path},#{pid},0'),
                                'TMUX_PANE': a, 'TMUX_CANOPY_STATE': str(state)}
            tm('set-option', '-g', '@tmux-canopy-theme', 'mono')
            tm('set-option', '-g', '@tmux_canopy_appearance', 'places')

            def run(script, *args, **extra):
                p = sp.run([str(ROOT / 'scripts' / script), *args], env=script_env | extra,
                           capture_output=True, text=True, timeout=15)
                assert p.returncode == 0, (script, p.stderr)
                return p.stdout

            def rows():
                return {row.split('\t')[0]: row.split('\t')[1] for row in run('tree-source').splitlines()}

            assert not any('feature/alpha' in line or 'fix/beta' in line for line in rows().values())
            assert not log.exists(), 'off mode started git'
            tm('set-option', '-g', '@tmux-canopy-git-context', 'branch')
            labels = rows()
            assert log.read_text().count('call') == 3, log.read_text()
            assert any('feature/alpha' in text for key, text in labels.items() if key.startswith('DIR:')), labels
            assert any('fix/beta' in text for key, text in labels.items() if key.startswith('DIR:'))
            assert any('feature/wt' in text for key, text in labels.items() if key.startswith('DIR:'))
            assert not any('git:' in text or '⎇' in text for key, text in labels.items()
                           if key == f'P:{c}')
            redirected = run('tree-source', GIT_DIR=str(other / '.git'))
            assert 'feature/alpha' in redirected and 'feature/wt' in redirected, \
                'inherited Git environment redirected a pane to a different repository'
            assert all('feature/alpha' not in text for key, text in labels.items() if key.startswith('S:'))
            assert not any('feature/alpha' in text or 'fix/beta' in text for key, text in labels.items()
                           if key.startswith('W:')), 'mixed windows must not claim one branch'
            print('ok - Git roots are deduplicated, scoped to panes, and opt-in')

            tm('set-option', '-g', '@tmux_canopy_appearance', 'quiet')
            quiet_labels = rows()
            assert any('feature/alpha' in value for key, value in quiet_labels.items() if key.startswith('DIR:'))
            assert not any('feature/alpha' in value or 'fix/beta' in value for key, value in quiet_labels.items()
                           if key.startswith(('S:', 'W:'))), 'quiet must keep branches on their directory'
            for appearance in ('classic', 'pills', 'lazygit'):
                tm('set-option', '-g', '@tmux_canopy_appearance', appearance)
                tm('set-option', '-g', '@tmux-canopy-density', 'compact')
                output = rows()
                assert any('feature/alpha' in text for key, text in output.items()
                           if key in (f'P:{a}', f'P:{d}') or key.startswith('W:')), (appearance, output)
                assert any('fix/beta' in text for key, text in output.items()
                           if key == f'P:{b}' or key.startswith('W:')), (appearance, output)
            tm('set-option', '-g', '@tmux-canopy-density', 'minimal')
            assert any('feature/alpha' in value for value in rows().values()), 'minimal lost Git labels'
            tm('set-option', '-g', '@tmux_canopy_appearance', 'places')
            tm('set-option', '-g', '@tmux_canopy_icon_theme', 'ascii')
            assert any('[git:feature/alpha]' in value for value in rows().values())
            tm('set-option', '-g', '@tmux_canopy_appearance', 'quiet')
            assert any('[git:feature/alpha]' in value for value in rows().values())
            tm('set-option', '-g', '@tmux_canopy_appearance', 'places')
            print('ok - branch labels render across appearances, density, and ASCII')

            tm('set-option', '-g', '@tmux_canopy_icon_theme', 'unicode')
            tm('set-option', '-g', 'window-size', 'manual')
            tm('resize-window', '-t', 'app:0', '-x', '24', '-y', '35')
            assert 'feature/alpha' not in '\n'.join(rows().values()), 'branch crowded narrow Tree'
            preview = run('pane-preview', a, FZF_PREVIEW_LINES='8', FZF_PREVIEW_COLUMNS='24')
            assert 'Git: feature/alpha' in preview, preview
            tm('resize-window', '-t', 'app:0', '-x', '120', '-y', '35')
            print('ok - narrow trees preserve space; pane preview retains the full branch')

            commit = sp.check_output([GIT, '-C', str(first), 'rev-parse', '--short', 'HEAD'], env=env, text=True).strip()
            sp.run([GIT, '-C', str(first), 'checkout', '-q', '--detach'], env=env, check=True)
            assert f'detached@{commit}' in '\n'.join(rows().values())
            assert 'Git: detached@' in run('pane-preview', a, FZF_PREVIEW_LINES='8')
            sp.run([GIT, '-C', str(first), 'checkout', '-q', '-b', 'now/updated'], env=env, check=True)
            assert 'now/updated' in '\n'.join(rows().values())
            print('ok - detached heads and manual refresh pick up branch changes')

            # A real attached client catches labels lost to fzf layout/clipping.
            tm('select-window', '-t', 'app:0')
            tm('set-option', '-g', 'default-shell', '/bin/bash')
            sp.run([str(ROOT / 'tmux-canopy.tmux')], env=script_env, check=True, timeout=15)
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 35, 120, 0, 0))
            client = os.ttyname(slave)
            client_env = env | {'TERM': 'xterm-256color'}
            client_process = sp.Popen([tmux, '-L', socket, 'attach-session', '-t', 'app'],
                                      stdin=slave, stdout=slave, stderr=slave,
                                      env=client_env, start_new_session=True)
            os.close(slave)

            def drain():
                try:
                    while os.read(master, 65536):
                        pass
                except OSError:
                    pass
            threading.Thread(target=drain, daemon=True).start()
            deadline = time.monotonic() + 8
            while client not in tm('list-clients', '-F', '#{client_tty}').splitlines():
                assert time.monotonic() < deadline, 'client did not attach'
                time.sleep(.05)
            script_env['TMUX_CANOPY_CLIENT'] = client
            run('toggle', client, a, '42', 'global', 'T', 'Tab', 'slot')
            sidebar = next(row.split('|')[0] for row in tm('list-panes', '-a', '-F', '#{pane_id}|#{@tmux_canopy}').splitlines()
                           if row.endswith('|1'))
            deadline = time.monotonic() + 10
            while 'now/updated' not in tm('capture-pane', '-p', '-t', sidebar):
                assert time.monotonic() < deadline, tm('capture-pane', '-p', '-t', sidebar)
                time.sleep(.05)
            # A painted frame can precede fzf's load binding or the focus
            # worker's first Ctrl-o reload. Wait for both before exercising the
            # *next* Ctrl-r; otherwise that startup reload may paint over it.
            focus = tm('display-message', '-p', '-t', a,
                       '#{session_id}|#{window_id}|#{pane_id}')
            while True:
                pending, _, location = tm('display-message', '-p', '-t', sidebar,
                                          '#{@tmux_canopy_focus_pending}|#{@tmux_canopy_focus_location}').partition('|')
                if not pending and location == focus and list(temp.glob('tmux-canopy.*.ready')):
                    break
                assert time.monotonic() < deadline, 'sidebar did not finish opening'
                time.sleep(.05)
            tm('set-option', '-g', '@tmux-canopy-git-context', 'off')
            assert 'now/updated' not in run('tree-source'), 'the source ignored git-context off'
            ready = next(temp.glob('tmux-canopy.*.ready'))
            ready_before = ready.stat().st_mtime_ns
            tm('send-keys', '-t', sidebar, 'C-r')
            deadline = time.monotonic() + 10
            while 'now/updated' in tm('capture-pane', '-p', '-t', sidebar):
                assert time.monotonic() < deadline, (
                    'Git label did not disappear after reload; option='
                    + tm('show-option', '-gqv', '@tmux-canopy-git-context')
                    + ', source_has_label=' + str('now/updated' in run('tree-source'))
                    + ', fzf_loaded_again=' + str(ready.stat().st_mtime_ns != ready_before)
                    + ', focus=' + tm('display-message', '-p', '-t', sidebar,
                                     '#{@tmux_canopy_focus_pending}|#{@tmux_canopy_focus_location}'))
                time.sleep(.05)
            tm('set-option', '-g', '@tmux-canopy-git-context', 'branch')
            tm('send-keys', '-t', sidebar, 'C-r')
            deadline = time.monotonic() + 10
            while 'now/updated' not in tm('capture-pane', '-p', '-t', sidebar):
                assert time.monotonic() < deadline, 'Git label did not return after reload'
                time.sleep(.05)
            print('ok - attached sidebar renders Git branch and updates without reopening')
        finally:
            sp.run([tmux, '-L', socket, 'kill-server'], env=env, capture_output=True, timeout=10)
            if client_process:
                client_process.terminate()
                try:
                    client_process.wait(timeout=3)
                except sp.TimeoutExpired:
                    client_process.kill()
                    client_process.wait(timeout=3)
            if master is not None:
                os.close(master)


if __name__ == '__main__':
    main()
