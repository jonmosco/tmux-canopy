#!/usr/bin/env python3
"""Quiet tree geometry and headings: tmux's own order, with no guides, so
indentation and session headings carry the hierarchy. Each window appears once,
every pane starts right of its window's name, pane names line up, sessions stand
apart, directories are details, and idle shells recede."""
import os
from pathlib import Path
import re
import subprocess as sp
import tempfile
import time
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
SEP = '\x1f'
ANSI = re.compile(r'\x1b\[[0-9;]*m')
INDEX = re.compile(r'\d+:')


def cells(text):
    return sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1 for c in text)


def label_column(row):
    """Display column where a window's or pane's `index:` label starts."""
    plain = ANSI.sub('', row)
    match = INDEX.search(plain)
    assert match, plain
    return cells(plain[:match.start()])


def render(icons, density='normal', compact=''):
    with tempfile.TemporaryDirectory(prefix='canopy-quiet-layout-') as directory:
        state = Path(directory) / 'state'
        state.write_text('')
        d = ['D', icons, 'activity,bell', 'ansi', density, '', '', '', '%0', '@0', '$0', '42', 'host']
        d.extend([''] * (39 - len(d)))
        d[13] = compact
        d.extend(['quiet', '', 'on'])

        def pane(pane_id, window, index, command, path, pid, activity='', bell=''):
            return ['P', pane_id, window, index, command, '', path, '0', '', '', activity, bell, '', '', '', '0', pid]
        records = [d, ['S', '$0', 'work', '1'],
                   ['W', '$0', '@0', '1', 'zsh', '3', 'off', '', '', '', '0'],
                   ['W', '$0', '@1', '2', 'web', '1', 'off', '', '', '', '0'],
                   pane('%0', '@0', '1', 'claude', '/projects/api', '100'),
                   pane('%1', '@0', '2', 'zsh', '/projects/api', '101', activity='1'),
                   pane('%2', '@0', '3', 'nvim', '/projects/api', '102', bell='1'),
                   pane('%3', '@1', '1', 'zsh', '/projects/web', '103'),
                   ['W', '$0', '@5', '3', 'mixed', '2', 'off', '', '', '', '0'],
                   pane('%6', '@5', '1', 'zsh', '/projects/api', '106'),
                   pane('%7', '@5', '2', 'claude', '/projects/docs', '107'),
                   ['S', '$1', 'reference', '0'], ['W', '$1', '@2', '1', 'zsh', '1', 'off', '', '', '', '0'],
                   pane('%4', '@2', '1', 'zsh', '/projects/docs', '104'),
                   ['S', '$2', 'session-3', '0'], ['W', '$2', '@3', '1', 'zsh', '1', 'off', '', '', '', '0'],
                   pane('%5', '@3', '1', 'zsh', '/projects/docs', '105'),
                   ['S', '$3', 'notes', '0'], ['W', '$3', '@4', '1', 'zsh', '1', 'off', '', '', '', '0'],
                   pane('%8', '@4', '1', 'zsh', '/projects/notes', '108')]
        run = sp.run(['awk', '-v', 'header=1', '-v', 'stable=1', '-v', 'nul=1',
                      '-f', str(ROOT / 'lib/tree-render.awk'), str(state), '-'],
                     input='\n'.join(SEP.join(r) for r in records) + '\n', text=True,
                     capture_output=True, check=True, env=os.environ | {'TMUX_CANOPY_RENDER_HOME': '/home/test'})
        rows = [record.split('\t') for record in run.stdout.strip('\0').split('\0')]
        return {row[2]: row[1] for row in rows}


def header(statuses, width=42, icons='unicode', agent_view=False):
    """The quiet header for agents in the given hook-reported states ('' = none)."""
    now = str(int(time.time()))
    with tempfile.TemporaryDirectory(prefix='canopy-quiet-header-') as directory:
        state = Path(directory) / 'state'
        state.write_text('')
        d = ['D', icons, 'activity,bell', 'ansi', 'normal', '', '', '', '%0', '@0', '$0', str(width), 'host']
        d.extend([''] * (39 - len(d)))
        d.extend(['quiet', '', 'on'])
        records = [d, ['S', '$0', 'work', '1'], ['W', '$0', '@0', '0', 'agents', str(len(statuses)), 'off', '', '', '', '0']]
        for index, status in enumerate(statuses):
            pid = str(200 + index)
            row = ['P', f'%{index}', '@0', str(index), 'claude', '', '/work', '0', '', '', '', '', '', '', '', '0', pid]
            if status:
                row += ['claude-hook', 's' + pid, pid, status, now, '', '']
            records += [row, ['A', f'%{index}', 'claude']] + ([['V', f'%{index}']] if status else [])
        run = sp.run(['awk', '-v', 'header=1', '-v', 'stable=1', '-v', 'nul=1', '-v', f'agent_view={int(agent_view)}',
                      '-v', f'now={now}', '-f', str(ROOT / 'lib/tree-render.awk'), str(state), '-'],
                     input='\n'.join(SEP.join(r) for r in records) + '\n', text=True, capture_output=True, check=True,
                     env=os.environ | {'TMUX_CANOPY_RENDER_HOME': '/home/test'})
        rows = {row.split('\t')[2]: row.split('\t')[1] for row in run.stdout.strip('\0').split('\0')}
        return ANSI.sub('', rows['H:tree']).rstrip()


def main():
    # The header counts every agent state ("◆1 ▷1 ○1"), not only the most
    # urgent one, and falls back to that state with the total when narrow.
    mixed = ('needs-input', 'working', '', 'turn-ended', 'working')
    assert header(mixed).endswith('◆1 ▷2 ✓1 ○1'), header(mixed)
    assert header(mixed, agent_view=True).endswith('◆1 ▷2 ✓1 ○1'), header(mixed, agent_view=True)
    assert header(mixed, icons='ascii').endswith('!1 +2 d1 o1'), header(mixed, icons='ascii')
    assert header(('working', '')).endswith('▷1 ○1'), header(('working', ''))
    assert header(mixed, width=22).endswith('◆1/5'), header(mixed, width=22)

    for icons in ('unicode', 'nerdfont', 'ascii'):
        tree = render(icons)
        window = label_column(tree['W:@0:$0'])
        # The last folder's window lines up with the first folder's, here as a
        # single-pane window's one row: the window's identity, the pane's command
        # after the name it differs from, and no separate pane row.
        assert label_column(tree['W:@1:$0']) == window, (icons, tree['W:@0:$0'], tree['W:@1:$0'])
        assert '2:web · zsh' in ANSI.sub('', tree['W:@1:$0']), tree['W:@1:$0']
        assert 'P:%3:$0' not in tree and 'P:%4:$1' not in tree, sorted(tree)
        assert ' · ' not in ANSI.sub('', tree['W:@2:$1']), tree['W:@2:$1']  # named after its command
        panes = {key: label_column(tree[key]) for key in ('P:%0:$0', 'P:%1:$0', 'P:%2:$0')}
        # Icon or not, every pane label starts in one column, right of its window's.
        assert len(set(panes.values())) == 1, (icons, panes, {key: ANSI.sub('', tree[key]) for key in panes})
        assert panes['P:%0:$0'] > window, (icons, panes, window)
        # Every session is a bold heading behind an accent glyph, current or not;
        # automatic names stay dim. A blank line sets each session after the first apart.
        first, second, automatic = tree['S:$0'], tree['S:$1'], tree['S:$2']
        assert '\n' not in first and '\x1b[1mwork' in first, first
        gap, heading = second.split('\n')
        assert gap == '', second
        assert '\x1b[1mreference' in heading and '\x1b[1;36m' in heading, heading
        assert '\x1b[1m\x1b[2msession-3' in automatic.split('\n')[1], automatic
        # Plain output is a dim notice; a bell keeps the amber.
        assert '\x1b[2m' + ('*' if icons == 'ascii' else '●') + '\x1b[0m' in tree['P:%1:$0'], tree['P:%1:$0']
        assert '\x1b[1;33m' in tree['P:%2:$0'], tree['P:%2:$0']
        # tmux order: no folder rows, windows in index order, and a window whose
        # panes are in different directories appears once.
        assert not any(key.startswith('DIR:') for key in tree), sorted(tree)
        assert [key for key in tree if key.startswith('W:') and key.endswith(':$0')] == ['W:@0:$0', 'W:@1:$0', 'W:@5:$0']
        # Directories are details on the highest row whose panes all share
        # them. A session in one directory shows it on its heading alone; in a
        # mixed session each window that agrees shows its own, and a mixed
        # window shows one per pane. Nothing mixed claims one.
        tail = {key: ANSI.sub('', tree[key]).rstrip() for key in tree}
        assert tail['S:$1'].endswith('docs') and not tail['W:@2:$1'].endswith('docs'), (tail['S:$1'], tail['W:@2:$1'])
        # ...unless the session is named after that directory: the detail would
        # only repeat its name.
        assert tail['S:$3'].split('\n')[-1].count('notes') == 1, tail['S:$3']
        assert not tail['S:$0'].endswith(('api', 'web', 'docs')), tail['S:$0']
        assert tail['W:@0:$0'].endswith('api') and tail['W:@1:$0'].endswith('web'), (tail['W:@0:$0'], tail['W:@1:$0'])
        assert not tail['W:@5:$0'].endswith(('api', 'docs')), tail['W:@5:$0']
        assert tail['P:%6:$0'].endswith('api') and tail['P:%7:$0'].endswith('docs'), (tail['P:%6:$0'], tail['P:%7:$0'])
        assert not tail['P:%0:$0'].endswith('api'), tail['P:%0:$0']  # its window already says
        # An idle shell recedes; one with output to report, or a running
        # program, does not.
        assert '\x1b[2mzsh' in tree['P:%6:$0'], tree['P:%6:$0']
        assert '\x1b[2mzsh' not in tree['P:%1:$0'] and '\x1b[2mclaude' not in tree['P:%7:$0']
    split = render('unicode', compact='off')
    assert 'P:%3:$0' in split and ' · ' not in ANSI.sub('', split['W:@1:$0']), 'compact-single-panes off keeps pane rows'
    for density in ('compact', 'minimal'):
        assert not any('\n' in row for key, row in render('unicode', density).items() if key.startswith('S:')), density
    print('ok - quiet follows tmux order, lines panes up, shows directories as details, and dims idle shells')


if __name__ == '__main__':
    main()
