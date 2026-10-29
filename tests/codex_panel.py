#!/usr/bin/env python3
"""Codex/Claude read-only inspectors from structured tmux metadata."""
import os
import json
from pathlib import Path
import re
from support import install_agent_fixture
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
    with tempfile.TemporaryDirectory(prefix='canopy-codex-panel-', ignore_cleanup_errors=True) as temp_dir:
        binary = Path(temp_dir) / 'codex'
        install_agent_fixture(binary)
        claude_binary = Path(temp_dir) / 'claude'
        install_agent_fixture(claude_binary)
        agent = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'studio', '-x', '120', '-y', '35',
                   '-P', '-F', '#{pane_id}',
                   f"/bin/bash -c 'printf \"TRANSCRIPT_FIXTURE_7b2\\nTUI_STATUS_FIXTURE_9c4 | context 42%%\\nDo you want to run this command?\\nAgent prompt>\"; exec {binary} 600'")
        tm('set-option', '-g', '@tmux-canopy-agents', 'on')
        window = tm('display-message', '-p', '-t', agent, '#{window_id}')
        session = tm('display-message', '-p', '-t', agent, '#{session_id}')
        other = tm('new-window', '-d', '-t', 'studio:', '-P', '-F', '#{pane_id}',
                   "/bin/bash -c 'printf \"TRANSCRIPT_FIXTURE_7b2\\nTUI_STATUS_FIXTURE_9c4 | context 42%%\\nDo you want to run this command?\\nTerminal cursor>\"; exec sleep 600'")
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

        def run(name, *args, extra=None, raw=False):
            result = sp.run([str(ROOT / 'scripts' / name), *args], env=script_env | (extra or {}),
                            text=True, capture_output=True, timeout=10)
            assert result.returncode == 0, (name, result.stderr)
            return result.stdout if raw else re.sub(r'\x1b\[[0-9;]*m', '', result.stdout)

        screen_markers = ('TRANSCRIPT_FIXTURE_7b2', 'TUI_STATUS_FIXTURE_9c4')

        def assert_screen_excluded(pane):
            screen = tm('capture-pane', '-p', '-t', pane)
            assert all(marker in screen for marker in screen_markers), screen
            for rows in (1, 2, 3, 6, 18, 50):
                inspector = run('sidebar-preview', 'P:' + pane,
                                extra={'FZF_PREVIEW_LINES': str(rows),
                                       'FZF_PREVIEW_COLUMNS': '100'})
                assert 0 < len(inspector.splitlines()) <= rows, (rows, inspector)
                assert all(marker not in inspector for marker in screen_markers), inspector
                assert 'Recent screen' not in inspector, inspector

        terminal = run('sidebar-preview', 'P:' + agent)
        assert 'Do you want to run this command?' in terminal and 'Agent prompt>' in terminal
        assert all(marker in terminal for marker in screen_markers), terminal
        run('preview-mode')
        assert tm('show-option', '-pqv', '-t', sidebar, '@tmux_canopy_preview_mode') == 'agent'
        agent_view = run('sidebar-preview', 'P:' + agent)
        assert 'Codex' in agent_view and 'Possible input requested (unverified)' in agent_view, agent_view
        assert 'Do you want to run this command?' in agent_view, agent_view
        assert len(agent_view.splitlines()) <= 12
        assert not re.search(r'^\s*[│|] ', agent_view, re.MULTILINE), agent_view
        assert '·hook' not in agent_view
        assert_screen_excluded(agent)
        def hook(event, pane=agent):
            result = sp.run([str(ROOT / 'scripts/codex-hook')],
                            input=json.dumps(event), text=True, capture_output=True,
                            env=script_env | {'TMUX_PANE': pane}, timeout=10)
            expected = '{}\n' if event['hook_event_name'] == 'Stop' else ''
            assert result.returncode == 0 and result.stdout == expected, result.stderr

        def report(rows=12, raw=False, columns=42):
            return run('sidebar-preview', 'P:' + agent,
                       extra={'FZF_PREVIEW_LINES': str(rows),
                              'FZF_PREVIEW_COLUMNS': str(columns)}, raw=raw)

        def tree_row(pane, raw=False):
            return next(line.split('\t')[1] for line in run('sidebar-source', '--stable', raw=raw).splitlines()
                        if line.startswith('P:' + pane + '\t'))

        hook({'hook_event_name': 'SessionStart', 'session_id': 'codex-session'})
        ready = report()
        assert 'Possible input requested' not in ready, ready
        assert len(ready.splitlines()) <= 12, ready
        assert 'READY' in tree_row(agent) and '·hook' in tree_row(agent)
        assert not re.search(r'^\s*[│|] ', ready, re.MULTILINE), ready
        assert_screen_excluded(agent)
        hook({'hook_event_name': 'UserPromptSubmit', 'session_id': 'codex-session', 'turn_id': 't1'})
        assert 'WORKING' in tree_row(agent) and '·hook' in tree_row(agent)
        tm('set-option', '-g', '@tmux-canopy-theme', 'mono')
        assert 'WORKING' in tree_row(agent) and '·hook' in tree_row(agent) and '\x1b' not in tree_row(agent, raw=True)
        assert '\x1b' not in report(raw=True)
        tm('set-option', '-gu', '@tmux-canopy-theme')
        request = {'hook_event_name': 'PermissionRequest', 'session_id': 'codex-session',
                   'turn_id': 't1', 'tool_name': 'shell_command',
                   'tool_input': {'description': 'Install fixture dependency 7b2',
                                  'command': 'npm install example'}}
        hook(request)
        assert 'NEEDS INPUT' in tree_row(agent) and '·hook' in tree_row(agent)
        tm('resize-pane', '-t', sidebar, '-x', '30')
        assert 'req' in tree_row(agent) and '·hook' in tree_row(agent), 'narrow row lost its approval label'
        tm('resize-pane', '-t', sidebar, '-x', '42')
        requested = report()
        assert 'Install fixture dependency 7b2' in requested and 'npm install example' in requested
        assert requested.index('Install fixture dependency 7b2') < requested.index('npm install example')
        request_line = next(i for i, line in enumerate(requested.splitlines())
                            if 'Install fixture dependency 7b2' in line)
        command_line = next(i for i, line in enumerate(requested.splitlines())
                            if 'npm install example' in line)
        assert request_line != command_line, requested
        directory = tm('display-message', '-p', '-t', agent, '#{pane_current_path}')
        if directory == str(Path.home()) or directory.startswith(str(Path.home()) + '/'):
            directory = '~' + directory[len(str(Path.home())):]
        location = tm('display-message', '-p', '-t', agent,
                      '#{session_name}:#{window_index} #{window_name}')
        rich = report(18, columns=100)
        rich_lines = rich.splitlines()
        assert rich_lines[0].startswith(' ') and rich_lines[0].endswith('Codex'), rich
        assert len(rich_lines[0]) == 99, rich_lines[0]
        assert 'lifecycle hook ·' in rich and directory in rich and location in rich, rich
        assert rich.index(directory) < rich.index(location) < rich.index('Install fixture dependency 7b2'), rich
        # Tall drawers stay compact: only one blank line before the request block.
        before_request = rich_lines[:next(i for i, line in enumerate(rich_lines)
                                          if 'Install fixture dependency 7b2' in line)]
        assert before_request[-1] == '', rich
        assert all(line.strip() for line in before_request[:-1]), rich
        tm('set-option', '-g', '@tmux-canopy-git-context', 'branch')
        with_git = report(18, columns=100)
        assert ' ⎇ ' in with_git, with_git
        assert with_git.index(directory) < with_git.index(' ⎇ ') < with_git.index(location), with_git
        tm('set-option', '-g', '@tmux-canopy-git-context', 'off')
        without_git = report(18, columns=100)
        assert ' ⎇ ' not in without_git, without_git
        assert_screen_excluded(agent)
        narrow = report(18, columns=32)
        assert 'Codex' in narrow.splitlines()[0], narrow
        assert directory in narrow and location in narrow, narrow
        assert 'Install fixture dependency 7b2' in narrow and 'npm install example' in narrow, narrow
        for rows in range(1, 19):
            bounded = report(rows, columns=32)
            assert 0 < len(bounded.splitlines()) <= rows, (rows, bounded)
        # The actionable details win over trust and place in short drawers.
        for rows in (1, 2, 3):
            short = report(rows)
            assert 0 < len(short.splitlines()) <= rows, (rows, short)
            assert 'Codex' in short.splitlines()[0], short
            if rows == 1:
                assert 'Install fixture dependency 7b2' not in short and 'npm install example' not in short, short
            if rows >= 2:
                assert 'Install fixture dependency 7b2' in short, (rows, short)
                assert 'Possible input requested' not in short, short
            if rows == 2:
                assert 'npm install example' not in short, short
            if rows == 3:
                assert 'npm install example' in short, short
        tm('set-option', '-pq', '-t', sidebar, '@tmux_canopy_target', agent)
        here = report()
        assert any(line.lstrip().startswith('● ') and location in line for line in here.splitlines()), here
        tm('set-option', '-pq', '-t', sidebar, '@tmux_canopy_target', other)
        elsewhere = report()
        assert location in elsewhere and not any(line.lstrip().startswith('● ') for line in elsewhere.splitlines()), elsewhere
        tm('set-option', '-g', '@tmux-canopy-theme', 'mono')
        tm('set-option', '-g', '@tmux_canopy_icon_theme', 'ascii')
        ascii_request = report(3, raw=True)
        assert '\x1b' not in ascii_request, ascii_request
        command_line = next(line for line in ascii_request.splitlines() if 'npm install example' in line)
        assert command_line.isascii(), command_line
        assert 'Install fixture dependency 7b2' in ascii_request and 'npm install example' in ascii_request
        assert command_line.lstrip().startswith('| '), command_line
        ascii_rich = report(18, raw=True, columns=100)
        assert '\x1b' not in ascii_rich, ascii_rich
        assert '│' not in ascii_rich and '─' not in ascii_rich and '●' not in ascii_rich, ascii_rich
        assert directory in ascii_rich and location in ascii_rich, ascii_rich
        literal_command = r"printf '%s\n' 'C:\work\fixture $HOME; café'"
        hook(request | {'tool_input': request['tool_input'] | {'command': literal_command}})
        literal_view = report(18, raw=True, columns=32)
        assert literal_command in literal_view and '\x1b' not in literal_view, literal_view
        hook(request)
        tm('set-option', '-gu', '@tmux_canopy_icon_theme')
        tm('set-option', '-gu', '@tmux-canopy-theme')
        assert 'Possible input requested' not in report()
        tm('set-option', '-pq', '-t', agent, '@tmux_canopy_agent_status', 'unrecognized-fixture-state')
        unknown = report()
        assert 'Unknown' in unknown.splitlines()[0], unknown
        assert 'Install fixture dependency 7b2' not in unknown and 'npm install example' not in unknown, unknown
        assert 'Possible input requested' not in unknown, unknown
        assert not re.search(r'^\s*[│|] ', unknown, re.MULTILINE), unknown
        tm('set-option', '-pq', '-t', agent, '@tmux_canopy_agent_status', 'needs-input')
        for field in ('summary', 'command', 'tool'):
            tm('set-option', '-pq', '-t', agent, '@tmux_canopy_agent_' + field, '')
        incomplete_request = report()
        assert 'Needs input' in incomplete_request.splitlines()[0], incomplete_request
        assert 'Install fixture dependency 7b2' not in incomplete_request and 'npm install example' not in incomplete_request
        assert 'Possible input requested' not in incomplete_request, incomplete_request
        assert not re.search(r'^\s*[│|] ', incomplete_request, re.MULTILINE), incomplete_request
        hook(request)
        hook({'hook_event_name': 'PostToolUse', 'session_id': 'codex-session',
              'turn_id': 't1', 'tool_name': 'other_tool', 'tool_input': {}})
        assert 'Install fixture dependency 7b2' in report() and 'npm install example' in report()
        hook({'hook_event_name': 'PreToolUse', 'session_id': 'codex-session',
              'turn_id': 't1', 'tool_name': 'other_tool', 'tool_input': {}})
        assert 'Install fixture dependency 7b2' in report() and 'npm install example' in report()
        hook({'hook_event_name': 'PreToolUse', 'session_id': 'codex-session',
              'turn_id': 't1', 'tool_name': 'shell_command',
              'tool_input': {'command': 'npm install example'}})
        assert 'npm install example' not in report() and 'Install fixture dependency 7b2' not in report()
        assert 'Working · shell_command' in report().splitlines()[0], report()
        assert 'WORKING' in tree_row(agent) and '·hook' in tree_row(agent)
        hook(request)
        hook({'hook_event_name': 'PostToolUse', 'session_id': 'codex-session',
              'turn_id': 't1', 'tool_name': 'shell_command',
              'tool_input': {'command': 'npm install example'}})
        assert 'npm install example' not in report() and 'Install fixture dependency 7b2' not in report()
        assert 'Working · shell_command' not in report().splitlines()[0], report()
        assert 'WORKING' in tree_row(agent) and '·hook' in tree_row(agent)
        hook({'hook_event_name': 'Stop', 'session_id': 'codex-session', 'turn_id': 't1'})
        assert 'TURN ENDED' in tree_row(agent) and '·hook' in tree_row(agent)
        hook(request)
        assert 'TURN ENDED' in tree_row(agent) and 'npm install example' not in report()
        hook({'hook_event_name': 'UserPromptSubmit', 'session_id': 'codex-session', 'turn_id': 't2'})
        hook(request | {'turn_id': 't2'})
        assert 'Install fixture dependency 7b2' in report()
        tm('set-option', '-pq', '-t', agent, '@tmux_canopy_agent_updated', '1')
        stale = report()
        assert 'Stale report' in stale.splitlines()[0] and 'lifecycle hook ·' in stale, stale
        assert 'Install fixture dependency 7b2' not in stale and 'npm install example' not in stale
        assert 'Possible input requested' not in stale
        assert not re.search(r'^\s*[│|] ', stale, re.MULTILINE), stale
        assert_screen_excluded(agent)
        assert 'UNKNOWN' not in tree_row(agent) and '·hook' not in tree_row(agent)
        timer = tm('show-option', '-pqv', '-t', agent, '@tmux_canopy_agent_timer')
        result = sp.run([str(ROOT / 'scripts/agent-expiry'), agent, timer],
                        env=script_env, capture_output=True, text=True, timeout=10)
        assert result.returncode == 0, result.stderr
        assert tm('show-option', '-pqv', '-t', agent, '@tmux_canopy_agent_timer') == ''
        hook({'hook_event_name': 'UserPromptSubmit', 'session_id': 'codex-session', 'turn_id': 't3'})
        hook(request | {'turn_id': 't3'})
        assert 'Install fixture dependency 7b2' in report()
        tm('set-option', '-pq', '-t', agent, '@tmux_canopy_agent_pane_pid', '999999')
        mismatched = report()
        assert 'Possible input requested (unverified)' in mismatched
        assert 'Install fixture dependency 7b2' not in mismatched and 'npm install example' not in mismatched
        assert 'UNKNOWN' not in tree_row(agent) and 'NEEDS INPUT' not in tree_row(agent)
        tm('set-option', '-pq', '-t', agent, '@tmux_canopy_agent_pane_pid',
           tm('display-message', '-p', '-t', agent, '#{pane_pid}'))
        tm('set-option', '-pq', '-t', agent, '@tmux_canopy_agent_updated', '1')
        hook({'hook_event_name': 'UserPromptSubmit', 'session_id': 'new-session', 'turn_id': 't2'})
        assert 'WORKING' in tree_row(agent) and '·hook' in tree_row(agent)
        for key, value in (('source', 'codex-hook'), ('session', 'old-agent'),
                           ('pane_pid', tm('display-message', '-p', '-t', other, '#{pane_pid}')),
                           ('status', 'working'), ('updated', tm('show-option', '-pqv', '-t', agent,
                                                               '@tmux_canopy_agent_updated'))):
            tm('set-option', '-pq', '-t', other, '@tmux_canopy_agent_' + key, value)
        assert 'WORKING' not in tree_row(other), 'old hook state appeared on a non-Codex pane'
        hook({'hook_event_name': 'SessionEnd', 'session_id': 'codex-session'})
        assert 'WORKING' in tree_row(agent) and '·hook' in tree_row(agent)
        assert 'Codex' in run('sidebar-preview', 'W:' + window + ':' + session)
        claude_view = run('sidebar-preview', 'P:' + claude)
        assert 'Claude Code' in claude_view
        assert 'WORKING' not in tree_row(claude) and 'NEEDS INPUT' not in tree_row(claude)
        assert 'Possible input requested (unverified)' in claude_view
        assert 'Do you want to proceed?' in claude_view
        assert len(claude_view.splitlines()) <= 12
        assert 'Claude Code' in run('sidebar-preview', 'W:' + claude_window + ':' + session)
        terminal_card = run('sidebar-preview', 'P:' + other)
        assert 'Terminal' in terminal_card.splitlines()[0], terminal_card
        assert 'sleep' in terminal_card and 'studio:' in terminal_card, terminal_card
        assert 'Possible input requested' not in terminal_card, terminal_card
        assert 'lifecycle hook' not in terminal_card, terminal_card
        assert not re.search(r'^\s*[│|] ', terminal_card, re.MULTILINE), terminal_card
        assert len(terminal_card.splitlines()) <= 12, terminal_card
        assert_screen_excluded(other)
        for rows in (1, 2, 3, 6):
            short_terminal = run('sidebar-preview', 'P:' + other,
                                 extra={'FZF_PREVIEW_LINES': str(rows)})
            assert 0 < len(short_terminal.splitlines()) <= rows, (rows, short_terminal)
            assert 'Terminal' in short_terminal.splitlines()[0], short_terminal
            assert 'Possible input requested' not in short_terminal, short_terminal
        assert 'Session: studio' in run('sidebar-preview', 'S:' + session)
        assert 'no longer available' in run('sidebar-preview', 'P:%999999'), run('sidebar-preview', 'P:%999999')
        expanded = run('sidebar-preview', 'P:' + agent,
                       extra={'TMUX_CANOPY_PREVIEW_EXPANDED': '1'})
        assert expanded == terminal
        tm('set-option', '-pq', '-t', sidebar, '@tmux_canopy_preview_mode', 'codex')
        assert 'Claude Code' in run('sidebar-preview', 'P:' + claude)
        # Question requests show '! Needs input · question' in inspector and 'Question: ...' in list.
        hook({'hook_event_name': 'PermissionRequest', 'session_id': 'new-session',
              'turn_id': 't2', 'tool_name': 'AskUserQuestion',
              'tool_input': {'questions': [{'question': 'Which database?'}]}})
        question_card = report(12, columns=70)
        assert '! Needs input · question' in question_card.splitlines()[0], question_card
        assert 'Which database?' in question_card, question_card
        # Interrupted with an error message surfaces the error in the inspector and list.
        hook({'hook_event_name': 'Interrupt', 'session_id': 'new-session',
              'turn_id': 't2', 'error': 'connection reset'})
        err_card = report(12, columns=70)
        assert '! Interrupted' in err_card.splitlines()[0] and 'connection reset' in err_card, err_card
        run('preview-mode')
        assert tm('show-option', '-pqv', '-t', sidebar, '@tmux_canopy_preview_mode') == 'agents'
        assert 'Agent list' in run('preview-mode', '--label')
        err_list = run('sidebar-preview', 'S:' + empty_session,
                       extra={'FZF_PREVIEW_LINES': '12', 'FZF_PREVIEW_COLUMNS': '70'}).splitlines()
        assert '2 agents · 1 interrupted · 1 idle' in err_list[0], err_list
        assert '! studio:0.1  Codex · Interrupted: connection reset' in err_list[1], err_list
        hook({'hook_event_name': 'UserPromptSubmit', 'session_id': 'new-session', 'turn_id': 't3'})
        hook({'hook_event_name': 'PermissionRequest', 'session_id': 'new-session',
              'turn_id': 't3', 'tool_name': 'AskUserQuestion',
              'tool_input': {'questions': [{'question': 'Which database?'}]}})
        q_list = run('sidebar-preview', 'S:' + empty_session,
                     extra={'FZF_PREVIEW_LINES': '12', 'FZF_PREVIEW_COLUMNS': '70'}).splitlines()
        assert '2 agents · 1 needs input · 1 idle' in q_list[0], q_list
        assert '! studio:0.1  Codex · Question: Which database?' in q_list[1], q_list
        tm('set-option', '-g', '@tmux_canopy_notifications', 'activity,bell')
        tm('set-option', '-pq', '-t', claude, '@tmux_canopy_notice_pane_activity', '1')
        hook({'hook_event_name': 'PreToolUse', 'session_id': 'new-session',
              'turn_id': 't3', 'tool_name': 'AskUserQuestion',
              'tool_input': {'questions': [{'question': 'Which database?'}]}})
        hook({'hook_event_name': 'PreToolUse', 'session_id': 'new-session',
              'turn_id': 't3', 'tool_name': 'shell_command', 'tool_input': {}})
        agent_list = run('sidebar-preview', 'S:' + empty_session,
                         extra={'FZF_PREVIEW_LINES': '12', 'FZF_PREVIEW_COLUMNS': '70'})
        list_lines = agent_list.splitlines()
        assert len(list_lines) == 3, agent_list
        assert '2 agents · 1 working · 1 idle' in list_lines[0], list_lines
        assert '▷ studio:0.1  Codex · Working · shell_command' in list_lines[1], list_lines
        assert '○ studio:2.0  Claude Code · Detected' in list_lines[2] and list_lines[2].endswith('●'), list_lines
        # Priority order: when Codex is idle and Claude has activity, Claude sorts ahead of Codex.
        hook({'hook_event_name': 'Stop', 'session_id': 'new-session', 'turn_id': 't3'})
        priority_lines = run('sidebar-preview', 'S:' + empty_session,
                             extra={'FZF_PREVIEW_LINES': '12', 'FZF_PREVIEW_COLUMNS': '70'}).splitlines()
        assert '2 agents · 2 idle' in priority_lines[0], priority_lines
        assert '○ studio:2.0  Claude Code · Detected' in priority_lines[1] and priority_lines[1].endswith('●'), priority_lines
        assert '✓ studio:0.1  Codex · Turn ended' in priority_lines[2], priority_lines
        hook({'hook_event_name': 'UserPromptSubmit', 'session_id': 'new-session', 'turn_id': 't4'})
        tm('set-option', '-pu', '-t', claude, '@tmux_canopy_notice_pane_activity')
        run('preview-mode')
        assert tm('show-option', '-pqv', '-t', sidebar, '@tmux_canopy_preview_mode') == 'terminal'
        assert run('sidebar-preview', 'P:' + agent) == terminal
        run('sidebar-action', 'view-agents')
        assert state.read_text() == 'VIEW\tagents\n'
        source = run('sidebar-source', '--stable')
        rows = [line.split('\t') for line in source.splitlines()]
        ids = [row[2] for row in rows]
        assert ids[0] == 'H:tree' and 'Agents' in rows[0][1]
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
        assert 'READY' in tree_row(restart) and '·hook' in tree_row(restart)
        hook({'hook_event_name': 'PermissionRequest', 'session_id': 'first-process',
              'tool_name': 'shell_command', 'tool_input': {
                  'description': 'Old process request 9c4', 'command': 'echo old-process-9c4'}}, pane=restart)
        assert 'Old process request 9c4' in run('agent-preview', 'P:' + restart)
        sp.run(['kill', '-TERM', first], check=True)
        deadline = time.monotonic() + 3
        while (not child() or child()[0] == first) and time.monotonic() < deadline:
            time.sleep(.05)
        assert child() and child()[0] != first, 'second nested Codex never started'
        assert 'READY' not in tree_row(restart) and 'NEEDS INPUT' not in tree_row(restart), \
            'old process state leaked to new Codex'
        restarted = run('agent-preview', 'P:' + restart)
        assert 'Old process request 9c4' not in restarted and 'echo old-process-9c4' not in restarted
        hook({'hook_event_name': 'SessionStart', 'session_id': 'second-process'}, pane=restart)
        assert 'READY' in tree_row(restart) and '·hook' in tree_row(restart), 'new process report missing'
        assert tm('show-option', '-pqv', '-t', restart,
                  '@tmux_canopy_agent_process_pid') == child()[0]
        script_env['TMUX_PANE'] = old_pane
        overflow_lines = run('agent-preview', '--list',
                             extra={'FZF_PREVIEW_LINES': '3', 'FZF_PREVIEW_COLUMNS': '70'}).splitlines()
        assert len(overflow_lines) == 3, overflow_lines
        assert '3 agents · 1 working · 2 idle' in overflow_lines[0], overflow_lines
        assert '▷ studio:0.1  Codex · Working' in overflow_lines[1], overflow_lines
        assert overflow_lines[2].strip() == '… +2 more', overflow_lines
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
