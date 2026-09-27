#!/usr/bin/env python3
"""Application icon colors without a tmux server or a font dependency."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ('bash', 39, ''), ('zsh', 39, ''), ('unknown', 39, ''),
    ('nvim', 94, ''), ('vim', 94, ''),
    ('node', 93, ''), ('npm', 91, ''), ('python3', 93, ''),
    ('/usr/bin/git', 91, '󰊢'), ('lazygit', 91, '󰊢'),
    ('kubectl', 94, '󱃾'), ('k9s', 94, '󱃾'), ('oc', 91, '󱃾'),
    ('ssh', 96, '󰢹'), ('pi', 95, '󰚩'), ('claude', 93, ''),
    ('codex', 96, ''), ('opencode', 95, '󰚩'), ('btop', 96, '󰍛'),
    ('gemini', 97, '󰊭'),
    ('claude.exe', 93, '\uec82'), ('codex.exe', 96, '\uec81'),
]


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
                result = subprocess.run(['awk', '-v', 'stable=1', '-v', 'header=0', '-f',
                                         str(ROOT / 'lib/tree-render.awk'), str(state), '-'],
                                        input=snapshot, text=True, capture_output=True, env=env, check=True)
                rows = {parts[0]: parts for line in result.stdout.splitlines() if (parts := line.split('\t'))}
                session_glyph = {'nerdfont': '', 'unicode': '◈', 'ascii': 'S'}[icons]
                assert session_glyph in rows['S:$0'][1], rows['S:$0']
                assert '─' not in rows['S:$0'][1], rows['S:$0']
                for index, (_, color, glyph) in enumerate(CASES):
                    row = rows[f'P:%{index}']
                    assert len(row) == 3 and row[2] == f'P:%{index}:$0'
                    glyph = glyph if icons == 'nerdfont' else '>' if icons == 'ascii' else '▹'
                    if theme == 'ansi':
                        assert f'\x1b[{color}m{glyph}\x1b[0m' in row[1], row
                    else:
                        assert glyph in row[1] and '\x1b' not in row[1], row
                if theme == 'ansi':
                    assert '\x1b[1;32m●\x1b[0m' in rows['P:%0'][1]
                else:
                    assert '\x1b' not in result.stdout
    print('ok - command-aware icon colors, active green marker, all glyph themes and monochrome output')


if __name__ == '__main__':
    main()
