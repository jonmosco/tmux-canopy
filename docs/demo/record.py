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
    parser.add_argument('--poster', type=float, default=7.5, help='preview GIF time in seconds for the still')
    parser.add_argument('--demo', choices=('both', 'preview', 'walkthrough'), default='both')
    parser.add_argument('--smoke', action='store_true', help='run attached PTY actions and assertions without agg')
    args = parser.parse_args()
    if args.demo == 'both':
        extra = ['--smoke'] if args.smoke else []
        for demo in ('preview', 'walkthrough'):
            sp.run([sys.executable, __file__, '--demo', demo, '--output', args.output,
                    '--font-family', args.font_family, '--theme', args.theme,
                    '--poster', str(args.poster), *extra], check=True)
        return
    required = ('tmux', 'fzf', 'git', 'asciinema') if args.smoke else ('tmux', 'fzf', 'git', 'asciinema', 'agg')
    for tool in required:
        if not shutil.which(tool):
            sys.exit(f'{tool} is required')
    sleeper = shutil.which('gsleep' if sys.platform == 'darwin' else 'sleep')
    if not sleeper:
        sys.exit('gsleep is required on macOS (brew install coreutils)')
    editor_bin = shutil.which('nvim') or shutil.which('vim')
    if not editor_bin:
        sys.exit('nvim or vim is required for the editor scene')
    real_home = str(Path.home().resolve())
    output = Path('/tmp/canopy-demo-smoke' if args.smoke else args.output).resolve()
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
                     home / 'projects' / 'web' / 'src' / 'pages',
                     home / 'projects' / 'web' / 'src' / 'session',
                     home / 'projects' / 'payments' / 'src',
                     home / 'projects' / 'payments' / 'tests',
                     home / 'notes', bin_dir):
            path.mkdir(parents=True)
        login_ts = (
            'import { checkRateLimit } from "./limiter";\n'
            'import { issueToken, verifyPassword } from "./tokens";\n\n'
            'export interface LoginRequest {\n'
            '  email: string;\n'
            '  password: string;\n'
            '  ipAddress: string;\n'
            '}\n\n'
            'export async function login(req: LoginRequest) {\n'
            '  const allowed = await checkRateLimit(req.ipAddress, {\n'
            '    windowSeconds: 60,\n'
            '    maxAttempts: 5,\n'
            '  });\n'
            '  if (!allowed) {\n'
            '    return { status: 429, error: "Too many login attempts" };\n'
            '  }\n\n'
            '  const user = await verifyPassword(req.email, req.password);\n'
            '  if (!user) {\n'
            '    return { status: 401, error: "Invalid credentials" };\n'
            '  }\n\n'
            '  return { status: 200, token: await issueToken(user.id) };\n'
            '}\n'
        )
        fixtures = {
            home / 'acme-api' / 'src' / 'auth' / 'login.ts': login_ts,
            home / 'acme-api' / 'tests' / 'integration' / 'login.test.ts': 'describe("login", () => {});\n',
            home / 'acme-api' / 'tests' / 'integration' / 'session.test.ts': 'describe("session", () => {});\n',
            home / 'acme-api' / 'config' / 'routes.yml': 'health: /health\n',
            home / 'acme-web' / 'src' / 'pages' / 'settings.tsx': 'export function Settings() {}\n',
            home / 'acme-web' / 'src' / 'components' / 'Profile.tsx': 'export function Profile() {}\n',
            home / 'acme-web' / 'tests' / 'settings.test.tsx': 'describe("settings", () => {});\n',
            home / 'projects' / 'web' / 'src' / 'pages' / 'settings.tsx': 'export function Settings() {\n  return <main>Account settings</main>;\n}\n',
            home / 'projects' / 'web' / 'src' / 'session' / 'store.ts': 'export class SessionStore {\n  ttl = 900;\n  backend = "memory";\n}\n',
            home / 'projects' / 'payments' / 'src' / 'webhooks.py': 'def handle_stripe_event(payload):\n    return {"ok": True}\n',
            home / 'projects' / 'payments' / 'tests' / 'webhooks.py': 'def test_retry_backoff():\n    assert True\n',
        }
        for path, content in fixtures.items():
            path.write_text(content)
        repos = ((home / 'acme-api', 'main'),
                 (home / 'acme-web', 'feature/settings'),
                 (home / 'projects' / 'web', 'redis'),
                 (home / 'projects' / 'payments', 'retry'))
        for project, branch in repos:
            sp.run(['git', '-C', str(project), 'init', '-q', '-b', branch], check=True)
            sp.run(['git', '-C', str(project), '-c', 'user.name=Canopy Demo',
                    '-c', 'user.email=demo@example.com', 'add', '.'], check=True)
            sp.run(['git', '-C', str(project), '-c', 'user.name=Canopy Demo',
                    '-c', 'user.email=demo@example.com', 'commit', '-q', '-m', 'demo fixture'], check=True)
        if args.demo == 'preview':
            (home / 'projects' / 'web' / 'src' / 'session' / 'store.ts').write_text(
                'export interface CacheOptions {\n  url?: string;\n  ttlSeconds: number;\n  prefix: string;\n}\n\n'
                'export class SessionStore {\n  ttlSeconds = 3600;\n  prefix = "sess:";\n'
                '  async get(id: string) {\n    return `${this.prefix}${id}`;\n  }\n}\n')
            (home / 'projects' / 'web' / 'src' / 'pages' / 'settings.tsx').write_text(
                'import { SessionStore } from "../session/store";\n\n'
                'export function Settings() {\n  const store = new SessionStore();\n'
                '  return <main data-ttl={store.ttlSeconds}>Account settings</main>;\n}\n')
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
        for name in ('claude', 'codex', 'opencode', 'api-server'):
            shutil.copy(sleeper, bin_dir / name)

        def program(name, text, then):
            script = bin_dir / f'{name}.sh'
            # Agents draw their own UI; hide the terminal cursor for them.
            cursor = "printf '\\033[?25l'\n" if then.startswith(f'exec {bin_dir}') else ''
            script.write_text('#!/bin/bash\nprintf \'\\033[2J\\033[H\'\ncat <<\'DEMO\'\n' + text + '\nDEMO\n' + cursor + then + '\n')
            script.chmod(0o755)
            return str(script)

        editor_script = bin_dir / 'editor.sh'
        editor_script.write_text(
            '#!/bin/bash\n'
            f'exec "{editor_bin}" --clean -n "+syntax on" '
            '"+set number signcolumn=no laststatus=2 noshowmode cursorline background=dark" '
            '"+call cursor(10, 17)" src/auth/login.ts\n'
        )
        editor_script.chmod(0o755)

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
        cache_agent = program('cache-agent', '''
 \033[36m▣\033[0m \033[1mOpenCode\033[0m \033[2m(demo)\033[0m

 \033[1m›\033[0m persist user sessions across web workers

 \033[36m⏺\033[0m Inspecting src/session/store.ts
 \033[36m⏺\033[0m Comparing cache backends…''', f'exec {bin_dir}/opencode 3600')
        billing_agent = program('billing-agent', '''
 \033[1mCodex\033[0m \033[2m(demo)\033[0m

 \033[1m›\033[0m add exponential retry backoff for Stripe webhooks

 \033[32m•\033[0m Updated src/webhooks.py
 \033[32m•\033[0m Prepared retry test cases in tests/webhooks.py''', f'exec {bin_dir}/codex 3600')
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

        shell_rc = Path(directory) / 'demo.bashrc'
        shell_rc.write_text('PS1=\'\\[\\033[32m\\]\\w\\[\\033[0m\\] $ \'\n')

        alerts_mode = 'off' if args.demo == 'preview' else 'tmux'
        sidebar_width = 42 if args.demo == 'preview' else 40
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
set -g status-right-length 76
set -g status-right '#{{@demo_caption}} '
set -g window-status-format ' #I:#W '
set -g window-status-current-format '#[fg=#282a36,bg=#50fa7b,bold] #I:#W #[default]'
set -g pane-border-style 'fg=#44475a'
set -g pane-active-border-style 'fg=#6272a4'
set -g @tmux-canopy-icon-theme nerdfont
set -g @tmux-canopy-agents on
set -g @tmux-canopy-width {sidebar_width}
set -g @tmux-canopy-preview-height 30%
set -g @tmux-canopy-animate on
set -g @tmux-canopy-alerts {alerts_mode}
set -g @tmux-canopy-appearance quiet
set -g @tmux-canopy-git-context branch
set -g @demo_caption ''
run-shell '{ROOT / "tmux-canopy.tmux"}'
''')

        key = '#[fg=#bd93f9,bold]'
        plain = '#[fg=#f8f8f2,nobold]'

        try:
            if args.demo == 'preview':
                editor = tm('-f', str(config), 'new-session', '-d', '-s', 'acme-api', '-x', str(COLS), '-y', str(ROWS),
                            '-n', 'editor', '-c', str(home / 'acme-api'),
                            '-P', '-F', '#{pane_id}', str(editor_script))
                api = tm('new-window', '-d', '-t', 'acme-api:', '-n', 'api',
                         '-c', str(home / 'acme-api' / 'src' / 'auth'),
                         '-P', '-F', '#{pane_id}', api_agent)
                web = tm('new-session', '-d', '-s', 'acme-web', '-n', 'cache',
                         '-c', str(home / 'projects' / 'web'),
                         '-P', '-F', '#{pane_id}', cache_agent)
                billing = tm('new-session', '-d', '-s', 'billing', '-n', 'webhooks',
                             '-c', str(home / 'projects' / 'payments'),
                             '-P', '-F', '#{pane_id}', billing_agent)
                tm('select-window', '-t', 'acme-api:0')
                tm('select-pane', '-t', editor)
                tm('set-option', '-g', '@demo_caption', f'{key}prefix T{plain}  open Canopy beside Neovim')
                for _ in range(60):
                    if tm('display-message', '-p', '-t', editor, '#{pane_current_command}') in ('nvim', 'vim') and \
                       tm('display-message', '-p', '-t', api, '#{pane_current_command}') == 'claude' and \
                       tm('display-message', '-p', '-t', web, '#{pane_current_command}') == 'opencode' and \
                       tm('display-message', '-p', '-t', billing, '#{pane_current_command}') == 'codex':
                        break
                    time.sleep(.05)
                base = env | {'TMUX': tm('display-message', '-p', '-t', api, '#{socket_path},#{pid},0')}

                def hook_claude(pane, session, payload):
                    sp.run([str(ROOT / 'scripts' / 'agent-hook'), 'claude'], env=base | {'TMUX_PANE': pane},
                           input=json.dumps({'session_id': session} | payload), capture_output=True, text=True,
                           timeout=10, check=True)

                def hook_opencode(pane, payload):
                    sp.run([str(ROOT / 'scripts' / 'agent-hook'), 'opencode'], env=base | {'TMUX_PANE': pane},
                           input=json.dumps(payload), capture_output=True, text=True,
                           timeout=10, check=True)

                def hook_codex(pane, session, payload):
                    sp.run([str(ROOT / 'scripts' / 'codex-hook')], env=base | {'TMUX_PANE': pane},
                           input=json.dumps({'session_id': session} | payload), capture_output=True, text=True,
                           timeout=10, check=True)

                hook_claude(api, 'api', {'hook_event_name': 'SessionStart'})
                hook_claude(api, 'api', {'hook_event_name': 'UserPromptSubmit'})
                hook_opencode(web, {'type': 'session.created',
                                    'properties': {'sessionID': 'web',
                                                   'info': {'id': 'web', 'directory': str(home / 'projects' / 'web')}}})
                hook_opencode(web, {'type': 'session.status',
                                    'properties': {'sessionID': 'web', 'status': {'type': 'busy'}}})
                hook_codex(billing, 'billing', {'hook_event_name': 'SessionStart'})
                hook_codex(billing, 'billing', {'hook_event_name': 'UserPromptSubmit'})
                time.sleep(.6)
            else:
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
                base = env | {'TMUX': tm('display-message', '-p', '-t', api, '#{socket_path},#{pid},0')}

                def hook_claude(pane, session, payload):
                    sp.run([str(ROOT / 'scripts' / 'agent-hook'), 'claude'], env=base | {'TMUX_PANE': pane},
                           input=json.dumps({'session_id': session} | payload), capture_output=True, text=True,
                           timeout=10, check=True)

                for pane, session in ((api, 'api'), (web, 'web')):
                    hook_claude(pane, session, {'hook_event_name': 'SessionStart'})
                    hook_claude(pane, session, {'hook_event_name': 'UserPromptSubmit'})

            record_socket = SOCKET
            record_target = 'acme-api'
            control = tm

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
            client = control_client

            def keys(*names, pause=.35):
                for name in names:
                    control('send-keys', '-K', '-c', control_client, name)
                    time.sleep(pause)

            def typed(text, pause=.05):
                for char in text:
                    control('send-keys', '-K', '-c', control_client, '-l', char)
                    time.sleep(pause)

            def caption(text):
                tm('set-option', '-g', '@demo_caption', text)
                tm('refresh-client', '-S', '-t', client)

            def find_sidebar():
                for line in tm('list-panes', '-a', '-F', '#{pane_id}|#{@tmux_canopy}').splitlines():
                    pane_id, flag = (line.split('|') + [''])[:2]
                    if flag == '1':
                        return pane_id
                return ''

            if args.demo == 'preview':
                time.sleep(.9)
                keys('C-b', 'T', pause=.15)
                sidebar = ''
                for _ in range(60):
                    sidebar = find_sidebar()
                    if sidebar:
                        break
                    time.sleep(.05)
                if not sidebar:
                    raise RuntimeError('sidebar did not open')
                time.sleep(1.3)

                caption(f'{plain}3 agents + subagents working across sessions')
                hook_claude(api, 'api', {'hook_event_name': 'SubagentStart', 'agent_id': 's1', 'agent_type': 'Explore'})
                time.sleep(.35)
                hook_claude(api, 'api', {'hook_event_name': 'SubagentStart', 'agent_id': 's2', 'agent_type': 'Plan'})
                time.sleep(1.6)
                if 'Explore' not in tm('capture-pane', '-p', '-t', sidebar):
                    raise RuntimeError('subagents did not render in sidebar')

                web_tty = tm('display-message', '-p', '-t', web, '#{pane_tty}')
                with open(web_tty, 'wb', buffering=0) as pane:
                    pane.write(b'\r\n\r\n ? Use Redis or memory cache?\r\n')
                hook_opencode(web, {'type': 'question.asked',
                                    'properties': {'sessionID': 'web',
                                                   'questions': [{'question': 'Use Redis or memory cache?'}]}})
                time.sleep(.9)

                caption(f'{key}i{plain}  inspect question & git diff without leaving Neovim')
                keys('j', 'j', 'j', pause=.22)
                keys('i', pause=.25)
                time.sleep(2.4)
                inspector_view = tm('capture-pane', '-p', '-t', sidebar)
                if 'Agent inspector' not in inspector_view or 'Use Redis or memory cache?' not in inspector_view or '(+' not in inspector_view:
                    raise RuntimeError(f'inspector label/question/diff did not appear:\n{inspector_view}')

                caption(f'{key}>{plain}  reply inline without switching sessions')
                keys('>', pause=.25)
                typed('Use Redis for shared sessions', pause=.045)
                time.sleep(.45)
                keys('Enter', pause=.2)
                with open(web_tty, 'wb', buffering=0) as pane:
                    pane.write(b' \x1b[1m\xe2\x80\xba\x1b[0m Use Redis for shared sessions\r\n'
                               b' \x1b[36m\xe2\x8f\xba\x1b[0m Wiring Redis session store\xe2\x80\xa6\r\n')
                hook_opencode(web, {'type': 'session.next.tool.called',
                                    'properties': {'sessionID': 'web', 'tool': 'edit'}})
                tm('send-keys', '-t', sidebar, 'C-r')
                time.sleep(2.1)
                if tm('display-message', '-p', '-t', client, '#{session_name}:#{window_name}') != 'acme-api:editor':
                    raise RuntimeError('inline reply unexpectedly switched away from acme-api:editor')

                keys('p', pause=.25)
                billing_tty = tm('display-message', '-p', '-t', billing, '#{pane_tty}')
                with open(billing_tty, 'wb', buffering=0) as pane:
                    pane.write(b'\r\n\r\n Run pytest tests/webhooks.py? [y/N]\r\n')
                hook_codex(billing, 'billing', {'hook_event_name': 'PermissionRequest', 'tool_name': 'Bash',
                                                'tool_input': {'command': 'pytest tests/webhooks.py'}})
                time.sleep(1.3)

                caption(f'{key}n{plain}  jump straight to the next agent needing you')
                keys('n', pause=.2)
                time.sleep(2.2)
                if tm('display-message', '-p', '-t', client, '#{session_name}') != 'billing':
                    raise RuntimeError('n did not jump to waiting billing session')
            else:
                def permission():
                    tty = tm('display-message', '-p', '-t', web, '#{pane_tty}')
                    with open(tty, 'wb', buffering=0) as pane:
                        pane.write(b'\r\n\r\n Run make test? [y/N]\r\n')
                    hook_claude(web, 'web', {'hook_event_name': 'PermissionRequest', 'tool_name': 'Bash',
                                             'tool_input': {'command': 'make test'}})

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
                hook_claude(api, 'api', {'hook_event_name': 'SubagentStart', 'agent_id': 's1', 'agent_type': 'Explore'})
                time.sleep(.6)
                hook_claude(api, 'api', {'hook_event_name': 'SubagentStart', 'agent_id': 's2', 'agent_type': 'Plan'})
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
            trimmed = ''.join([header, *events[:teardown]])
            for forbidden in (str(Path(directory).resolve()), str(directory), real_home, str(ROOT)):
                if forbidden and forbidden in trimmed:
                    raise RuntimeError(f'private path leaked into recording: {forbidden}')
            cast.write_text(trimmed)
        finally:
            for socket in (SOCKET, STAGE_SOCKET):
                sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)

    if args.smoke:
        print(f'smoke ok ({args.demo})')
        return
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
