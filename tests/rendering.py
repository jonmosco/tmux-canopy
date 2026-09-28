#!/usr/bin/env python3
"""Snapshot, notification-coalescing and real-fzf identity regressions."""
import fcntl
from support import install_fzf_probe
import os
from pathlib import Path
import pty
import shlex
import shutil
import struct
import subprocess as sp
import sys
import tempfile
import termios
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    socket = f'tree-rendering-test-{os.getpid()}'
    tmux = shutil.which('tmux')
    env = os.environ.copy()
    env.pop('TMUX', None)
    env.pop('TMUX_PANE', None)
    env['TERM'] = 'xterm-256color'
    client_process = None
    master = None
    with tempfile.TemporaryDirectory(prefix='tree-rendering-', ignore_cleanup_errors=True) as directory:
        temp = Path(directory)
        state = temp / 'state'
        selected = temp / 'selected'
        loads = temp / 'loads'
        deliveries = temp / 'deliveries'
        clears = temp / 'clears'
        clears.touch()
        state.touch()
        loads.touch()
        deliveries.touch()

        def tm(*args):
            p = sp.run([tmux, '-L', socket, *args], env=env, text=True, capture_output=True, timeout=15)
            assert p.returncode == 0, (args, p.stderr)
            return p.stdout.strip()

        def run(script, *args):
            p = sp.run([str(ROOT / 'scripts' / script), *args], env=script_env,
                       text=True, capture_output=True, timeout=15)
            assert p.returncode == 0, (script, args, p.stderr)
            return p.stdout

        def rows():
            return [row.split('\t') for row in run('sidebar-source', '--stable').splitlines()]

        def wait_for(predicate, description):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if predicate():
                    return
                time.sleep(.03)
            raise AssertionError(description)

        def selection():
            selected.unlink(missing_ok=True)
            # Redraw/reload can overlap the test-only Alt-key injection. Poll
            # the read-only probe, as the other PTY suites do; mutations and
            # actual navigation keys are still sent exactly once.
            def probe_ready():
                if selected.exists() and selected.stat().st_size:
                    return True
                tm('send-keys', '-t', sidebar, 'M-z')
                time.sleep(.08)
                return False
            wait_for(probe_ready, 'fzf selection probe')
            return selected.read_text().strip().split('|')

        try:
            pane_a = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'one', '-x', '160', '-y', '44', '-P', '-F', '#{pane_id}', 'sleep 600')
            pane_b = tm('new-window', '-d', '-t', 'one:', '-n', 'stable-beta', '-P', '-F', '#{pane_id}', 'sleep 600')
            window_b = tm('display-message', '-p', '-t', pane_b, '#{window_id}')
            sid_a = tm('display-message', '-p', '-t', pane_a, '#{session_id}')
            pane_c = tm('new-session', '-d', '-s', 'two', '-x', '160', '-y', '44', '-P', '-F', '#{pane_id}', 'sleep 600')
            sid_b = tm('display-message', '-p', '-t', pane_c, '#{session_id}')
            tm('link-window', '-s', window_b, '-t', 'two:5')
            tm('set-option', '-g', 'default-shell', '/bin/bash')
            tm('set-option', '-g', 'status', 'off')
            tm('set-option', '-g', '@tmux-canopy-scope', 'global')
            tm('set-option', '-g', '@tmux-canopy-transition', 'slot')
            tm('set-option', '-g', '@tmux-canopy-theme', 'mono')
            tm('set-option', '-g', '@tmux-canopy-density', 'detailed')
            tm('set-option', '-g', '@tmux-canopy-preview', 'off')
            script_env = env.copy()
            script_env.update(TMUX=tm('display-message', '-p', '#{socket_path},#{pid},0'),
                              TMUX_CANOPY_STATE=str(state), TMUX_PANE=pane_a)
            sp.run([str(ROOT / 'tmux-canopy.tmux')], env=script_env, check=True, timeout=15)
            # Inject deterministic events; shell-startup output is not part of this test.
            tm('set-window-option', '-g', 'monitor-activity', 'off')
            tm('set-window-option', '-g', 'monitor-bell', 'off')

            tm('set-option', '-p', '-t', pane_b, 'allow-set-title', 'off')
            tm('select-pane', '-t', pane_b, '-T', 'title|with spaces')
            tm('set-option', '-g', '@tmux-canopy-icon-pane', 'icon\tline\n\x1b')
            snapshot = rows()
            assert all(len(row) == 3 for row in snapshot), snapshot
            assert len({row[2] for row in snapshot}) == len(snapshot)
            # The inline boundary keeps the pointer beside text in both modes.
            framed = [record.split('\t', 1) for record in run('sidebar-source', '--read0').strip('\0').split('\0')]
            session_rows = [row for row in framed if row[0].startswith('S:')]
            assert len(session_rows) == 2
            assert '─' not in session_rows[0][1] and '─' not in session_rows[1][1]
            assert all(icon not in row[1] for row in session_rows for icon in ('', '◈'))
            assert all(not row[1].startswith('\n') for row in framed)
            assert len(rows()) == len(snapshot), 'legacy record count changed'
            state.write_text('FILTER\tsession\n')
            only_session = [record.split('\t', 1) for record in run('sidebar-source', '--read0').strip('\0').split('\0')
                            if record.startswith('S:')]
            assert len(only_session) == 1 and '─' not in only_session[0][1]
            state.write_text('')
            pane_rows = [row for row in snapshot if row[0] == 'P:' + pane_b]
            assert {row[2] for row in pane_rows} == {f'P:{pane_b}:{sid_a}', f'P:{pane_b}:{sid_b}'}
            assert all('title|with spaces' in row[1] and 'icon line  ' in row[1] for row in pane_rows), pane_rows
            assert '\x1b' not in run('sidebar-source', '--stable')
            state.write_text(f'W:{window_b}:{sid_b}\n')
            assert [row[2] for row in rows() if row[0] == 'P:' + pane_b] == [f'P:{pane_b}:{sid_a}']
            state.write_text('')
            tm('set-option', '-gu', '@tmux-canopy-icon-pane')
            active_window = tm('display-message', '-p', '-t', pane_a, '#{window_id}')
            state.write_text(f'S:{sid_a}\n')
            folded_session = rows()
            assert '●' in next(row[1] for row in folded_session if row[0] == f'S:{sid_a}')
            assert sum('●' in row[1] for row in folded_session) == 1
            state.write_text(f'W:{active_window}:{sid_a}\n')
            folded_window = rows()
            assert '●' in next(row[1] for row in folded_window if row[0] == f'W:{active_window}:{sid_a}')
            assert sum('●' in row[1] for row in folded_window) == 1
            state.write_text('')
            expanded = rows()
            assert '●' in next(row[1] for row in expanded if row[0] == f'P:{pane_a}')
            assert sum('●' in row[1] for row in expanded) == 1
            print('ok - snapshot identities, linked occurrences, control-byte sanitization and collapse state')

            preserved = f'VIEW\ttree\nMOVE\tP:{pane_a}\nLINK\tW:{window_b}:{sid_a}\nDELETE\tP:{pane_c}\t1\n'
            state.write_text(preserved + 'S:$999\nW:@999:$999\n')
            run('sidebar-action', 'collapse-all')
            collapsed = state.read_text()
            expected_folds = set(tm('list-sessions', '-F', 'S:#{session_id}').splitlines())
            expected_folds.update(tm('list-windows', '-a', '-F', 'W:#{window_id}:#{session_id}').splitlines())
            assert collapsed.startswith(preserved)
            assert set(collapsed[len(preserved):].splitlines()) == expected_folds
            assert all(row[0].startswith(('H:', 'S:')) for row in rows())
            run('sidebar-action', 'collapse-all')
            assert state.read_text() == collapsed, 'collapse-all is not idempotent'
            run('sidebar-action', 'expand', 'S:' + sid_a)
            assert not any(row[0].startswith('P:') for row in rows()), 'nested windows were not collapsed'
            run('sidebar-action', 'expand-all')
            assert state.read_text() == preserved
            assert {row[2] for row in rows() if row[0] == 'P:' + pane_b} == {f'P:{pane_b}:{sid_a}', f'P:{pane_b}:{sid_b}'}
            run('sidebar-action', 'expand-all')
            assert state.read_text() == preserved
            for view in ('processes', 'buffers'):
                other = f'VIEW\t{view}\nS:{sid_a}\n'
                state.write_text(other)
                run('sidebar-action', 'collapse-all')
                run('sidebar-action', 'expand-all')
                assert state.read_text() == other, view
            failed_provider = temp / 'failed-provider'
            failed_provider.mkdir()
            failed_tmux = failed_provider / 'tmux'
            failed_tmux.write_text('#!/bin/sh\nprintf "S:$0\\n"\nexit 1\n')
            failed_tmux.chmod(0o755)
            state.write_text(preserved + 'S:$999\n')
            failure = sp.run([str(ROOT / 'scripts/sidebar-action'), 'collapse-all'],
                             env=script_env | {'PATH': str(failed_provider) + ':' + env['PATH']},
                             capture_output=True, text=True, timeout=10)
            assert failure.returncode != 0
            assert state.read_text() == preserved + 'S:$999\n', 'partial inventory changed state'
            run('sidebar-action', 'expand-all')
            assert state.read_text() == preserved, 'expand-all did not remove stale collapse records'
            state.write_text('')
            print('ok - bulk folding covers linked/hidden branches and preserves view and pending actions')

            # Instrument the actual sidebar fzf via extra test-only bindings.
            window_token = f'W:{window_b}:{sid_a}'
            pane_identity = f'P:{pane_b}:{sid_b}'
            position_w = next(i for i, row in enumerate(snapshot) if row[0] == window_token)
            position_p = next(i for i, row in enumerate(snapshot) if row[2] == pane_identity)
            position_s = next(i for i, row in enumerate(snapshot) if row[0] == f'S:{sid_b}')
            query = temp / 'query'
            bindings = [f'alt-a:pos({position_w})', f'alt-b:pos({position_p})', f'alt-c:pos({position_s})',
                        f"alt-q:execute-silent(printf '%s' {{q}} > {query})",
                        f"alt-z:execute-silent(printf '%s|%s|%s\\n' {{1}} {{3}} {{q}} > {selected})",
                        f'load:execute-silent(printf x >> {loads})']
            install_fzf_probe(temp, bindings, script_env)
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 44, 160, 0, 0))
            client_process = sp.Popen([tmux, '-L', socket, 'attach-session', '-t', 'one'],
                                     stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True)
            os.close(slave)

            def drain(fd):
                try:
                    while os.read(fd, 65536):
                        pass
                except OSError:
                    pass
            threading.Thread(target=drain, args=(master,), daemon=True).start()
            time.sleep(.2)
            client = tm('list-clients', '-F', '#{client_tty}')
            script_env['TMUX_CANOPY_CLIENT'] = client
            run('toggle', client, pane_a, '42', 'global', 'T', 'Tab', 'slot')
            sidebar = next(row.split('|')[0] for row in tm('list-panes', '-a', '-F', '#{pane_id}|#{@tmux_canopy}').splitlines() if row.endswith('|1'))
            wait_for(lambda: loads.stat().st_size > 0, 'initial sidebar load')
            time.sleep(.3)
            script_env['TMUX_PANE'] = sidebar
            wait_for(lambda: tm('show-option', '-pqv', '-t', sidebar, '@tmux_canopy_focus_location').endswith('|' + pane_a), 'current content location')
            frame = tm('capture-pane', '-p', '-t', sidebar).splitlines()
            second_session_line = next(i for i, line in enumerate(frame) if '▾' in line and 'two' in line)
            assert second_session_line > 0 and frame[second_session_line - 1].strip(), frame
            assert 'two' in frame[second_session_line] and all(icon not in frame[second_session_line] for icon in ('', '◈')), frame
            tm('send-keys', '-t', sidebar, 'M-c')
            wait_for(lambda: selection()[0] == f'S:{sid_b}', 'second session selection')
            frame = tm('capture-pane', '-p', '-t', sidebar).splitlines()
            second_session_line = next(i for i, line in enumerate(frame) if '▾' in line and 'two' in line)
            assert '›' in frame[second_session_line] and '›' not in frame[second_session_line - 1], frame
            tm('send-keys', '-t', sidebar, 'M-a')
            assert selection()[0] == window_token
            tm('send-keys', '-t', sidebar, 'C-o')
            assert selection()[1] == f'P:{pane_a}:{sid_a}'
            print('ok - Ctrl-o returns the pointer to the current content pane')
            sidebar_pid = tm('display-message', '-p', '-t', sidebar, '#{pane_pid}')
            fzf_pid = sp.check_output(['pgrep', '-P', sidebar_pid, '-x', 'fzf'], text=True).strip()
            geometry = tm('list-panes', '-a', '-F', '#{pane_id}|#{window_id}|#{pane_width}|#{pane_height}')
            for key, collapsed in (('H', True), ('L', False)):
                count = loads.stat().st_size
                tm('send-keys', '-t', sidebar, key)
                wait_for(lambda: loads.stat().st_size > count, 'bulk fold reload')
                screen = tm('capture-pane', '-p', '-t', sidebar)
                assert ('stable-beta' not in screen) == collapsed, screen
                assert selection()[0].startswith('S:')
            # In search mode these uppercase letters must be literal input,
            # even when the query produces no selected row.
            count = loads.stat().st_size
            tm('send-keys', '-t', sidebar, '/')
            tm('send-keys', '-t', sidebar, '-l', 'HL')
            tm('send-keys', '-t', sidebar, 'M-q')
            wait_for(lambda: query.exists() and query.read_text() == 'HL', 'uppercase search text')
            assert loads.stat().st_size == count, 'search letters triggered bulk folding'
            tm('send-keys', '-t', sidebar, 'Escape')
            time.sleep(.6)
            for key in ('H', 'L'):
                count = loads.stat().st_size
                tm('send-keys', '-t', sidebar, key)
                wait_for(lambda: loads.stat().st_size > count, 'bulk bindings restored after search')
            assert tm('list-panes', '-a', '-F', '#{pane_id}|#{window_id}|#{pane_width}|#{pane_height}') == geometry
            assert sp.check_output(['pgrep', '-P', sidebar_pid, '-x', 'fzf'], text=True).strip() == fzf_pid
            print('ok - H/L fold the live tree, behave as search text, and preserve fzf and geometry')
            # Expanded panes sharing a directory show its path once, without
            # a count. Folding hides them and puts the count at the edge.
            shared_dir = temp / 'shared'
            shared_dir.mkdir()
            count_pane = tm('new-window', '-d', '-t', 'one:', '-n', 'shared-count',
                            '-c', str(shared_dir), '-P', '-F', '#{pane_id}', 'sleep 600')
            count_peer = tm('split-window', '-d', '-h', '-t', count_pane, '-c', str(shared_dir),
                            '-P', '-F', '#{pane_id}', 'sleep 600')
            count_window = tm('display-message', '-p', '-t', count_pane, '#{window_id}')
            count_token = f'W:{count_window}:{sid_a}'
            tm('set-option', '-g', '@tmux-canopy-density', 'normal')
            state.write_text('')
            expanded_rows = rows()
            assert '2p' not in next(row[1] for row in expanded_rows if row[0] == count_token)
            shared_rows = [row[1] for row in expanded_rows if row[0] in ('P:' + count_pane, 'P:' + count_peer)]
            assert len(shared_rows) == 2 and all('2p' not in value for value in shared_rows)
            assert sum('shared' in value for value in shared_rows) == 1, shared_rows
            state.write_text('FILTER_WINDOW\tshared-count\n')
            filtered_row = next(row[1] for row in rows() if row[0] == count_token)
            assert '2p' not in filtered_row, filtered_row
            state.write_text('FILTER_WINDOW\tshared-count\n' + count_token + '\n')
            assert '[2/2p]' in next(row[1] for row in rows() if row[0] == count_token)
            state.write_text(count_token + '\n')
            folded_row = next(row[1] for row in rows() if row[0] == count_token)
            assert folded_row.endswith('2p'), folded_row
            width = int(tm('display-message', '-p', '-t', sidebar, '#{pane_width}'))
            assert len(folded_row) == width - 3, (len(folded_row), width, folded_row)
            tm('kill-window', '-t', count_window)
            tm('set-option', '-g', '@tmux-canopy-density', 'detailed')
            state.write_text('')
            print('ok - pane count appears only on collapsed windows')
            if '--folding-only' in sys.argv:
                return
            tm('send-keys', '-t', sidebar, 'M-a')
            assert selection()[0] == window_token
            tm('rename-window', '-t', window_b, 'stable-renamed')
            time.sleep(.4)
            assert selection()[0] == window_token
            tm('send-keys', '-t', sidebar, 'M-b')
            assert selection()[1] == pane_identity
            tm('rename-session', '-t', sid_a, 'zeta')
            time.sleep(.3)
            assert selection()[1] == pane_identity
            tm('rename-session', '-t', sid_a, 'one')
            time.sleep(.3)
            assert selection()[1] == pane_identity
            tm('send-keys', '-t', sidebar, '/')
            tm('send-keys', '-t', sidebar, '-l', 'sleep')
            time.sleep(.15)
            filtered_selection = selection()
            assert filtered_selection[0].startswith('P:') and filtered_selection[2] == 'sleep', filtered_selection
            tm('send-keys', '-t', sidebar, 'C-r')
            time.sleep(.15)
            assert selection() == filtered_selection
            tm('send-keys', '-t', sidebar, 'Escape')
            # Let the terminal's Escape/Alt ambiguity timeout expire before
            # injecting the Alt-z probe.
            time.sleep(.6)
            wait_for(lambda: selection()[2] == '', 'search mode exit')
            tm('send-keys', '-t', sidebar, 'M-b')
            assert selection()[1] == pane_identity, selection()
            print('ok - actual fzf retains renamed/linked objects and the query across filtered reloads')

            wrapper = temp / 'tmux'
            wrapper.write_text('#!/bin/bash\nif [[ "$1" == if-shell && "$*" == *tmux_canopy_notice_pending* && "$*" == *send-keys* ]]; then printf x >> ' + shlex.quote(str(deliveries)) + '; fi\nif [[ "$1" == list-clients && "${3:-}" == \'C|#{client_tty}|#{window_id}\' ]]; then printf x >> ' + shlex.quote(str(clears)) + '; fi\nexec ' + shlex.join([tmux, '-L', socket]) + ' "$@"\n')
            wrapper.chmod(0o755)
            tm('set-environment', '-g', 'PATH', str(temp) + ':' + env['PATH'])
            script_env['TMUX_CANOPY_NOTIFY_QUIET'] = '1'
            run('notify', 'clear-all')
            script_env.pop('TMUX_CANOPY_NOTIFY_QUIET')
            time.sleep(.3)
            count = deliveries.stat().st_size
            jobs = [sp.Popen([str(ROOT / 'scripts/notify'), 'set', window_b, pane_b, 'activity'],
                             env=script_env, stdout=sp.DEVNULL, stderr=sp.PIPE) for _ in range(20)]
            for job in jobs:
                _, err = job.communicate(timeout=10)
                assert job.returncode == 0, err
            time.sleep(.5)
            assert deliveries.stat().st_size == count + 1, (count, deliveries.read_text())
            assert selection()[1] == pane_identity
            assert tm('show-option', '-gqv', '@tmux_canopy_notice_pending') == ''
            assert tm('show-option', '-pqv', '-t', pane_b, '@tmux_canopy_notice_pane_activity') == '1'
            assert tm('show-option', '-pqv', '-t', pane_a, '@tmux_canopy_notice_pane_activity') == ''
            print('ok - 20 concurrent identical events produce one refresh without moving selection')

            count = deliveries.stat().st_size
            run('notify', 'set', window_b, sidebar, 'bell')
            run('notify', 'set', '@999999', pane_b, 'bell')
            run('notify', 'clear-client', 'missing-client')
            time.sleep(.2)
            assert deliveries.stat().st_size == count
            assert tm('show-option', '-wqv', '-t', window_b, '@tmux_canopy_notice_activity') == '1'
            print('ok - sidebar, wrong-window and detached-client events do not mutate notices')

            # Native selection hooks and the navigation transaction clear once,
            # quietly, and release the claim for future notifications.
            script_env.update(TMUX_PANE=sidebar, TMUX_CANOPY_SCOPE='global', TMUX_CANOPY_TRANSITION='slot')
            clears.write_text('')
            run('sidebar-action', 'activate', 'P:' + pane_b)
            wait_for(lambda: tm('show-option', '-wqv', '-t', window_b, '@tmux_canopy_notice_activity') == '', 'quiet destination clear')
            assert tm('show-option', '-pqv', '-t', pane_b, '@tmux_canopy_notice_pane_activity') == ''
            assert tm('show-option', '-wqv', '-t', window_b, '@tmux_canopy_notice_clear_pending') == ''
            assert tm('show-option', '-wqv', '-t', window_b, '@tmux_canopy_notice_suppress') == ''
            assert clears.read_text() == 'x', clears.read_text()
            print('ok - guarded navigation runs one quiet destination clear and releases claims')

            # Lost workers cannot permanently prevent subsequent refreshes.
            tm('set-option', '-g', '@tmux_canopy_notice_pending', '1.1.1')
            tm('set-option', '-g', '@tmux_canopy_notice_deadline', '1')
            run('notify', 'set', window_b, pane_b, 'bell')
            wait_for(lambda: tm('show-option', '-gqv', '@tmux_canopy_notice_pending') == '', 'expired refresh claim recovery')
            run('notify', 'clear-all')
            assert tm('show-option', '-wqv', '-t', window_b, '@tmux_canopy_notice_bell') == ''
            print('ok - expired refresh claims recover and clear-all removes notification state')

            tm('select-pane', '-t', sidebar)
            time.sleep(.2)
            def linked_selection_ready():
                tm('send-keys', '-t', sidebar, 'M-b')
                return selection()[1] == pane_identity
            wait_for(linked_selection_ready, 'linked pane selection after focus refresh')
            tm('send-keys', '-t', sidebar, 'Enter')
            wait_for(lambda: tm('list-clients', '-F', '#{session_id}|#{pane_id}') == f'{sid_b}|{pane_b}', 'linked pane activation in its displayed session')
            tm('select-pane', '-t', sidebar)
            time.sleep(.2)
            print('ok - Enter on a linked pane focuses its displayed session occurrence')
            tm('kill-pane', '-t', pane_b)
            time.sleep(.4)
            remaining = {row[2] for row in rows()[1:]}
            chosen = selection()[1]
            assert chosen in remaining and chosen != pane_identity, chosen
            print('ok - deleting the tracked object falls back to a live row without freezing fzf')
        finally:
            sp.run([tmux, '-L', socket, 'kill-server'], env=env, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
            if client_process:
                client_process.wait(timeout=5)
            if master is not None:
                os.close(master)
    print('all snapshot, notification and selection tests passed')


if __name__ == '__main__':
    main()
