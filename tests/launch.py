#!/usr/bin/env python3
"""Real-client launch, failure recovery, quoting, and diagnostics regressions."""
import fcntl
import os
from pathlib import Path
import pty
import shlex
import shutil
import subprocess as sp
import struct
import tempfile
import termios
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    tmux, fzf = shutil.which('tmux'), shutil.which('fzf')
    socket = f'tree-launch-test-{os.getpid()}'
    env = os.environ.copy()
    for key in ('TMUX', 'TMUX_PANE', 'FZF_DEFAULT_OPTS', 'FZF_DEFAULT_OPTS_FILE'):
        env.pop(key, None)
    env['TERM'] = 'xterm-256color'
    attached = None
    master = None
    with tempfile.TemporaryDirectory(prefix='tree-launch-', ignore_cleanup_errors=True) as directory:
        temp = Path(directory)
        project = temp / 'project \'quoted\', $literal #{version} (test)'
        shutil.copytree(ROOT, project, ignore=shutil.ignore_patterns('.git', 'tests', '__pycache__'))
        tmpdir = temp / "state 'quoted' #{version}"
        tmpdir.mkdir()
        binary_dir = temp / 'bin'
        binary_dir.mkdir()
        dispatches = temp / 'failure-dispatches'
        dispatches.touch()
        tmux_wrapper = binary_dir / 'tmux'
        buffer_failure = temp / 'buffer-failure'
        tmux_wrapper.write_text(f'''#!/bin/bash
if [[ "$1" == display-message && " $* " == *" -d 7000 "* ]]; then
  previous=""
  for argument in "$@"; do
    [[ "$previous" != -c ]] || printf '%s\\n' "$argument" >> {shlex.quote(str(dispatches))}
    previous="$argument"
  done
fi
if [[ "$1" == list-buffers && -f {shlex.quote(str(buffer_failure))} ]]; then
  printf 'PARTIAL_NOT_A_BUFFER\\n'
  printf 'NOT_FOR_DIAGNOSTICS\\n' >&2
  exit 6
fi
exec {shlex.quote(tmux)} "$@"
''')
        tmux_wrapper.chmod(0o755)
        mode = temp / 'mode'
        mode.write_text('ok')
        selected = temp / 'selected'
        loads = temp / 'loads'
        loads.touch()
        marker = temp / 'ambient-executed'
        defaults = temp / 'fzf defaults'
        defaults.write_text('--filter=NEVER_MATCH_THIS\n')
        ui_binding = f"alt-z:execute-silent(printf '%s|%s\\n' {{1}} {{q}} > {shlex.quote(str(selected))})"
        wrapper = binary_dir / 'fzf'
        wrapper.write_text('''#!/bin/bash
for argument in "$@"; do
  case "$argument" in
    --version|--help) exec REAL "$@" ;;
  esac
done
mode=$(< MODE)
if [[ "$mode" == incompatible ]]; then echo NOT_FOR_DIAGNOSTICS >&2; exit 2; fi
if [[ "$mode" == crash && " $* " != *' --filter=probe '* ]]; then
  sleep .25; echo NOT_FOR_DIAGNOSTICS >&2; exit 42
fi
exec REAL --bind BINDING --bind LOAD "$@" 2>>/tmp/canopy-fzf-err
'''.replace('REAL', shlex.quote(fzf)).replace('MODE', shlex.quote(str(mode))).replace('BINDING', shlex.quote(ui_binding)).replace('LOAD', shlex.quote('load:execute-silent(printf x >> ' + str(loads) + ')')))
        wrapper.chmod(0o755)
        state = temp / 'state'
        state.touch()

        def tm(*args):
            result = sp.run([tmux, '-L', socket, *args], env=env, text=True, capture_output=True, timeout=15)
            assert result.returncode == 0, (args, result.stderr)
            return result.stdout.strip()

        def display(pane, fmt):
            return tm('display-message', '-p', '-t', pane, fmt)

        def run(script, *args, environment=None, success=True):
            result = sp.run([str(project / 'scripts' / script), *args], env=environment or script_env,
                            text=True, capture_output=True, timeout=20)
            if success:
                assert result.returncode == 0, (script, result.stderr, result.stdout)
            return result

        def wait(predicate, message):
            deadline = time.monotonic() + 7
            while time.monotonic() < deadline:
                if predicate():
                    return
                time.sleep(.05)
            kids = ''
            try:
                side = sidebars()[0]
                pid = tm('display-message', '-p', '-t', side, '#{pane_pid}')
                kids = sp.check_output(['ps', '-o', 'command=', '-g', pid], text=True, stderr=sp.STDOUT)
                Path('/tmp/canopy-fzf-cmd').write_text(kids)
            except Exception as exc:
                kids = str(exc)
            raise AssertionError((message, loads.stat().st_size, kids[:1500]))

        def sidebars():
            return tm('list-panes', '-a', '-f', '#{==:#{@tmux_canopy},1}', '-F', '#{pane_id}').splitlines()

        def open_sidebar():
            loads.write_text('')
            run('toggle', client, pane, '42', 'global', 'T', 'Tab', 'slot')
            wait(lambda: len(sidebars()) == 1, 'sidebar creation')
            side = sidebars()[0]
            script_env['TMUX_PANE'] = side
            wait(lambda: loads.stat().st_size >= 1, 'initial UI load')
            assert display(side, '#{pane_in_mode}') == '0'
            return side

        def close_sidebar(side):
            def poll():
                if not sidebars():
                    return True
                tm('send-keys', '-t', side, 'C-q')
                time.sleep(.1)
                return False
            wait(poll, 'normal close')

        def probe():
            selected.unlink(missing_ok=True)
            def poll():
                if selected.exists() and selected.stat().st_size:
                    return True
                tm('send-keys', '-t', sidebar, 'M-z')
                time.sleep(.1)
                return False
            wait(poll, 'fzf probe')
            return selected.read_text().strip()

        try:
            pane = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'launch', '-x', '160', '-y', '44',
                      '-P', '-F', '#{pane_id}', '/bin/bash', '--noprofile', '--norc')
            other = tm('new-window', '-d', '-P', '-F', '#{pane_id}', 'sleep 600')
            tm('set-option', '-g', 'status', 'off')
            tm('set-option', '-g', 'status-keys', 'emacs')
            for option, value in [('scope', 'global'), ('transition', 'slot'), ('preview', 'off'), ('notifications', 'activity,bell')]:
                tm('set-option', '-g', '@tmux-canopy-' + option, value)
            script_env = env | {'TMUX': display(pane, '#{socket_path},#{pid},0'), 'TMUX_PANE': pane,
                                'TMUX_CANOPY_STATE': str(state), 'TMPDIR': str(tmpdir),
                                'PATH': str(binary_dir) + ':' + env['PATH']}
            ambient = '--bind=start:execute-silent(touch ' + str(marker) + ')+abort --height=3'
            script_env.update(FZF_DEFAULT_OPTS=ambient, FZF_DEFAULT_OPTS_FILE=str(defaults), SHELL='/bin/false')
            for key in ('PATH', 'FZF_DEFAULT_OPTS', 'FZF_DEFAULT_OPTS_FILE', 'SHELL', 'TMPDIR'):
                tm('set-environment', '-g', key, script_env[key])
            sp.run([str(project / 'tmux-canopy.tmux')], env=script_env, check=True, timeout=20)
            literal = 'START "double" \'single\' $literal #{version} 中文\nsecond\tfield END'
            quoted = sp.check_output(['/bin/bash', '-c', 'source "$1"; tmux_quote "$2"', '_', str(project / 'scripts/launch-lib.sh'), literal], text=True)
            tm('if-shell', '-F', '1', 'set-option -g @quote ' + quoted)
            assert tm('show-option', '-gqv', '@quote') == literal
            print('ok - tmux quoting preserves literal formats, quotes, Unicode and control whitespace')
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 44, 160, 0, 0))
            client = os.ttyname(slave)
            attached = sp.Popen([tmux, '-L', socket, 'attach-session', '-t', 'launch'], stdin=slave,
                                stdout=slave, stderr=slave, env=env, start_new_session=True)
            os.close(slave)
            terminal_output = bytearray()
            def drain():
                try:
                    while chunk := os.read(master, 65536):
                        terminal_output.extend(chunk)
                        del terminal_output[:-8192]
                except OSError:
                    pass
            threading.Thread(target=drain, daemon=True).start()
            wait(lambda: client in tm('list-clients', '-F', '#{client_tty}'), 'client attach')
            script_env['TMUX_CANOPY_CLIENT'] = client
            initial_layout = display(pane, '#{window_layout}')

            missing = temp / 'missing-fzf-bin'
            missing.mkdir()
            for name in ('bash', 'tmux', 'awk', 'mktemp', 'dirname', 'cksum', 'grep', 'date'):
                (missing / name).symlink_to(shutil.which(name))
            result = run('toggle', client, pane, '42', 'global', 'T', 'Tab', 'slot',
                         environment=script_env | {'PATH': str(missing)}, success=False)
            assert result.returncode != 0 and not sidebars()
            assert display(pane, '#{window_layout}') == initial_layout
            assert 'Required executable is missing: fzf' in tm('show-options', '-g')
            mode.write_text('incompatible')
            result = run('toggle', client, pane, '42', 'global', 'T', 'Tab', 'slot', success=False)
            assert result.returncode != 0 and not sidebars()
            assert display(pane, '#{window_layout}') == initial_layout
            assert '[fzf-capabilities]' in tm('show-options', '-g')
            assert 'NOT_FOR_DIAGNOSTICS' not in tm('show-options', '-g')
            print('ok - missing/incompatible fzf is rejected before any geometry change, without retaining stderr')

            mode.write_text('ok')
            extra = tm('split-window', '-d', '-t', pane, '-P', '-F', '#{pane_id}', 'sleep 600')
            tm('set-option', '-g', '@tmux-canopy-zoom-action', 'unzoom')
            tm('resize-pane', '-Z', '-t', pane)
            assert display(pane, '#{window_zoomed_flag}') == '1'
            zoomed_layout = display(pane, '#{window_layout}')
            entry = project / 'scripts/sidebar'
            executable_mode = entry.stat().st_mode
            entry.chmod(0o644)
            result = run('toggle', client, pane, '42', 'global', 'T', 'Tab', 'slot', success=False)
            entry.chmod(executable_mode)
            assert result.returncode != 0 and not sidebars()
            assert '[install]' in tm('show-options', '-g')
            assert display(pane, '#{window_zoomed_flag}') == '1'
            assert display(pane, '#{window_layout}') == zoomed_layout
            bad_tmp = temp / 'not-a-directory'
            bad_tmp.write_text('fixture')
            result = run('toggle', client, pane, '42', 'global', 'T', 'Tab', 'slot', environment=script_env | {'TMPDIR': str(bad_tmp)}, success=False)
            assert result.returncode != 0 and not sidebars()
            assert '[temporary-state]' in tm('show-options', '-g')
            assert display(pane, '#{window_zoomed_flag}') == '1'
            assert display(pane, '#{window_layout}') == zoomed_layout
            tm('resize-pane', '-Z', '-t', pane)
            tm('kill-pane', '-t', extra)
            tm('set-option', '-g', '@tmux-canopy-zoom-action', 'refuse')
            assert display(pane, '#{window_layout}') == initial_layout
            print('ok - damaged installation and unusable TMPDIR leave application layout and zoom unchanged')

            # A pending notification exercises the clear hook's true branch.
            # A literal -t '#{window_id}' here makes toggle return 1 even
            # though the sidebar was successfully created.
            window = display(pane, '#{window_id}')
            for _ in range(2):
                tm('set-option', '-w', '-t', window, '@tmux_canopy_notice_activity', '1')
                sidebar = open_sidebar()
                sidebar_pid = display(sidebar, '#{pane_pid}')
                fzf_pid = sp.check_output(['pgrep', '-P', sidebar_pid, '-x', 'fzf'], text=True).strip()
                wait(lambda: tm('show-option', '-wqv', '-t', window,
                                '@tmux_canopy_notice_activity') != '1', 'notice cleared on open')
                run('toggle', client, pane, '42', 'global', 'T', 'Tab', 'slot')
                wait(lambda: not sidebars(), 'toggle close')
                wait(lambda: not sp.run(['ps', '-p', f'{sidebar_pid},{fzf_pid}', '-o', 'pid='],
                                        capture_output=True, text=True).stdout.strip(),
                     'sidebar and fzf process exit')
                script_env['TMUX_PANE'] = pane
                assert display(pane, '#{pane_in_mode}') == '0'
            print('ok - close/reopen clears notifications and reaps sidebar/fzf processes')

            for shell in ('bash', 'zsh', 'fish'):
                executable = shutil.which(shell)
                if not executable:
                    continue
                tm('set-option', '-g', 'default-shell', executable)
                sidebar = open_sidebar()
                assert not marker.exists()
                assert display(sidebar, '#{pane_width}') == '42'
                close_sidebar(sidebar)
                script_env['TMUX_PANE'] = pane
                time.sleep(.2)
            print('ok - Bash/zsh/fish launches, quoted paths/TMPDIR, and hostile ambient fzf defaults')

            sidebar = open_sidebar()
            parent = display(sidebar, '#{pane_pid}')
            ui_pid = sp.check_output(['pgrep', '-P', parent, '-x', 'fzf'], text=True).strip()
            tm('send-keys', '-t', sidebar, '/')
            wait(lambda: tm('capture-pane', '-p', '-t', sidebar).startswith('search'), 'search mode')
            tm('send-keys', '-t', sidebar, '-l', 'bash')
            time.sleep(.2)
            value = probe()
            assert value.endswith('|bash'), value
            renderer = project / 'scripts/tree-source'
            original = renderer.read_bytes()
            renderer.write_text("#!/bin/bash\nprintf 'NOT_FOR_DIAGNOSTICS'; echo NOT_FOR_DIAGNOSTICS >&2; exit 19\n")
            tm('send-keys', '-t', sidebar, 'C-r')
            wait(lambda: 'data unavailable' in tm('capture-pane', '-p', '-t', sidebar), 'retry header')
            assert 'NOT_FOR_DIAGNOSTICS' not in tm('capture-pane', '-p', '-t', sidebar)
            assert probe().endswith('|bash')
            renderer.write_bytes(original)
            tm('send-keys', '-t', sidebar, 'C-r')
            wait(lambda: 'data unavailable' not in tm('capture-pane', '-p', '-t', sidebar), 'source recovery')
            assert probe().endswith('|bash')
            assert sp.check_output(['pgrep', '-P', parent, '-x', 'fzf'], text=True).strip() == ui_pid
            print('ok - source failure/recovery retains fzf and the query, discards partial data, and provides retry diagnostics')

            # Exercise failures inside the actual subordinate providers.
            tm('send-keys', '-t', sidebar, 'Escape')
            wait(lambda: '[Tree]' in tm('capture-pane', '-p', '-t', sidebar).splitlines()[0], 'navigation header with hidden search input')
            assert probe().endswith('|'), 'Escape must clear the search query'
            ps_failure = binary_dir / 'ps'
            ps_failure.write_text('#!/bin/bash\necho NOT_FOR_DIAGNOSTICS >&2\nexit 6\n')
            ps_failure.chmod(0o755)
            tm('send-keys', '-t', sidebar, '2')
            wait(lambda: 'data unavailable' in tm('capture-pane', '-p', '-t', sidebar), 'ps provider failure')
            ps_failure.unlink()
            tm('send-keys', '-t', sidebar, 'C-r')
            wait(lambda: '[Proc]' in tm('capture-pane', '-p', '-t', sidebar), 'ps provider recovery')
            buffer_failure.touch()
            tm('send-keys', '-t', sidebar, '3')
            wait(lambda: 'data unavailable' in tm('capture-pane', '-p', '-t', sidebar), 'buffer provider failure')
            assert 'PARTIAL_NOT_A_BUFFER' not in tm('capture-pane', '-p', '-t', sidebar)
            buffer_failure.unlink()
            tm('send-keys', '-t', sidebar, 'C-r')
            wait(lambda: '[Buff]' in tm('capture-pane', '-p', '-t', sidebar), 'buffer provider recovery')
            assert sp.check_output(['pgrep', '-P', parent, '-x', 'fzf'], text=True).strip() == ui_pid
            tm('send-keys', '-t', sidebar, '1')
            wait(lambda: '[Tree]' in tm('capture-pane', '-p', '-t', sidebar), 'tree restored')
            print('ok - ps and tmux buffer failures propagate through the real providers and recover in place')

            format_marker = temp / 'format-job-executed'
            buffer_name = "buf' quoted, $literal #{version} #(touch " + shlex.quote(str(format_marker)) + ')'
            tm('set-buffer', '-b', buffer_name, 'fixture')
            tm('send-keys', '-t', sidebar, '3')
            wait(lambda: '[Buff]' in tm('capture-pane', '-p', '-t', sidebar), 'buffer view')
            terminal_output.clear()
            tm('send-keys', '-t', sidebar, 'a')
            wait(lambda: b'Buffer actions' in terminal_output, 'literal buffer context menu')
            os.write(master, b'D')
            wait(lambda: str(project / 'scripts/doctor') + ' --render' in sp.check_output(['ps', '-eo', 'args='], text=True), 'buffer diagnostics popup')
            time.sleep(.2)
            before_popup_close = loads.stat().st_size
            os.write(master, b'q')
            # The menu callback reloads after the popup command has returned.
            # Process disappearance alone races tmux's overlay teardown.
            wait(lambda: loads.stat().st_size > before_popup_close, 'buffer diagnostics callback completed')
            assert not format_marker.exists()
            tm('delete-buffer', '-b', buffer_name)
            tm('send-keys', '-t', sidebar, '1')
            wait(lambda: '[Tree]' in tm('capture-pane', '-p', '-t', sidebar), 'tree restored after buffer menu')
            print('ok - buffer context actions and diagnostics treat format-like buffer names as data')

            terminal_output.clear()
            tm('send-keys', '-t', sidebar, 'a')
            wait(lambda: b'Session actions' in terminal_output, 'session context menu')
            os.write(master, b'D')
            wait(lambda: str(project / 'scripts/doctor') + ' --render' in sp.check_output(['ps', '-eo', 'args='], text=True), 'diagnostics popup')
            time.sleep(.3)
            os.write(master, b'q')
            time.sleep(.2)
            report = run('doctor', '--report', client, sidebar).stdout
            assert 'Last recorded failure' in report and 'source exit 1' in report
            assert 'NOT_FOR_DIAGNOSTICS' not in report and 'OK' in report
            # Native hooks and queued callbacks must also work from this path.
            tm('select-window', '-t', other)
            wait(lambda: display(sidebar, '#{window_id}') == display(other, '#{window_id}'), 'native follow from quoted path')
            tm('select-window', '-t', pane)
            wait(lambda: display(sidebar, '#{window_id}') == display(pane, '#{window_id}'), 'return from native follow')
            before = tm('show-options', '-g')
            close_sidebar(sidebar)
            failures = lambda text: [line for line in text.splitlines() if line.startswith('@tmux_canopy_failure_')]
            assert failures(before) == failures(tm('show-options', '-g'))
            print('ok - contextual diagnostics and native follow work through all quoting layers; normal close is not an error')

            mode.write_text('crash')
            script_env['TMUX_PANE'] = pane
            run('toggle', client, pane, '42', 'global', 'T', 'Tab', 'slot')
            wait(lambda: '[fzf-exit]' in tm('show-options', '-g'), 'runtime failure report')
            wait(lambda: not sidebars(), 'crashed sidebar cleanup')
            report = run('doctor', '--report', client, pane).stdout
            assert 'fzf exit 42' in report and 'NOT_FOR_DIAGNOSTICS' not in report
            assert display(pane, '#{pane_dead}') == '0'
            print('ok - unexpected UI exit is recorded for its owner without retaining stderr or killing content panes')

            delivered = dispatches.read_text()
            assert delivered and set(delivered.splitlines()) == {client}
            sp.run(['/bin/bash', '-c', 'source "$1"; sidebar_failure /dev/pts/not-an-owner fixture "Fixed test summary"', '_', str(project / 'scripts/launch-lib.sh')], env=script_env, check=True)
            assert dispatches.read_text() == delivered, 'stale owner fell back to another client'
            print('ok - failure messages target only the live owner, never an unrelated fallback client')

            mode.write_text('ok')
            loads.write_text('')
            os.write(master, b'\x02T')
            wait(lambda: len(sidebars()) == 1 and loads.stat().st_size >= 1, 'native toggle binding')
            sidebar = sidebars()[0]
            assert display(sidebar, '#{pane_in_mode}') == '0'
            os.write(master, b'\x02T')
            wait(lambda: not sidebars(), 'native toggle close')
            print('ok - native toggle binding opens and closes correctly from a quoted installation path')
            cli_env = script_env | {'TMUX_PANE': pane}
            cli_env.pop('TMUX_CANOPY_CLIENT', None)
            report = run('doctor', '--report', environment=cli_env).stdout
            assert 'fzf exit 42' in report, report
            print('ok - a plain terminal doctor invocation resolves an unambiguous owner and its last failure')

            # Native command blocks keep prompt responses as data, not commands.
            tm('set-option', '-g', '@rename_count', '0')
            for hook in ('window-renamed', 'session-renamed'):
                tm('set-hook', '-g', hook + '[8000]', 'set-option -gF @rename_count "#{e|+:#{@rename_count},1}"')
            window = display(pane, '#{window_id}')
            session = display(pane, '#{session_id}')
            rename_env = cli_env | {'TMUX_CANOPY_CLIENT': client}
            def rename_response(token, response):
                terminal_output.clear()
                pending = sp.Popen([str(project / 'scripts/tree-action'), 'rename', token], env=rename_env, stdout=sp.PIPE, stderr=sp.PIPE)
                try:
                    label = b'Rename session:' if token.startswith('S:') else b'Rename window:'
                    wait(lambda: label in terminal_output, 'native rename prompt')
                    os.write(master, response)
                    _, error = pending.communicate(timeout=5)
                    assert pending.returncode == 0, error
                finally:
                    if pending.poll() is None:
                        pending.kill()
                        pending.wait(timeout=5)
            count = 0
            for token, field, name in (
                (f'W:{window}:{session}', '#{window_name}', "safe'; set -g @rename_injected yes; #"),
                (f'W:{window}:{session}', '#{window_name}', "quoted 'name', $literal #{version}"),
                (f'S:{session}', '#{session_name}', "session 'quoted', $literal #{version}"),
                (f'W:{window}:{session}', '#{window_name}', '#(touch ' + shlex.quote(str(format_marker)) + ')'),
            ):
                rename_response(token, b'\x15' + name.encode() + b'\r')
                count += 1
                wait(lambda: tm('show-option', '-gqv', '@rename_count') == str(count), 'rename response')
                assert display(pane, field) == name, (display(pane, field), name, tm('show-option', '-gqv', '@rename_injected'))
                rename_response(token, b'\x01prefix-\r')
                count += 1
                wait(lambda: tm('show-option', '-gqv', '@rename_count') == str(count), 'literal rename prefill')
                assert display(pane, field) == 'prefix-' + name, (display(pane, field), name)
                assert not tm('show-option', '-gqv', '@rename_injected')
            rename_response(f'W:{window}:{session}', b'\x1b')
            assert display(pane, '#{window_name}') == 'prefix-' + name
            assert not format_marker.exists()
            assert '@tmux_canopy_rename_' not in tm('show-options', '-w', '-t', window)
            assert '@tmux_canopy_rename_' not in tm('show-options', '-t', session)
            print('ok - native rename prompts preserve quotes, commas, dollar signs and literal formats without command injection; cancellation cleans temporary state')
        finally:
            sp.run([tmux, '-L', socket, 'kill-server'], env=env, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            if attached:
                attached.wait(timeout=5)
            if master is not None:
                os.close(master)
    print('all launch/diagnostics tests passed')


if __name__ == '__main__':
    main()
