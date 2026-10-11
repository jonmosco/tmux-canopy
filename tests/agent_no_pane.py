#!/usr/bin/env python3
"""Hooks without TMUX_PANE still reach their pane: through the process tree
when the agent runs in the pane, or, for a Claude Code background session that
runs outside tmux, through the pane whose claude resumes the same session.
Two such panes, or none, mean no report."""
import json
import os
import sys
from pathlib import Path
import subprocess as sp
import tempfile
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))
from support import install_agent_fixture

ROOT = Path(__file__).resolve().parents[1]
HOOK = str(ROOT / 'scripts/agent-hook')
socket = f'canopy-no-pane-{os.getpid()}'
env = os.environ.copy()
env.pop('TMUX', None)
env.pop('TMUX_PANE', None)


def tm(*args):
    result = sp.run(['tmux', '-L', socket, *args], env=env, text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, (args, result.stderr)
    return result.stdout.strip()


def wait(condition, message, timeout=6):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.05)
    raise AssertionError(message)


def claude(*argv, script):
    """A shell that ps reports as `claude ARGV...`, running script."""
    return ['bash', '-c', 'exec -a claude bash -c "$0" claude "$@"', script, *argv]


try:
    with tempfile.TemporaryDirectory(prefix='canopy-no-pane-') as directory:
        temp = Path(directory)
        tm('-f', '/dev/null', 'new-session', '-d', '-s', 'work', '-x', '120', '-y', '30', 'sleep 600')
        socket_path = tm('display-message', '-p', '#{socket_path}')
        # TMUX names the server; TMUX_PANE is what is missing.
        hook_env = env | {'TMUX': f'{socket_path},0,0'}

        def status(pane):
            return tm('display-message', '-p', '-t', pane, '#{@tmux_canopy_agent_session}|#{@tmux_canopy_agent_status}')

        def event_file(name, payload):
            path = temp / name
            path.write_text(json.dumps(payload))
            return str(path)

        # 1. The agent runs in the pane but its hooks lack TMUX_PANE.
        inside = event_file('inside.json', {'hook_event_name': 'UserPromptSubmit', 'session_id': 'inside-1'})
        command = ' '.join(f"'{part}'" for part in claude(script=f'unset TMUX_PANE; "{HOOK}" claude < "{inside}"; sleep 600; :'))
        pane = tm('new-window', '-d', '-t', 'work:', '-e', f'TMUX={socket_path},0,0', '-P', '-F', '#{pane_id}', command)
        wait(lambda: status(pane) == 'inside-1|working', f'hook without TMUX_PANE reaches its pane: {status(pane)}')

        # 2. A background session runs outside tmux; its pane resumes the same
        # original session.
        viewer = tm('new-window', '-d', '-t', 'work:', '-P', '-F', '#{pane_id}',
                    ' '.join(f"'{part}'" for part in claude('--resume', 'original-session-1', script='sleep 600; :')))
        background = event_file('background.json', {'hook_event_name': 'UserPromptSubmit', 'session_id': 'forked-session-1'})

        def from_background(path):
            sp.run(claude('--session-id', 'forked-session-1', '--fork-session', '--resume',
                          '/home/u/.claude/projects/x/original-session-1.jsonl',
                          script=f'"{HOOK}" claude < "{path}"'),
                   env=hook_env, check=True, timeout=10, capture_output=True)
        from_background(background)
        wait(lambda: status(viewer) == 'forked-session-1|working', f'background hook reaches the pane resuming its session: {status(viewer)}')
        stop = event_file('stop.json', {'hook_event_name': 'Stop', 'session_id': 'forked-session-1'})
        from_background(stop)
        wait(lambda: status(viewer) == 'forked-session-1|turn-ended', f'later background reports follow: {status(viewer)}')

        # 3. Two panes resume that session: no guess.
        twin = tm('new-window', '-d', '-t', 'work:', '-P', '-F', '#{pane_id}',
                  ' '.join(f"'{part}'" for part in claude('--resume', 'original-session-1', script='sleep 600; :')))
        time.sleep(0.3)
        from_background(background)
        time.sleep(0.5)
        assert status(viewer) == 'forked-session-1|turn-ended' and status(twin) == '|', (status(viewer), status(twin))

        # 4. `claude attach <prefix>` views a background session by an id prefix.
        attached = tm('new-window', '-d', '-t', 'work:', '-P', '-F', '#{pane_id}',
                      ' '.join(f"'{part}'" for part in claude('attach', 'attachsess', script='sleep 600; :')))
        time.sleep(0.3)
        attach_event = event_file('attach.json', {'hook_event_name': 'UserPromptSubmit', 'session_id': 'attachsess-1234'})
        sp.run(claude('--session-id', 'attachsess-1234', script=f'"{HOOK}" claude < "{attach_event}"'), env=hook_env,
               check=True, timeout=10, capture_output=True)
        wait(lambda: status(attached) == 'attachsess-1234|working', f'claude attach by prefix reaches its pane: {status(attached)}')

        # 5. An agent outside tmux with no linked pane reports nowhere.
        lonely = event_file('lonely.json', {'hook_event_name': 'UserPromptSubmit', 'session_id': 'lonely-1'})
        sp.run(claude('--session-id', 'lonely-1', script=f'"{HOOK}" claude < "{lonely}"'), env=hook_env,
               check=True, timeout=10, capture_output=True)
        time.sleep(0.3)
        assert all(status(p) in ('|', 'inside-1|working', 'forked-session-1|turn-ended', 'attachsess-1234|working')
                   for p in (pane, viewer, twin, attached))
        print('ok - hooks without TMUX_PANE reach their pane by process tree or linked session, and never guess')

        # 6. OpenCode 2 runs plugins in a shared service outside tmux: events
        # reach the OpenCode pane by session and directory, never another.
        install_agent_fixture(temp / 'opencode')
        project = temp / 'project'
        project.mkdir()
        oc = tm('new-window', '-d', '-t', 'work:', '-c', str(project), '-P', '-F', '#{pane_id}',
                f"{temp / 'opencode'} 600")
        project = Path(tm('display-message', '-p', '-t', oc, '#{pane_current_path}'))

        def service(payload):
            sp.run([HOOK, 'opencode'], input=json.dumps(payload), env=hook_env, text=True,
                   check=True, timeout=10, capture_output=True)
        service({'type': 'session.created', 'properties': {'sessionID': 'oc-1',
                 'info': {'id': 'oc-1', 'directory': str(project)}}})
        wait(lambda: status(oc) == 'oc-1|ready', f'service session binds its pane: {status(oc)}')
        service({'type': 'session.status', 'properties': {'sessionID': 'oc-1', 'status': {'type': 'busy'}}})
        wait(lambda: status(oc) == 'oc-1|working', f'later service events follow the session: {status(oc)}')
        service({'type': 'session.created', 'properties': {'sessionID': 'oc-elsewhere',
                 'info': {'id': 'oc-elsewhere', 'directory': '/somewhere/else'}}})
        time.sleep(.3)
        assert status(oc) == 'oc-1|working', status(oc)
        print('ok - OpenCode service events without TMUX_PANE reach the pane by session and directory')
finally:
    sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True, timeout=10)
