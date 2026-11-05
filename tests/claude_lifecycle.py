#!/usr/bin/env python3
"""Claude Code status survives process exit, restart, and pane reuse.

Each case runs a real process named `claude` in a real pane, feeds it hook
events through scripts/agent-hook, and checks what the sidebar renders. The
raw pane options may keep old values; what matters is that the tree, the Agents
view, and the inspector never show them for a different process.
"""
import json
import os
from pathlib import Path
import re
import subprocess as sp
import tempfile
import time

from support import install_agent_fixture

ROOT = Path(__file__).resolve().parents[1]
socket = f'canopy-claude-lifecycle-{os.getpid()}'
env = os.environ.copy()
env.pop('TMUX', None)
env.pop('TMUX_PANE', None)
STALE = 'old-request-7f3'


def tm(*args):
    result = sp.run(['tmux', '-L', socket, *args], env=env, text=True,
                    capture_output=True, timeout=10)
    assert result.returncode == 0, (args, result.stderr)
    return result.stdout.strip()


def until(condition, message, seconds=3):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = condition()
        if value:
            return value
        time.sleep(.05)
    raise AssertionError(message)


try:
    with tempfile.TemporaryDirectory(prefix='canopy-claude-lifecycle-', ignore_cleanup_errors=True) as temp_dir:
        claude = Path(temp_dir) / 'claude'
        codex = Path(temp_dir) / 'codex'
        install_agent_fixture(claude)
        install_agent_fixture(codex)
        pane = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'studio', '-x', '120', '-y', '35',
                  '-P', '-F', '#{pane_id}', f"/bin/bash -c '{claude} 600; exec sleep 600'")
        tm('set-option', '-g', '@tmux-canopy-agents', 'on')
        sidebar = tm('split-window', '-d', '-h', '-b', '-l', '42', '-t', pane,
                     '-P', '-F', '#{pane_id}', 'sleep 600')
        tm('set-option', '-p', '-t', sidebar, '@tmux_canopy', '1')
        state = Path(temp_dir) / 'state'
        state.write_text('')
        script_env = env | {'TMUX': tm('display-message', '-p', '-t', pane, '#{socket_path},#{pid},0'),
                            'TMUX_PANE': sidebar, 'TMUX_CANOPY_STATE': str(state),
                            'FZF_PREVIEW_LINES': '12', 'FZF_PREVIEW_COLUMNS': '60'}

        def run(name, *args):
            result = sp.run([str(ROOT / 'scripts' / name), *args], env=script_env,
                            text=True, capture_output=True, timeout=10)
            assert result.returncode == 0, (name, result.stderr)
            return re.sub(r'\x1b\[[0-9;]*m', '', result.stdout)

        def hook(event):
            result = sp.run([str(ROOT / 'scripts/agent-hook'), 'claude'], input=json.dumps(event),
                            text=True, capture_output=True, env=script_env | {'TMUX_PANE': pane}, timeout=10)
            assert result.returncode == 0 and result.stdout == '', (result.stdout, result.stderr)

        def row():
            return next(line.split('\t')[1] for line in run('sidebar-source', '--stable').splitlines()
                        if line.startswith('P:' + pane + '\t'))

        def agents_view():
            run('sidebar-action', 'view-agents')
            try:
                return run('sidebar-source', '--stable')
            finally:
                run('sidebar-action', 'view-tree')

        def option(name):
            return tm('show-option', '-pqv', '-t', pane, '@tmux_canopy_agent_' + name)

        def children(name='claude'):
            root = tm('display-message', '-p', '-t', pane, '#{pane_pid}')
            result = sp.run(['pgrep', '-P', root, '-x', name], text=True, capture_output=True)
            return result.stdout.split()

        def start_session(session):
            hook({'hook_event_name': 'SessionStart', 'session_id': session})

        def raise_request():
            hook({'hook_event_name': 'UserPromptSubmit', 'session_id': 'first'})
            hook({'hook_event_name': 'PermissionRequest', 'session_id': 'first', 'tool_name': 'Bash',
                  'tool_input': {'description': f'Run {STALE}', 'command': f'echo {STALE}'}})

        def assert_clean(label):
            """No Claude hook state is visible for whatever runs in the pane now."""
            text = row()
            assert not any(word in text for word in ('READY', 'WORKING', 'NEEDS INPUT', 'TURN ENDED',
                                                     'SESSION ENDED', '·hook')), (label, text)
            assert STALE not in run('agent-preview', 'P:' + pane), label

        first = until(children, 'fixture claude never started')[0]
        start_session('first')
        assert 'READY' in row() and '·hook' in row()
        raise_request()
        assert 'NEEDS INPUT' in row() and STALE in run('agent-preview', 'P:' + pane)
        assert f'P:{pane}:' in agents_view()

        # 1. The process exits and the pane falls back to its shell. The old
        # request must disappear from every view, and a hook that was already
        # in flight must not bring it back.
        sp.run(['kill', '-TERM', first], check=True)
        until(lambda: not children(), 'claude did not exit')
        assert_clean('after exit')
        assert 'V:agents-empty' in agents_view(), 'exited Claude still listed as an agent'
        hook({'hook_event_name': 'Stop', 'session_id': 'first'})
        hook({'hook_event_name': 'SessionEnd', 'session_id': 'first'})
        assert_clean('late hooks after exit')
        assert 'V:agents-empty' in agents_view()
        print('ok - Claude exit clears status and request, and late hooks cannot revive them', flush=True)

        # 2. A shell starts a second Claude without changing the pane PID.
        tm('respawn-pane', '-k', '-t', pane,
           f"/bin/bash -c '{claude} 600; {claude} 600; exec sleep 600'")
        until(lambda: children(), 'first nested claude never started')
        nested = children()[0]
        start_session('nested-one')
        assert 'READY' in row() and option('process_pid') == nested
        raise_request()
        assert 'NEEDS INPUT' in row()
        sp.run(['kill', '-TERM', nested], check=True)
        until(lambda: children() and children()[0] != nested, 'second nested claude never started')
        assert_clean('after in-shell restart')
        restarted = children()[0]
        start_session('nested-two')
        assert 'READY' in row() and '·hook' in row(), row()
        assert option('session') == 'nested-two' and option('process_pid') == restarted
        assert option('request') == '' and STALE not in run('agent-preview', 'P:' + pane)
        print('ok - a Claude restarted by the same shell reports as a fresh process', flush=True)

        # 3. /clear and resume end and start sessions inside one live process.
        hook({'hook_event_name': 'SessionEnd', 'session_id': 'nested-two'})
        assert 'SESSION ENDED' in row()
        hook({'hook_event_name': 'SessionStart', 'session_id': 'nested-three', 'source': 'clear'})
        assert 'READY' in row() and option('session') == 'nested-three'
        assert option('process_pid') == restarted
        print('ok - an ended session in a live Claude process can be replaced by a new one', flush=True)

        # 4. The pane is reused for another program. Claude's state must not
        # appear on it, and hooks from a Claude that is not there are ignored.
        raise_request()
        assert 'NEEDS INPUT' in row()
        tm('respawn-pane', '-k', '-t', pane, f"/bin/bash -c '{codex} 600; exec sleep 600'")
        until(lambda: children('codex'), 'codex fixture never started')
        assert_clean('pane reused by Codex')
        assert 'Codex' in agents_view() and 'Claude' not in agents_view()
        tm('respawn-pane', '-k', '-t', pane, 'sleep 600')
        until(lambda: not children() and not children('codex'), 'pane did not return to a shell')
        before = option('session')
        start_session('ghost')
        assert option('session') == before, 'hook accepted for a pane without Claude'
        assert_clean('hook sent to a pane without Claude')
        print('ok - a pane reused by another program shows none of Claude\'s state', flush=True)

        # 5. A fresh Claude in the reused pane starts from a clean record.
        tm('respawn-pane', '-k', '-t', pane, f"/bin/bash -c '{claude} 600; exec sleep 600'")
        until(children, 'replacement claude never started')
        assert_clean('replacement Claude before any hook')
        start_session('replacement')
        assert 'READY' in row() and option('session') == 'replacement' and option('request') == ''
        print('ok - a replacement Claude in a reused pane starts clean', flush=True)
finally:
    sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)
