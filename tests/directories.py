#!/usr/bin/env python3
"""Shared directory presentation without changing selectable object identities."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='canopy-directories-') as directory:
        state_file = Path(directory) / 'state'

        def render(paths, *, density='normal', nul=True, collapsed=False, linked=False,
                   internal=False, width=42, icons='unicode', compact='off', switcher=False, notices=False):
            state_file.write_text('W:@0:$0\n' if collapsed else '')
            data = [
                ['D', icons, 'activity,bell' if notices else 'none', 'mono', density, '', '', '', '%0', '@0', '$0', str(width), 'host', compact],
                ['S', '$0', 'work', '1'],
                ['W', '$0', '@0', '0', 'main', '2' if linked else '1', 'off', '', '', ''],
            ]
            if linked:
                data += [['S', '$1', 'linked', '0'], ['W', '$1', '@0', '1', 'main', '2', 'off', '', '', '']]
            for i, path in enumerate(paths):
                data.append(['P', f'%{i}', '@0', str(i), 'bash', '', path, '0', '', '', '1' if notices else '', '1' if notices else '', '', '', '', ''])
            if internal:
                data += [
                    ['P', '%90', '@0', '90', 'fzf', '', '/sidebar', '0', '1', '', '', '', '', '', '', ''],
                    ['P', '%91', '@0', '91', 'sleep', '', '/slot', '0', '', '1', '', '', '', '', '', ''],
                ]
            output = subprocess.check_output(
                ['awk', '-v', f'switcher={int(switcher)}', '-v', 'stable=1', '-v', f'nul={int(nul)}', '-f', str(ROOT / 'lib/tree-render.awk'), str(state_file), '-'],
                input='\n'.join('\x1f'.join(row) for row in data)+'\n', text=True,
                env=os.environ | {'TMUX_CANOPY_RENDER_HOME': '/home/test', 'TMUX_CANOPY_RENDER_CLIENT': ''})
            rows = [row.split('\t') for row in output.rstrip('\0' if nul else '\n').split('\0' if nul else '\n')]
            assert all(len(row) == 3 for row in rows)
            assert len({row[2] for row in rows}) == len(rows)
            return rows

        for icons in ('ascii', 'unicode', 'nerdfont'):
            for width in (24, 30, 42, 80):
                rows = render(['/work/project']*3, icons=icons, width=width, internal=True)
                window = next(row for row in rows if row[0] == 'W:@0:$0')
                panes = [row for row in rows if row[0].startswith('P:')]
                assert window[1].count('\n') == 1
                assert len(window[1].split('\n')[1]) <= width-2
                assert sum(row[1].count('project') for row in rows) == 1
                assert len(panes) == 3 and all('\n' not in row[1] for row in panes)
                assert [row[2] for row in panes] == ['P:%0:$0', 'P:%1:$0', 'P:%2:$0']
        for paths in (['/work/project'], ['/work/project', '/other/project'], ['', '/work/project'], ['', '']):
            rows = render(paths)
            assert all('\n' not in row[1] for row in rows if row[0].startswith('W:'))
            assert all(row[1].count('\n') == 1 for row in rows if row[0].startswith('P:'))
        for density, nul in (('compact', True), ('detailed', True), ('normal', False)):
            rows = render(['/work/project']*2, density=density, nul=nul)
            assert all('\n' not in row[1] for row in rows if row[0].startswith('W:'))
            assert sum('project' in row[1] for row in rows) == 2
        rows = render(['/work/project']*2, collapsed=True, linked=True)
        assert '\n' not in next(row[1] for row in rows if row[0] == 'W:@0:$0')
        assert '\n' in next(row[1] for row in rows if row[0] == 'W:@0:$1')
        assert [row[2] for row in rows if row[0].startswith('P:')] == ['P:%0:$1', 'P:%1:$1']
        for density in ('normal', 'compact', 'detailed'):
            for icons in ('ascii', 'unicode', 'nerdfont'):
                for collapsed in (False, True):
                    rows = render(['/work/project'], compact='on', density=density,
                                  icons=icons, collapsed=collapsed, internal=True, linked=True)
                    windows = [row for row in rows if row[0].startswith('W:')]
                    assert len(windows) == 2 and not any(row[0].startswith('P:') for row in rows)
                    assert all('bash' in row[1] and 'project' in row[1] and '\n' not in row[1] for row in windows)
                    assert [row[2] for row in windows] == ['W:@0:$0', 'W:@0:$1']
            rows = render(['/work/project']*2, compact='on', density=density, internal=True)
            assert sum(row[0].startswith('P:') for row in rows) == 2
        notice_rows = render(['/work/project'], compact='on', notices=True, icons='ascii')
        compact_row = next(row[1] for row in notice_rows if row[0].startswith('W:'))
        assert 'bash B' in compact_row and 'B1' not in compact_row and '*' not in compact_row
        for compact in ('off', 'invalid', ''):
            assert any(row[0].startswith('P:') for row in render(['/work/project'], compact=compact))
        rows = render(['/work/project'], compact='on', switcher=True, collapsed=True, internal=True, linked=True)
        assert [row[2] for row in rows if row[0].startswith('P:')] == ['P:%0:$0', 'P:%0:$1']
        assert all('project' in row[1] for row in rows if row[0].startswith('P:'))
        assert 'work:0:main.0' in next(row[1] for row in rows if row[2] == 'P:%0:$0')
        assert state_file.read_text() == 'W:@0:$0\n'
    print('ok - compact single-pane rows, linked identities, density/icon modes and unfolded quick-switch inventory')
    print('ok - shared/mixed/missing directories, densities, widths, internal panes, linked windows and stable identities')


if __name__ == '__main__':
    main()
