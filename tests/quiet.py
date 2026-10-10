#!/usr/bin/env python3
"""Opt-in quiet tree: compact attention without changing object identities."""
import os
from pathlib import Path
import re
import subprocess as sp
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
SEP = '\x1f'
ANSI = re.compile(r'\x1b\[[0-9;]*m')


def main():
    with tempfile.TemporaryDirectory(prefix='canopy-quiet-') as directory:
        state = Path(directory) / 'state'
        now = int(time.time())

        def render(*, appearance='quiet', width=42, icons='unicode', theme='ansi',
                   agent_view=False, agents=True, notice=True, subagent=False,
                   verified=True, long_command=False, state_text=''):
            state.write_text(state_text)
            d = ['D', icons, 'activity,bell', theme, 'normal', '', '', '',
                 '%0', '@0', '$0', str(width), 'host']
            d.extend([''] * (39 - len(d)))
            d.extend([appearance, '', 'on' if agents else 'off'])
            pane = ['P', '%0', '@0', '0', 'claude', '', '/projects/api', '0', '', '',
                    '', '', '', '', '', '0', '100', 'claude-hook', 'session', '100',
                    'working' if subagent else 'needs-input', str(now), '', '',
                    f'1,Explore,needs-input,{now},' if subagent else '', '0']
            other = ['P', '%1', '@0', '1',
                     'a-very-long-application-command' if long_command else 'nvim',
                     '', '/projects/api', '0', '', '',
                     '1' if notice else '', '', '', '', '', '0', '101']
            records = [d, ['S', '$0', 'acme-api', '1'],
                       ['W', '$0', '@0', '0', 'server', '1', 'off', '', '', '', '0'],
                       pane, other, ['A', '%0', 'claude'],
                       ['G', '%0', 'feature/auth'], ['G', '%1', 'feature/auth']]
            if verified:
                records.append(['V', '%0'])
            snapshot = '\n'.join(SEP.join(r) for r in records) + '\n'
            run = sp.run(['awk', '-v', 'header=1', '-v', 'stable=1', '-v', 'nul=1',
                          '-v', f'agent_view={int(agent_view)}', '-v', f'now={now}',
                          '-f', str(ROOT / 'lib/tree-render.awk'), str(state), '-'],
                         input=snapshot, text=True, capture_output=True, check=True,
                         env=os.environ | {'TMUX_CANOPY_RENDER_HOME': '/home/test'})
            rows = [record.split('\t') for record in run.stdout.strip('\0').split('\0')]
            assert all(len(row) == 3 for row in rows), rows
            return {row[2]: row[1] for row in rows}

        classic = render(appearance='places')
        assert 'Tree Agents Proc Buff' in ANSI.sub('', classic['H:tree'])
        quiet = render()
        header = ANSI.sub('', quiet['H:tree'])
        assert 'Tree · All' in header and header.rstrip().endswith('◆1') and 'Proc Buff' not in header, header
        assert '1 Tree' in quiet['F:'] and '4 Agents' in quiet['F:'] and 'n Next' in quiet['F:']
        # tmux order: no folder rows; the session's directory and branch are a
        # detail on its heading, and rows in that directory carry none.
        assert ANSI.sub('', quiet['S:$0']).rstrip().endswith('api ⎇ feature/auth'), quiet['S:$0']
        assert not any('⎇' in ANSI.sub('', quiet[key]) for key in ('W:@0:$0', 'P:%0:$0', 'P:%1:$0'))
        assert '\x1b[1;32m●\x1b[0m' in quiet['P:%0:$0'] and '▶' not in quiet['P:%0:$0']
        assert '\x1b[1;33m!\x1b[0m' in quiet['P:%0:$0']
        assert 'NEEDS INPUT' not in quiet['P:%0:$0'] and '·hook' not in quiet['P:%0:$0']
        assert '\x1b[2m●\x1b[0m' in quiet['P:%1:$0']  # plain activity is a dim notice, not agent attention
        assert 'P:%0:$0' in quiet and 'W:@0:$0' in quiet and 'S:$0' in quiet
        assert '◈' in quiet['S:$0'] and '▣' in quiet['W:@0:$0']
        assert '\x1b[1mserver\x1b[0m' in quiet['W:@0:$0'], quiet['W:@0:$0']
        assert '0:' in quiet['W:@0:$0'] and '0:' in quiet['P:%0:$0']
        # No tree guides; the session heading's dim rule is its separator.
        assert 'DIR:%0:$0' not in quiet and '─' not in ANSI.sub('', quiet['W:@0:$0']) and '──' in ANSI.sub('', quiet['S:$0'])
        assert 'Tree Agents Proc Buff' in ANSI.sub('', render(appearance='places')['H:tree']), 'default appearance changed'
        print('ok - quiet appearance keeps tree identities and separates active, agent, and unread marks')

        for icons in ('unicode', 'ascii', 'nerdfont'):
            for width in (24, 30, 42, 56):
                rows = render(width=width, icons=icons)
                header = ANSI.sub('', rows['H:tree'])
                assert header.startswith('Tree') and len(header) < width, (icons, width, header)
                assert 'P:%0:$0' in rows and 'DIR:%0:$0' not in rows
                if width == 24:
                    # Too narrow for the branch: the detail keeps just the directory.
                    session = ANSI.sub('', rows['S:$0'])
                    assert 'feature' not in session and session.rstrip().endswith('api'), (icons, session)
                if icons == 'ascii':
                    assert 'Tree - All' in header
                    assert '\x1b' in rows['P:%0:$0'] and '!' in ANSI.sub('', rows['P:%0:$0'])
                    assert '>' in ANSI.sub('', rows['P:%0:$0'])
                if width >= 42:
                    assert 'feature/auth' in rows['S:$0'], (icons, width, rows['S:$0'])
        narrow = render(width=24, long_command=True)
        pane = ANSI.sub('', narrow['P:%1:$0'])
        assert pane.endswith('●') and len(pane) <= 21, pane
        mono = render(theme='mono')
        assert not any('\x1b' in value for value in mono.values()), mono
        hidden = render(state_text='FOOTER\toff\n')
        assert 'F:' not in hidden and ANSI.sub('', hidden['H:tree']).rstrip().endswith('◆1')
        filtered = render(state_text='FILTER\tsession\n')
        assert 'Tree · Session' in ANSI.sub('', filtered['H:tree'])
        pending = render(state_text='MOVE\tP:%0\n')
        assert 'MOVE' in ANSI.sub('', pending['H:tree'])
        summary = render(agent_view=True)
        assert 'Agents' in summary['H:tree'] and ANSI.sub('', summary['H:tree']).rstrip().endswith('◆1')
        assert 'P:%1:$0' not in summary and 'P:%0:$0' in summary
        unknown = render(agent_view=True, verified=False)
        assert '○' in ANSI.sub('', unknown['P:%0:$0']) and '!' not in unknown['P:%0:$0']
        work = render(subagent=True)
        assert '!' in ANSI.sub('', work['P:%0:$0']) and 'Explore' in work['P:%0:$0']
        # A folder folded in another appearance does not hide panes in quiet.
        folded_folder = render(state_text='DIR:%0\n')
        assert 'DIR:%0:$0' not in folded_folder and 'P:%0:$0' in folded_folder, sorted(folded_folder)
        folded = render(state_text='S:$0\n')
        assert '▶' in folded['S:$0'] and not any(k.startswith('P:') for k in folded)
        folded_window = render(state_text='W:@0:$0\n')
        window = ANSI.sub('', folded_window['W:@0:$0'])
        assert '[2p]' in window and '◆' in window and '▶' in window, window
        assert not any(k.startswith('P:') for k in folded_window)
        print('ok - quiet appearance handles widths, themes, footer visibility, agent view and subagents')


if __name__ == '__main__':
    main()
