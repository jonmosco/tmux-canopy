#!/usr/bin/env python3
"""Process graph correctness and provider call counts, without a live server."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def process(pid, parent, command='worker', args=None):
    return f'{pid:6} {parent:6} tester S 00:12 {command} {args or command}\n'


def pane(number, root, sidebar=0, slot=0, path='/fixture/project'):
    return f'session|{number}|window|%{number}|0|{root}|bash|{path}|{sidebar}|{slot}\n'


def main():
    with tempfile.TemporaryDirectory(prefix='tree-processes-', ignore_cleanup_errors=True) as directory:
        temp = Path(directory)
        env = dict(os.environ, PATH=str(temp) + ':' + os.environ['PATH'],
                   PROCESS_FIXTURE=str(temp), HOME='/fixture', TEST_THEME='mono',
                   TMUX_CANOPY_STATE=str(temp / 'state'),
                   TMUX_CANOPY_CLIENT='', TMUX_PANE='%99')
        env.pop('TMUX_CANOPY_RECORD_FORMAT', None)
        (temp / 'state').write_text('VIEW\tprocesses\n')
        wrappers = {
            'tmux': '''#!/bin/bash
printf 'tmux %s\\n' "$1" >> "$PROCESS_FIXTURE/calls"
case "$1" in
  show-option) printf '%s\\n' "$TEST_THEME" ;;
  list-panes) [[ "${FAIL_PANES:-0}" != 1 ]] || exit 1
    exec cat "$PROCESS_FIXTURE/panes" ;;
  display-message) printf '42\\n' ;;
  *) exit 1 ;;
esac
''',
            'ps': '''#!/bin/bash
printf 'ps\\n' >> "$PROCESS_FIXTURE/calls"
[[ "$*" == '-eo pid=,ppid=,user=,stat=,etime=,comm=,args=' ]] || exit 2
[[ "${FAIL_PS:-0}" != 1 ]] || exit 1
exec cat "$PROCESS_FIXTURE/processes"
''',
            'awk': '#!/bin/bash\nprintf "awk\\n" >> "$PROCESS_FIXTURE/calls"\nexec '
                   + shlex.quote(shutil.which('awk')) + ' "$@"\n',
        }
        for name, body in wrappers.items():
            (temp / name).write_text(body)
            (temp / name).chmod(0o755)

        def run(processes, panes, script='process-source', arguments=(), **overrides):
            (temp / 'processes').write_text(processes)
            (temp / 'panes').write_text(panes)
            (temp / 'calls').write_text('')
            return subprocess.run([str(ROOT / 'scripts' / script), *arguments],
                                  env=dict(env, **overrides), capture_output=True,
                                  text=True, timeout=10)

        def tokens(result):
            assert result.returncode == 0, result.stderr
            return [row.split('\t')[0] for row in result.stdout.splitlines()]

        # Deliberately unordered input; a grandchild precedes its parent, with
        # siblings after both a leaf and a non-leaf. Pane roots stay headings.
        processes = (process(112, 110) + process(100, 1, 'bash') +
                     process(110, 100, args=r'worker  --label "two words" C:\tmp') +
                     process(111, 110) + process(120, 100) + process(121, 120) +
                     process(130, 100) + process(210, 200) + process(999, 1) +
                     process(110, 100))
        panes = pane(1, 100) + pane(2, 200) + pane(1, 100) + pane(3, 999, sidebar=1) + pane(4, 999, slot=1)
        expected = ['Q:%1', 'X:110:%1', 'X:112:%1', 'X:111:%1',
                    'X:120:%1', 'X:121:%1', 'X:130:%1', 'Q:%2', 'X:210:%2']
        result = run(processes, panes)
        assert tokens(result) == expected, result.stdout
        assert '\x1b' not in result.stdout
        assert r'worker  --label "two words" C:\tmp' in result.stdout
        assert 'X:110:%1\t    worker' in result.stdout
        assert 'X:112:%1\t      worker' in result.stdout
        calls = (temp / 'calls').read_text().splitlines()
        assert calls.count('ps') == 1 and calls.count('awk') == 1, calls
        assert calls.count('tmux list-panes') == 1, calls
        assert tokens(run(processes, panes, TEST_THEME='ansi')) == expected
        colored = run(processes, panes, TEST_THEME='ansi').stdout
        assert 'worker\x1b[0m' in colored and '\x1b[32m' not in colored
        print('ok - descendants, sibling order, indentation, pane attribution, linked duplicates and themes')

        for elapsed, seconds in [('00:12', 12), ('02:03', 123),
                                 ('01:02:03', 3723), ('2-01:02:03', 176523)]:
            result = run(process(110, 100).replace('00:12', elapsed), pane(1, 100))
            assert tokens(result) == ['Q:%1', 'X:110:%1']
            assert f' {seconds}s ' in result.stdout, result.stdout
        print('ok - portable ps elapsed times retain seconds display')

        assert tokens(run('', pane(1, 100))) == ['Q:%1']
        assert tokens(run(processes, '')) == []
        assert tokens(run(processes, pane(1, 100, sidebar=1))) == []
        nested = run(processes, pane(1, 100) + pane(2, 110))
        assert tokens(nested)[-3:] == ['Q:%2', 'X:112:%2', 'X:111:%2']
        cycle = process(100, 120) + process(110, 100) + process(120, 110)
        assert tokens(run(cycle, pane(1, 100))) == ['Q:%1', 'X:110:%1', 'X:120:%1']
        deep = ''.join(process(i + 1, i) for i in range(100, 1600))
        assert len(tokens(run(deep, pane(1, 100)))) == 1501
        print('ok - empty snapshots, missing roots, nested panes, cycles and deep descendants')

        large = ''.join(process(i, 1) for i in range(1000, 11000))
        assert len(tokens(run(large, ''.join(pane(i, 100 + i) for i in range(50))))) == 50
        calls = (temp / 'calls').read_text().splitlines()
        assert calls.count('awk') == 1 and calls.count('ps') == 1, calls
        print('ok - 50 panes and 10,000 system processes still use one graph renderer')

        for failure in ('FAIL_PS', 'FAIL_PANES'):
            failed = run(processes, panes, **{failure: '1'})
            assert failed.returncode != 0 and failed.stdout == '', failed
            recovered = run(processes, panes, script='sidebar-source', **{failure: '1'})
            assert tokens(recovered) == ['H:failure', 'V:failure'], recovered
        for arguments, separator in ((('--stable',), '\n'), (('--stable', '--read0'), '\0')):
            result = run(processes, panes, script='sidebar-source', arguments=arguments)
            assert result.returncode == 0, result.stderr
            rows = [row.split('\t') for row in result.stdout.split(separator) if row]
            assert rows[0][0] == 'H:'
            assert [row[0] for row in rows[1:]] == expected
            assert all(len(row) == 3 and row[0] == row[2] for row in rows)
        print('ok - provider failure propagation and stable newline/NUL sidebar records')


if __name__ == '__main__':
    main()
