#!/usr/bin/env python3
"""Application icon colors without a tmux server or a font dependency."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ('bash', 39, ' '), ('zsh', 39, ' '), ('unknown', 39, ' '),
    ('nvim', 94, ''), ('vim', 94, ''),
    ('node', 93, ''), ('npm', 91, ''), ('python3', 93, ''),
    ('/usr/bin/git', 91, '󰊢'), ('lazygit', 91, '󰊢'),
    ('kubectl', 94, '󱃾'), ('k9s', 94, '󱃾'), ('oc', 91, '󱃾'),
    ('ssh', 96, '󰢹'),     ('pi', 95, 'π'), ('omp', 93, 'π'), ('claude', 93, ''),
    ('codex', 96, ''), ('opencode', 39, ''), ('agent', 39, ''), ('btop', 96, '󰍛'),
    ('gemini', 94, '󰫢'), ('agy', 96, '󰀘'),
    ('claude.exe', 93, ''), ('codex.exe', 96, ''), ('agy.exe', 96, '\U000f0018'),
]
UNICODE_ICONS = {
    'nvim': '✎', 'vim': '✎', 'node': '◆', 'npm': '◆',
    'python3': '◉', '/usr/bin/git': '◇', 'lazygit': '◇',
    'kubectl': '✣', 'k9s': '✣', 'oc': '✣', 'ssh': '⇄',
    'pi': 'π', 'omp': 'π', 'claude': '✳', 'codex': '❋', 'opencode': '▦', 'agent': '▸',
    'btop': '▥', 'gemini': '✧', 'agy': '◎',
    'claude.exe': '✳', 'codex.exe': '❋', 'agy.exe': '◎',
}


def main():
    env = os.environ.copy()
    env.update(TMUX_CANOPY_RENDER_CLIENT='', TMUX_CANOPY_RENDER_HOME='/test')
    with tempfile.TemporaryDirectory(prefix='tree-icons-', ignore_cleanup_errors=True) as directory:
        state = Path(directory) / 'state'
        state.touch()
        for theme in ('ansi', 'mono'):
            for icons in ('nerdfont', 'unicode', 'ascii'):
                records = [
                    ['D', icons, 'none', theme, 'compact', '', '', '', '%0', '@0', '$0', '42', 'host'],
                    ['S', '$0', 'test', '0'],
                    ['W', '$0', '@0', '0', 'tools', '1', 'off', '', '', ''],
                ]
                for index, (command, _, _) in enumerate(CASES):
                    records.append(['P', f'%{index}', '@0', str(index), command, '', '/test', '0', '', '', '', '', '', '', '', ''])
                snapshot = '\n'.join('\x1f'.join(record) for record in records) + '\n'
                result = subprocess.run(['awk', '-v', 'stable=1', '-v', 'header=1', '-f',
                                         str(ROOT / 'lib/tree-render.awk'), str(state), '-'],
                                        input=snapshot, text=True, capture_output=True, env=env, check=True)
                rows = {parts[0]: parts for line in result.stdout.splitlines() if (parts := line.split('\t'))}
                assert (' | All' if icons == 'ascii' else ' · All') in rows['H:'][1]
                session_row = re.sub(r'\x1b\[[0-9;]*m', '', rows['S:$0'][1])
                assert session_row.startswith('▾ test'), session_row
                assert '─' not in rows['S:$0'][1], rows['S:$0']
                for index, (command, color, glyph) in enumerate(CASES):
                    row = rows[f'P:%{index}']
                    assert len(row) == 3 and row[2] == f'P:%{index}:$0'
                    glyph = glyph if icons == 'nerdfont' else '>' if icons == 'ascii' else UNICODE_ICONS.get(command, ' ')
                    if theme == 'ansi':
                        assert f'\x1b[{color}m{glyph}\x1b[0m' in row[1], row
                    else:
                        assert glyph in row[1] and '\x1b' not in row[1], row
                if theme == 'ansi':
                    assert '\x1b[1;32m▶\x1b[0m' in rows['P:%0'][1]
                else:
                    assert '\x1b' not in result.stdout

                if theme == 'ansi' and icons == 'nerdfont':
                    keys = 'nvim vim shell node python git ssh kubectl claude codex gemini pi omp opencode agent antigravity make top'.split()
                    overrides = {'shell': 'S', 'python': 'P', 'claude': 'C', 'codex': 'none'}
                    records[0].extend([''] * (17 - len(records[0])))
                    records[0].extend(overrides.get(key, '') for key in keys)
                    changed = subprocess.run(['awk', '-v', 'stable=1', '-f',
                                              str(ROOT / 'lib/tree-render.awk'), str(state), '-'],
                                             input='\n'.join('\x1f'.join(record) for record in records)+'\n',
                                             text=True, capture_output=True, env=env, check=True)
                    changed_rows = {parts[0]: parts[1] for line in changed.stdout.splitlines()
                                    if (parts := line.split('\t'))}
                    for command, glyph in (('bash', 'S'), ('python3', 'P'), ('claude', 'C'), ('claude.exe', 'C')):
                        index = next(i for i, case in enumerate(CASES) if case[0] == command)
                        assert f'{glyph}\x1b[0m' in changed_rows[f'P:%{index}'], (command, changed_rows[f'P:%{index}'])
                    for command in ('codex', 'codex.exe'):
                        index = next(i for i, case in enumerate(CASES) if case[0] == command)
                        assert '◈' not in changed_rows[f'P:%{index}']

        # Lazygit appearance: box header, rounded ends, structural glyphs, cyan folds.
        for icons, session_glyph, window_glyph in (
            ('nerdfont', '', '󰖯'),
            ('unicode', '◈', '▣'),
            ('ascii', 'S', 'W'),
        ):
            d = ['D', icons, 'none', 'ansi', 'compact', '', '', '', '%0', '@0', '$0', '42', 'host']
            d.extend([''] * (38 - len(d)))
            d.append('lazygit')  # $39 appearance; agents stay unset/$40 empty
            records = [
                d,
                ['S', '$0', 'test', '0'],
                ['W', '$0', '@0', '0', 'tools', '1', 'off', '', '', ''],
                ['P', '%0', '@0', '0', 'bash', '', '/test', '0', '', '', '', '', '', '', '', ''],
                ['P', '%1', '@0', '1', 'nvim', '', '/test', '0', '', '', '', '', '', '', '', ''],
            ]
            result = subprocess.run(['awk', '-v', 'stable=1', '-v', 'header=1', '-f',
                                     str(ROOT / 'lib/tree-render.awk'), str(state), '-'],
                                    input='\n'.join('\x1f'.join(r) for r in records) + '\n',
                                    text=True, capture_output=True, env=env, check=True)
            rows = {parts[0]: parts for line in result.stdout.splitlines() if (parts := line.split('\t'))}
            header = re.sub(r'\x1b\[[0-9;]*m', '', rows['H:'][1])
            assert header.startswith('╭─ '), header
            assert '╮' not in header, header
            assert '[' not in header and ' · ' not in header, header
            assert ' ─ All' in header or ' | All' in header, header
            session_row = re.sub(r'\x1b\[[0-9;]*m', '', rows['S:$0'][1])
            fold = 'v ' if icons == 'ascii' else '▼ '
            assert session_row.startswith(f'{fold}{session_glyph} test'), session_row
            window_row = re.sub(r'\x1b\[[0-9;]*m', '', rows['W:@0:$0'][1])
            assert window_glyph not in window_row and 'tools' in window_row and '0:tools' not in window_row, window_row
            assert ('╰─' if icons != 'ascii' else '`-') in window_row or \
                   ('├─' if icons != 'ascii' else '|-') in window_row, window_row
            if icons != 'ascii':
                assert '\x1b[1;36m' in rows['S:$0'][1], rows['S:$0']  # cyan fold

        records_zoom = [
            ['D', 'unicode', 'none', 'ansi', 'normal', '', '', '', '%0', '@0', '$0', '42', 'host'],
            ['S', '$0', 'test', '0'],
            ['W', '$0', '@0', '0', 'tools', '1', 'off', '', '', '', '1'],
            ['P', '%0', '@0', '0', 'bash', '', '/test', '0', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '1'],
            ['P', '%1', '@0', '1', 'nvim', '', '/test', '0', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '', '0'],
        ]
        res_zoom = subprocess.run(['awk', '-v', 'stable=1', '-v', 'header=1', '-f',
                                   str(ROOT / 'lib/tree-render.awk'), str(state), '-'],
                                  input='\n'.join('\x1f'.join(r) for r in records_zoom) + '\n',
                                  text=True, capture_output=True, env=env, check=True)
        rows_zoom = {parts[0]: parts for line in res_zoom.stdout.splitlines() if (parts := line.split('\t'))}
        assert '[Z]' in rows_zoom['W:@0:$0'][1], rows_zoom['W:@0:$0']
        assert '[Z]' in rows_zoom['P:%0'][1], rows_zoom['P:%0']
        assert '[Z]' not in rows_zoom['P:%1'][1], rows_zoom['P:%1']
    print('ok - command-aware icon colors, active green marker, all glyph themes and monochrome output')
    print('ok - lazygit appearance header, structural glyphs, and rounded branches')


if __name__ == '__main__':
    main()
