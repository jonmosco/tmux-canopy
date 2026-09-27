#!/usr/bin/env python3
"""Aggregated agent-attention summaries on collapsed window/session rows."""
import os
from pathlib import Path
import subprocess as sp
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def agent_pane(pane_id, window_id, index, command, pane_pid, status, dead='0'):
    # Field order mirrors scripts/tree-source's panes format string.
    return ['P', pane_id, window_id, index, command, '', '/work', dead, '', '',
            '0', '0', '0', '', '', '0', pane_pid, command + '-hook', 'sess1',
            pane_pid, status, '0', '', '']


def main():
    with tempfile.TemporaryDirectory(prefix='canopy-attention-test-', ignore_cleanup_errors=True) as directory:
        state = Path(directory) / 'state'

        def render(*, collapsed='', icons='nerdfont', theme='ansi', extra_rows=()):
            state.write_text(collapsed)
            data = [
                ['D', icons, 'all', theme, 'normal', '', '', '', '%0', '@0', '$0', '42', 'host'],
                ['S', '$0', 'work', '1'],
                ['W', '$0', '@0', '0', 'web', '1', 'off', '0', '0', '0'],
                ['P', '%1', '@0', '1', 'bash', '', '/work', '0', '', '', '0', '0', '0', '', '', '0', '', '', '', '', '', '', '', ''],
                *extra_rows,
            ]
            result = sp.check_output(['awk', '-v', 'stable=1', '-v', 'nul=1', '-f', str(ROOT/'lib/tree-render.awk'), str(state), '-'],
                                     input='\n'.join('\x1f'.join(row) for row in data)+'\n', text=True,
                                     env=os.environ | {'TMUX_CANOPY_RENDER_CLIENT': '', 'TMUX_CANOPY_RENDER_HOME': '/home/test'})
            rows = [line.split('\t') for line in result.rstrip('\0').split('\0')]
            assert all(len(row) == 3 for row in rows)
            return {row[2]: row[1] for row in rows}

        need_pane = agent_pane('%10', '@0', '2', 'claude', '111', 'needs-input')
        verified_10 = ['V', '%10']
        work_pane = agent_pane('%11', '@0', '3', 'codex', '112', 'working')
        verified_11 = ['V', '%11']

        # Collapsed window aggregates a single needs-input pane, undecorated
        # (count omitted below 2, matching the unread-badge count convention).
        collapsed = render(collapsed='W:@0:$0\n', extra_rows=[need_pane, verified_10])
        assert '\x1b[1;33m◆\x1b[0m' in collapsed['W:@0:$0']
        assert not any(k.startswith('P:') for k in collapsed)

        # Needs-input outranks working: both present, only the need count shows.
        collapsed_both = render(collapsed='W:@0:$0\n', extra_rows=[need_pane, verified_10, work_pane, verified_11])
        assert '\x1b[1;33m◆\x1b[0m' in collapsed_both['W:@0:$0']
        assert '\x1b[1;36m▷' not in collapsed_both['W:@0:$0']

        # Two needs-input panes roll up to a counted badge.
        need_pane_2 = agent_pane('%12', '@0', '4', 'gemini', '113', 'needs-input')
        verified_12 = ['V', '%12']
        collapsed_two = render(collapsed='W:@0:$0\n', extra_rows=[need_pane, verified_10, need_pane_2, verified_12])
        assert '\x1b[1;33m◆2\x1b[0m' in collapsed_two['W:@0:$0']

        # Working-only rolls up with the working glyph/color instead.
        collapsed_work = render(collapsed='W:@0:$0\n', extra_rows=[work_pane, verified_11])
        assert '\x1b[1;36m▷\x1b[0m' in collapsed_work['W:@0:$0']

        # Finished (ready/turn-ended/session-ended, and interrupted counts as
        # needs-input) is the lowest tier, shown only when nothing outranks it.
        done_pane = agent_pane('%13', '@0', '5', 'pi', '114', 'turn-ended')
        verified_13 = ['V', '%13']
        collapsed_done = render(collapsed='W:@0:$0\n', extra_rows=[done_pane, verified_13])
        assert '\x1b[2m✓\x1b[0m' in collapsed_done['W:@0:$0']
        collapsed_done_and_work = render(collapsed='W:@0:$0\n', extra_rows=[done_pane, verified_13, work_pane, verified_11])
        assert '\x1b[1;36m▷\x1b[0m' in collapsed_done_and_work['W:@0:$0']
        assert '✓' not in collapsed_done_and_work['W:@0:$0']
        interrupted_pane = agent_pane('%14', '@0', '6', 'omp', '115', 'interrupted')
        verified_14 = ['V', '%14']
        collapsed_interrupted = render(collapsed='W:@0:$0\n', extra_rows=[interrupted_pane, verified_14])
        assert '\x1b[1;33m◆\x1b[0m' in collapsed_interrupted['W:@0:$0']

        # Collapsed session sees the same rollup as its collapsed window did.
        session_collapsed = render(collapsed='S:$0\n', extra_rows=[need_pane, verified_10])
        assert '\x1b[1;33m◆\x1b[0m' in session_collapsed['S:$0']

        # Expanded: the pane's own inline badge already shows it, so the
        # window row itself is not redundantly decorated.
        expanded = render(extra_rows=[need_pane, verified_10])
        assert 'NEEDS INPUT' in expanded['P:%10:$0'] and '·hook' in expanded['P:%10:$0']
        assert '◆' not in expanded['W:@0:$0']

        # ascii theme uses a plain-text glyph instead of the Unicode diamond.
        ascii_collapsed = render(collapsed='W:@0:$0\n', icons='ascii', extra_rows=[need_pane, verified_10])
        assert '!' in ascii_collapsed['W:@0:$0'] and '◆' not in ascii_collapsed['W:@0:$0']

        # mono theme carries the glyph without ANSI color codes.
        mono_collapsed = render(collapsed='W:@0:$0\n', theme='mono', extra_rows=[need_pane, verified_10])
        assert '◆' in mono_collapsed['W:@0:$0'] and '\x1b' not in mono_collapsed['W:@0:$0']

        print('ok - agent attention summaries aggregate onto collapsed window/session rows with needs-input priority')


if __name__ == '__main__':
    main()
