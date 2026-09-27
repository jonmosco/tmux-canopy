#!/usr/bin/env python3
"""Exercise real TPM with a local snapshot, private server and temporary home.

Usage: python3 tests/tpm_install.py /path/to/tpm
No network or changes to the user's plugin installation are needed.
"""
import os
from pathlib import Path
import shutil
import subprocess as sp
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    tpm_source = Path(sys.argv[1]).resolve()
    assert (tpm_source / 'tpm').is_file(), 'Pass an existing TPM checkout'
    with tempfile.TemporaryDirectory(prefix='canopy-tpm-install-', ignore_cleanup_errors=True) as directory:
        temp = Path(directory)
        env = dict(os.environ, HOME=str(temp / 'home'),
                   XDG_CONFIG_HOME=str(temp / 'home/.config'),
                   PYTHONDONTWRITEBYTECODE='1')
        for key in ('TMUX', 'TMUX_PANE', 'TMUX_PLUGIN_MANAGER_PATH'):
            env.pop(key, None)
        plugins = Path(env['HOME']) / '.tmux/plugins'
        plugins.mkdir(parents=True)
        tpm = plugins / 'tpm'
        shutil.copytree(tpm_source, tpm, ignore=shutil.ignore_patterns('.git'))

        def run(*args, **kwargs):
            result = sp.run(args, env=env, capture_output=True, text=True,
                            timeout=60, **kwargs)
            assert result.returncode == 0, (args, result.stdout, result.stderr)
            return result.stdout.strip()

        # Commit a disposable copy so TPM installs the working tree, including
        # uncommitted fixes, without touching this repository's index/history.
        source = temp / 'source/tmux-canopy'
        shutil.copytree(ROOT, source, ignore=shutil.ignore_patterns('.git', '__pycache__'))
        run('git', 'init', '-q', str(source))
        run('git', '-C', str(source), 'add', '.')
        run('git', '-C', str(source), '-c', 'user.name=Canopy Test',
            '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false',
            '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'Test snapshot')
        config = Path(env['HOME']) / '.tmux.conf'
        config.write_text(f"set -g @plugin '{source}'\nrun-shell '{tpm}/tpm'\n")
        socket = f'canopy-install-{os.getpid()}'

        def tm(*args):
            return run('tmux', '-L', socket, *args)

        try:
            pane = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'install',
                      '-x', '160', '-y', '44', '-P', '-F', '#{pane_id}', 'sleep 600')
            env['TMUX'] = tm('display-message', '-p', '-t', pane, '#{socket_path},#{pid},0')
            env['TMUX_PANE'] = pane
            tm('set-environment', '-g', 'TMUX_PLUGIN_MANAGER_PATH', str(plugins) + '/')
            run(str(tpm / 'tpm'))
            run(str(tpm / 'bin/install_plugins'))
            installed = plugins / 'tmux-canopy'
            assert (installed / 'canopy').is_file()
            run(str(tpm / 'scripts/source_plugins.sh'))
            assert tm('show-option', '-gqv', '@tmux_canopy_loaded_path') == str(installed)
            assert 'Required commands, formats, UI options and temporary state: OK' in run(str(installed / 'canopy'), 'doctor')
            print('ok - real TPM installs and loads a fresh working-tree snapshot; doctor passes', flush=True)

            # Verify the installed providers against real tmux and ps, using
            # the same NUL record framing as the interactive sidebar.
            state = temp / 'state'
            env['TMUX_CANOPY_STATE'] = str(state)
            for view in ('tree', 'processes', 'buffers', 'agents'):
                state.write_text(f'VIEW\t{view}\n')
                output = run(str(installed / 'scripts/sidebar-source'), '--read0')
                assert '\0' in output and 'V:failure' not in output, (view, output)
            print('ok - installed Tree, Processes, Buffers and Agents providers render', flush=True)
            run(str(tpm / 'bin/install_plugins'))
            run(str(tpm / 'scripts/source_plugins.sh'))
            assert tm('show-option', '-gqv', '@tmux_canopy_loaded_path') == str(installed)
            print('ok - repeat TPM install and reload are idempotent', flush=True)

            config.write_text(f"run-shell '{tpm}/tpm'\n")
            run(str(tpm / 'bin/clean_plugins'))
            assert not installed.exists() and tpm.exists()
            print('ok - TPM removes the unlisted plugin and preserves TPM', flush=True)

            # Exercise the documented manual clone/load path separately.
            run('git', 'clone', '-q', str(source), str(installed))
            tm('set-option', '-gu', '@tmux_canopy_loaded_path')
            tm('run-shell', str(installed / 'tmux-canopy.tmux'))
            assert tm('show-option', '-gqv', '@tmux_canopy_loaded_path') == str(installed)
            run(str(installed / 'canopy'), 'doctor')
            print('ok - manual clone and run-shell installation passes doctor', flush=True)
        finally:
            sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)


if __name__ == '__main__':
    main()
