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
                   verified=True, long_command=False, state_text='', status='needs-input', second_agent=False,
                   density='normal', other_path='/projects/api', nul=1):
            state.write_text(state_text)
            d = ['D', icons, 'activity,bell', theme, density, '', '', '',
                 '%0', '@0', '$0', str(width), 'host']
            d.extend([''] * (39 - len(d)))
            d.extend([appearance, '', 'on' if agents else 'off'])
            pane = ['P', '%0', '@0', '0', 'claude', '', '/projects/api', '0', '', '',
                    '', '', '', '', '', '0', '100', 'claude-hook', 'session', '100',
                    'working' if subagent else status, str(now), '', '',
                    f'1,Explore,needs-input,{now},' if subagent else '', '0']
            other = ['P', '%1', '@0', '1',
                     'a-very-long-application-command' if long_command else 'nvim',
                     '', other_path, '0', '', '',
                     '1' if notice else '', '', '', '', '', '0', '101']
            if second_agent:
                other = ['P', '%1', '@0', '1', 'codex', '', other_path, '0', '', '',
                         '', '', '', '', '', '0', '101', 'codex-hook', 'other', '101',
                         'needs-input', str(now), '', '', '', '0']
            records = [d, ['S', '$0', 'acme-api', '1'],
                       ['W', '$0', '@0', '0', 'server', '1', 'off', '', '', '', '0'],
                       pane, other, ['A', '%0', 'claude'],
                       ['G', '%0', 'feature/auth'], ['G', '%1', 'feature/auth']]
            if verified:
                records.append(['V', '%0'])
            if second_agent:
                records += [['A', '%1', 'codex'], ['V', '%1']]
            snapshot = '\n'.join(SEP.join(r) for r in records) + '\n'
            run = sp.run(['awk', '-v', 'header=1', '-v', 'stable=1',
                          '-v', f'agent_view={int(agent_view)}', '-v', f'now={now}', '-v', f'nul={nul}',
                          '-f', str(ROOT / 'lib/tree-render.awk'), str(state), '-'],
                         input=snapshot, text=True, capture_output=True, check=True,
                         env=os.environ | {'TMUX_CANOPY_RENDER_HOME': '/home/test'})
            records = run.stdout.strip('\0').split('\0') if nul else run.stdout.splitlines()
            rows = [record.split('\t') for record in records]
            assert all(len(row) == 3 for row in rows), rows
            return {row[2]: row[1] for row in rows}

        classic = render(appearance='places')
        assert '╭─ Tree ─ All' in ANSI.sub('', classic['H:tree'])
        quiet = render()
        header = ANSI.sub('', quiet['H:tree'])
        assert 'Tree · All' in header and header.rstrip().endswith('◆1') and 'Proc Buff' not in header, header
        # A waiting agent takes priority over the normal view actions.
        footer = ANSI.sub('', quiet['F:'])
        assert footer == '◆ Claude Code waiting  n go  > reply', footer
        assert '\x1b[1;33m' in quiet['F:'], quiet['F:']
        # tmux order: no folder rows; the session's directory and branch are a
        # detail on its heading, and rows in that directory carry none.
        assert ANSI.sub('', quiet['S:$0']).rstrip().endswith('api ⎇ feature/auth'), quiet['S:$0']
        assert not any('⎇' in ANSI.sub('', quiet[key]) for key in ('W:@0:$0', 'P:%0:$0', 'P:%1:$0'))
        assert '\x1b[1;32m●\x1b[0m' in quiet['P:%0:$0'] and '▶' not in quiet['P:%0:$0']
        assert '\x1b[1;33m!\x1b[0m' in quiet['P:%0:$0']
        assert 'NEEDS INPUT' not in quiet['P:%0:$0'] and '·hook' not in quiet['P:%0:$0']
        assert '\x1b[38;5;245m●\x1b[0m' in quiet['P:%1:$0']  # plain activity is muted, not agent attention
        assert 'P:%0:$0' in quiet and 'W:@0:$0' in quiet and 'S:$0' in quiet
        assert '◈' in quiet['S:$0'] and '▣' in quiet['W:@0:$0']
        assert '\x1b[1mserver\x1b[0m' in quiet['W:@0:$0'], quiet['W:@0:$0']
        assert '0:' in quiet['W:@0:$0'] and '0:' in quiet['P:%0:$0']
        # No tree guides; the session heading's dim rule is its separator.
        assert 'DIR:%0:$0' not in quiet and '─' not in ANSI.sub('', quiet['W:@0:$0']) and '──' in ANSI.sub('', quiet['S:$0'])
        assert '╭─ Tree ─ All' in ANSI.sub('', render(appearance='places')['H:tree']), 'folder header changed'
        print('ok - quiet appearance keeps tree identities and separates active, agent, and unread marks')

        def footer(**options):
            return ANSI.sub('', render(**options).get('F:', ''))
        assert footer(status='working') == '↵ focus  a actions  / search  ? help', footer(status='working')
        assert footer(status='working', agents=False) == '↵ focus  a actions  / search  ? help'
        off = ANSI.sub('', render(agents=False)['H:tree']).rstrip()
        assert off.endswith('agent mode off'), off
        assert footer(second_agent=True) == '◆ 2 waiting  n next  > reply', footer(second_agent=True)
        assert footer(icons='ascii') == '! Claude Code waiting  n go  > reply', footer(icons='ascii')
        assert footer(state_text='MOVE\tP:%0\n') == 'Moving  ↵ move here  c cancel'
        assert footer(state_text='LINK\tW:@0:$0\n') == 'Linking  ↵ link here  c cancel'
        assert footer(state_text=f'DELETE\tP:%1\t{now}\n') == 'x again within 5 s to delete'
        # Narrow sidebars keep the most important part and drop what will not fit.
        assert footer(width=30) == '◆ Claude Code waiting', footer(width=30)
        assert footer(width=24) == '◆ 1 waiting  n go', footer(width=24)
        assert footer(width=24, status='working') == '↵ focus  a actions', footer(width=24, status='working')
        # Agents advertises its own actions; a waiting request still overrides it.
        assert footer(agent_view=True, status='working') == '↵ focus  n waiting  > reply  i summary', \
            footer(agent_view=True, status='working')
        assert footer(agent_view=True) == '◆ Claude Code waiting  n go  > reply', footer(agent_view=True)
        assert footer(agent_view=True, status='working', width=30) == '↵ focus  n waiting', \
            footer(agent_view=True, status='working', width=30)
        assert footer(appearance='places', status='working') == '↵ focus  a actions  / search  ? help'
        assert footer(agent_view=True, status='working', state_text='FOOTER\toff\n') == ''
        print('ok - the quiet footer follows what is pending: a move, a delete, agents waiting, or the keys')

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

        # An interrupted agent is not asking a question: it has its own red mark,
        # separate from the amber one, in the row, header, footer and Agents view.
        broken = render(status='interrupted')
        assert '\x1b[1;31m\u2715\x1b[0m' in broken['P:%0:$0'] and '!' not in ANSI.sub('', broken['P:%0:$0']), broken['P:%0:$0']
        assert ANSI.sub('', broken['H:tree']).rstrip().endswith('\u27151') and '\x1b[1;31m' in broken['H:tree'], broken['H:tree']
        # "interrupted" is longer than "waiting", so at 42 columns the reply hint is the part that gives way.
        assert footer(status='interrupted') == '\u2715 Claude Code interrupted  n go', footer(status='interrupted')
        assert footer(status='interrupted', width=56) == '\u2715 Claude Code interrupted  n go  > reply'
        assert '\x1b[1;31m' in broken['F:'] and '\x1b[1;33m' not in broken['F:'], broken['F:']
        assert ANSI.sub('', render(status='interrupted', agent_view=True)['H:tree']).rstrip().endswith('\u27151')
        # Waiting and interrupted at once: both are counted and both keep their color.
        both = render(status='interrupted', second_agent=True)
        assert ANSI.sub('', both['H:tree']).rstrip().endswith('\u25c61 \u27151'), ANSI.sub('', both['H:tree'])
        assert footer(status='interrupted', second_agent=True) == '\u25c6 Codex waiting  \u27151  n go  > reply', \
            footer(status='interrupted', second_agent=True)
        assert footer(status='interrupted', second_agent=True, width=30).startswith('\u25c6 Codex waiting')
        # ASCII uses x, and mono keeps the glyph without color.
        ascii_broken = render(status='interrupted', icons='ascii')
        assert '\x1b[1;31mx\x1b[0m' in ascii_broken['P:%0:$0'], ascii_broken['P:%0:$0']
        assert footer(status='interrupted', icons='ascii') == 'x Claude Code interrupted  n go'
        mono_broken = render(status='interrupted', theme='mono')
        assert '\u2715' in mono_broken['P:%0:$0'] and not any('\x1b' in value for value in mono_broken.values())
        # A folded window shows the red mark too, and more than one interrupted agent
        # is a count rather than a repeated mark.
        folded_broken = ANSI.sub('', render(status='interrupted', state_text='W:@0:$0\n')['W:@0:$0'])
        assert '\u2715' in folded_broken and '\u25c6' not in folded_broken, folded_broken
        # Every look colors the mark, not just quiet: lazygit drew it dim before.
        for look in ('lazygit', 'places'):
            row = render(appearance=look, status='interrupted')['P:%0:$0']
            assert re.search(r'\x1b\[1;31m[^\x1b]*\u2715', row), (look, row)
            window = render(appearance=look, status='interrupted', state_text='W:@0:$0\n')['W:@0:$0']
            assert re.search(r'\x1b\[1;31m[^\x1b]*\u2715', window), (look, window)
        print('ok - an interrupted agent has its own red mark, count and footer, apart from one that is waiting')

        # Detailed density makes a session a card: the directory and branch it
        # claims move from the heading's right edge to a line of their own,
        # aligned under the name, so the name keeps the whole heading.
        card = render(density='detailed')
        heading, detail = ANSI.sub('', card['S:$0']).split('\n')
        assert heading.startswith('\u25be \u25c8 acme-api \u2500') and '\u2387' not in heading, heading
        assert detail == '    api \u2387 feature/auth' and detail.index('api') == heading.index('acme-api'), (heading, detail)
        # The rows below still say nothing the session already claims.
        assert not any('\u2387' in ANSI.sub('', card[key]) for key in ('W:@0:$0', 'P:%0:$0', 'P:%1:$0'))
        # Other densities keep the single line with the detail at the right edge.
        for density in ('normal', 'compact', 'minimal'):
            plain = ANSI.sub('', render(density=density)['S:$0'])
            assert '\n' not in plain and plain.rstrip().endswith('api \u2387 feature/auth'), (density, plain)
        # A folded session is one row, and so is the legacy one-line-per-object framing.
        assert '\n' not in render(density='detailed', state_text='S:$0\n')['S:$0']
        assert ANSI.sub('', render(density='detailed', nul=0)['S:$0']).rstrip().endswith('api \u2387 feature/auth')
        # Panes in different directories claim nothing at the session level: no card.
        mixed = render(density='detailed', other_path='/projects/web')
        assert '\n' not in mixed['S:$0'] and '\u2387' not in ANSI.sub('', mixed['S:$0'])
        # ASCII and narrow sidebars: the branch gives way, the name does not.
        ascii_card = ANSI.sub('', render(density='detailed', icons='ascii')['S:$0']).split('\n')
        assert ascii_card[1] == '    api [git:feature/auth]', ascii_card
        narrow_card = ANSI.sub('', render(density='detailed', width=24)['S:$0']).split('\n')
        assert len(narrow_card) == 2 and narrow_card[1].endswith('\u2026') and len(narrow_card[1]) <= 21, narrow_card
        assert 'acme-api' in narrow_card[0]
        print('ok - a detailed session is a card: its directory and branch sit on their own line under the name')


if __name__ == '__main__':
    main()
