#!/usr/bin/env python3
"""Live tmux checks for distinct process, screen, and lifecycle evidence."""
import json
import os
from pathlib import Path
from support import install_agent_fixture
import subprocess as sp
import tempfile

ROOT = Path(__file__).resolve().parents[1]
socket = f'canopy-harnesses-{os.getpid()}'
env = os.environ.copy()
env.pop('TMUX', None)
env.pop('TMUX_PANE', None)


def tm(*args):
    result = sp.run(['tmux', '-L', socket, *args], env=env, text=True,
                    capture_output=True, timeout=10)
    assert result.returncode == 0, (args, result.stderr)
    return result.stdout.strip()


try:
    with tempfile.TemporaryDirectory(prefix='canopy-harnesses-', ignore_cleanup_errors=True) as directory:
        temp = Path(directory)
        state = temp / 'state'
        state.touch()
        names = ('claude', 'opencode', 'gemini', 'pi', 'omp')
        for name in names:
            install_agent_fixture(temp / name)
        pane = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'agents', '-x', '100', '-y', '30',
                  '-P', '-F', '#{pane_id}', str(temp / names[0]) + ' 600')
        panes = {names[0]: pane}
        for name in names[1:]:
            panes[name] = tm('new-window', '-d', '-t', 'agents:', '-P', '-F', '#{pane_id}',
                             str(temp / name) + ' 600')
        # Native Claude Code installs run as claude.exe, including on macOS.
        install_agent_fixture(temp / 'claude.exe')
        panes['claude.exe'] = tm('new-window', '-d', '-t', 'agents:', '-P', '-F', '#{pane_id}',
                                 str(temp / 'claude.exe') + ' 600')
        tmux_env = tm('display-message', '-p', '-t', pane, '#{socket_path},#{pid},0')

        def run(name, pane_id, payload=None):
            script_env = env | {'TMUX': tmux_env, 'TMUX_PANE': pane_id,
                                'TMUX_CANOPY_STATE': str(state)}
            result = sp.run([str(ROOT / 'scripts' / name), *(payload or [])], env=script_env,
                            text=True, capture_output=True, timeout=10)
            assert result.returncode == 0, (name, result.stderr)
            return result.stdout

        def event(kind, pane_id, payload):
            script_env = env | {'TMUX': tmux_env, 'TMUX_PANE': pane_id}
            result = sp.run([str(ROOT / 'scripts/agent-hook'), kind],
                            input=json.dumps(payload), env=script_env, text=True,
                            capture_output=True, timeout=10)
            assert result.returncode == 0 and result.stdout == '', result.stderr

        agent_view = run('tree-source', pane, ['--agents'])
        for name, pane_id in panes.items():
            row = next(line for line in agent_view.splitlines() if line.startswith('P:' + pane_id + '\t'))
            assert '[process]' in row and '·hook' not in row, (name, row)
            assert 'Source: visible terminal text' in run('agent-preview', pane, ['P:' + pane_id])

        event('claude', panes['claude'], {'hook_event_name': 'SessionStart', 'session_id': 'c1'})
        event('claude', panes['claude'], {'hook_event_name': 'UserPromptSubmit', 'session_id': 'c1'})
        event('claude', panes['claude'], {'hook_event_name': 'PermissionRequest', 'session_id': 'c1',
                                         'tool_name': 'Bash', 'tool_input': {'command': 'date'}})
        assert 'Status: Approval requested (hook report)' in run('agent-preview', panes['claude'], ['P:' + panes['claude']])
        event('claude', panes['claude'], {'hook_event_name': 'PostToolUse', 'session_id': 'c1',
                                         'tool_name': 'Other'})
        assert 'Approval requested' in run('agent-preview', panes['claude'], ['P:' + panes['claude']])
        event('claude', panes['claude'], {'hook_event_name': 'PostToolUse', 'session_id': 'c1',
                                         'tool_name': 'Bash'})
        assert 'Status: Working' in run('agent-preview', panes['claude'], ['P:' + panes['claude']])

        event('claude', panes['claude.exe'], {'hook_event_name': 'SessionStart', 'session_id': 'n1'})
        event('claude', panes['claude.exe'], {'hook_event_name': 'PermissionRequest', 'session_id': 'n1',
                                             'tool_name': 'Bash', 'tool_input': {'command': 'date'}})
        assert 'Status: Approval requested (hook report)' in run('agent-preview', panes['claude.exe'], ['P:' + panes['claude.exe']])

        event('gemini', panes['gemini'], {'hook_event_name': 'SessionStart', 'session_id': 'g1'})
        event('gemini', panes['gemini'], {'hook_event_name': 'Notification', 'session_id': 'g1',
                                         'notification_type': 'ToolPermission', 'message': 'Allow shell command?'})
        event('gemini', panes['gemini'], {'hook_event_name': 'BeforeAgent', 'session_id': 'other'})
        assert 'Status: Approval requested' in run('agent-preview', panes['gemini'], ['P:' + panes['gemini']])

        event('pi', panes['pi'], {'type': 'session_start', 'session_id': 'p1'})
        event('pi', panes['pi'], {'type': 'agent_start', 'session_id': 'p1'})
        event('omp', panes['omp'], {'type': 'session_start', 'session_id': 'o1'})
        event('omp', panes['omp'], {'type': 'agent_end', 'session_id': 'o1'})

        event('opencode', panes['opencode'], {'type': 'session.created', 'properties': {'info': {'id': 'oc1'}}})
        event('opencode', panes['opencode'], {'type': 'session.status', 'properties': {'sessionID': 'oc1',
                                               'status': {'type': 'busy'}}})
        event('opencode', panes['opencode'], {'type': 'permission.asked', 'properties': {'sessionID': 'other'}})
        assert 'Status: Working' in run('agent-preview', panes['opencode'], ['P:' + panes['opencode']])

        agent_view = run('tree-source', pane, ['--agents'])
        assert 'WORKING' in agent_view and 'NEEDS INPUT' in agent_view and '·hook' in agent_view
        assert 'WORKING' in agent_view and '·plugin?' in agent_view and 'TURN ENDED' in agent_view
        tm('set-option', '-pq', '-t', panes['pi'], '@tmux_canopy_agent_updated', '1')
        stale_view = run('tree-source', pane, ['--agents'])
        assert 'UNKNOWN' in stale_view and '·hook' in stale_view
        print('ok - harness rows distinguish process-only, unverified screen, and reported lifecycle states')
finally:
    sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)
