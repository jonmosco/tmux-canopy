#!/usr/bin/env python3
"""Claude Code subagents reported as read-only children of their parent pane."""
import json
import os
from pathlib import Path
from support import install_agent_fixture
import subprocess as sp
import tempfile

ROOT = Path(__file__).resolve().parents[1]
socket = f'canopy-subagents-{os.getpid()}'
env = os.environ.copy()
env.pop('TMUX', None)
env.pop('TMUX_PANE', None)


def tm(*args):
    result = sp.run(['tmux', '-L', socket, *args], env=env, text=True,
                    capture_output=True, timeout=10)
    assert result.returncode == 0, (args, result.stderr)
    return result.stdout.strip()


try:
    with tempfile.TemporaryDirectory(prefix='canopy-subagents-', ignore_cleanup_errors=True) as directory:
        temp = Path(directory)
        state = temp / 'state'
        state.touch()
        install_agent_fixture(temp / 'claude')
        pane = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'agents', '-x', '120', '-y', '30',
                  '-P', '-F', '#{pane_id}', str(temp / 'claude') + ' 600')
        tm('set-option', '-g', '@tmux-canopy-agents', 'on')
        other = tm('new-window', '-d', '-t', 'agents:', '-P', '-F', '#{pane_id}', 'sleep 600')
        tmux_env = tm('display-message', '-p', '-t', pane, '#{socket_path},#{pid},0')
        base = env | {'TMUX': tmux_env, 'TMUX_CANOPY_STATE': str(state)}

        def event(payload):
            result = sp.run([str(ROOT / 'scripts/agent-hook'), 'claude'], input=json.dumps(payload),
                            env=base | {'TMUX_PANE': pane}, text=True, capture_output=True, timeout=10)
            assert result.returncode == 0 and result.stdout == '', result.stderr

        def rows(*args):
            # Multi-line pane rows (and so subagent lines) need NUL framing.
            result = sp.run([str(ROOT / 'scripts/tree-source'), *args], env=base | {
                'TMUX_PANE': other, 'TMUX_CANOPY_NUL': '1'}, capture_output=True, text=True, timeout=10)
            assert result.returncode == 0, result.stderr
            return {record.split('\t', 1)[0]: record.split('\t', 1)[1]
                    for record in result.stdout.split('\0') if '\t' in record}

        def pane_row(*args):
            return rows(*args)['P:' + pane]

        def needs_input():
            result = sp.run([str(ROOT / 'scripts/tree-source'), '--needs-input'], env=base | {'TMUX_PANE': other},
                            capture_output=True, text=True, timeout=10)
            return result.stdout

        def option(name):
            return tm('display-message', '-p', '-t', pane, '#{@tmux_canopy_agent_' + name + '}')

        def preview():
            result = sp.run([str(ROOT / 'scripts/agent-preview'), 'P:' + pane], env=base | {'TMUX_PANE': other},
                            capture_output=True, text=True, timeout=10)
            return result.stdout

        session = {'session_id': 'main'}
        event(session | {'hook_event_name': 'SessionStart'})
        event(session | {'hook_event_name': 'UserPromptSubmit'})
        event(session | {'hook_event_name': 'SubagentStart', 'agent_id': 'a1', 'agent_type': 'Explore'})
        # A tool event can be the first sign of a subagent (hooks installed mid-run).
        event(session | {'hook_event_name': 'PostToolUse', 'agent_id': 'a2', 'agent_type': 'general-purpose',
                         'tool_name': 'Read'})
        for view in ((), ('--agents',)):
            lines = pane_row(*view).split('\n')
            assert any('Explore' in line and 'WORKING' in line for line in lines[1:]), (view, lines)
            assert any('general-purpose' in line and 'WORKING' in line for line in lines[1:]), (view, lines)
        assert option('status') == 'working'
        print('ok - subagents appear as child lines of their pane in Tree and Agents views')

        # A subagent's permission request is attributed to it and marks the pane.
        event(session | {'hook_event_name': 'PermissionRequest', 'agent_id': 'a2', 'agent_type': 'general-purpose',
                         'tool_name': 'Bash', 'tool_input': {'command': 'make'}})
        lines = pane_row('--agents').split('\n')
        assert any('general-purpose' in line and 'NEEDS INPUT' in line for line in lines[1:]), lines
        assert any('Explore' in line and 'WORKING' in line for line in lines[1:]), lines
        assert 'Request: general-purpose: Approval requested' in preview()
        assert f'P:{pane}\t' in needs_input()
        # Neither the main thread nor another subagent may clear it.
        event(session | {'hook_event_name': 'PostToolUse', 'tool_name': 'Bash'})
        event(session | {'hook_event_name': 'PostToolUse', 'agent_id': 'a1', 'agent_type': 'Explore',
                         'tool_name': 'Bash'})
        assert option('status') == 'needs-input' and option('request_agent') == 'a2'
        print('ok - a subagent request is attributed to that subagent and only it can clear the pane request')

        # Its own tool completion clears it; the pane goes back to working.
        event(session | {'hook_event_name': 'PostToolUse', 'agent_id': 'a2', 'agent_type': 'general-purpose',
                         'tool_name': 'Bash'})
        assert option('status') == 'working' and option('request_agent') == ''
        assert f'P:{pane}\t' not in needs_input()
        event(session | {'hook_event_name': 'SubagentStop', 'agent_id': 'a1', 'agent_type': 'Explore'})
        lines = pane_row().split('\n')
        assert not any('Explore' in line for line in lines[1:]), lines
        assert all(not entry.startswith('a1,') for entry in option('subagents').split(';'))
        assert option('status') == 'working'
        print('ok - subagent completion removes its row without changing the main thread status')

        # A subagent still waiting on input keeps the pane actionable even after
        # the main thread reports something else.
        event(session | {'hook_event_name': 'PermissionRequest', 'agent_id': 'a2', 'agent_type': 'general-purpose',
                         'tool_name': 'Edit'})
        event(session | {'hook_event_name': 'Stop'})
        assert option('status') == 'turn-ended'
        assert f'P:{pane}\t' in needs_input()
        session_token = 'S:' + tm('display-message', '-p', '-t', pane, '#{session_id}')
        state.write_text(session_token + '\n')
        assert '◆' in rows()[session_token], rows()[session_token]
        state.write_text('')
        print('ok - a waiting subagent rolls up as needs-input and is a jump target')

        event(session | {'hook_event_name': 'SubagentStop', 'agent_id': 'a2',
                         'agent_type': 'general-purpose'})
        assert option('status') == 'turn-ended' and option('request_agent') == ''
        assert option('subagents') == '' and f'P:{pane}\t' not in needs_input()
        event(session | {'hook_event_name': 'SubagentStart', 'agent_id': 'a4', 'agent_type': 'Plan'})
        event(session | {'hook_event_name': 'PermissionRequest', 'agent_id': 'a4',
                         'agent_type': 'Plan', 'tool_name': 'Bash'})
        event(session | {'hook_event_name': 'SubagentStop', 'agent_id': 'a4', 'agent_type': 'Plan'})
        assert option('status') == 'working' and option('request_agent') == ''
        assert option('subagents') == '' and f'P:{pane}\t' not in needs_input()
        print('ok - child completion clears outstanding requests and removes its row')

        # A background child disappears as soon as it stops, even if the
        # parent's next prompt has not yet arrived.
        event(session | {'hook_event_name': 'SubagentStart', 'agent_id': 'a3', 'agent_type': 'Research'})
        event(session | {'hook_event_name': 'SubagentStop', 'agent_id': 'a3', 'agent_type': 'Research'})
        assert option('subagents') == ''
        event(session | {'hook_event_name': 'UserPromptSubmit'})
        lines = pane_row().split('\n')
        assert not any('Research' in line or 'Explore' in line for line in lines[1:]), lines
        print('ok - completed background children stay absent on the next prompt')

        # Legacy DONE entries are hidden and pruned on the next hook event.
        tm('set-option', '-p', '-t', pane, '@tmux_canopy_agent_subagents', 'old,Explore,done,1,')
        assert not any('Explore' in line for line in pane_row().split('\n')[1:])
        event(session | {'hook_event_name': 'UserPromptSubmit'})
        assert option('subagents') == ''
        event(session | {'hook_event_name': 'SubagentStart', 'agent_id': 'a2',
                         'agent_type': 'general-purpose'})
        assert any('general-purpose' in line for line in pane_row().split('\n')[1:])
        for index in range(12):
            event(session | {'hook_event_name': 'SubagentStart', 'agent_id': f'b{index}', 'agent_type': 'Plan'})
        assert len(option('subagents').split(';')) == 8
        event(session | {'hook_event_name': 'SessionEnd'})
        assert option('subagents') == ''
        print('ok - legacy rows are pruned, the list is capped, and session end clears it')

        # Delimiters and control bytes in agent_type cannot forge extra entries.
        event(session | {'hook_event_name': 'SessionStart'})
        event(session | {'hook_event_name': 'SubagentStart', 'agent_id': 'c1',
                         'agent_type': 'evil;x,done,1,\x1b[31m'})
        entries = option('subagents').split(';')
        assert len(entries) == 1 and entries[0].startswith('c1,') and '\x1b' not in entries[0], entries
        event(session | {'hook_event_name': 'SubagentStart', 'agent_id': '../bad id'})
        assert len(option('subagents').split(';')) == 1
        print('ok - subagent fields are sanitized and malformed ids are ignored')

finally:
    sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)
