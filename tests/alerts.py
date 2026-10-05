#!/usr/bin/env python3
"""Agent alerts: focus suppression, desktop and tmux delivery, literal text,
missing notifiers, and a reporter hook that never waits for delivery."""
import fcntl
import json
import os
from pathlib import Path
import pty
import shutil
import struct
import subprocess as sp
import tempfile
import termios
import threading
import time
from support import install_agent_fixture

ROOT = Path(__file__).resolve().parents[1]
socket = f'canopy-alerts-{os.getpid()}'
env = os.environ.copy()
env.pop('TMUX', None)
env.pop('TMUX_PANE', None)
env['TERM'] = 'xterm-256color'
darwin = os.uname().sysname == 'Darwin'


def tm(*args):
    result = sp.run(['tmux', '-L', socket, *args], env=env, text=True,
                    capture_output=True, timeout=10)
    assert result.returncode == 0, (args, result.stderr)
    return result.stdout.strip()


def wait(condition, message, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.05)
    raise AssertionError(message)


try:
    with tempfile.TemporaryDirectory(prefix='canopy-alerts-', ignore_cleanup_errors=True) as directory:
        temp = Path(directory)
        log = temp / 'log'
        stubs = temp / 'bin'
        stubs.mkdir()
        # Each stub records its arguments, one call per line, fields split by
        # \x1f and newlines shown as ⏎. A stub named in CANOPY_STUB_REFUSE then
        # fails, as a notifier that macOS has not allowed does.
        for name in ('terminal-notifier', 'osascript', 'notify-send'):
            stub = stubs / name
            stub.write_text('#!/bin/bash\n${CANOPY_STUB_DELAY:+sleep "$CANOPY_STUB_DELAY"}\n'
                            f'{{ printf "%s\\037" "$(basename "$0")" "${{@//$\'\\n\'/⏎}}"; echo; }} >> {log}\n'
                            '[[ " ${CANOPY_STUB_REFUSE:-} " != *" $(basename "$0") "* ]] || exit 3\n')
            stub.chmod(0o755)
        agent = temp / 'claude'
        install_agent_fixture(agent)
        project = temp / 'shop-api'
        project.mkdir()

        watched = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'work', '-n', 'agent', '-x', '120', '-y', '30',
                     '-c', str(project), '-P', '-F', '#{pane_id}', f'{agent} 600')
        tm('new-window', '-d', '-t', 'work:', '-n', 'other', 'sleep 600')
        build = tm('new-window', '-d', '-t', 'work:', '-n', 'build', '-c', str(project), '-P', '-F', '#{pane_id}',
                   "sh -c 'echo compiling; echo build ok; echo; exec sleep 600'")
        socket_path = tm('display-message', '-p', '#{socket_path}')
        host = tm('display-message', '-p', '#{host}')
        script_env = env | {'TMUX': f'{socket_path},0,0', 'PATH': f'{stubs}:{env["PATH"]}'}
        # Jobs that tmux hooks start see the server's environment: keep them on
        # the stub notifiers too.
        tm('set-environment', '-g', 'PATH', script_env['PATH'])
        for name in ('SUMMARY', 'COMMAND', 'REPLY', 'ELAPSED'):
            script_env.pop(f'CANOPY_ALERT_{name}', None)

        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 30, 120, 0, 0))
        client = sp.Popen([shutil.which('tmux'), '-L', socket, 'attach-session', '-t', 'work'], env=env,
                          stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
        output = bytearray()

        def read():
            try:
                while data := os.read(master, 65536):
                    output.extend(data)
            except OSError:
                pass
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        wait(lambda: tm('list-clients', '-F', '#{client_name}'), 'client attached')

        def notify(pane, event, kind, mode, extra=None, **text):
            alert_env = script_env | {f'CANOPY_ALERT_{key.upper()}': value for key, value in text.items()}
            sp.run([str(ROOT / 'scripts/alert'), pane, event, kind, mode], env=alert_env | (extra or {}),
                   check=True, timeout=10)

        def calls():
            return [line.split('\x1f')[:-1] for line in log.read_text().splitlines()] if log.exists() else []

        def message(*args, **text):
            """Title, subtitle, and body of one desktop alert."""
            if log.exists():
                log.unlink()
            notify(*args, **text)
            wait(lambda: calls(), f'desktop alert for {args}')
            notifier, *arguments = calls()[-1]
            if notifier == 'terminal-notifier':
                return tuple(arguments[arguments.index(flag) + 1] for flag in ('-title', '-subtitle', '-message'))
            if notifier == 'osascript':
                title, body, subtitle = arguments[-3:]
                return title, subtitle, body
            title, text = arguments[-2:]
            return (title, *text.split('⏎', 1))

        summary = 'rm -rf "$(id)" `x` #{pane_id} \\n it;'

        # Without focus-events, a pane on screen counts as seen.
        notify(watched, 'needs-input', 'claude', 'both', summary=summary)
        time.sleep(0.3)
        assert calls() == [] and b'needs input' not in output, (calls(), 'visible pane stays quiet')

        # Title: agent, event, and project. Subtitle: session:window, and the
        # topic from the pane title once its leading glyph is dropped.
        tm('select-window', '-t', 'work:other')
        tm('select-pane', '-t', watched, '-T', '✳ Fix the build')
        output.clear()
        assert message(watched, 'needs-input', 'claude', 'both', summary=summary) == \
            ('Claude Code needs input · shop-api', 'work:0 · Fix the build', summary)
        notifier, *arguments = calls()[-1]
        if notifier == 'terminal-notifier':
            assert arguments[arguments.index('-group') + 1] == f'tmux-canopy-{watched}', arguments
            assert '-execute' in arguments and '-sound' not in arguments, arguments
        wait(lambda: b'Claude Code needs input' in output and b'#{pane_id}' in output,
             'tmux alert shows the summary literally')

        # Bodies: a request and its command, how long a turn took, and the
        # agent's last reply only when detail is full.
        assert message(watched, 'needs-input', 'claude', 'desktop', summary='Run the tests',
                       command='make test')[2] == 'Run the tests: make test'
        assert message(watched, 'needs-input', 'claude', 'desktop', summary='Approve make test',
                       command='make test')[2] == 'Approve make test'
        assert message(watched, 'needs-input', 'claude', 'desktop')[2] == 'Waiting for you'
        reply = 'All tests pass.\n\n' + 'x' * 300
        assert message(watched, 'done', 'claude', 'desktop', reply=reply, elapsed='125')[2] == 'Turn ended after 2m'
        tm('set-option', '-g', '@tmux_canopy_alert_detail', 'full')
        body = message(watched, 'done', 'claude', 'desktop', reply=reply, elapsed='125')[2]
        assert body.startswith('All tests pass. xxx') and body.endswith('… (after 2m)') and len(body) <= 161, body
        tm('set-option', '-gu', '@tmux_canopy_alert_detail')
        assert message(watched, 'done', 'claude', 'desktop', elapsed='42')[2] == 'Turn ended after 42s'
        assert message(watched, 'interrupted', 'claude', 'desktop', elapsed='4000')[2] == 'Stopped after 1h6m'
        assert message(watched, 'done', 'claude', 'desktop', elapsed='soon')[2] == 'Turn ended'
        # A pane title that is only the host name is no topic.
        tm('select-pane', '-t', watched, '-T', host)
        assert message(watched, 'done', 'claude', 'desktop')[1] == 'work:0 agent'
        tm('select-pane', '-t', watched, '-T', '✳ Fix the build')

        # With focus-events, only a focused terminal showing the pane counts as seen.
        tm('set-option', '-g', 'focus-events', 'on')
        tm('select-window', '-t', 'work:agent')
        os.write(master, b'\x1b[I')
        wait(lambda: 'focused' in tm('list-clients', '-F', '#{client_flags}'), 'client focused')
        log.unlink()
        notify(watched, 'done', 'claude', 'desktop')
        time.sleep(0.3)
        assert calls() == [], 'focused pane stays quiet'
        os.write(master, b'\x1b[O')
        wait(lambda: 'focused' not in tm('list-clients', '-F', '#{client_flags}'), 'client unfocused')
        assert message(watched, 'done', 'claude', 'desktop')[0] == 'Claude Code finished · shop-api'

        # Only the requested channels deliver, and bad arguments do nothing.
        log.unlink()
        output.clear()
        tm('select-window', '-t', 'work:other')
        notify(watched, 'done', 'claude', 'tmux')
        wait(lambda: b'Claude Code finished' in output, 'tmux-only alert reaches the client')
        for bad in (('nope', 'done', 'claude', 'both'), (watched, 'done', 'unknown', 'both'),
                    (watched, 'other', 'claude', 'both'), (watched, 'done', 'claude', 'off')):
            notify(*bad)
        time.sleep(0.3)
        assert calls() == [], calls()

        # A refused notifier hands over to the next one, and the test command
        # says which delivered and which refused.
        notify(watched, 'interrupted', 'claude', 'desktop', extra={'CANOPY_STUB_REFUSE': 'terminal-notifier'})
        wait(lambda: calls(), 'alert after a refusal')
        order = [call[0] for call in calls()]
        assert order == (['terminal-notifier', 'osascript'] if darwin else ['notify-send']), order
        assert 'Claude Code was interrupted · shop-api' in calls()[-1], calls()

        def sample(refuse):
            return sp.run([str(ROOT / 'scripts/alert'), '--test', 'desktop'], capture_output=True, text=True,
                          env=script_env | {'CANOPY_STUB_REFUSE': refuse}, timeout=10)
        result = sample('terminal-notifier' if darwin else '')
        assert result.returncode == 0, result
        if darwin:
            assert result.stdout == ('desktop: sent with osascript\n'
                                     'desktop: refused by terminal-notifier; check its macOS notification permission\n'), result.stdout
        result = sample('terminal-notifier osascript notify-send')
        assert result.returncode == 1 and result.stdout.startswith('desktop: not sent\n'), result
        probe = sp.run([str(ROOT / 'scripts/alert'), '--notifier'], env=script_env,
                       capture_output=True, text=True, timeout=10)
        assert probe.stdout == ('terminal-notifier,osascript\n' if darwin else 'notify-send\n'), probe.stdout
        log.unlink()

        # Clicking a terminal-notifier alert runs a /bin/sh command, outside
        # tmux and with a minimal PATH, that brings the client to the pane and
        # the terminal app forward.
        if darwin:
            tm('select-window', '-t', 'work:other')
            notify(watched, 'done', 'claude', 'desktop', extra={'__CFBundleIdentifier': 'com.example.term'})
            wait(lambda: calls(), 'clickable alert')
            arguments = calls()[0][1:]
            assert arguments[arguments.index('-activate') + 1] == 'com.example.term', arguments
            click = arguments[arguments.index('-execute') + 1]
            assert tm('list-clients', '-F', '#{window_name}') == 'other'
            sp.run(['/bin/sh', '-c', click], env={'PATH': '/usr/bin:/bin'}, check=True, timeout=10)
            assert tm('list-clients', '-F', '#{window_name}|#{pane_id}') == f'agent|{watched}'
            log.unlink()
            tm('select-window', '-t', 'work:other')

        # An optional sound goes to whichever notifier delivers. 'default' maps
        # to each platform's usual sound; anything that is not a plain name is
        # ignored.
        def sounded(value, refuse=''):
            tm('set-option', '-g', '@tmux_canopy_alert_sound', value)
            notify(watched, 'done', 'claude', 'desktop', extra={'CANOPY_STUB_REFUSE': refuse})
            wait(lambda: calls(), f'alert with sound {value!r}')
            result = calls()[-1]
            log.unlink()
            return result
        if darwin:
            call = sounded('Glass')
            assert call[call.index('-sound') + 1] == 'Glass', call
            call = sounded('default', refuse='terminal-notifier')
            assert call[0] == 'osascript' and call[-1] == 'Glass' and 'sound name (item 4 of argv)' in call[4], call
            call = sounded('Ping', refuse='terminal-notifier')
            assert call[-4:] == ['Claude Code finished · shop-api', 'Turn ended', 'work:0 · Fix the build', 'Ping'], call
            assert '-sound' not in sounded('a b') and '-sound' not in sounded('off')
        else:
            assert 'string:sound-name:Glass' in sounded('Glass')
            assert 'string:sound-name:message-new-instant' in sounded('default')
            assert not any('sound-name' in arg for arg in sounded('a b'))
        tm('set-option', '-gu', '@tmux_canopy_alert_sound')

        # No desktop notifier installed: a silent no-op.
        bare = temp / 'bare'
        bare.mkdir()
        for tool in ('bash', 'tmux', 'env'):
            (bare / tool).symlink_to(shutil.which(tool))
        notify(watched, 'done', 'claude', 'desktop', extra={'PATH': str(bare)})
        probe = sp.run([str(ROOT / 'scripts/alert'), '--notifier'], env=script_env | {'PATH': str(bare)},
                       capture_output=True, text=True, timeout=10)
        assert probe.stdout == 'none\n', probe.stdout

        # The real reporter path: the setting rides on its pane check, the
        # reply reaches delivery through the environment, and a slow notifier
        # never holds up the agent's hook.
        tm('set-option', '-g', '@tmux_canopy_agent_alerts', 'desktop')
        tm('set-option', '-g', '@tmux_canopy_alert_detail', 'full')

        def hook(event):
            started = time.monotonic()
            sp.run([str(ROOT / 'scripts/agent-hook'), 'claude'], input=json.dumps(event), text=True,
                   env=script_env | {'TMUX_PANE': watched, 'CANOPY_STUB_DELAY': '2'},
                   capture_output=True, check=True, timeout=10)
            return time.monotonic() - started
        hook({'hook_event_name': 'SessionStart', 'session_id': 'e2e'})
        hook({'hook_event_name': 'UserPromptSubmit', 'session_id': 'e2e'})
        elapsed = hook({'hook_event_name': 'Stop', 'session_id': 'e2e', 'last_assistant_message': 'Shipped it.'})
        assert tm('show-option', '-pqv', '-t', watched, '@tmux_canopy_agent_status') == 'turn-ended'
        assert elapsed < 1.5, f'hook waited for delivery: {elapsed:.2f}s'
        wait(lambda: any('Claude Code finished · shop-api' in call and any('Shipped it. (after ' in arg
                                                                           for arg in call) for call in calls()),
             'reporter started delivery with the reply')

        # tmux's own alerts name the pane's command; full detail adds the pane's
        # last line of output.
        tm('set-option', '-gu', '@tmux_canopy_alert_detail')
        tm('select-window', '-t', 'work:other')
        wait(lambda: 'build ok' in tm('capture-pane', '-p', '-t', build), 'build output')
        assert message(build, 'bell', 'tmux', 'desktop') == \
            ('Bell from sleep · shop-api', 'work:2 build', 'Rang the bell')
        tm('set-window-option', '-t', 'work:build', 'monitor-silence', '30')
        assert message(build, 'silence', 'tmux', 'desktop') == \
            ('sleep went quiet · shop-api', 'work:2 build', 'No output for 30s')
        assert message(build, 'activity', 'tmux', 'desktop')[0] == 'Output from sleep · shop-api'
        tm('set-option', '-g', '@tmux_canopy_alert_detail', 'full')
        assert message(build, 'bell', 'tmux', 'desktop')[2] == 'build ok'
        assert message(build, 'silence', 'tmux', 'desktop')[2] == 'No output for 30s · build ok'
        tm('set-option', '-gu', '@tmux_canopy_alert_detail')
        log.unlink()
        for bad in ((build, 'done', 'tmux', 'desktop'), (build, 'bell', 'claude', 'desktop')):
            notify(*bad)
        time.sleep(0.3)
        assert calls() == [], calls()

        # The tmux alert hooks reach alerts through scripts/notify. Without a
        # sidebar badge every event alerts. With one, an alert rides on the
        # badge's own check, so it fires once until the pane is read, however
        # many events arrive together.
        window = tm('display-message', '-p', '-t', build, '#{window_id}')

        def notice(count=1):
            processes = [sp.Popen([str(ROOT / 'scripts/notify'), 'set', window, build, 'bell'], env=script_env)
                         for _ in range(count)]
            for process in processes:
                assert process.wait(timeout=10) == 0
        tm('set-option', '-g', '@tmux_canopy_alerts', 'desktop')
        tm('set-option', '-g', '@tmux_canopy_alert_events', 'agents,bell')
        tm('set-option', '-g', '@tmux_canopy_notifications', 'none')
        notice()
        notice()
        wait(lambda: len(calls()) == 2, 'each bell alerts when the sidebar keeps no badge')
        assert all('Bell from sleep · shop-api' in call for call in calls()), calls()
        log.unlink()
        tm('set-option', '-g', '@tmux_canopy_notifications', 'bell')
        notice(5)
        wait(lambda: calls(), 'a burst of bells alerts')
        time.sleep(0.5)
        assert len(calls()) == 1 and tm('show-option', '-pqv', '-t', build, '@tmux_canopy_notice_pane_bell') == '1'
        notice()
        time.sleep(0.5)
        assert len(calls()) == 1, 'an unread bell does not alert again'
        log.unlink()
        tm('set-option', '-pu', '-t', build, '@tmux_canopy_notice_pane_bell')
        tm('set-option', '-g', '@tmux_canopy_alert_events', 'agents')
        notice()
        time.sleep(0.5)
        assert calls() == [] and tm('show-option', '-pqv', '-t', build, '@tmux_canopy_notice_pane_bell') == '1', \
            'bell left out of alert-events still gets its badge, but no alert'

        # Loading the plugin turns the settings into what hooks and reporters
        # read, and registers a tmux alert hook for alerts alone.
        def load(**settings):
            for name, value in settings.items():
                tm('set-option', '-g', f'@tmux-canopy-{name.replace("_", "-")}', value)
            sp.run([str(ROOT / 'tmux-canopy.tmux')], env=script_env, check=True, timeout=30, capture_output=True)
            return (tm('show-option', '-gqv', '@tmux_canopy_alert_events'),
                    tm('show-option', '-gqv', '@tmux_canopy_agent_alerts'), tm('show-hooks', '-g'))
        events, agents, hooks = load(alerts='both', alert_events='bell, agents,nonsense', notifications='none')
        assert events == 'agents,bell' and agents == 'both', (events, agents)
        assert 'alert-bell[9002]' in hooks and 'alert-silence[9002]' not in hooks, hooks
        events, agents, hooks = load(alert_events='silence')
        assert events == 'silence' and agents == 'off', (events, agents)
        assert 'alert-silence[9002]' in hooks and 'alert-bell[9002]' not in hooks, hooks
        events, agents, hooks = load(alerts='nope', alert_events='all')
        assert events == 'agents,bell,silence,activity' and agents == 'off', (events, agents)
        assert '[9002]' not in hooks, hooks

        client.terminate()
        client.wait(timeout=5)
        # Closing the slave ends the reader; closing a master that a thread is
        # still reading can block on macOS.
        os.close(slave)
        reader.join(timeout=5)
        os.close(master)
    print('ok - agent and tmux alerts respect focus, deliver literally, skip missing notifiers, and never block hooks')
finally:
    sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True, timeout=10)
