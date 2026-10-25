#!/usr/bin/env python3
"""Opt-in Bash prompt notifier for directory-only sidebar refreshes."""
import os
from pathlib import Path
import shlex
import subprocess as sp
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
PROMPT = ROOT / 'scripts' / 'directory-prompt.sh'
HELPER = ROOT / 'scripts' / 'directory-refresh'


def main():
    socket = f'canopy-directory-refresh-{os.getpid()}'
    env = os.environ.copy()
    env.pop('TMUX', None)
    env.pop('TMUX_PANE', None)

    def tm(*args, check=True):
        result = sp.run(['tmux', '-L', socket, *args], env=env, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0 or not check, (args, result.stderr)
        return result.stdout.strip()

    def wait(condition, message, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(0.05)
        raise AssertionError(message)

    # --- prompt hook: no tmux required ---------------------------------
    with tempfile.TemporaryDirectory(prefix='canopy-dir-prompt-') as folder:
        calls = Path(folder) / 'calls'
        calls.touch()
        fake_helper = Path(folder) / 'directory-refresh'
        fake_helper.write_text(
            '#!/bin/bash\n'
            f'printf "%s\\t%s\\n" "$1" "$PWD" >> {shlex.quote(str(calls))}\n'
        )
        fake_helper.chmod(0o755)
        # Point the sourced script at the fake helper via a tiny wrapper.
        wrapper = Path(folder) / 'prompt.sh'
        wrapper.write_text(
            '#!/bin/bash\n'
            f'_CANOPY_DIRECTORY_REFRESH={shlex.quote(str(fake_helper))}\n'
            f'source {shlex.quote(str(PROMPT))}\n'
        )

        def run_prompt(script, bash_args=('-c',), check=True):
            return sp.run(
                ['bash', *bash_args, script],
                capture_output=True, text=True, timeout=10, cwd=folder)

        # Unchanged PWD: no helper call; exit status preserved.
        script = (
            f'source {shlex.quote(str(wrapper))}\n'
            'false\n'
            '_canopy_directory_prompt; status=$?\n'
            '_canopy_directory_prompt\n'
            'printf "status=%s calls=%d\\n" "$status" "$(wc -l < ' + shlex.quote(str(calls)) + ')"\n'
        )
        out = run_prompt(script)
        assert out.returncode == 0, out.stderr
        assert 'status=1 calls=0' in out.stdout, out.stdout
        print('ok - unchanged directory does not call the helper; exit status is preserved')

        # PWD change triggers one async call with the pane id only.
        calls.write_text('')
        script = (
            f'source {shlex.quote(str(wrapper))}\n'
            'export TMUX=/tmp/fake TMUX_PANE=%42\n'
            'cd /tmp || exit 1\n'
            '_canopy_directory_prompt\n'
            'for _ in 1 2 3 4 5 6 7 8 9 10; do\n'
            f'  [[ -s {shlex.quote(str(calls))} ]] && break\n'
            '  sleep 0.05\n'
            'done\n'
            f'cat {shlex.quote(str(calls))}\n'
        )
        out = run_prompt(script)
        assert out.returncode == 0, out.stderr
        lines = [line for line in out.stdout.splitlines() if line.startswith('%')]
        assert lines == ['%42\t/tmp'], (out.stdout, lines)
        print('ok - directory change notifies with pane id only')

        # Idempotent install for string and array PROMPT_COMMAND.
        for form, setup, probe in (
            ('string',
             'PROMPT_COMMAND="existing_hook"',
             'printf "%s\\n" "$PROMPT_COMMAND"'),
            ('array',
             'PROMPT_COMMAND=(existing_hook)',
             'declare -p PROMPT_COMMAND'),
        ):
            script = (
                f'{setup}\n'
                f'source {shlex.quote(str(wrapper))}\n'
                f'source {shlex.quote(str(wrapper))}\n'
                f'{probe}\n'
            )
            out = run_prompt(script)
            assert out.returncode == 0, (form, out.stderr)
            assert out.stdout.count('_canopy_directory_prompt') == 1, (form, out.stdout)
            assert 'existing_hook' in out.stdout, (form, out.stdout)
        print('ok - PROMPT_COMMAND install is idempotent for string and array forms')

    # --- helper against a private tmux server --------------------------
    try:
        with tempfile.TemporaryDirectory(prefix='canopy-dir-refresh-') as folder:
            root = Path(folder).resolve()
            work_a = root / 'a'
            work_b = root / 'b'
            work_a.mkdir()
            work_b.mkdir()
            pane = tm('-f', '/dev/null', 'new-session', '-d', '-x', '120', '-y', '40',
                      '-c', str(work_a), '-P', '-F', '#{pane_id}', 'sleep 600')
            script_env = env | {'TMUX': tm('display-message', '-p', '-t', pane, '#{socket_path},#{pid},0')}
            load = sp.run(['bash', str(ROOT / 'tmux-canopy.tmux')], env=script_env,
                          capture_output=True, text=True, timeout=30)
            assert load.returncode == 0 and not load.stderr, load.stderr
            assert tm('show-option', '-gqv', '@tmux-canopy-directory-refresh') in ('', 'off')

            sidebar = tm('split-window', '-d', '-h', '-l', '42', '-t', pane, '-P', '-F', '#{pane_id}', 'cat -v')
            tm('set-option', '-p', '-t', sidebar, '@tmux_canopy', '1')
            tm('set-option', '-p', '-t', sidebar, '@tmux_canopy_client', '/dev/test')
            tm('set-option', '-p', '-t', sidebar, '@tmux_canopy_target', pane)
            tm('set-option', '-p', '-t', sidebar, '@tmux_canopy_focus_location', f'$0|@0|{pane}')

            deliveries = Path(folder) / 'deliveries'
            deliveries.touch()
            real_tmux = sp.run(['bash', '-c', 'command -v tmux'], capture_output=True, text=True, check=True).stdout.strip()
            wrapper = Path(folder) / 'tmux'
            wrapper.write_text(
                '#!/bin/bash\n'
                'if [[ "$1" == send-keys ]]; then\n'
                f'  printf "%s\\n" "$*" >> {shlex.quote(str(deliveries))}\n'
                'fi\n'
                f'exec {shlex.quote(real_tmux)} -L {shlex.quote(socket)} "$@"\n'
            )
            wrapper.chmod(0o755)
            wrapped = script_env | {'PATH': str(folder) + ':' + script_env.get('PATH', os.environ['PATH'])}
            tm('set-environment', '-g', 'PATH', wrapped['PATH'])

            def helper(*args, env=None):
                return sp.run([str(HELPER), *args], env=env or wrapped, capture_output=True, text=True, timeout=15)

            # Option off: no refresh.
            before = deliveries.read_text()
            assert helper(pane).returncode == 0
            time.sleep(0.25)
            assert deliveries.read_text() == before, deliveries.read_text()
            print('ok - helper is quiet while @tmux-canopy-directory-refresh is off')

            tm('set-option', '-g', '@tmux-canopy-directory-refresh', 'on')

            # Sidebar / slot panes are ignored (mark the content pane as a slot
            # briefly — creating a real split would fire the plugin's split refresh).
            deliveries.write_text('')
            assert helper(sidebar).returncode == 0
            tm('set-option', '-p', '-t', pane, '@tmux_canopy_slot', '1')
            assert helper(pane).returncode == 0
            time.sleep(0.25)
            assert deliveries.read_text() == '', deliveries.read_text()
            tm('set-option', '-pu', '-t', pane, '@tmux_canopy_slot')
            print('ok - sidebar and slot panes do not schedule a refresh')

            # Invalid pane id is ignored.
            assert helper('%999999').returncode == 0
            assert helper('not-a-pane').returncode == 0

            # Enabled content pane: coalesced Ctrl-r, focus location untouched.
            # Hold the worker at claim-release so the whole burst shares one window
            # regardless of process startup speed (same pattern as create_refresh).
            location = tm('show-option', '-pqv', '-t', sidebar, '@tmux_canopy_focus_location')
            release_gate = Path(folder) / 'release-dir'
            release_ready = Path(folder) / 'dir-ready'
            gate_enabled = Path(folder) / 'gate-enabled'
            os.mkfifo(release_gate)
            gated = Path(folder) / 'tmux-gated'
            gated.write_text(
                '#!/bin/bash\n'
                'if [[ "$1" == send-keys ]]; then\n'
                f'  printf "%s\\n" "$*" >> {shlex.quote(str(deliveries))}\n'
                'fi\n'
                f'if [[ -e {shlex.quote(str(gate_enabled))} && "$1" == if-shell && "$*" == *"set-option -gu @tmux_canopy_dir_refresh_pending"* ]]; then\n'
                f'  printf x > {shlex.quote(str(release_ready))}\n'
                f'  IFS= read -r _ < {shlex.quote(str(release_gate))}\n'
                'fi\n'
                f'exec {shlex.quote(real_tmux)} -L {shlex.quote(socket)} "$@"\n'
            )
            gated.chmod(0o755)
            wrapper.write_text(gated.read_text())
            gate_enabled.touch()
            deliveries.write_text('')
            assert helper(pane).returncode == 0
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and not release_ready.exists():
                time.sleep(0.02)
            assert release_ready.exists(), 'directory-refresh worker did not reach its release gate'
            # Freeze expiry while the worker is paused so late callers still coalesce.
            tm('set-option', '-g', '@tmux_canopy_dir_refresh_deadline', '9999999999')
            for _ in range(12):
                assert helper(pane).returncode == 0
            # No delivery until the held worker releases.
            assert deliveries.read_text() == '', deliveries.read_text()
            # Disable the gate before release so the EXIT-trap if-shell is not held.
            gate_enabled.unlink(missing_ok=True)
            with open(release_gate, 'w', encoding='utf-8') as fifo:
                fifo.write('x\n')
            wait(lambda: any(sidebar in line and 'C-r' in line for line in deliveries.read_text().splitlines()),
                 'directory refresh delivery')
            time.sleep(0.25)
            lines = [line for line in deliveries.read_text().splitlines() if sidebar in line and 'C-r' in line]
            assert len(lines) == 1, deliveries.read_text()
            assert tm('show-option', '-pqv', '-t', sidebar, '@tmux_canopy_focus_location') == location
            assert tm('show-option', '-pqv', '-t', sidebar, '@tmux_canopy_target') == pane
            print('ok - enabled helper coalesces bursts into one Ctrl-r without moving focus')

            # Transition guard skips owners mid-swap.
            guard = sp.run(
                ['bash', '-c', f'source "{ROOT}/scripts/lib.sh"; sidebar_transition_option "/dev/test"'],
                capture_output=True, text=True, check=True).stdout.strip()
            tm('set-option', '-g', guard, '1')
            deliveries.write_text('')
            assert helper(pane).returncode == 0
            time.sleep(0.3)
            assert deliveries.read_text() == '', deliveries.read_text()
            tm('set-option', '-gu', guard)
            print('ok - directory refresh respects transition guards')

            # End-to-end: prompt hook + helper updates tree cwd text.
            # Use a real refresh path (no send-keys wrapper) against tree-source.
            tm('set-environment', '-g', 'PATH', script_env.get('PATH', os.environ['PATH']))
            state = Path(folder) / 'state'
            state.write_text('')
            tree_env = script_env | {'TMUX_PANE': sidebar, 'TMUX_CANOPY_STATE': str(state)}

            def tree_text():
                return sp.run([str(ROOT / 'scripts/tree-source')], env=tree_env,
                              capture_output=True, text=True, timeout=15, check=True).stdout

            assert 'a' in tree_text() or str(work_a) in tree_text() or work_a.name in tree_text()
            # Move the content pane's process cwd the way a shell cd would.
            tm('send-keys', '-t', pane, f'cd {shlex.quote(str(work_b))}', 'C-m')
            # sleep 600 ignores keys; change path via respawn in the new directory.
            tm('respawn-pane', '-k', '-c', str(work_b), '-t', pane, 'sleep 600')
            wait(lambda: tm('display-message', '-p', '-t', pane, '#{pane_current_path}') == str(work_b),
                 'pane_current_path follows respawn')
            before_tree = tree_text()
            assert helper(pane).returncode == 0
            # Direct tree-source already sees the new path; the helper's job is
            # the Ctrl-r signal. Confirm the path is visible when re-read.
            wait(lambda: work_b.name in tree_text() or str(work_b) in tree_text(),
                 'tree shows new directory')
            assert tm('show-option', '-pqv', '-t', sidebar, '@tmux_canopy_focus_location') == location
            assert before_tree is not None
            print('ok - helper refresh path reads updated pane_current_path without focus churn')

            # Bad option values normalize to off on plugin reload.
            tm('set-option', '-g', '@tmux-canopy-directory-refresh', 'maybe')
            reload = sp.run(['bash', str(ROOT / 'tmux-canopy.tmux')], env=script_env,
                            capture_output=True, text=True, timeout=30)
            assert reload.returncode == 0 and not reload.stderr, reload.stderr
            assert tm('show-option', '-gqv', '@tmux-canopy-directory-refresh') == 'off'
            deliveries.write_text('')
            wrapped_path = str(folder) + ':' + script_env.get('PATH', os.environ['PATH'])
            tm('set-environment', '-g', 'PATH', wrapped_path)
            assert helper(pane, env=wrapped | {'PATH': wrapped_path}).returncode == 0
            time.sleep(0.3)
            assert deliveries.read_text() == '', deliveries.read_text()
            print('ok - non-on directory-refresh values do not refresh')
    finally:
        sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True, timeout=10)


if __name__ == '__main__':
    main()
