#!/usr/bin/env python3
"""Live tmux checks for distinct process, screen, and lifecycle evidence."""
import json
import re
import os
import shutil
from pathlib import Path
from support import install_agent_fixture
import subprocess as sp
import tempfile
import time

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
        names = ('claude', 'opencode', 'gemini', 'pi', 'omp', 'agy', 'agent', 'crush', 'copilot', 'grok')
        for name in names:
            install_agent_fixture(temp / name)
        pane = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'agents', '-x', '100', '-y', '30',
                  '-P', '-F', '#{pane_id}', str(temp / names[0]) + ' 600')
        tm('set-option', '-g', '@tmux-canopy-agents', 'on')
        panes = {names[0]: pane}
        for name in names[1:]:
            panes[name] = tm('new-window', '-d', '-t', 'agents:', '-P', '-F', '#{pane_id}',
                             str(temp / name) + ' 600')
        # An editor that starts an agent as its own child (an editor plugin)
        # owns that agent: the pane is the editor, not an agent pane.
        install_agent_fixture(temp / 'nvim')
        editor = temp / 'editor.sh'
        editor.write_text(f'#!/bin/bash\n{temp / "opencode"} 600 &\nexec {temp / "nvim"} 600\n')
        editor.chmod(0o755)
        # Its own directory: OpenCode events are matched to panes by directory.
        (temp / 'editor-project').mkdir()
        editor_pane = tm('new-window', '-d', '-t', 'agents:', '-c', str(temp / 'editor-project'),
                         '-P', '-F', '#{pane_id}', str(editor))
        # A sandbox wrapper stays the agent's parent and still counts as its pane.
        sandbox = temp / 'bwrap'
        shutil.copy(shutil.which('bash'), sandbox)
        panes['sandboxed'] = tm('new-window', '-d', '-t', 'agents:', '-P', '-F', '#{pane_id}',
                                f'{sandbox} -c "{temp / "claude"} 600; :"')
        sandbox_root = tm('display-message', '-p', '-t', panes['sandboxed'], '#{pane_pid}')
        for _ in range(100):
            if sp.run(['pgrep', '-P', sandbox_root], capture_output=True).returncode == 0:
                break
            time.sleep(.05)
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

        def event(kind, pane_id, payload, name=None):
            script_env = env | {'TMUX': tmux_env, 'TMUX_PANE': pane_id}
            result = sp.run([str(ROOT / 'scripts/agent-hook'), kind, *([name] if name else [])],
                            input=json.dumps(payload), env=script_env, text=True,
                            capture_output=True, timeout=10)
            if kind == 'agy':
                expected_out = '{"decision": ""}\n' if name == 'Stop' else '{}\n'
            elif kind == 'cursor-agent':
                expected_out = ('{"permission":"allow"}\n' if payload.get('hook_event_name') == 'subagentStart'
                                else '{}\n')
            else:
                expected_out = ''
            assert result.returncode == 0 and result.stdout == expected_out, result.stderr

        agent_view = run('tree-source', pane, ['--agents'])
        for name, pane_id in panes.items():
            row = next(line for line in agent_view.splitlines() if line.startswith('P:' + pane_id + '\t'))
            assert '[process]' in row and '·hook' not in row, (name, row)
            assert 'Source: visible terminal text' in run('agent-preview', pane, ['P:' + pane_id])
        assert not any(line.startswith('P:' + editor_pane + '\t') for line in agent_view.splitlines()), agent_view
        assert 'No supported agent process' in run('agent-preview', pane, ['P:' + editor_pane])
        # Crush is detected by process only (it has no lifecycle adapter yet).
        crush_row = next(line for line in agent_view.splitlines() if line.startswith('P:' + panes['crush'] + '\t'))
        assert 'Crush' in crush_row and '❖' in crush_row, crush_row
        assert 'Crush' in run('agent-preview', pane, ['P:' + panes['crush']])
        tm('set-option', '-g', '@tmux-canopy-icon-crush', 'C')
        crush_row = next(line for line in run('tree-source', pane, ['--agents']).splitlines()
                         if line.startswith('P:' + panes['crush'] + '\t'))
        crush_text = re.sub(r'\x1b\[[0-9;]*m', '', crush_row)
        assert ' C Crush' in crush_text and '❖' not in crush_text, crush_text
        tm('set-option', '-gu', '@tmux-canopy-icon-crush')
        for name, label, glyph in (('copilot', 'Copilot CLI', '⊚'), ('grok', 'Grok Build', '⨯')):
            row = next(line for line in agent_view.splitlines() if line.startswith('P:' + panes[name] + '\t'))
            assert label in row and glyph in row, row
            assert label in run('agent-preview', pane, ['P:' + panes[name]])

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

        event('copilot', panes['copilot'], {'sessionId': 'k1'}, 'sessionStart')
        event('copilot', panes['copilot'], {'sessionId': 'k1', 'notification_type': 'permission_prompt',
                                            'message': 'Allow shell command?'}, 'notification')
        assert 'Status: Approval requested' in run('agent-preview', panes['copilot'], ['P:' + panes['copilot']])
        event('grok', panes['grok'], {'hook_event_name': 'SessionStart', 'sessionId': 'x1'})
        event('grok', panes['grok'], {'hook_event_name': 'UserPromptSubmit', 'sessionId': 'x1', 'promptId': 'p1'})
        assert 'Status: Working' in run('agent-preview', panes['grok'], ['P:' + panes['grok']])
        # Grok also runs Claude's hooks; a Claude report from a Grok pane is ignored.
        event('claude', panes['grok'], {'hook_event_name': 'Stop', 'session_id': 'x1'})
        assert 'Status: Working' in run('agent-preview', panes['grok'], ['P:' + panes['grok']])

        agy = {'conversationId': 'a1', 'workspacePaths': ['/work'],
               'transcriptPath': '/work/transcript.jsonl', 'modelName': 'gemini'}
        event('agy', panes['agy'], agy | {'hook_event_name': 'PermissionRequest'}, 'PermissionRequest')
        assert 'Source: visible terminal text' in run('agent-preview', panes['agy'], ['P:' + panes['agy']])
        event('agy', panes['agy'], agy | {'invocationNum': 0, 'initialNumSteps': 0}, 'PreInvocation')
        assert 'Status: Working' in run('agent-preview', panes['agy'], ['P:' + panes['agy']])
        event('agy', panes['agy'], agy | {'toolCall': {'name': 'run_command', 'args': {'CommandLine': 'date'}},
                                          'stepIdx': 1, 'error': ''}, 'PostToolUse')
        assert 'Status: Working' in run('agent-preview', panes['agy'], ['P:' + panes['agy']])
        event('agy', panes['agy'], agy | {'invocationNum': 0, 'initialNumSteps': 1}, 'PostInvocation')
        assert 'Status: Working' in run('agent-preview', panes['agy'], ['P:' + panes['agy']])
        event('agy', panes['agy'], agy | {'executionNum': 1, 'terminationReason': 'model_stop',
                                          'error': '', 'fullyIdle': False}, 'Stop')
        assert 'Status: Working' in run('agent-preview', panes['agy'], ['P:' + panes['agy']])
        event('agy', panes['agy'], agy | {'executionNum': 1, 'terminationReason': 'model_stop',
                                          'error': '', 'fullyIdle': True}, 'Stop')
        assert 'Status: Turn ended' in run('agent-preview', panes['agy'], ['P:' + panes['agy']])
        event('agy', panes['agy'], agy | {'invocationNum': 1, 'initialNumSteps': 4}, 'PreInvocation')
        assert 'Status: Working' in run('agent-preview', panes['agy'], ['P:' + panes['agy']])
        event('agy', panes['agy'], agy | {'executionNum': 2, 'terminationReason': 'error',
                                          'error': 'request failed', 'fullyIdle': True}, 'Stop')
        assert 'Status: Interrupted' in run('agent-preview', panes['agy'], ['P:' + panes['agy']])

        event('pi', panes['pi'], {'type': 'session_start', 'session_id': 'p1'})
        event('pi', panes['pi'], {'type': 'agent_start', 'session_id': 'p1'})
        event('omp', panes['omp'], {'type': 'session_start', 'session_id': 'o1'})
        event('omp', panes['omp'], {'type': 'agent_end', 'session_id': 'o1'})

        opencode_dir = tm('display-message', '-p', '-t', panes['opencode'], '#{pane_current_path}')
        event('opencode', panes['opencode'], {'type': 'session.created', 'properties': {
            'sessionID': 'oc1', 'info': {'id': 'oc1', 'directory': opencode_dir}}})
        event('opencode', panes['opencode'], {'type': 'session.status', 'properties': {'sessionID': 'oc1',
                                               'status': {'type': 'busy'}}})
        event('opencode', panes['opencode'], {'type': 'permission.asked', 'properties': {'sessionID': 'other'}})
        assert 'Status: Working' in run('agent-preview', panes['opencode'], ['P:' + panes['opencode']])

        event('cursor-agent', panes['agent'], {'hook_event_name': 'sessionStart', 'conversation_id': 'ca1'})
        event('cursor-agent', panes['agent'], {'hook_event_name': 'beforeSubmitPrompt', 'conversation_id': 'ca1'})
        assert 'Status: Working' in run('agent-preview', panes['agent'], ['P:' + panes['agent']])

        agent_view = run('tree-source', pane, ['--agents'])
        assert 'WORKING' in agent_view and 'NEEDS INPUT' in agent_view and '·hook' in agent_view
        assert 'WORKING' in agent_view and '·plugin?' in agent_view and 'TURN ENDED' in agent_view
        cursor_row = next(line for line in agent_view.splitlines() if line.startswith('P:' + panes['agent'] + '\t'))
        assert 'cursor-agent' in cursor_row and 'WORKING' in cursor_row, cursor_row
        # Tree view (no --agents) must also resolve the raw "agent" process
        # command to cursor-agent's lifecycle label, not only the process scan.
        tree_view = run('tree-source', pane)
        tree_cursor_row = next(line for line in tree_view.splitlines() if line.startswith('P:' + panes['agent'] + '\t'))
        assert 'WORKING' in tree_cursor_row, tree_cursor_row
        tm('set-option', '-pq', '-t', panes['pi'], '@tmux_canopy_agent_updated', '1')
        stale_view = run('tree-source', pane, ['--agents'])
        stale_row = next(line for line in stale_view.splitlines() if line.startswith('P:' + panes['pi'] + '\t'))
        assert 'UNKNOWN' not in stale_row and '·hook' not in stale_row and '[process]' in stale_row
        print('ok - harness rows distinguish process-only, unverified screen, and reported lifecycle states')
finally:
    sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)
