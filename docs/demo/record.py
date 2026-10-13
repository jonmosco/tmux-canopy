#!/usr/bin/env python3
"""Record the README demo and focused feature walkthrough from real tmux clients.

The preview starts at a blank shell and visibly builds its workspace. Both
recordings use private tmux servers, fictional projects, and real scripted
agent hook events, then render asciinema captures with agg. No user's sessions,
config, or projects are captured.

    python3 docs/demo/record.py --output /tmp/canopy-demo-review
    python3 docs/demo/record.py --demo preview  # only the README demo

Requires tmux, fzf, git, Python 3, asciinema 3, agg, and on macOS coreutils
(gsleep). ffmpeg exports the preview still. Review the GIFs at README size and
check the .cast files for private data before copying assets into docs/assets.
The .cast files are ignored by git and can be played with `asciinema play`.
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
STAGE_SOCKET = f'{SOCKET}-stage'
COLS, ROWS = 120, 32


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(ROOT / 'docs' / 'assets'), help='directory for the .cast and .gif')
    parser.add_argument('--font-family', default='Hack Nerd Font Mono,JetBrains Mono,Menlo')
    parser.add_argument('--theme', default='dracula')
    parser.add_argument('--poster', type=float, default=41, help='preview GIF time in seconds for the still')
    parser.add_argument('--demo', choices=('both', 'preview', 'walkthrough'), default='both')
    args = parser.parse_args()
    if args.demo == 'both':
        for demo in ('preview', 'walkthrough'):
            sp.run([sys.executable, __file__, '--demo', demo, '--output', args.output,
                    '--font-family', args.font_family, '--theme', args.theme,
                    '--poster', str(args.poster)], check=True)
        return
    for tool in ('tmux', 'fzf', 'git', 'asciinema', 'agg'):
        if not shutil.which(tool):
            sys.exit(f'{tool} is required')
    sleeper = shutil.which('gsleep' if sys.platform == 'darwin' else 'sleep')
    if not sleeper:
        sys.exit('gsleep is required on macOS (brew install coreutils)')
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    name = 'canopy-demo' if args.demo == 'preview' else 'canopy-walkthrough'
    cast, gif = output / f'{name}.cast', output / f'{name}.gif'

    with tempfile.TemporaryDirectory(prefix='canopy-demo-') as directory:
        home = Path(directory).resolve() / 'home'
        bin_dir = Path(directory) / 'bin'
        for path in (home / 'acme-api' / 'src' / 'auth',
                     home / 'acme-api' / 'tests' / 'integration',
                     home / 'acme-api' / 'config',
                     home / 'acme-web' / 'src' / 'pages',
                     home / 'acme-web' / 'src' / 'components',
                     home / 'acme-web' / 'tests',
                     home / 'notes', bin_dir):
            path.mkdir(parents=True)
        fixtures = {
            home / 'acme-api' / 'src' / 'auth' / 'login.ts': 'export function login() {}\\n',
            home / 'acme-api' / 'tests' / 'integration' / 'login.test.ts': 'describe(\"login\", () => {});\\n',
            home / 'acme-api' / 'tests' / 'integration' / 'session.test.ts': 'describe(\"session\", () => {});\\n',
            home / 'acme-api' / 'config' / 'routes.yml': 'health: /health\\n',
            home / 'acme-web' / 'src' / 'pages' / 'settings.tsx': 'export function Settings() {}\\n',
            home / 'acme-web' / 'src' / 'components' / 'Profile.tsx': 'export function Profile() {}\\n',
            home / 'acme-web' / 'tests' / 'settings.test.tsx': 'describe(\"settings\", () => {});\\n',
        }
        for path, content in fixtures.items():
            path.write_text(content)
        for project, branch in ((home / 'acme-api', 'main'), (home / 'acme-web', 'feature/settings')):
            sp.run(['git', '-C', str(project), 'init', '-q', '-b', branch], check=True)
            sp.run(['git', '-C', str(project), '-c', 'user.name=Canopy Demo',
                    '-c', 'user.email=demo@example.com', 'add', '.'], check=True)
            sp.run(['git', '-C', str(project), '-c', 'user.name=Canopy Demo',
                    '-c', 'user.email=demo@example.com', 'commit', '-q', '-m', 'demo fixture'], check=True)
        env = {'PATH': os.environ['PATH'], 'HOME': str(home), 'TERM': 'xterm-256color',
               'LANG': os.environ.get('LANG', 'en_US.UTF-8'), 'SHELL': '/bin/bash',
               'BASH_SILENCE_DEPRECATION_WARNING': '1'}

        def run_tm(socket, *argv):
            result = sp.run(['tmux', '-L', socket, *argv], env=env, capture_output=True, text=True, timeout=15)
            if result.returncode:
                raise RuntimeError((argv, result.stderr))
            return result.stdout.strip()

        def tm(*argv):
            return run_tm(SOCKET, *argv)

        def stage(*argv):
            return run_tm(STAGE_SOCKET, *argv)

        # Agents are detected by process name, so each fake agent is a renamed
        # sleep binary. A wrapper prints a fictional transcript, then execs it.
        for name in ('claude', 'codex', 'api-server'):
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
        tests = program('tests', '''\033[32m~/acme-api/tests/integration\033[0m $ make test

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

        test_output = bin_dir / 'test-output.sh'
        test_output.write_text('''#!/bin/bash
cat <<'DEMO'

 \033[32mPASS\033[0m  src/auth/login.test.ts
 \033[32mPASS\033[0m  src/auth/session.test.ts
 \033[32mPASS\033[0m  src/routes/health.test.ts

 Tests:  \033[32m42 passed\033[0m, 42 total
DEMO
''')
        test_output.chmod(0o755)
        shell_rc = Path(directory) / 'demo.bashrc'
        shell_rc.write_text(f'''PS1='\\[\\033[32m\\]\\w\\[\\033[0m\\] $ '
claude() {{
    if [[ $PWD == "$HOME/acme-web"* ]]; then
        exec {web_agent}
    else
        exec {api_agent}
    fi
}}
make() {{
    if [[ $1 == test ]]; then
        {test_output}
    elif [[ $1 == dev ]]; then
        printf '\\n \\033[32mready\\033[0m  API server at http://localhost:4000\\n'
        printf '        watching src/ and config/\\n'
        exec {bin_dir}/api-server 3600
    else
        printf 'demo supports make dev and make test only\\n' >&2
        return 2
    fi
}}
''')

        config = Path(directory) / 'tmux.conf'
        config.write_text(f'''
set -g default-terminal tmux-256color
set -g default-shell /bin/bash
set -g default-command 'exec /bin/bash --noprofile --rcfile "{shell_rc}" -i'
set -g escape-time 10
set -g mouse on
set -g display-time 2200
set -g status on
set -g status-interval 0
set -g status-style 'bg=#21222c,fg=#f8f8f2'
set -g message-style 'bg=#44475a,fg=#f8f8f2'
set -g status-left-length 24
set -g status-left '#[fg=#8be9fd,bold] #S #[default]'
set -g status-right-length 72
set -g status-right '#{{@demo_caption}} '
set -g window-status-format ' #I:#W '
set -g window-status-current-format '#[fg=#282a36,bg=#50fa7b,bold] #I:#W #[default]'
set -g pane-border-style 'fg=#44475a'
set -g pane-active-border-style 'fg=#6272a4'
set -g @tmux-canopy-icon-theme nerdfont
set -g @tmux-canopy-agents on
set -g @tmux-canopy-width 40
set -g @tmux-canopy-animate on
set -g @tmux-canopy-alerts tmux
set -g @tmux-canopy-appearance quiet
set -g @tmux-canopy-git-context branch
set -g @demo_caption ''
run-shell '{ROOT / "tmux-canopy.tmux"}'
''')

        try:
            if args.demo == 'walkthrough':
                api = tm('-f', str(config), 'new-session', '-d', '-s', 'acme-api', '-x', str(COLS), '-y', str(ROWS),
                         '-n', 'server', '-c', str(home / 'acme-api' / 'src' / 'auth'),
                         '-P', '-F', '#{pane_id}', api_agent)
                tm('split-window', '-d', '-v', '-l', '50%', '-t', api,
                   '-c', str(home / 'acme-api' / 'tests' / 'integration'), tests)
                tm('new-window', '-d', '-t', 'acme-api:', '-n', 'release', '-c', str(home / 'acme-api'), codex)
                web = tm('new-session', '-d', '-s', 'acme-web', '-n', 'ui',
                         '-c', str(home / 'acme-web' / 'src' / 'pages'),
                         '-P', '-F', '#{pane_id}', web_agent)
                tm('split-window', '-d', '-h', '-l', '50%', '-t', web, '-c', str(home / 'acme-web'), git)
                tm('new-session', '-d', '-s', 'notes', '-n', 'today', '-c', str(home / 'notes'), notes)
                tm('select-pane', '-t', api)
                record_socket = SOCKET
                record_target = 'acme-api'
                control = tm
            else:
                stage_config = Path(directory) / 'stage.conf'
                stage_config.write_text('set -g status off\nset -g prefix None\nset -g escape-time 0\n')
                stage_rc = Path(directory) / 'stage.bashrc'
                tmux = shutil.which('tmux')
                stage_rc.write_text(f'''PS1='\\[\\033[32m\\]\\w\\[\\033[0m\\] $ '
cd "$HOME/acme-api"
tmux() {{
    TMUX= command {tmux} -L {SOCKET} -f {config} "$@"
}}
''')
                stage('-f', str(stage_config), 'new-session', '-d', '-s', 'recording',
                      '-x', str(COLS), '-y', str(ROWS),
                      f'exec /bin/bash --noprofile --rcfile "{stage_rc}" -i')
                record_socket = STAGE_SOCKET
                record_target = 'recording'
                control = stage

            recorder = sp.Popen(['asciinema', 'rec', '--headless', '--overwrite', '--quiet',
                                 '--window-size', f'{COLS}x{ROWS}', '--idle-time-limit', '2',
                                 '--title', 'tmux-canopy', '-c',
                                 f'tmux -L {record_socket} attach -t {record_target}', str(cast)],
                                env=env)
            control_client = ''
            for _ in range(100):
                control_client = control('list-clients', '-F', '#{client_name}')
                if control_client:
                    break
                time.sleep(.05)
            if not control_client:
                raise RuntimeError('the recorded client did not attach')

            def keys(*names, pause=.35):
                for name in names:
                    control('send-keys', '-K', '-c', control_client, name)
                    time.sleep(pause)

            def typed(text, pause=.08):
                for char in text:
                    control('send-keys', '-K', '-c', control_client, '-l', char)
                    time.sleep(pause)

            key = '#[fg=#bd93f9,bold]'
            plain = '#[fg=#f8f8f2,nobold]'

            if args.demo == 'preview':
                time.sleep(1)
                typed('tmux new -s acme-api', pause=.07)
                keys('Enter', pause=.2)
                client = ''
                for _ in range(100):
                    result = sp.run(['tmux', '-L', SOCKET, 'list-clients', '-F', '#{client_name}'],
                                    env=env, capture_output=True, text=True, timeout=15)
                    client = result.stdout.strip() if result.returncode == 0 else ''
                    if client:
                        break
                    time.sleep(.05)
                if not client:
                    raise RuntimeError('the demo tmux client did not attach')
                time.sleep(1.2)

                def caption(text):
                    tm('set-option', '-g', '@demo_caption', text)
                    tm('refresh-client', '-S', '-t', client)

                caption(f'{key}prefix ,{plain}  rename the first window')
                keys('C-b', ',', pause=.2)
                keys('C-u', pause=.1)
                typed('server')
                keys('Enter', pause=.2)
                typed('make dev', pause=.07)
                keys('Enter', pause=.2)
                time.sleep(1.3)
                caption(f'{key}prefix c{plain}  create another window')
                keys('C-b', 'c', pause=.2)
                keys('C-b', ',', pause=.2)
                keys('C-u', pause=.1)
                typed('tests')
                keys('Enter', pause=.2)
                typed('cd tests/integration && ls', pause=.045)
                keys('Enter', pause=.2)
                time.sleep(1.2)
                caption(f'{key}prefix "{plain}  split the server window')
                keys('C-b', '0', pause=.2)
                keys('C-b', '"', pause=.2)
                typed('cd src/auth && claude', pause=.06)
                keys('Enter', pause=.2)
                time.sleep(1.5)
                api = next(line for line in tm('list-panes', '-t', 'acme-api:server',
                                               '-F', '#{?pane_active,#{pane_id},}').splitlines() if line)
                caption(f'{plain}Add a second project as another tmux session')
                keys('C-b', ':', pause=.2)
                typed('new-session -d -s acme-web -n ui -c ~/acme-web/src/pages', pause=.035)
                keys('Enter', pause=.2)
                time.sleep(1)
                web = tm('list-panes', '-t', 'acme-web:ui', '-F', '#{pane_id}')
                tm('send-keys', '-t', web, 'claude', 'Enter')
                time.sleep(1)
            else:
                client = tm('list-clients', '-F', '#{client_name}')

                def caption(text):
                    tm('set-option', '-g', '@demo_caption', text)
                    tm('refresh-client', '-S', '-t', client)

            base = env | {'TMUX': tm('display-message', '-p', '-t', api, '#{socket_path},#{pid},0')}

            def hook(pane, session, payload):
                sp.run([str(ROOT / 'scripts' / 'agent-hook'), 'claude'], env=base | {'TMUX_PANE': pane},
                       input=json.dumps({'session_id': session} | payload), capture_output=True, text=True,
                       timeout=10, check=True)

            for pane, session in ((api, 'api'), (web, 'web')):
                hook(pane, session, {'hook_event_name': 'SessionStart'})
                hook(pane, session, {'hook_event_name': 'UserPromptSubmit'})

            def permission():
                tty = tm('display-message', '-p', '-t', web, '#{pane_tty}')
                with open(tty, 'wb', buffering=0) as pane:
                    pane.write(b'\r\n\r\n Run make test? [y/N]\r\n')
                hook(web, 'web', {'hook_event_name': 'PermissionRequest', 'tool_name': 'Bash',
                                  'tool_input': {'command': 'make test'}})

            if args.demo == 'preview':
                caption(f'{key}prefix T{plain}  open Canopy')
                keys('C-b', 'T', pause=.15)
                time.sleep(2.2)
                caption(f'{key}A{plain}  turn agent monitoring off')
                keys('A', pause=.2)
                time.sleep(2.6)
                caption(f'{key}A{plain}  turn agent monitoring back on')
                keys('A', pause=.2)
                time.sleep(2.6)
                caption(f'{key}?{plain}  open the built-in help')
                keys('?', pause=.2)
                time.sleep(2.5)
                keys('q', pause=.2)
                time.sleep(1.2)
                caption(f'{key}j k{plain}  browse · {key}h l{plain}  fold branches')
                keys('j', 'j', 'k', pause=.3)
                time.sleep(1.3)
                caption(f'{plain}Agents and subagents stay visible across projects')
                hook(api, 'api', {'hook_event_name': 'SubagentStart', 'agent_id': 's1', 'agent_type': 'Explore'})
                time.sleep(.4)
                hook(api, 'api', {'hook_event_name': 'SubagentStart', 'agent_id': 's2', 'agent_type': 'Plan'})
                time.sleep(1.5)
                caption('')
                permission()
                time.sleep(2.4)
                caption(f'{key}n{plain}  jump straight to the waiting agent')
                keys('n', pause=.2)
                time.sleep(2.5)
                caption(f'{plain}One sidebar follows every tmux session · no daemon')
                time.sleep(2)
            else:
                caption(f'{plain}Navigate sessions, windows, and panes')
                keys('C-b', 'T', pause=.15)
                time.sleep(2)
                caption(f'{key}j k{plain}  browse · {key}h l{plain}  fold branches')
                keys('j', 'j', 'j', 'j', pause=.35)
                keys('h', pause=.6)
                keys('l', pause=.6)
                time.sleep(1.5)
                caption(f'{key}/{plain}  find a pane by name')
                keys('/', pause=.3)
                typed('notes')
                time.sleep(2)
                keys('Escape', pause=.3)
                keys('C-o', pause=.2)
                caption(f'{key}p{plain}  preview without leaving the tree')
                keys('p', pause=.3)
                time.sleep(2.5)
                keys('p', pause=.3)
                caption(f'{plain}Subagents appear beneath their parent')
                hook(api, 'api', {'hook_event_name': 'SubagentStart', 'agent_id': 's1', 'agent_type': 'Explore'})
                time.sleep(.6)
                hook(api, 'api', {'hook_event_name': 'SubagentStart', 'agent_id': 's2', 'agent_type': 'Plan'})
                time.sleep(2.5)
                caption(f'{key}4{plain}  only show work with agents')
                keys('4', pause=.3)
                time.sleep(2)
                caption('')
                permission()
                time.sleep(2.4)
                caption(f'{key}n{plain}  jump to the blocker')
                keys('n', pause=.2)
                time.sleep(2.5)
                caption(f'{plain}Need more space? Open Canopy as a popup')
                keys('C-b', 'T', pause=.15)
                tm('set-option', '-g', '@tmux-canopy-mode', 'popup')
                time.sleep(.7)
                keys('C-b', 'T', pause=.15)
                time.sleep(3)
                caption(f'{key}q / Esc{plain}  close the popup without switching panes')
                time.sleep(2)
            control('detach-client', '-t', control_client)
            recorder.wait(timeout=20)
            # tmux clears the screen on detach. Keep the last real frame so the
            # GIF loops from the product, not a black "detached" terminal.
            with cast.open() as recording:
                header = recording.readline()
                events = recording.readlines()
            if len(events) < 4 or 'detached (from session' not in events[-2]:
                raise RuntimeError('unexpected asciinema ending; inspect the cast before rendering')
            teardown = next((i for i in range(max(0, len(events) - 10), len(events))
                             if f'\\u001b[1;{ROWS}r' in events[i] and '\\u001b[?1l' in events[i]), None)
            if teardown is None:
                raise RuntimeError('tmux screen reset not found; inspect the cast before rendering')
            with cast.open('w') as recording:
                recording.write(header)
                recording.writelines(events[:teardown])
        finally:
            for socket in (SOCKET, STAGE_SOCKET):
                sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)

    sp.run(['agg', '--quiet', '--font-family', args.font_family, '--font-size', '20', '--line-height', '1.25',
            '--theme', args.theme, '--idle-time-limit', '2', '--fps-cap', '30', '--last-frame-duration', '2',
            str(cast), str(gif)], check=True)
    print(f'wrote {cast}\nwrote {gif}')
    # A still for the README link and for viewers that do not animate GIFs:
    # project paths and branches visible, sidebar open with subagents.
    if args.demo == 'preview' and shutil.which('ffmpeg'):
        png = output / 'canopy-demo.png'
        sp.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-ss', str(args.poster), '-i', str(gif),
                '-frames:v', '1', str(png)], check=True)
        print(f'wrote {png}')


if __name__ == '__main__':
    main()
