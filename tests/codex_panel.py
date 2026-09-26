#!/usr/bin/env python3
"""Codex/Claude read-only previews from tmux metadata and a bounded screen."""
import os
import json
from pathlib import Path
import shutil
import subprocess as sp
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
socket = f'canopy-codex-panel-{os.getpid()}'
env = os.environ.copy()
env.pop('TMUX', None)
env.pop('TMUX_PANE', None)


def tm(*args):
    result = sp.run(['tmux', '-L', socket, *args], env=env, text=True,
                    capture_output=True, timeout=10)
    assert result.returncode == 0, (args, result.stderr)
    return result.stdout.strip()


try:
    with tempfile.TemporaryDirectory(prefix='canopy-codex-panel-') as temp_dir:
        binary = Path(temp_dir) / 'codex'
        shutil.copy2(shutil.which('sleep'), binary)
        claude_binary = Path(temp_dir) / 'claude'
        shutil.copy2(shutil.which('sleep'), claude_binary)
        agent = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'studio', '-x', '120', '-y', '35',
                   '-P', '-F', '#{pane_id}',
                   f"/bin/bash -c 'printf \"Do you want to run this command?\\n\"; exec {binary} 600'")
        window = tm('display-message', '-p', '-t', agent, '#{window_id}')
        session = tm('display-message', '-p', '-t', agent, '#{session_id}')
        other = tm('new-window', '-d', '-t', 'studio:', '-P', '-F', '#{pane_id}', 'sleep 600')
        claude = tm('new-window', '-d', '-t', 'studio:', '-P', '-F', '#{pane_id}',
                    f"/bin/bash -c 'printf \"Do you want to proceed?\\n\"; {claude_binary} 600; printf done'")
        claude_window = tm('display-message', '-p', '-t', claude, '#{window_id}')
        empty = tm('new-session', '-d', '-s', 'empty', '-x', '120', '-y', '35',
                   '-P', '-F', '#{pane_id}', 'sleep 600')
        empty_session = tm('display-message', '-p', '-t', empty, '#{session_id}')
        sidebar = tm('split-window', '-d', '-h', '-b', '-l', '42', '-t', agent,
                     '-P', '-F', '#{pane_id}', 'sleep 600')
        tm('set-option', '-p', '-t', sidebar, '@tmux_canopy', '1')
        script_env = env | {'TMUX': tm('display-message', '-p', '-t', agent,
                                       '#{socket_path},#{pid},0'), 'TMUX_PANE': sidebar,
                            'FZF_PREVIEW_LINES': '12', 'FZF_PREVIEW_COLUMNS': '42'}
        state = Path(temp_dir) / 'state'
        state.write_text('')
        script_env['TMUX_CANOPY_STATE'] = str(state)

        def run(name, *args, extra=None):
            result = sp.run([str(ROOT / 'scripts' / name), *args], env=script_env | (extra or {}),
                            text=True, capture_output=True, timeout=10)
            assert result.returncode == 0, (name, result.stderr)
            return result.stdout

        terminal = run('sidebar-preview', 'P:' + agent)
        assert 'Do you want to run this command?' in terminal
        run('preview-mode')
        assert tm('show-option', '-pqv', '-t', sidebar, '@tmux_canopy_preview_mode') == 'agent'
        agent_view = run('sidebar-preview', 'P:' + agent)
        assert 'Codex ·' in agent_view and 'Possible input requested (unverified)' in agent_view
        assert 'Do you want to run this command?' in agent_view
        assert len(agent_view.splitlines()) <= 12
        def hook(event, pane=agent):
            result = sp.run([str(ROOT / 'scripts/codex-hook')],
                            input=json.dumps(event), text=True, capture_output=True,
                            env=script_env | {'TMUX_PANE': pane}, timeout=10)
            expected = '{}\n' if event['hook_event_name'] == 'Stop' else ''
            assert result.returncode == 0 and result.stdout == expected, result.stderr

        def report():
            return run('sidebar-preview', 'P:' + agent)

        def tree_row(pane):
            return next(line.split('\t')[1] for line in run('sidebar-source', '--stable').splitlines()
                        if line.startswith('P:' + pane + '\t'))

        hook({'hook_event_name': 'SessionStart', 'session_id': 'codex-session'})
        assert 'Status: Ready' in report() and 'Source: Codex lifecycle hook' in report()
        assert '[ready·hook]' in tree_row(agent)
        hook({'hook_event_name': 'UserPromptSubmit', 'session_id': 'codex-session', 'turn_id': 't1'})
        assert 'Status: Working' in report()
        assert '[working·hook]' in tree_row(agent)
        tm('set-option', '-g', '@tmux-canopy-theme', 'mono')
        assert '[working·hook]' in tree_row(agent) and '\x1b' not in tree_row(agent)
        tm('set-option', '-gu', '@tmux-canopy-theme')
        request = {'hook_event_name': 'PermissionRequest', 'session_id': 'codex-session',
                   'turn_id': 't1', 'tool_name': 'shell_command',
                   'tool_input': {'description': 'Install the dependency',
                                  'command': 'npm install example'}}
        hook(request)
        assert 'Status: Approval requested (hook report)' in report()
        assert '[approval·hook]' in tree_row(agent)
        tm('resize-pane', '-t', sidebar, '-x', '30')
        assert '[req·hook]' in tree_row(agent), 'narrow row lost its approval label'
        tm('resize-pane', '-t', sidebar, '-x', '42')
        assert 'Request: Install the dependency' in report()
        assert 'Command: npm install example' in report()
        assert 'Possible input requested' not in report()
        hook({'hook_event_name': 'PostToolUse', 'session_id': 'codex-session',
              'turn_id': 't1', 'tool_name': 'other_tool', 'tool_input': {}})
        assert 'Status: Approval requested (hook report)' in report()
        hook({'hook_event_name': 'PostToolUse', 'session_id': 'codex-session',
              'turn_id': 't1', 'tool_name': 'shell_command',
              'tool_input': request['tool_input']})
        assert 'Status: Working' in report() and 'npm install example' not in report()
        assert '[working·hook]' in tree_row(agent)
        hook({'hook_event_name': 'Stop', 'session_id': 'codex-session', 'turn_id': 't1'})
        assert 'Status: Turn ended' in report(), report()
        assert '[turn ended·hook]' in tree_row(agent)
        hook(request)
        assert 'Status: Turn ended' in report()
        tm('set-option', '-pq', '-t', agent, '@tmux_canopy_agent_updated', '1')
        assert 'Status: Unknown (report stale)' in report()
        assert '[unknown·hook]' in tree_row(agent)
        timer = tm('show-option', '-pqv', '-t', agent, '@tmux_canopy_agent_timer')
        result = sp.run([str(ROOT / 'scripts/agent-expiry'), agent, timer],
                        env=script_env, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        assert tm('show-option', '-pqv', '-t', agent, '@tmux_canopy_agent_timer') == ''
        tm('set-option', '-pq', '-t', agent, '@tmux_canopy_agent_pane_pid', '999999')
        assert 'Possible input requested (unverified)' in report()
        assert '[unknown·hook]' not in tree_row(agent) and '[turn ended·hook]' not in tree_row(agent)
        tm('set-option', '-pq', '-t', agent, '@tmux_canopy_agent_pane_pid',
           tm('display-message', '-p', '-t', agent, '#{pane_pid}'))
        tm('set-option', '-pq', '-t', agent, '@tmux_canopy_agent_updated', '1')
        hook({'hook_event_name': 'UserPromptSubmit', 'session_id': 'new-session', 'turn_id': 't2'})
        assert 'Status: Working' in report()
        assert '[working·hook]' in tree_row(agent)
        for key, value in (('source', 'codex-hook'), ('session', 'old-agent'),
                           ('pane_pid', tm('display-message', '-p', '-t', other, '#{pane_pid}')),
                           ('status', 'working'), ('updated', tm('show-option', '-pqv', '-t', agent,
                                                               '@tmux_canopy_agent_updated'))):
            tm('set-option', '-pq', '-t', other, '@tmux_canopy_agent_' + key, value)
        assert '[working·hook]' not in tree_row(other), 'old hook state appeared on a non-Codex pane'
        hook({'hook_event_name': 'SessionEnd', 'session_id': 'codex-session'})
        assert 'Status: Working' in report()
        assert 'Codex ·' in run('sidebar-preview', 'W:' + window + ':' + session)
        claude_view = run('sidebar-preview', 'P:' + claude)
        assert 'Claude Code ·' in claude_view
        assert '[working·hook]' not in tree_row(claude) and '[approval·hook]' not in tree_row(claude)
        assert 'Possible input requested (unverified)' in claude_view
        assert 'Do you want to proceed?' in claude_view
        assert len(claude_view.splitlines()) <= 12
        assert 'Claude Code ·' in run('sidebar-preview', 'W:' + claude_window + ':' + session)
        assert 'No supported agent process found' in run('sidebar-preview', 'P:' + other)
        assert 'Session: studio' in run('sidebar-preview', 'S:' + session)
        assert 'no longer available' in run('sidebar-preview', 'P:%999999'), run('sidebar-preview', 'P:%999999')
        assert 'Codex ·' not in run('sidebar-preview', 'P:' + agent,
                                  extra={'TMUX_CANOPY_PREVIEW_EXPANDED': '1'})
        tm('set-option', '-pq', '-t', sidebar, '@tmux_canopy_preview_mode', 'codex')
        assert 'Claude Code ·' in run('sidebar-preview', 'P:' + claude)
        run('preview-mode')
        assert run('sidebar-preview', 'P:' + agent) == terminal
        run('sidebar-action', 'view-agents')
        assert state.read_text() == 'VIEW\tagents\n'
        source = run('sidebar-source', '--stable')
        rows = [line.split('\t') for line in source.splitlines()]
        ids = [row[2] for row in rows]
        assert ids[0] == 'H:tree' and '[4 Agents]' in rows[0][1]
        assert f'P:{agent}:{session}' in ids and f'P:{claude}:{session}' in ids
        assert f'P:{other}:{session}' not in ids
        assert f'S:{empty_session}' not in ids
        assert any('2 agents' in row[1] for row in rows if row[0] == f'S:{session}')
        assert any('Codex' in row[1] for row in rows if row[0] == f'P:{agent}')
        assert any('Claude' in row[1] for row in rows if row[0] == f'P:{claude}')
        assert run('tree-source', '--agents', '--focus-target', 'W:' + window + ':' + session) == f'P:{agent}\t{session}\n'
        assert run('tree-source', '--agents', '--focus-target', 'S:' + empty_session) == ''
        # A shell may launch a second Codex without changing its pane PID.
        restart = tm('new-window', '-d', '-t', 'studio:', '-P', '-F', '#{pane_id}',
                     f"/bin/bash -c '{binary} 600; {binary} 600; sleep 1'")
        restart_root = tm('display-message', '-p', '-t', restart, '#{pane_pid}')
        def child():
            result = sp.run(['pgrep', '-P', restart_root, '-x', 'codex'],
                            text=True, capture_output=True)
            return result.stdout.strip().splitlines()[:1]
        deadline = time.monotonic() + 3
        while not child() and time.monotonic() < deadline:
            time.sleep(.05)
        assert child(), 'first nested Codex never started'
        first = child()[0]
        old_pane = script_env['TMUX_PANE']
        script_env['TMUX_PANE'] = restart
        hook({'hook_event_name': 'SessionStart', 'session_id': 'first-process'}, pane=restart)
        assert tm('show-option', '-pqv', '-t', restart,
                  '@tmux_canopy_agent_process_pid') == first
        assert '[ready·hook]' in tree_row(restart)
        sp.run(['kill', '-TERM', first], check=True)
        deadline = time.monotonic() + 3
        while (not child() or child()[0] == first) and time.monotonic() < deadline:
            time.sleep(.05)
        assert child() and child()[0] != first, 'second nested Codex never started'
        assert '[ready·hook]' not in tree_row(restart), 'old process state leaked to new Codex'
        assert 'Source: Codex lifecycle hook' not in run('sidebar-preview', 'P:' + restart), \
            'old process report leaked into drawer'
        hook({'hook_event_name': 'SessionStart', 'session_id': 'second-process'}, pane=restart)
        assert '[ready·hook]' in tree_row(restart), 'new process report missing'
        assert tm('show-option', '-pqv', '-t', restart,
                  '@tmux_canopy_agent_process_pid') == child()[0]
        script_env['TMUX_PANE'] = old_pane
        tm('kill-pane', '-t', restart)
        tm('kill-pane', '-t', claude)
        source = run('sidebar-source', '--stable')
        assert f'P:{claude}:{session}' not in source
        tm('kill-pane', '-t', agent)
        source = run('sidebar-source', '--stable')
        assert 'V:agents-empty' in source and 'No supported agent processes detected' in source
        run('sidebar-action', 'view-tree')
        assert 'V:agents-empty' not in run('sidebar-source', '--stable')
        print('ok - agent preview, Codex hook lifecycle and request freshness, toggle, and agents view')
finally:
    sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)
