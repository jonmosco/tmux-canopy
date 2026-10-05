#!/usr/bin/env python3
"""Codex 0.159+ runs hooks in a shared app-server daemon that keeps the
TMUX_PANE of whichever pane started it. Reports must reach the pane that owns
each session, and an ambiguous session must report nowhere."""
import json
import os
from pathlib import Path
import subprocess as sp
import tempfile
from support import install_agent_fixture

ROOT = Path(__file__).resolve().parents[1]
socket = f'canopy-codex-daemon-{os.getpid()}'
env = os.environ.copy()
env.pop('TMUX', None)
env.pop('TMUX_PANE', None)


def tm(*args):
    result = sp.run(['tmux', '-L', socket, *args], env=env, text=True,
                    capture_output=True, timeout=10)
    assert result.returncode == 0, (args, result.stderr)
    return result.stdout.strip()


try:
    with tempfile.TemporaryDirectory(prefix='canopy-codex-daemon-', ignore_cleanup_errors=True) as directory:
        temp = Path(directory)
        binary = temp / 'codex'
        install_agent_fixture(binary)
        folders = {}
        for name in ('api', 'web', 'shared', 'solo'):
            folders[name] = temp / name
            folders[name].mkdir()

        def codex_pane(folder, first=False):
            if first:
                return tm('-f', '/dev/null', 'new-session', '-d', '-s', 'work', '-x', '120', '-y', '30',
                          '-c', str(folders[folder]), '-P', '-F', '#{pane_id}', f'{binary} 600')
            return tm('new-window', '-d', '-t', 'work:', '-c', str(folders[folder]), '-P', '-F', '#{pane_id}',
                      f'{binary} 600')
        starter = codex_pane('api', first=True)
        web = codex_pane('web')
        shared = [codex_pane('shared'), codex_pane('shared')]
        socket_path = tm('display-message', '-p', '#{socket_path}')

        # Stands in for `codex app-server`: the hook runs as its child, with the
        # environment of the pane that started the daemon.
        daemon_dir = temp / 'daemon'
        daemon_dir.mkdir()
        daemon = daemon_dir / 'codex'
        daemon.write_text('#!/bin/bash\nexec 3<"$CANOPY_EVENT"\n"$CANOPY_HOOK" <&3\n')
        daemon.chmod(0o755)
        event_file = temp / 'event.json'
        daemon_env = env | {'TMUX': f'{socket_path},0,0', 'TMUX_PANE': starter,
                            'CANOPY_HOOK': str(ROOT / 'scripts/codex-hook'), 'CANOPY_EVENT': str(event_file)}

        def hook(name, session, folder, **extra):
            event = {'hook_event_name': name, 'session_id': session, 'cwd': str(folders[folder]), **extra}
            event_file.write_text(json.dumps(event))
            result = sp.run([str(daemon), 'app-server', '--listen', 'unix://'], env=daemon_env,
                            capture_output=True, text=True, timeout=10)
            assert result.returncode == 0, result.stderr
            assert result.stdout == ('{}\n' if name in ('Stop', 'SubagentStop') else ''), result.stdout

        def state(pane):
            return tm('display-message', '-p', '-t', pane,
                      '#{@tmux_canopy_agent_source}|#{@tmux_canopy_agent_session}|#{@tmux_canopy_agent_status}')

        # A session starting in another pane reaches that pane, not the one the
        # daemon's environment names.
        hook('SessionStart', 'web-1', 'web', source='startup')
        assert state(web) == 'codex-hook|web-1|ready', state(web)
        assert state(starter) == '||', state(starter)
        hook('UserPromptSubmit', 'web-1', 'web', turn_id='t1')
        assert state(web) == 'codex-hook|web-1|working', state(web)
        hook('SessionStart', 'api-1', 'api', source='startup')
        assert state(starter) == 'codex-hook|api-1|ready', state(starter)

        # Once bound, a session follows its pane even if its cwd changes.
        hook('PermissionRequest', 'web-1', 'api', turn_id='t1', tool_name='Bash',
             tool_input={'command': 'make', 'description': 'Build'})
        assert state(web) == 'codex-hook|web-1|needs-input', state(web)
        assert state(starter) == 'codex-hook|api-1|ready', state(starter)
        hook('Stop', 'web-1', 'web', turn_id='t1', last_assistant_message='done')
        assert state(web) == 'codex-hook|web-1|turn-ended', state(web)

        # Two Codex panes in one directory: no guess, no report.
        hook('SessionStart', 'shared-1', 'shared', source='startup')
        hook('UserPromptSubmit', 'shared-1', 'shared', turn_id='t1')
        assert [state(pane) for pane in shared] == ['||', '||'], [state(pane) for pane in shared]
        hook('Stop', 'unknown', 'shared', turn_id='t1', last_assistant_message='')

        # A new session in a pane that already follows one (/new) rebinds it,
        # when it is the only Codex pane in that directory.
        hook('SessionStart', 'web-2', 'web', source='clear')
        assert state(web) == 'codex-hook|web-2|ready', state(web)
        hook('Stop', 'web-1', 'web', turn_id='t9', last_assistant_message='')
        assert state(web) == 'codex-hook|web-2|ready', 'the old session no longer reports to the pane'

        # The pane that started the daemon closes; the daemon keeps its id.
        solo = codex_pane('solo')
        tm('kill-pane', '-t', starter)
        hook('SessionStart', 'solo-1', 'solo', source='startup')
        assert state(solo) == 'codex-hook|solo-1|ready', state(solo)

        # Outside the daemon, TMUX_PANE still decides, as before.
        plain = sp.run([str(ROOT / 'scripts/codex-hook')], input=json.dumps(
            {'hook_event_name': 'SessionStart', 'session_id': 'plain-1', 'cwd': str(folders['shared'])}),
            env=daemon_env | {'TMUX_PANE': shared[0]}, capture_output=True, text=True, timeout=10)
        assert plain.returncode == 0 and state(shared[0]) == 'codex-hook|plain-1|ready', state(shared[0])
    print('ok - daemon-run Codex hooks reach the pane that owns each session, and never guess')
finally:
    sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True, timeout=10)
