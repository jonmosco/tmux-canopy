#!/usr/bin/env python3
"""Notification placement, unique descendant counts, and portable glyphs."""
import os
from pathlib import Path
import subprocess as sp
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='canopy-notifications-test-', ignore_cleanup_errors=True) as directory:
        state = Path(directory) / 'state'

        def render(*, collapsed='', icons='nerdfont', theme='ansi', density='normal',
                   enabled=True, linked=False, orphan=False, width=42):
            state.write_text(collapsed)
            data = [
                ['D', icons, 'all' if enabled else 'none', theme, density, '', '', '', '%0', '@0', '$0', str(width), 'host'],
                ['S', '$0', 'work', '1'],
                ['W', '$0', '@0', '0', 'web', '2' if linked else '1', 'off', '1', '1', '0'],
                ['W', '$0', '@1', '1', 'api', '1', 'off', '0', '0', '1'],
                ['P', '%0', '@0', '0', 'nvim', '', '/work/web', '0', '', '', '1', '1', '0', '', '', ''],
                ['P', '%1', '@0', '1', 'bash', '', '/work/web', '0', '', '', '1', '0', '0', '', '', ''],
                ['P', '%2', '@1', '0', 'python3', '', '/work/api', '0', '', '', '0', '0', '1', '', '', ''],
                ['P', '%90', '@0', '90', 'fzf', '', '/internal', '0', '1', '', '1', '1', '1', '', '', ''],
                ['P', '%91', '@0', '91', '', '', '/internal', '0', '', '1', '1', '1', '1', '', '', ''],
            ]
            if orphan:
                for row in data:
                    if row[0] == 'P':
                        row[10:13] = ['0'] * 3
            if linked:
                data += [['S', '$1', 'linked', '0'], ['W', '$1', '@0', '3', 'web', '2', 'off', '1', '1', '0']]
            result = sp.check_output(['awk', '-v', 'stable=1', '-v', 'nul=1', '-f', str(ROOT/'lib/tree-render.awk'), str(state), '-'],
                                     input='\n'.join('\x1f'.join(row) for row in data)+'\n', text=True,
                                     env=os.environ | {'TMUX_CANOPY_RENDER_CLIENT': '', 'TMUX_CANOPY_RENDER_HOME': '/home/test'})
            rows = [line.split('\t') for line in result.rstrip('\0').split('\0')]
            assert all(len(row) == 3 for row in rows)
            assert len({row[2] for row in rows}) == len(rows)
            return {row[2]: row[1] for row in rows}

        for icons, activity, bell, silence in [('nerdfont', '●', '', '◷'), ('unicode', '●', '🔔', '◷'), ('ascii', '*', 'B', '~')]:
            for theme in ('ansi', 'mono'):
                badge = lambda glyph: '\x1b[1;33m'+glyph+'\x1b[0m' if theme == 'ansi' else glyph
                for density in ('normal', 'compact', 'detailed'):
                    for width in (24, 42, 80):
                        args = dict(icons=icons, theme=theme, density=density, width=width)
                        rows = render(**args)
                        assert 'nvim '+badge(bell) in rows['P:%0:$0']
                        assert 'bash '+badge(activity) in rows['P:%1:$0']
                        assert 'python3 '+badge(silence) in rows['P:%2:$0']
                        assert not any('!' in row or bell+'1' in row for row in rows.values())
                        for identity in ('S:$0', 'W:@0:$0', 'W:@1:$0'):
                            assert badge(bell) not in rows[identity] and badge(silence) not in rows[identity]
                            if theme == 'ansi':
                                assert '\x1b[1;33m' not in rows[identity]
                        collapsed = render(collapsed='W:@0:$0\nW:@1:$0\n', **args)
                        assert 'web' in collapsed['W:@0:$0'] and badge(bell+'2') in collapsed['W:@0:$0']
                        assert 'api' in collapsed['W:@1:$0'] and badge(silence) in collapsed['W:@1:$0']
                        assert not any(k.startswith('P:') for k in collapsed)
                        sessions = render(collapsed='S:$0\nS:$1\n', linked=True, **args)
                        assert 'work' in sessions['S:$0'] and badge(bell+'2') in sessions['S:$0']
                        assert 'linked' in sessions['S:$1'] and badge(bell) in sessions['S:$1']
                        disabled = render(enabled=False, **args)
                        assert 'nvim '+badge(bell) not in disabled['P:%0:$0']
                        orphan = render(orphan=True, **args)
                        assert 'web' in orphan['W:@0:$0'] and badge(bell) in orphan['W:@0:$0']
                        if theme == 'ansi':
                            assert '\x1b[1;32m●\x1b[0m' in rows['P:%0:$0']
                        else:
                            assert all('\x1b' not in value for value in rows.values())
        print('ok - one badge per pane, collapsed unique counts, priority, linked rows, fallback, themes and densities')


if __name__ == '__main__':
    main()
