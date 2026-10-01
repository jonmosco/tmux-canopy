#!/usr/bin/env python3
"""Record the README demo: a scripted Canopy session captured with asciinema.

Builds a fictional workspace (acme-api, acme-web, notes) in a temporary home
on a private tmux server, records one client headlessly with asciinema while a
timeline drives keys (tmux send-keys -K) and real agent hook events, then
converts the recording to a GIF with agg. Captions use the demo server's own
status line. The agent panes are renamed sleep binaries printing a fictional
transcript. Nothing from the user's own tmux server, files, or projects is shown.

    python3 docs/demo/record.py                  # docs/assets/canopy-demo.{cast,gif,png}
    python3 docs/demo/record.py --output /tmp/x  # review elsewhere first

Options: --theme (an agg theme, default dracula), --font-family, and --poster
(the GIF time in seconds exported as canopy-demo.png).

Requires tmux, fzf, Python 3, asciinema 3, agg, and on macOS coreutils
(gsleep). ffmpeg is optional and only exports the still image. The GIF uses
Hack Nerd Font Mono when installed. Adjust the timeline's pauses to change pacing.

Before committing, watch the GIF and check the recording holds nothing private:

    grep -c -e "$USER" -e "$(hostname -s)" -e /Users/ -e /home/ docs/assets/canopy-demo.cast  # expect 0

The .cast is not committed (.gitignore); it is about three times the GIF's size
and this script recreates it. Use it locally with `asciinema play`, or to
re-render with other agg settings without recording again.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess as sp
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
SOCKET = f'canopy-demo-{os.getpid()}'
COLS, ROWS = 112, 30


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(ROOT / 'docs' / 'assets'), help='directory for the .cast and .gif')
    parser.add_argument('--font-family', default='Hack Nerd Font Mono,JetBrains Mono,Menlo')
    parser.add_argument('--theme', default='dracula')
    parser.add_argument('--poster', type=float, default=26, help='GIF time in seconds for canopy-demo.png')
    args = parser.parse_args()
    for tool in ('tmux', 'fzf', 'asciinema', 'agg'):
        if not shutil.which(tool):
            sys.exit(f'{tool} is required')
    sleeper = shutil.which('gsleep' if sys.platform == 'darwin' else 'sleep')
    if not sleeper:
        sys.exit('gsleep is required on macOS (brew install coreutils)')
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    cast, gif = output / 'canopy-demo.cast', output / 'canopy-demo.gif'

    with tempfile.TemporaryDirectory(prefix='canopy-demo-') as directory:
        home = Path(directory) / 'home'
        bin_dir = Path(directory) / 'bin'
        for path in (home / 'acme-api', home / 'acme-web', home / 'notes', bin_dir):
            path.mkdir(parents=True)
        env = {'PATH': os.environ['PATH'], 'HOME': str(home), 'TERM': 'xterm-256color',
               'LANG': os.environ.get('LANG', 'en_US.UTF-8'), 'SHELL': '/bin/bash'}

        def tm(*argv):
            result = sp.run(['tmux', '-L', SOCKET, *argv], env=env, capture_output=True, text=True, timeout=15)
            if result.returncode:
                raise RuntimeError((argv, result.stderr))
            return result.stdout.strip()

        # Agents are detected by process name, so each fake agent is a renamed
        # sleep binary. A wrapper prints a fictional transcript, then execs it.
        for name in ('claude', 'codex'):
            shutil.copy(sleeper, bin_dir / name)

        def program(name, text, then):
            script = bin_dir / f'{name}.sh'
            # Agents draw their own UI; hide the terminal cursor for them.
            cursor = "printf '\\033[?25l'\n" if then.startswith(f'exec {bin_dir}') else ''
            script.write_text('#!/bin/bash\nprintf \'\\033[2J\\033[H\'\ncat <<\'DEMO\'\n' + text + '\nDEMO\n' + cursor + then + '\n')
            script.chmod(0o755)
            return str(script)

        shell = 'export PS1="\\[\\033[32m\\]\\w\\[\\033[0m\\] $ "; exec bash --noprofile --norc -i'
        api_agent = program('api-agent', '''
 \033[38;5;173m✻\033[0m Claude Code \033[2m(demo)\033[0m

 \033[1m>\033[0m add rate limiting to the login endpoint

 \033[38;5;173m⏺\033[0m Reading src/auth/login.ts
 \033[38;5;173m⏺\033[0m Planning the change with two subagents…''', f'exec {bin_dir}/claude 3600')
        web_agent = program('web-agent', '''
 \033[38;5;173m✻\033[0m Claude Code \033[2m(demo)\033[0m

 \033[1m>\033[0m make settings responsive

 \033[38;5;173m⏺\033[0m Updating src/pages/settings.tsx
 \033[38;5;173m⏺\033[0m Running the component tests…''', f'exec {bin_dir}/claude 3600')
        codex = program('codex', '''
 \033[1mCodex\033[0m \033[2m(demo)\033[0m

 \033[1m›\033[0m write release notes for v2.4

 \033[2mwaiting for your next prompt\033[0m''', f'exec {bin_dir}/codex 3600')
        tests = program('tests', '''\033[32m~/acme-api\033[0m $ npm test

 \033[32mPASS\033[0m  src/auth/login.test.ts
 \033[32mPASS\033[0m  src/auth/session.test.ts
 \033[32mPASS\033[0m  src/routes/health.test.ts

 Tests:  \033[32m42 passed\033[0m, 42 total''', shell)
        git = program('git', '''\033[32m~/acme-web\033[0m $ git log
\033[33m9f2c1ab\033[0m tidy settings
\033[33m41d07ce\033[0m avatar upload
\033[33m7be95a2\033[0m theme toggle
\033[33mc3aa610\033[0m bump deps''', shell)
        notes = program('notes', '''\033[32m~/notes\033[0m $ cat today.md
- review the rate limit PR
- ship v2.4 release notes''', shell)

        config = Path(directory) / 'tmux.conf'
        config.write_text(f'''
set -g default-terminal tmux-256color
set -g default-shell /bin/bash
set -g escape-time 10
set -g mouse on
set -g status on
set -g status-interval 0
set -g status-style 'bg=#21222c,fg=#f8f8f2'
set -g status-format[0] '#[align=centre]#{{@demo_caption}}'
set -g pane-border-style 'fg=#44475a'
set -g pane-active-border-style 'fg=#6272a4'
set -g @tmux-canopy-icon-theme nerdfont
set -g @tmux-canopy-agents off
set -g @tmux-canopy-animate on
set -g @demo_caption ''
''')
        try:
            api = tm('-f', str(config), 'new-session', '-d', '-s', 'acme-api', '-x', str(COLS), '-y', str(ROWS),
                     '-n', 'server', '-c', str(home / 'acme-api'), '-P', '-F', '#{pane_id}', api_agent)
            tm('split-window', '-d', '-v', '-l', '40%', '-t', api, '-c', str(home / 'acme-api'), tests)
            tm('new-window', '-d', '-t', 'acme-api:', '-n', 'release', '-c', str(home / 'acme-api'), codex)
            web = tm('new-session', '-d', '-s', 'acme-web', '-n', 'ui', '-c', str(home / 'acme-web'),
                     '-P', '-F', '#{pane_id}', web_agent)
            tm('split-window', '-d', '-h', '-l', '30%', '-t', web, '-c', str(home / 'acme-web'), git)
            tm('new-session', '-d', '-s', 'notes', '-n', 'today', '-c', str(home / 'notes'), notes)
            tm('select-pane', '-t', api)
            base = env | {'TMUX': tm('display-message', '-p', '-t', api, '#{socket_path},#{pid},0')}
            load = sp.run(['bash', str(ROOT / 'tmux-canopy.tmux')], env=base, capture_output=True, text=True)
            if load.returncode:
                raise RuntimeError(load.stderr)

            def hook(pane, session, payload):
                sp.run([str(ROOT / 'scripts' / 'agent-hook'), 'claude'], env=base | {'TMUX_PANE': pane},
                       input=json.dumps({'session_id': session} | payload), capture_output=True, text=True,
                       timeout=10, check=True)

            for pane, session in ((api, 'api'), (web, 'web')):
                hook(pane, session, {'hook_event_name': 'SessionStart'})
                hook(pane, session, {'hook_event_name': 'UserPromptSubmit'})

            recorder = sp.Popen(['asciinema', 'rec', '--headless', '--overwrite', '--quiet',
                                 '--window-size', f'{COLS}x{ROWS}', '--idle-time-limit', '2',
                                 '--title', 'tmux-canopy', '-c', f'tmux -L {SOCKET} attach -t acme-api', str(cast)],
                                env=env)
            client = ''
            for _ in range(100):
                client = tm('list-clients', '-F', '#{client_name}')
                if client:
                    break
                time.sleep(.05)
            if not client:
                raise RuntimeError('the recorded client did not attach')

            def caption(text):
                tm('set-option', '-g', '@demo_caption', text)
                tm('refresh-client', '-S', '-t', client)

            def keys(*names, pause=.35):
                for name in names:
                    tm('send-keys', '-K', '-c', client, name)
                    time.sleep(pause)

            def typed(text, pause=.12):
                for char in text:
                    tm('send-keys', '-K', '-c', client, '-l', char)
                    time.sleep(pause)

            key = '#[fg=#bd93f9,bold]'
            plain = '#[fg=#f8f8f2,nobold]'
            # The timeline. Pauses are long enough to read each step.
            time.sleep(1.5)
            caption(f'{plain}A workspace tree and AI-agent monitor for tmux · no daemon')
            time.sleep(2.5)
            caption(f'{key}prefix T{plain}  opens the sidebar')
            keys('C-b', 'T', pause=.1)
            time.sleep(2.5)
            caption(f'{key}j k{plain}  move through every session, window, and pane')
            keys('j', 'j', 'j', 'j', 'j', 'k', pause=.45)
            time.sleep(1)
            caption(f'{key}h l{plain}  fold and unfold')
            keys('h', pause=1.2)
            keys('l', pause=1.2)
            caption(f'{key}/{plain}  searches everything')
            keys('/', pause=.5)
            typed('notes')
            time.sleep(1.5)
            keys('Escape', pause=1)
            caption(f'{key}A{plain}  turns on agent mode · the footer counts every agent')
            keys('A', pause=.2)
            time.sleep(3)
            caption(f'{plain}Subagents appear under the agent that started them')
            hook(api, 'api', {'hook_event_name': 'SubagentStart', 'agent_id': 's1', 'agent_type': 'Explore'})
            time.sleep(.8)
            hook(api, 'api', {'hook_event_name': 'SubagentStart', 'agent_id': 's2', 'agent_type': 'Plan'})
            time.sleep(3)
            hook(web, 'web', {'hook_event_name': 'PermissionRequest', 'tool_name': 'Bash',
                              'tool_input': {'command': 'npm run e2e'}})
            time.sleep(.8)
            caption(f'#[fg=#f1fa8c,bold]◆{plain} an agent in another session needs your approval')
            time.sleep(3)
            caption(f'{key}n{plain}  jumps straight to it')
            keys('n', pause=.2)
            time.sleep(3)
            caption(f'{plain}One sidebar that follows you · {key}prefix T{plain} to close · no daemon')
            time.sleep(3.5)
            tm('detach-client', '-t', client)
            recorder.wait(timeout=20)
        finally:
            sp.run(['tmux', '-L', SOCKET, 'kill-server'], env=env, capture_output=True)

    sp.run(['agg', '--quiet', '--font-family', args.font_family, '--font-size', '15', '--line-height', '1.3',
            '--theme', args.theme, '--idle-time-limit', '2', '--fps-cap', '30', '--last-frame-duration', '3',
            str(cast), str(gif)], check=True)
    print(f'wrote {cast}\nwrote {gif}')
    # A still for the README link and for viewers that do not animate GIFs:
    # the moment the waiting agent appears, sidebar open with subagents.
    if shutil.which('ffmpeg'):
        png = output / 'canopy-demo.png'
        sp.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-ss', str(args.poster), '-i', str(gif),
                '-frames:v', '1', str(png)], check=True)
        print(f'wrote {png}')


if __name__ == '__main__':
    main()
