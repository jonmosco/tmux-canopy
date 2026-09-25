#!/usr/bin/env python3
"""Capture an isolated Canopy fixture and render a README GIF (Linux + Pillow)."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import pty
import re
import shlex
import shutil
import struct
import subprocess as sp
import tempfile
import termios
import threading
import time
from PIL import Image, ImageDraw, ImageFont

COLS, ROWS = 96, 26
CW, CH, PAD, TOP = 11, 23, 24, 24
# ANSI palettes from the themes' official Alacritty ports; see README.md.
THEMES = {
    'canopy': {
        'background': '#161b22', 'foreground': '#d5dde5', 'dim': '#89939f',
        'ansi': '#202630 #ed8796 #a6da95 #eed49f #8aadf4 #c6a0f6 #8bd5ca #cad3f5 #6e7888 #ed8796 #a6da95 #eed49f #8aadf4 #c6a0f6 #8bd5ca #f4f5f8'.split(),
    },
    'catppuccin-mocha': {
        'background': '#1e1e2e', 'foreground': '#cdd6f4', 'dim': '#7f849c',
        'ansi': '#45475a #f38ba8 #a6e3a1 #f9e2af #89b4fa #f5c2e7 #94e2d5 #bac2de #585b70 #f38ba8 #a6e3a1 #f9e2af #89b4fa #f5c2e7 #94e2d5 #a6adc8'.split(),
    },
    'tokyo-night': {
        'background': '#1a1b26', 'foreground': '#c0caf5', 'dim': '#787c99',
        'ansi': '#15161e #f7768e #9ece6a #e0af68 #7aa2f7 #bb9af7 #7dcfff #a9b1d6 #414868 #ff899d #9fe044 #faba4a #8db0ff #c7a9ff #a4daff #c0caf5'.split(),
    },
    'dracula': {
        'background': '#282a36', 'foreground': '#f8f8f2', 'dim': '#9699b2',
        'ansi': '#21222c #ff5555 #50fa7b #f1fa8c #bd93f9 #ff79c6 #8be9fd #f8f8f2 #6272a4 #ff6e6e #69ff94 #ffffa5 #d6acff #ff92df #a4ffff #ffffff'.split(),
    },
}
ESC = re.compile(r'\x1b\[([0-9;:]*)m')


def color(index, theme):
    if index < 16:
        return theme['ansi'][index]
    if index >= 232:
        n = 8 + (index - 232) * 10
        return (n, n, n)
    index -= 16
    levels = [0, 95, 135, 175, 215, 255]
    return tuple(levels[n] for n in (index // 36, index // 6 % 6, index % 6))


def ansi_line(draw, text, x, y, font, width, theme):
    FG, BG, ANSI = theme['foreground'], theme['background'], theme['ansi']
    fg, bg, dim, reverse = FG, BG, False, False
    column, pos = 0, 0
    for match in list(ESC.finditer(text)) + [None]:
        end = match.start() if match else len(text)
        for char in text[pos:end]:
            if column >= width:
                break
            ink, paper = (bg, fg) if reverse else (fg, bg)
            if dim:
                ink = theme['dim']
            left = x + column * CW
            draw.rectangle((left, y, left + CW - 1, y + CH - 1), fill=paper)
            draw.text((left, y - 1), char, font=font, fill=ink)
            column += 1
        if not match:
            break
        codes = [int(v or 0) for v in match.group(1).replace(':', ';').split(';')]
        i = 0
        while i < len(codes):
            c = codes[i]
            if c == 0:
                fg, bg, dim, reverse = FG, BG, False, False
            elif c == 2:
                dim = True
            elif c == 22:
                dim = False
            elif c == 7:
                reverse = True
            elif c == 27:
                reverse = False
            elif 30 <= c <= 37:
                fg = ANSI[c - 30]
            elif 90 <= c <= 97:
                fg = ANSI[c - 90 + 8]
            elif 40 <= c <= 47:
                bg = ANSI[c - 40]
            elif 100 <= c <= 107:
                bg = ANSI[c - 100 + 8]
            elif c == 39:
                fg = FG
            elif c == 49:
                bg = BG
            elif c in (38, 48) and i + 2 < len(codes):
                if codes[i + 1] == 5:
                    value = color(codes[i + 2], theme)
                    i += 2
                elif codes[i + 1] == 2 and i + 4 < len(codes):
                    value = tuple(codes[i + 2:i + 5])
                    i += 4
                else:
                    i += 1
                    continue
                if c == 38:
                    fg = value
                else:
                    bg = value
            i += 1
        pos = match.end()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'assets')
    parser.add_argument('--font', help='Monospace TrueType font with Unicode / Nerd Font symbols')
    parser.add_argument('--theme', choices=THEMES, default='dracula', help='Terminal palette (default: dracula)')
    args = parser.parse_args()
    theme = THEMES[args.theme]
    BG, FG, GREEN = theme['background'], theme['foreground'], theme['ansi'][2]
    border = tuple(int(int(BG[i:i + 2], 16) * .65 + int(theme['dim'][i:i + 2], 16) * .35) for i in (1, 3, 5))
    matte = tuple(int(int(BG[i:i + 2], 16) * .8) for i in (1, 3, 5))
    root = args.root.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    for tool in ('tmux', 'fzf', 'nvim', 'bash', 'python3'):
        if not shutil.which(tool):
            raise SystemExit(f'Missing dependency: {tool}')
    font_path = args.font or sp.check_output(
        ['fc-match', '-f', '%{file}', 'Hack Nerd Font Mono'], text=True)
    font = ImageFont.truetype(font_path, 18)
    small_font = ImageFont.truetype(font_path, 15)
    frames, durations, captures = [], [], []
    client_process = master = None
    with tempfile.TemporaryDirectory(prefix='canopy-demo-') as directory:
        temp = Path(directory)
        home = temp / 'home'
        home.mkdir()
        web, api, docs = [temp / 'workspace' / name for name in ('web', 'api', 'handbook')]
        for folder in (web, api, docs):
            folder.mkdir(parents=True)
        env = dict(PATH='/usr/local/bin:/usr/bin:/bin', HOME=str(home), USER='demo', LOGNAME='demo',
                   SHELL='/bin/bash', TERM='xterm-256color', LANG='C.UTF-8', LC_ALL='C.UTF-8',
                   XDG_CONFIG_HOME=str(home / '.config'), XDG_DATA_HOME=str(home / '.local/share'),
                   XDG_CACHE_HOME=str(home / '.cache'))
        socket = str(temp / 'tmux.sock')

        def tm(*commands):
            result = sp.run(['tmux', '-S', socket, *commands], env=env, capture_output=True, text=True, timeout=20)
            if result.returncode:
                raise RuntimeError(f'tmux {commands}: {result.stderr}')
            return result.stdout.rstrip('\n')

        def run(script, *commands):
            sp.run([str(root / 'scripts' / script), *commands], env=env, check=True, capture_output=True, timeout=20)

        def keys(*sequence):
            tm('send-keys', '-t', sidebar, *sequence)
            time.sleep(.24)

        def screen():
            panes = []
            for row in tm('list-panes', '-t', client, '-F', '#{pane_id}|#{pane_left}|#{pane_top}|#{pane_width}|#{pane_height}').splitlines():
                pane, left, top, width, height = row.split('|')
                text = tm('capture-pane', '-p', '-e', '-t', pane)
                # No redaction: fail if isolation leaks a host path or user identity.
                for forbidden in ('/home/', '/Users/', str(root), os.uname().nodename, os.environ.get('USER', '')):
                    if len(forbidden) > 2 and forbidden in text:
                        raise RuntimeError(f'Privacy check failed for {forbidden!r}')
                panes.append(dict(left=int(left), top=int(top), width=int(width), height=int(height), text=text))
            return panes

        def capture(chapter, title, detail, shortcut, duration=1500):
            panes = screen()
            captures.append(dict(chapter=chapter, title=title, panes=panes))
            w, h = COLS * CW + PAD * 2, TOP + ROWS * CH + 92
            image = Image.new('RGB', (w, h), matte)
            draw = ImageDraw.Draw(image)
            draw.rectangle((PAD - 1, TOP - 1, w - PAD, TOP + ROWS * CH), outline=border)
            draw.rectangle((PAD, TOP, w - PAD - 1, TOP + ROWS * CH - 1), fill=BG)
            for pane in panes:
                x, y = PAD + pane['left'] * CW, TOP + pane['top'] * CH
                if pane['left']:
                    draw.line((x - CW // 2 - 1, y, x - CW // 2 - 1, y + pane['height'] * CH - 1), fill=border)
                if pane['top']:
                    draw.line((x, y - CH // 2, x + pane['width'] * CW - 1, y - CH // 2), fill=border)
                for i, line in enumerate(pane['text'].splitlines()[:pane['height']]):
                    ansi_line(draw, line, x, y + i * CH, font, pane['width'], theme)
            y = TOP + ROWS * CH + 16
            draw.text((PAD, y), title, font=font, fill=GREEN)
            draw.text((PAD, y + 27), detail, font=small_font, fill=theme['dim'])
            if shortcut:
                label_width = int(font.getlength(shortcut)) + 24
                x = w - PAD - label_width
                draw.rounded_rectangle((x, y - 2, w - PAD, y + 26), radius=5, fill=theme['ansi'][0])
                draw.text((x + 12, y + 1), shortcut, font=font, fill=FG)
            for n in range(6):
                x = w - PAD - 88 + n * 16
                draw.ellipse((x, y + 42, x + 5, y + 47), fill=GREEN if n == chapter else border)
            frames.append(image)
            durations.append(duration)

        try:
            (web / 'app.py').write_text('''"""A tiny example application."""\n\nfrom dataclasses import dataclass\n\n\n@dataclass\nclass Project:\n    name: str\n    ready: bool = True\n\n\ndef greeting(project: Project) -> str:\n    return f"Welcome to {project.name}"\n\n\nproject = Project("Canopy demo")\nprint(greeting(project))\n''')
            (temp / 'editor.vim').write_text('''set number nowrap noswapfile nobackup nowritebackup\nset notermguicolors\nset laststatus=0 noruler noshowcmd noshowmode\nset shortmess+=I\nsyntax on\nhi Normal ctermfg=7 ctermbg=NONE\nhi LineNr ctermfg=8\nhi Comment ctermfg=8\nhi String ctermfg=2\nhi Statement ctermfg=4\nhi Type ctermfg=3\nhi PreProc ctermfg=4\nhi Constant ctermfg=3\n''')
            def fixture(name, lines):
                path = temp / f'{name}.sh'
                path.write_text("#!/bin/bash\nprintf '\\033[2J\\033[H'\ncat <<'DEMO'\n" + lines + "\nDEMO\nwhile IFS= read -r line; do :; done\n")
                return shlex.join(['/bin/bash', '--noprofile', '--norc', str(path)])
            tests = fixture('tests', '\n  $ pytest -q\n\n  ......................          [100%]\n  \033[32m22 passed in 0.38s\033[0m\n\n  $ ')
            guide = fixture('guide', '\n  HANDBOOK\n  ========\n\n  01  Getting started\n  02  Local development\n  03  Running tests\n  04  Release checklist\n\n  Everything you need, one pane away.')
            (api / 'server.py').write_text('import time\nprint("\\n  $ python3 server.py\\n\\n  Development server\\n  ------------------\\n\\n  Ready at http://localhost:8000\\n\\n  \\033[32mGET /health       200 OK\\n  GET /projects     200 OK\\n  GET /projects/1   200 OK\\033[0m\\n\\n  Waiting for requests...", flush=True)\ntime.sleep(300)\n')
            editor_cmd = shlex.join(['nvim', '--clean', '-n', '-u', str(temp / 'editor.vim'), 'app.py'])
            editor = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'studio', '-n', 'web', '-x', str(COLS), '-y', str(ROWS), '-c', str(web), '-P', '-F', '#{pane_id}', editor_cmd)
            env['TMUX'] = tm('display-message', '-p', '-t', editor, '#{socket_path},#{pid},0')
            env['TMUX_PANE'] = editor
            tm('set-option', '-g', 'default-shell', '/bin/bash')
            tm('set-option', '-g', 'status', 'off')
            tm('set-option', '-g', 'automatic-rename', 'off')
            tm('set-option', '-g', 'allow-rename', 'off')
            tm('set-option', '-g', '@tmux-canopy-icon-theme', 'nerdfont')
            tm('set-option', '-g', '@tmux-canopy-notifications', 'none')
            tm('set-option', '-g', '@tmux-canopy-preview', 'off')
            tm('set-option', '-g', '@tmux-canopy-density', 'normal')
            test_pane = tm('split-window', '-d', '-v', '-l', '9', '-t', editor, '-c', str(web), '-P', '-F', '#{pane_id}', tests)
            api_pane = tm('new-window', '-d', '-t', 'studio:', '-n', 'api', '-c', str(api), '-P', '-F', '#{pane_id}', 'python3 server.py')
            doc_pane = tm('new-session', '-d', '-s', 'docs', '-n', 'handbook', '-x', str(COLS), '-y', str(ROWS), '-c', str(docs), '-P', '-F', '#{pane_id}', guide)
            for pane, title in ((editor, 'editor'), (test_pane, 'tests'), (api_pane, 'server'), (doc_pane, 'guide')):
                tm('set-option', '-p', '-t', pane, 'allow-set-title', 'off')
                tm('select-pane', '-t', pane, '-T', title)
            tm('select-window', '-t', 'studio:web')
            tm('select-pane', '-t', editor)
            tm('set-buffer', '-b', 'test-command', 'pytest -q')
            tm('set-buffer', '-b', 'health-check', 'curl http://localhost:8000/health')
            tm('set-buffer', '-b', 'release-notes', 'Ready for the next release.')
            sp.run([str(root / 'tmux-canopy.tmux')], env=env, check=True, capture_output=True, timeout=20)
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', ROWS, COLS, 0, 0))
            client_process = sp.Popen(['tmux', '-S', socket, 'attach-session', '-t', 'studio'], stdin=slave, stdout=slave, stderr=slave, env=env, start_new_session=True)
            os.close(slave)
            def drain():
                try:
                    while os.read(master, 65536):
                        pass
                except OSError:
                    pass
            threading.Thread(target=drain, daemon=True).start()
            time.sleep(.4)
            client = tm('list-clients', '-F', '#{client_tty}')
            run('toggle', client, editor, '42', 'global', 'T', 'Tab', 'slot')
            sidebar = next(row.split('|')[0] for row in tm('list-panes', '-a', '-F', '#{pane_id}|#{@tmux_canopy}').splitlines() if row.endswith('|1'))
            time.sleep(1)
            tm('set-option', '-g', '@tmux_canopy_notifications', 'all')
            keys(*(['Up'] * 12 + ['Down'] * 5))
            overview = (0, 'Your workspace, in one tree', 'Sessions, windows, panes. Shared directories shown once.', '')
            capture(*overview, duration=2600)
            for _ in range(3):
                keys('j')
                capture(*overview, duration=180)
            capture(*overview, duration=800)
            # Exercise the real navigation wrapper, preserving the sidebar process.
            run('navigate', client, 'next', '42', 'global', 'slot')
            time.sleep(.6)
            capture(1, 'A sidebar that follows you', 'Switch windows and keep the same tree and selection.', 'prefix + n', 2300)
            run('navigate', client, 'previous', '42', 'global', 'slot')
            time.sleep(.5)
            capture(1, 'A sidebar that follows you', 'Back to your editor, with its layout intact.', 'prefix + p', 1400)
            tm('select-pane', '-t', sidebar)
            keys('/')
            search = (2, 'Find a pane in a few keystrokes', 'Search across your workspace without leaving the sidebar.', '/  api')
            capture(*search, duration=250)
            for letter in 'api':
                keys(letter)
                capture(*search, duration=180)
            capture(*search, duration=1900)
            keys('Escape')
            # Real notification providers on fictional background panes only.
            for pane, provider in ((api_pane, 'activity'), (doc_pane, 'bell')):
                window = tm('display-message', '-p', '-t', pane, '#{window_id}')
                run('notify', 'set', window, pane, provider)
            time.sleep(.4)
            keys('C-r')
            capture(3, 'Unread activity, without the clutter', 'One bold amber badge beside the affected pane.', '', 2600)
            keys('H')
            capture(3, 'Unread activity, without the clutter', 'Collapsed branches keep their unread summary.', 'H', 1900)
            keys('L')
            capture(3, 'Unread activity, without the clutter', 'Expand to see exactly which pane needs a look.', 'L', 1400)
            keys('U')
            keys('H')
            capture(4, 'Less noise when you need focus', 'Collapse every branch, then expand the full tree again.', 'H  /  L', 1600)
            keys('L')
            capture(4, 'Less noise when you need focus', 'Collapse every branch, then expand the full tree again.', 'H  /  L', 1600)
            keys('3')
            keys('Up', 'Up')
            keys('p')
            capture(5, 'Keep useful snippets close', 'Browse tmux buffers and preview their contents.', '3  /  p', 2100)
            keys('j')
            capture(5, 'Keep useful snippets close', 'Browse tmux buffers and preview their contents.', 'j  /  k', 1600)
            keys('p')
            keys('1')
            keys(*(['Up'] * 12 + ['Down'] * 5))
            capture(*overview, duration=1700)
        finally:
            sp.run(['tmux', '-S', socket, 'kill-server'], env=env, capture_output=True)
            if client_process:
                client_process.wait(timeout=5)
            if master is not None:
                os.close(master)
    # One palette avoids per-frame color shimmer. No dithering keeps text crisp.
    contact = Image.new('RGB', (frames[0].width, frames[0].height * len(frames)))
    for i, frame in enumerate(frames):
        contact.paste(frame, (0, i * frame.height))
    palette = contact.quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    indexed = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]
    indexed[0].save(args.output / 'canopy-demo.gif', save_all=True, append_images=indexed[1:], duration=durations, loop=0, optimize=True, disposal=1)
    poster = next((frame for frame, metadata in zip(frames, captures) if metadata['chapter'] == 3), frames[0])
    poster.save(args.output / 'canopy-demo.png', optimize=True)
    (args.output / 'canopy-demo-captures.json').write_text(json.dumps(captures, indent=2))
    print(f'Wrote {len(frames)} frames, {sum(durations)/1000:.1f}s, {(args.output / "canopy-demo.gif").stat().st_size:,} bytes to {args.output}')


if __name__ == '__main__':
    main()
