#!/usr/bin/env python3
"""Acting on agents from the sidebar: an agent waiting on you shows what it
asks for beneath its pane, and `>` types a reply into a pane through a native
tmux prompt without moving focus."""
import fcntl
import json
import os
from pathlib import Path
import pty
import re
import shutil
import struct
from support import install_agent_fixture
import subprocess as sp
import tempfile
import termios
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
socket = f'canopy-agent-actions-{os.getpid()}'
env = os.environ.copy()
env.pop('TMUX', None)
env.pop('TMUX_PANE', None)
env['TERM'] = 'xterm-256color'
plain = lambda text: re.sub(r'\x1b\[[0-9;]*m', '', text)


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


client = master = None
try:
    with tempfile.TemporaryDirectory(prefix='canopy-agent-actions-', ignore_cleanup_errors=True) as directory:
        temp = Path(directory)
        state = temp / 'state'
        state.touch()
        install_agent_fixture(temp / 'claude')
        agent = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'work', '-n', 'agent', '-x', '120', '-y', '30',
                   '-P', '-F', '#{pane_id}', str(temp / 'claude') + ' 600')
        tm('set-option', '-g', '@tmux-canopy-agents', 'on')
        tm('set-option', '-g', '@tmux_canopy_appearance', 'quiet')
        # A pane that records each line typed into it.
        received = temp / 'received'
        reader = tm('new-window', '-d', '-t', 'work:', '-n', 'reader', '-P', '-F', '#{pane_id}',
                    f"bash -c 'stty -echo; while IFS= read -r line; do printf \"%s\\n\" \"$line\" >> {received}; done'")
        sidebar = tm('split-window', '-d', '-h', '-b', '-l', '42', '-t', agent, '-P', '-F', '#{pane_id}', 'sleep 600')
        tm('set-option', '-p', '-t', sidebar, '@tmux_canopy', '1')
        socket_path = tm('display-message', '-p', '#{socket_path}')
        base = env | {'TMUX': f'{socket_path},0,0', 'TMUX_CANOPY_STATE': str(state)}

        def event(payload):
            result = sp.run([str(ROOT / 'scripts/agent-hook'), 'claude'], input=json.dumps(payload),
                            env=base | {'TMUX_PANE': agent}, text=True, capture_output=True, timeout=10)
            assert result.returncode == 0, result.stderr

        def lines(*args, nul=True):
            result = sp.run([str(ROOT / 'scripts/tree-source'), *args], env=base | {
                'TMUX_PANE': sidebar, **({'TMUX_CANOPY_NUL': '1'} if nul else {})},
                capture_output=True, text=True, timeout=10)
            assert result.returncode == 0, result.stderr
            records = result.stdout.split('\0') if nul else result.stdout.splitlines()
            rows = {record.split('\t', 1)[0]: record.split('\t', 2)[1] for record in records if '\t' in record}
            return [re.sub(r'^[\s│|]+', '', line) if i else line for i, line in enumerate(plain(rows.get('P:' + agent) or rows.get('W:' + tm('display-message', '-p', '-t', agent,
                                                                        '#{window_id}:#{session_id}'), '')).split('\n'))]

        session = {'session_id': 'main'}
        event(session | {'hook_event_name': 'SessionStart'})
        event(session | {'hook_event_name': 'UserPromptSubmit'})
        assert len(lines()) == 1, lines()
        event(session | {'hook_event_name': 'PermissionRequest', 'tool_name': 'Bash',
                         'tool_input': {'command': 'make test', 'description': 'Run the tests'}})
        for appearance in ('quiet', 'places', 'classic'):
            tm('set-option', '-g', '@tmux_canopy_appearance', appearance)
            for view in ((), ('--agents',)):
                shown = lines(*view)
                assert len(shown) == 2 and shown[1].strip() == 'make test · Run the tests', (appearance, view, shown)
        tm('set-option', '-g', '@tmux_canopy_appearance', 'quiet')
        assert len(lines(nul=False)) == 1, 'single-line rows carry no request line'
        print('ok - an agent waiting on you shows its command and request beneath its pane')

        # A generic summary adds nothing to the waiting glyph: the command alone.
        event(session | {'hook_event_name': 'PostToolUse', 'tool_name': 'Bash',
                         'tool_input': {'command': 'make test', 'description': 'Run the tests'}})
        assert len(lines()) == 1, lines()
        event(session | {'hook_event_name': 'PermissionRequest', 'tool_name': 'Bash',
                         'tool_input': {'command': 'npm publish  #{pane_id}'}})
        assert lines()[1:] and lines()[1].strip() == 'npm publish  #{pane_id}', lines()
        tm('resize-pane', '-t', sidebar, '-x', '24')
        assert all(len(line) <= 21 for line in lines()), lines()
        tm('resize-pane', '-t', sidebar, '-x', '42')
        event(session | {'hook_event_name': 'Stop'})
        assert len(lines()) == 1, lines()
        tm('set-option', '-g', '@tmux-canopy-agents', 'off')
        event(session | {'hook_event_name': 'PermissionRequest', 'tool_name': 'Bash',
                         'tool_input': {'command': 'make test'}})
        assert len(lines()) == 1, 'agent mode off shows no request'
        tm('set-option', '-g', '@tmux-canopy-agents', 'on')
        print('ok - the request line names only the command when the summary is generic, fits the width, and clears with the request')

        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 120, 0, 0))
        client = sp.Popen([shutil.which('tmux'), '-L', socket, 'attach-session', '-t', 'work'], env=env,
                          stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
        os.close(slave)
        output = bytearray()

        def read():
            try:
                while data := os.read(master, 65536):
                    output.extend(data)
            except OSError:
                pass
        threading.Thread(target=read, daemon=True).start()
        wait(lambda: tm('list-clients', '-F', '#{client_name}'), 'client attached')
        client_name = tm('list-clients', '-F', '#{client_name}')
        tm('select-pane', '-t', sidebar)
        action_env = base | {'TMUX_PANE': sidebar, 'TMUX_CANOPY_CLIENT': client_name}

        def send(token, keys, label=None, script='sidebar-action'):
            output.clear()
            pending = sp.Popen([str(ROOT / 'scripts' / script), 'send', token], env=action_env,
                               stdout=sp.PIPE, stderr=sp.PIPE)
            try:
                if label is not None:
                    wait(lambda: label.encode() in output, f'send prompt for {token}')
                    os.write(master, keys)
                _, error = pending.communicate(timeout=5)
                assert pending.returncode == 0, error
            finally:
                if pending.poll() is None:
                    pending.kill()
                    pending.wait(timeout=5)

        def got():
            return received.read_text().splitlines() if received.exists() else []

        reader_label = 'Send to work:' + tm('display-message', '-p', '-t', reader, '#{window_index}.#{pane_index}') + ':'
        text = 'it\'s "$HOME" `id` #{pane_id} ; kill-server \\ ünïcode, 50%'
        send('P:' + reader, text.encode() + b'\r', reader_label)
        wait(lambda: got() == [text], f'literal text arrives: {got()}')
        assert tm('display-message', '-p', '-c', client_name, '#{pane_id}') == sidebar, 'focus stays in the sidebar'
        print('ok - > sends literal text and Enter to a pane without leaving the sidebar')

        window = tm('display-message', '-p', '-t', reader, '#{window_id}:#{session_id}')
        send('W:' + window, b'to the window\r', reader_label)
        send('Q:' + reader, b'from agents\r', reader_label)
        wait(lambda: got()[1:] == ['to the window', 'from agents'], f'window and agents rows: {got()}')
        # tmux picks vi prompt keys when $EDITOR mentions vi; there Escape
        # only leaves insert mode.
        tm('set-option', '-g', 'status-keys', 'emacs')
        tm('set-option', '-g', 'escape-time', '10')
        send('P:' + reader, b'\x1b', reader_label)
        # The sidebar is the active pane of the agent's window: its row sends
        # to the agent instead.
        assert tm('display-message', '-p', '-t', tm('display-message', '-p', '-t', agent, '#{window_id}'), '#{pane_id}') == sidebar
        agent_label = 'Send to work:' + tm('display-message', '-p', '-t', agent, '#{window_index}.#{pane_index}') + ':'
        send('W:' + tm('display-message', '-p', '-t', agent, '#{window_id}:#{session_id}'), b'\x1b', agent_label)
        send('P:' + reader, b'\r', reader_label)
        time.sleep(0.3)
        assert len(got()) == 3, got()
        assert '@tmux_canopy_send_' not in tm('show-options', '-g'), 'a cancelled prompt leaves no state'
        print('ok - window and Agents rows send to their content pane, never the sidebar; Escape and an empty line send nothing')

        tm('set-option', '-p', '-t', reader, 'remain-on-exit', 'on')
        tm('respawn-pane', '-k', '-t', reader, 'true')
        wait(lambda: tm('display-message', '-p', '-t', reader, '#{pane_dead}') == '1', 'reader exits')
        send('P:' + reader, b'')
        send('P:' + sidebar, b'')
        time.sleep(0.2)
        assert b'Send to' not in output, 'dead and sidebar panes get no prompt'
        assert 'Send text…' in (ROOT / 'scripts/tree-action').read_text()
        print('ok - dead panes and sidebar panes are never sent to')
    print('all agent action tests passed')
finally:
    sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True, timeout=10)
    if client is not None:
        client.wait(timeout=5)
    if master is not None:
        os.close(master)
