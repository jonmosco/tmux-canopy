#!/usr/bin/env python3
"""Jump-to-next-agent-needing-input: detection, order, and wraparound."""
import json
import os
from pathlib import Path
from support import install_agent_fixture
import subprocess as sp
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
socket = f'canopy-jump-agent-{os.getpid()}'
env = os.environ.copy()
env.pop('TMUX', None)
env.pop('TMUX_PANE', None)


def tm(*args):
    result = sp.run(['tmux', '-L', socket, *args], env=env, text=True,
                    capture_output=True, timeout=10)
    assert result.returncode == 0, (args, result.stderr)
    return result.stdout.strip()


try:
    with tempfile.TemporaryDirectory(prefix='canopy-jump-agent-', ignore_cleanup_errors=True) as directory:
        temp = Path(directory)
        binary = temp / 'codex'
        install_agent_fixture(binary)

        first = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'work', '-x', '100', '-y', '30',
                   '-P', '-F', '#{pane_id}', f'{binary} 600')
        tm('set-option', '-g', '@tmux-canopy-agents', 'on')
        # A wrapper shell in front of the agent: only the agent_view-caliber
        # descendant walk finds this, not a direct pane_current_command match.
        wrapped = tm('new-window', '-d', '-t', 'work:', '-n', 'wrapped', '-P', '-F', '#{pane_id}',
                    f"/bin/bash -c 'echo working; exec {binary} 600'")
        idle = tm('new-window', '-d', '-t', 'work:', '-n', 'idle', 'sleep 600')
        other = tm('new-session', '-d', '-s', 'other', '-x', '100', '-y', '30',
                   '-P', '-F', '#{pane_id}', f'{binary} 600')

        sidebar = tm('split-window', '-d', '-h', '-b', '-l', '42', '-t', first,
                     '-P', '-F', '#{pane_id}', 'sleep 600')
        tm('set-option', '-p', '-t', sidebar, '@tmux_canopy', '1')
        script_env = env | {'TMUX': tm('display-message', '-p', '-t', first, '#{socket_path},#{pid},0'),
                            'TMUX_PANE': sidebar}
        state = temp / 'state'
        state.write_text('')
        script_env['TMUX_CANOPY_STATE'] = str(state)

        def hook(event, pane):
            result = sp.run([str(ROOT / 'scripts/codex-hook')], input=json.dumps(event), text=True,
                            capture_output=True, env=script_env | {'TMUX_PANE': pane}, timeout=10)
            assert result.returncode == 0, result.stderr

        def needs_input():
            result = sp.run([str(ROOT / 'scripts/tree-source'), '--needs-input'], env=script_env,
                            capture_output=True, text=True, timeout=10)
            assert result.returncode == 0, result.stderr
            return [line.split('\t') for line in result.stdout.splitlines()]

        def jump():
            result = sp.run([str(ROOT / 'scripts/jump-agent')], env=script_env,
                            capture_output=True, text=True, timeout=10)
            assert result.returncode == 0, result.stderr
            return tm('show-option', '-pqv', '-t', sidebar, '@tmux_canopy_target')

        def set_location(pane, window='@0', session='$0'):
            tm('set-option', '-p', '-t', sidebar, '@tmux_canopy_focus_location', f'{session}|{window}|{pane}')

        # Nothing has reported anything yet: no-op, no crash.
        tm('set-option', '-p', '-t', sidebar, '@tmux_canopy_focus_location', '')
        assert needs_input() == []
        before = tm('show-option', '-pqv', '-t', sidebar, '@tmux_canopy_target')
        jump()
        assert tm('show-option', '-pqv', '-t', sidebar, '@tmux_canopy_target') == before
        print('ok - a jump with nothing needing input is a no-op')

        hook({'hook_event_name': 'SessionStart', 'session_id': 's1'}, first)
        hook({'hook_event_name': 'UserPromptSubmit', 'session_id': 's1', 'turn_id': 't1'}, first)
        hook({'hook_event_name': 'PermissionRequest', 'session_id': 's1', 'turn_id': 't1',
              'tool_name': 'Bash', 'tool_input': {'command': 'one'}}, first)
        hook({'hook_event_name': 'SessionStart', 'session_id': 's2'}, other)
        hook({'hook_event_name': 'UserPromptSubmit', 'session_id': 's2', 'turn_id': 't1'}, other)
        # 'other' stays in "working" (no PermissionRequest): must not appear.
        rows = needs_input()
        panes = [row[0] for row in rows]
        assert panes == ['P:' + first], (panes, rows)
        print('ok - only the approval-state pane is listed, not the working one')

        # A wrapper-shell agent is still detected (agent_view-caliber walk).
        hook({'hook_event_name': 'SessionStart', 'session_id': 's3'}, wrapped)
        hook({'hook_event_name': 'UserPromptSubmit', 'session_id': 's3', 'turn_id': 't1'}, wrapped)
        hook({'hook_event_name': 'PermissionRequest', 'session_id': 's3', 'turn_id': 't1',
              'tool_name': 'Bash', 'tool_input': {'command': 'two'}}, wrapped)
        rows = needs_input()
        panes = {row[0] for row in rows}
        assert panes == {'P:' + first, 'P:' + wrapped}, (panes, rows)
        print('ok - an agent running under a wrapper shell is still found')

        # Interrupted also counts as needs-input.
        hook({'hook_event_name': 'Interrupt', 'session_id': 's2', 'turn_id': 't1'}, other)
        rows = needs_input()
        panes = {row[0] for row in rows}
        assert panes == {'P:' + first, 'P:' + wrapped, 'P:' + other}, (panes, rows)
        print('ok - interrupted also counts as needing input')

        # Wraparound: jumping repeatedly must visit exactly the pane order
        # tree-source itself reports (natural tmux list order, not assumed
        # creation order), then wrap back to the first entry.
        order = [row[0][len('P:'):] for row in needs_input()]
        assert len(order) == 3
        tm('set-option', '-p', '-t', sidebar, '@tmux_canopy_focus_location', '')
        seen = []
        current = jump()
        seen.append(current)
        for _ in range(len(order) - 1):
            set_location(current)
            current = jump()
            seen.append(current)
        assert seen == order, (seen, order)
        set_location(current)
        wrapped_back = jump()
        assert wrapped_back == order[0], 'did not wrap back to the first match'
        print('ok - repeated jumps advance in tree-source order and wrap around')

        # A pane not itself in the list lands on the first match.
        set_location(idle)
        assert jump() == order[0]
        print('ok - jumping from a pane not in the list lands on the first match')

        # Longest wait first: the order follows how long each pane has waited,
        # not where it sits in the tree. Ages are set directly so the check does
        # not depend on real elapsed time. All three are in a different order
        # than the tree, so a pass cannot be tree order by accident.
        def wait_since(pane, seconds):
            tm('set-option', '-p', '-t', pane, '@tmux_canopy_agent_updated', str(int(time.time()) - seconds))

        def ranked():
            return [row[0] for row in needs_input()]

        pane_list = tm('list-panes', '-a', '-F', '#{pane_id}').split()
        tree_order = ['P:' + p for p in pane_list if p in (first, wrapped, other)]
        for pane in (first, wrapped, other):
            wait_since(pane, 100)
        assert ranked() == tree_order, (ranked(), tree_order)
        print('ok - panes that have waited equally long keep tree order')

        ages = {first: 60, other: 120, wrapped: 300}
        for pane, seconds in ages.items():
            wait_since(pane, seconds)
        longest_first = ['P:' + p for p in sorted(ages, key=ages.get, reverse=True)]
        assert ranked() == longest_first, (ranked(), longest_first)
        assert longest_first != tree_order
        set_location(idle)
        current = jump()
        assert current == longest_first[0][len('P:'):], (current, longest_first)
        set_location(current)
        assert jump() == longest_first[1][len('P:'):]
        print('ok - the pane that has waited longest is visited first, then the next longest')

        # A subagent's request ranks by the subagent's own wait. Its parent keeps
        # working with a fresh report, so the parent's age would put it last.
        hook({'hook_event_name': 'PostToolUse', 'session_id': 's3', 'turn_id': 't1',
              'tool_name': 'Bash', 'tool_input': {'command': 'two'}}, wrapped)
        asked = int(time.time()) - 500
        tm('set-option', '-p', '-t', wrapped, '@tmux_canopy_agent_subagents', f'a1,Explore,needs-input,{asked},Bash')
        assert ranked() == ['P:' + wrapped, 'P:' + other, 'P:' + first], ranked()
        tm('set-option', '-pu', '-t', wrapped, '@tmux_canopy_agent_subagents')
        print('ok - a waiting subagent ranks by its own wait, not its parent report')

        # A window linked into two sessions is listed once per session, and the sort
        # puts those twins side by side. Pressing n must still move on to the other
        # waiting panes instead of returning to the twin of the pane you are on.
        hook({'hook_event_name': 'PermissionRequest', 'session_id': 's3', 'turn_id': 't1',
              'tool_name': 'Bash', 'tool_input': {'command': 'two'}}, wrapped)
        tm('link-window', '-d', '-s', 'work:wrapped', '-t', 'other:7')
        try:
            for pane, seconds in ((first, 60), (other, 120), (wrapped, 300)):
                wait_since(pane, seconds)
            listed = ranked()
            assert listed.count('P:' + wrapped) == 2, listed
            set_location(idle)
            visited = []
            current = jump()
            for _ in range(3):
                visited.append(current)
                set_location(current)
                current = jump()
            assert visited == [wrapped, other, first] and current == wrapped, (visited, current)
        finally:
            tm('unlink-window', '-t', 'other:7')
        print('ok - a pane linked into two sessions does not trap n; it still visits every waiting pane')

        # Unread completed agents are a fallback only when nothing needs input:
        # while 'other' is still interrupted, an unread finished pane waits its
        # turn; once 'other' resumes working, the unread finished agent is next,
        # while working or non-agent panes with activity flags are skipped.
        tm('set-option', '-g', '@tmux_canopy_notifications', 'activity,bell')
        hook({'hook_event_name': 'Stop', 'session_id': 's1', 'turn_id': 't1'}, first)
        hook({'hook_event_name': 'PostToolUse', 'session_id': 's3', 'turn_id': 't1',
              'tool_name': 'Bash', 'tool_input': {'command': 'two'}}, wrapped)
        tm('set-option', '-p', '-t', first, '@tmux_canopy_notice_pane_activity', '1')
        tm('set-option', '-p', '-t', wrapped, '@tmux_canopy_notice_pane_activity', '1')
        tm('set-option', '-p', '-t', idle, '@tmux_canopy_notice_pane_activity', '1')
        assert [row[0] for row in needs_input()] == ['P:' + other]
        hook({'hook_event_name': 'UserPromptSubmit', 'session_id': 's2', 'turn_id': 't2'}, other)
        assert [row[0] for row in needs_input()] == ['P:' + first]
        set_location(idle)
        assert jump() == first
        print('ok - unread completed agents are visited after needs-input, skipping working and non-agent panes')

        # Unread completions follow the same rule: the oldest unseen finish first.
        hook({'hook_event_name': 'Stop', 'session_id': 's3', 'turn_id': 't1'}, wrapped)
        wait_since(first, 30)
        wait_since(wrapped, 200)
        assert ranked() == ['P:' + wrapped, 'P:' + first], ranked()
        set_location(idle)
        assert jump() == wrapped
        print('ok - unread completions are visited oldest first')
finally:
    sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)
