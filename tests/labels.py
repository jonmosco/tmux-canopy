#!/usr/bin/env python3
"""@tmux-canopy-labels 'places': quiet rows are named by what tells them apart.
A window name you gave wins; otherwise where the row is, said from its
session's directory; otherwise what runs there."""
import os
from pathlib import Path
import re
import subprocess as sp
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SEP = '\x1f'
ANSI = re.compile(r'\x1b\[[0-9;]*m')
HOME = '/home/test'
REPO = '/work/tmux-canopy'


def window(session, wid, index, name, auto):
    return ['W', session, wid, str(index), name, '1', 'off', '', '', '', '0', '1' if auto else '0']


def pane(pid, wid, index, command, path):
    return ['P', pid, wid, str(index), command, '', path, '0', '', '', '', '', '', '', '', '0',
            str(100 + int(pid[1:]))]


def main():
    with tempfile.TemporaryDirectory(prefix='canopy-labels-') as directory:
        state = Path(directory) / 'state'
        state.touch()

        def render(labels='places', icons='nerdfont', width=47, git=True, tmux_names=False):
            d = ['D', icons, '', 'ansi', 'normal', '', '', '', '%9', '@9', '$9', str(width), 'host']
            d.extend([''] * (39 - len(d)))
            d.extend(['quiet', 'branch' if git else '', 'off'])
            records = [d,
                       ['S', '$0', 'canopy', '1', REPO], ['S', '$1', 'scratch', '0', HOME],
                       window('$0', '@0', 0, 'editor', False), pane('%0', '@0', 0, 'nvim', REPO),
                       window('$0', '@1', 1, 'zsh', True), pane('%1', '@1', 0, 'zsh', REPO),
                       window('$0', '@2', 2, 'zsh', True), pane('%2', '@2', 0, 'zsh', REPO + '/docs'),
                       window('$0', '@3', 3, 'claude', True), pane('%3', '@3', 0, 'claude', REPO),
                       pane('%4', '@3', 1, 'codex', '/work/canopy-footer'),
                       window('$0', '@4', 4, 'make', True), pane('%5', '@4', 0, 'make', REPO + '/tests'),
                       window('$0', '@5', 5, 'nvim', True), pane('%6', '@5', 0, 'nvim', REPO),
                       window('$0', '@6', 6, 'zsh', True), pane('%7', '@6', 0, 'zsh', REPO + '/vendor/lib'),
                       window('$0', '@8', 8, 'codex', True), pane('%9', '@8', 0, 'codex', REPO),
                       pane('%10', '@8', 1, 'zsh', REPO),
                       window('$1', '@7', 0, 'zsh', True), pane('%8', '@7', 0, 'zsh', HOME + '/code/api')]
            if git:
                records += [['G', '$0', 'main'], ['G', '%0', 'main'], ['G', '%1', 'main'], ['G', '%2', 'main'],
                            ['G', '%3', 'main'], ['G', '%4', 'feature/footer'], ['G', '%5', 'main'],
                            ['G', '%6', 'main'], ['G', '%7', 'vendored'], ['G', '%8', 'fix/auth']]
            snapshot = '\n'.join(SEP.join(r) for r in records) + '\n'
            run = sp.run(['awk', '-v', 'header=1', '-v', 'stable=1', '-v', 'nul=1', '-v', f'now={int(time.time())}',
                          '-v', f'labels={labels}', '-v', f'tmux_names={int(tmux_names)}', '-f', str(ROOT / 'lib/tree-render.awk'), str(state), '-'],
                         input=snapshot, text=True, capture_output=True, check=True,
                         env=os.environ | {'TMUX_CANOPY_RENDER_HOME': HOME, 'LC_COLLATE': 'C'})
            rows = [record.split('\t') for record in run.stdout.strip('\0').split('\0')]
            return {row[2]: row[1] for row in rows}

        def text(rows, key):
            return ' '.join(ANSI.sub('', rows[key]).split())

        rows = render()
        assert text(rows, 'S:$0').endswith('tmux-canopy ⎇ main'), text(rows, 'S:$0')
        # A name you gave wins; its program goes to the right.
        assert text(rows, 'W:@0:$0').endswith('0:editor nvim'), text(rows, 'W:@0:$0')
        # An idle shell shows where it is, dimmed, not "zsh".
        assert text(rows, 'W:@1:$0').endswith('1:tmux-canopy'), text(rows, 'W:@1:$0')
        assert '\x1b[38;5;245mtmux-canopy' in rows['W:@1:$0'], rows['W:@1:$0']
        assert 'zsh' not in text(rows, 'W:@1:$0')
        # A subfolder of the session's directory: a folder, no repeated branch.
        assert text(rows, 'W:@2:$0').endswith('2: docs'), text(rows, 'W:@2:$0')
        assert text(rows, 'W:@4:$0').endswith('4: tests make'), text(rows, 'W:@4:$0')
        # A program in the session's directory is the label itself.
        assert text(rows, 'W:@5:$0').endswith('5:nvim'), text(rows, 'W:@5:$0')
        # A nested repository keeps its own branch.
        assert text(rows, 'W:@6:$0').endswith('6: vendor/lib ⎇ vendored'), text(rows, 'W:@6:$0')
        # A window in the session's directory is named by its program, plus how
        # many panes are elsewhere.
        assert text(rows, 'W:@3:$0').endswith('3:claude +1'), text(rows, 'W:@3:$0')
        assert text(rows, 'W:@8:$0').endswith('8:codex'), text(rows, 'W:@8:$0')
        assert text(rows, 'P:%10:$0').endswith('1:shell'), text(rows, 'P:%10:$0')
        assert text(rows, 'P:%3:$0').endswith('0:claude'), text(rows, 'P:%3:$0')
        wide = render(width=60)
        assert text(wide, 'P:%4:$0').endswith('1: canopy-footer ⎇ feature/footer codex'), text(wide, 'P:%4:$0')
        assert text(rows, 'P:%4:$0').endswith('1: canopy-footer codex'), text(rows, 'P:%4:$0')
        # A session in your home directory has no subfolders worth naming.
        assert text(rows, 'W:@7:$1').endswith('0: api ⎇ fix/auth'), text(rows, 'W:@7:$1')
        assert 'code/api' not in text(rows, 'W:@7:$1')
        assert 'home' not in text(rows, 'S:$1'), text(rows, 'S:$1')
        print('ok - places labels name rows by their window name, place, or program, with the program on the right')

        unicode = render(icons='unicode', width=60)
        assert text(unicode, 'W:@2:$0').endswith('2:docs/'), text(unicode, 'W:@2:$0')
        assert text(unicode, 'P:%4:$0').endswith('1:↗ canopy-footer ⎇ feature/footer codex'), text(unicode, 'P:%4:$0')
        ascii_rows = render(icons='ascii', width=60)
        assert text(ascii_rows, 'P:%4:$0').endswith('1:[canopy-footer] @feature/footer codex'), text(ascii_rows, 'P:%4:$0')
        assert all(ord(c) < 128 for c in text(ascii_rows, 'P:%4:$0')), text(ascii_rows, 'P:%4:$0')
        no_git = render(git=False, width=60)
        assert text(no_git, 'P:%4:$0').endswith('1: canopy-footer codex'), text(no_git, 'P:%4:$0')
        # Narrow: the branch gives way before the label or the program.
        narrow = render(width=30)
        assert 'feature/footer' not in text(narrow, 'P:%4:$0') and 'canopy-footer' in text(narrow, 'P:%4:$0'), \
            text(narrow, 'P:%4:$0')
        assert all(len(ANSI.sub('', value)) <= 27 for key, value in narrow.items() if key[0] in 'WP'), narrow
        print('ok - places labels fall back to Unicode and ASCII marks and narrow sidebars drop the branch first')

        # Without the setting, quiet keeps tmux's window names.
        default = render(labels='')
        assert '1:zsh' in text(default, 'W:@1:$0'), text(default, 'W:@1:$0')
        assert '0:editor · nvim' in text(default, 'W:@0:$0'), text(default, 'W:@0:$0')
        print('ok - quiet keeps tmux window names unless places labels are on')

        # A custom automatic-rename-format is your choice of window names: keep
        # them, and label only panes.
        named = render(tmux_names=True, width=60)
        assert text(named, 'W:@1:$0').endswith('1:zsh'), text(named, 'W:@1:$0')
        assert text(named, 'W:@3:$0').endswith('3:claude'), text(named, 'W:@3:$0')
        assert text(named, 'P:%4:$0').endswith('1: canopy-footer ⎇ feature/footer codex'), text(named, 'P:%4:$0')
        print('ok - a custom automatic-rename-format keeps tmux window names and labels only panes')

        # tree-source reads both settings from tmux in its one snapshot call.
        socket = f'canopy-labels-{os.getpid()}'
        env = {k: v for k, v in os.environ.items() if k not in ('TMUX', 'TMUX_PANE')}

        def tm(*args):
            return sp.run(['tmux', '-L', socket, *args], env=env, capture_output=True, text=True, timeout=10).stdout.strip()
        try:
            work = Path(directory) / 'work'
            (work / 'docs').mkdir(parents=True)
            link = Path(directory) / 'link-[v1]'
            link.symlink_to(work)
            tm('-f', '/dev/null', 'new-session', '-d', '-s', 'w', '-x', '120', '-y', '30', '-c', str(link), 'sleep 600')
            tm('new-window', '-d', '-t', 'w:', '-c', str((work / 'docs').resolve()), 'sleep 600')
            sidebar = tm('split-window', '-d', '-h', '-l', '42', '-t', 'w:0', '-P', '-F', '#{pane_id}', 'sleep 600')
            tm('set-option', '-p', '-t', sidebar, '@tmux_canopy', '1')
            tm('set-option', '-g', '@tmux_canopy_appearance', 'quiet')
            tm('set-option', '-g', '@tmux_canopy_icon_theme', 'ascii')
            tm('set-option', '-g', '@tmux-canopy-labels', 'places')
            source_env = env | {'TMUX': tm('display-message', '-p', '#{socket_path},0,0'), 'TMUX_PANE': sidebar,
                                'TMUX_CANOPY_STATE': str(state), 'TMUX_CANOPY_NUL': '1'}

            def docs_row():
                out = sp.run([str(ROOT / 'scripts/tree-source')], env=source_env, capture_output=True, text=True,
                             timeout=10).stdout
                return next(' '.join(ANSI.sub('', r.split('\t')[1]).split()) for r in out.split('\0')
                            if r.startswith('W:') and ':1:' not in r.split('\t')[0] and '1:' in r)
            assert '1:docs/ sleep' in docs_row(), docs_row()
            # The preview names the window as tmux does, next to the label.
            docs_pane = tm('display-message', '-p', '-t', 'w:1', '#{pane_id}')
            preview = sp.run([str(ROOT / 'scripts/pane-preview'), docs_pane], env=source_env, capture_output=True,
                             text=True, timeout=10).stdout.splitlines()[0]
            name = tm('display-message', '-p', '-t', 'w:1', '#{window_name}')
            assert preview.startswith(f'w:1 {name} · {docs_pane} · '), preview
            tm('set-option', '-gw', 'automatic-rename-format', '#{b:pane_current_path}')
            tm('rename-window', '-t', 'w:1', 'docs-by-tmux')
            tm('set-option', '-w', '-t', 'w:1', 'automatic-rename', 'on')
            assert 'docs/' not in docs_row(), docs_row()
            print('ok - tree-source passes the labels setting and notices a custom automatic-rename-format')
        finally:
            sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True, timeout=10)


if __name__ == '__main__':
    main()
