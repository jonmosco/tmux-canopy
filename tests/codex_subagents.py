#!/usr/bin/env python3
"""Codex subagent hooks appear under the owning pane without changing its status."""
import json
import os
from pathlib import Path
import re
import subprocess as sp
import tempfile

from support import install_agent_fixture

ROOT = Path(__file__).resolve().parents[1]
socket = f'canopy-codex-subagents-{os.getpid()}'
env = os.environ.copy()
env.pop('TMUX', None)
env.pop('TMUX_PANE', None)


def tm(*args):
    result = sp.run(['tmux', '-L', socket, *args], env=env, text=True,
                    capture_output=True, timeout=10)
    assert result.returncode == 0, (args, result.stderr)
    return result.stdout.strip()


try:
    with tempfile.TemporaryDirectory(prefix='canopy-codex-subagents-', ignore_cleanup_errors=True) as directory:
        temp = Path(directory)
        state = temp / 'state'
        state.touch()
        install_agent_fixture(temp / 'codex')
        pane = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'agents', '-x', '120', '-y', '30',
                  '-P', '-F', '#{pane_id}', str(temp / 'codex') + ' 600')
        tm('set-option', '-g', '@tmux-canopy-agents', 'on')
        other = tm('new-window', '-d', '-t', 'agents:', '-P', '-F', '#{pane_id}', 'sleep 600')
        tmux_env = tm('display-message', '-p', '-t', pane, '#{socket_path},#{pid},0')
        base = env | {'TMUX': tmux_env, 'TMUX_CANOPY_STATE': str(state), 'TMUX_PANE': other}

        def event(payload):
            result = sp.run([str(ROOT / 'scripts/codex-hook')], input=json.dumps(payload),
                            env=base | {'TMUX_PANE': pane}, text=True, capture_output=True, timeout=10)
            expected = '{}\n' if payload['hook_event_name'] in ('Stop', 'SubagentStop') else ''
            assert result.returncode == 0 and result.stdout == expected, (payload, result.stderr, result.stdout)

        def rows(*args):
            result = sp.run([str(ROOT / 'scripts/tree-source'), *args], env=base | {
                'TMUX_CANOPY_NUL': '1'}, capture_output=True, text=True, timeout=10)
            assert result.returncode == 0, result.stderr
            return {record.split('\t', 1)[0]: record.split('\t', 1)[1]
                    for record in result.stdout.split('\0') if '\t' in record}

        def option(name):
            return tm('display-message', '-p', '-t', pane, '#{@tmux_canopy_agent_' + name + '}')

        session = {'session_id': 'codex-main', 'turn_id': 'turn-1'}
        event(session | {'hook_event_name': 'SessionStart'})
        tm('set-option', '-g', '@tmux-canopy-icon-codex', 'C')
        for view, name in (((), 'codex'), (('--agents',), 'Codex')):
            row = re.sub(r'\x1b\[[0-9;]*m', '', rows(*view)['P:' + pane])
            assert f'C {name}' in row, (view, row)
        tm('set-option', '-g', '@tmux-canopy-icon-codex', 'none')
        assert '◈' not in rows()['P:' + pane]
        tm('set-option', '-gu', '@tmux-canopy-icon-codex')
        print('ok - per-app override reaches Tree and Agents and none hides the glyph')
        event(session | {'hook_event_name': 'UserPromptSubmit'})
        event(session | {'hook_event_name': 'SubagentStart', 'agent_id': 'child-1', 'agent_type': 'Explore'})
        event(session | {'hook_event_name': 'SubagentStart', 'agent_id': 'child-2', 'agent_type': 'general-purpose'})
        for view in ((), ('--agents',)):
            lines = rows(*view)['P:' + pane].split('\n')
            assert any('Explore' in line and 'WORKING' in line for line in lines[1:]), (view, lines)
            assert any('general-purpose' in line and 'WORKING' in line for line in lines[1:]), (view, lines)
        assert option('status') == 'working'
        print('ok - Codex subagents appear under their parent pane in Tree and Agents')

        # Codex currently documents agent_id for child lifecycle events, but
        # does not promise it on permission/tool events. Attribute only if sent.
        request = session | {'hook_event_name': 'PermissionRequest', 'agent_id': 'child-2',
                             'agent_type': 'general-purpose', 'tool_name': 'Bash',
                             'tool_input': {'description': 'Build the project', 'command': 'make'}}
        event(request)
        assert any('general-purpose' in line and 'NEEDS INPUT' in line
                   for line in rows('--agents')['P:' + pane].split('\n')[1:])
        assert option('request_agent') == 'child-2'
        needs = sp.run([str(ROOT / 'scripts/tree-source'), '--needs-input'], env=base,
                       capture_output=True, text=True, timeout=10)
        assert needs.returncode == 0 and f'P:{pane}\t' in needs.stdout
        event(session | {'hook_event_name': 'PostToolUse', 'tool_name': 'Bash',
                         'tool_input': {'command': 'make'}})
        assert option('status') == 'needs-input'
        event(request | {'hook_event_name': 'PreToolUse', 'tool_input': {'command': 'make'}})
        assert option('status') == 'working'
        print('ok - matching tool start clears a tagged child request without waiting for tool completion')

        event(request)
        event(session | {'hook_event_name': 'SubagentStop', 'agent_id': 'child-2',
                         'agent_type': 'general-purpose'})
        assert option('status') == 'working' and option('request_agent') == ''
        assert not any('general-purpose' in line for line in rows()['P:' + pane].split('\n')[1:])
        print('ok - child completion clears its request and removes its row')

        event(session | {'hook_event_name': 'SubagentStop', 'agent_id': 'child-1', 'agent_type': 'Explore'})
        assert option('status') == 'working'
        lines = rows()['P:' + pane].split('\n')
        assert not any('Explore' in line for line in lines[1:]), lines
        assert option('subagents') == ''
        event(session | {'hook_event_name': 'Stop'})
        assert option('status') == 'turn-ended'
        assert option('subagents') == ''
        print('ok - child completion leaves the parent state alone and rows stay removed')

        event(session | {'hook_event_name': 'SubagentStart', 'agent_id': '../bad id'})
        assert option('subagents') == ''
        event(session | {'hook_event_name': 'UserPromptSubmit'})
        event(session | {'hook_event_name': 'SubagentStart', 'agent_id': 'waiting', 'agent_type': 'Plan'})
        event(request | {'agent_id': 'waiting', 'agent_type': 'Plan'})
        for index in range(8):
            event(session | {'hook_event_name': 'SubagentStart', 'agent_id': f'other-{index}'})
        assert 'waiting,' not in option('subagents')
        event(session | {'hook_event_name': 'SubagentStop', 'agent_id': 'waiting'})
        assert option('status') == 'working' and option('request_agent') == ''
        print('ok - completion clears a request even if its child row was evicted')
        event(session | {'hook_event_name': 'SessionEnd'})
        assert option('subagents') == ''
        print('ok - invalid child IDs are ignored and session end clears child state')
finally:
    sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)
