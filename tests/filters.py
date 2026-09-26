#!/usr/bin/env python3
"""Tree visibility, filtered parent navigation, and real native filter controls."""
import fcntl
import os
from pathlib import Path
import pty
import shutil
import struct
import subprocess as sp
import sys
import tempfile
import termios
import threading
import time
from support import install_fzf_probe

ROOT = Path(__file__).resolve().parents[1]


def snapshots():
    with tempfile.TemporaryDirectory(prefix='canopy-filter-snapshot-') as folder:
        state = Path(folder) / 'state'
        def render(saved='', *, default='all', window='', title='', width=42, notices='all',
                   switcher=False, target='', owner='owner'):
            state.write_text(saved)
            data = [
                ['D', 'ascii', notices, 'mono', 'normal', '', '', '', '%0', '@0', '$0', str(width), 'host', 'on', default, window, title],
                ['S', '$0', 'one', '1'], ['S', '$1', 'two', '1'],
                ['W', '$0', '@0', '0', 'Orchestrator', '2', 'off', '1', '1', ''],
                ['W', '$0', '@1', '1', 'worker', '1', 'off', '', '', ''],
                ['W', '$1', '@0', '5', 'Orchestrator', '2', 'off', '1', '1', ''],
                ['W', '$1', '@2', '0', 'orphan-alert', '1', 'off', '1', '', ''],
                ['P', '%0', '@0', '0', 'bash', 'clean-worker', '/work/repo', '0', '', '', '', '', '', '', '', ''],
                ['P', '%1', '@0', '1', 'sleep', 'Orch:API', '/work/repo', '0', '', '', '1', '1', '', '', '', ''],
                ['P', '%2', '@1', '0', 'bash', 'worker', '/other', '0', '', '', '', '', '', '', '', ''],
                ['P', '%3', '@2', '0', 'bash', 'clean', '/other', '0', '', '', '', '', '', '', '', ''],
                ['P', '%90', '@0', '2', 'fzf', 'Orch:hidden', '/work/repo', '0', '1', '', '1', '', '', '', '', ''],
                ['P', '%91', '@0', '3', '', 'Orch:slot', '/work/repo', '0', '', '1', '1', '', '', '', '', ''],
                ['C', 'owner', '$1', '@0', '%0'], ['C', 'other', '$0', '@0', '%0'],
            ]
            raw = sp.check_output(['awk', '-v', 'stable=1', '-v', 'nul=1', '-v', 'header=1',
                                   '-v', f'switcher={int(switcher)}', '-v', 'now=100', '-f',
                                   str(ROOT / 'lib/tree-render.awk'), str(state), '-'],
                                  input='\n'.join('\x1f'.join(row) for row in data)+'\n', text=True,
                                  env=os.environ | {'TMUX_CANOPY_RENDER_CLIENT': owner,
                                                    'TMUX_CANOPY_FILTER_TARGET': target})
            assert state.read_text() == saved
            if target:
                return raw
            rows = [row.split('\t') for row in raw.rstrip('\0').split('\0')]
            assert all(len(row) == 3 for row in rows)
            assert len({row[2] for row in rows}) == len(rows)
            return rows

        def ids(rows):
            return [row[2] for row in rows]

        all_ids = ids(render())
        assert 'P:%0:$0' in all_ids and 'P:%1:$1' in all_ids and 'P:%90:$0' not in all_ids
        current = ids(render('FILTER\tsession\n'))
        assert 'S:$0' not in current and 'P:%1:$1' in current
        assert 'S:$1' not in ids(render('FILTER\tsession\n', owner='other'))
        unread = render('FILTER\tunread\n')
        assert [r[0] for r in unread if r[0].startswith('P:')] == ['P:%1', 'P:%1']
        assert 'W:@2:$1' in ids(unread) and 'P:%3:$1' not in ids(unread)
        assert all('p]' not in r[1] for r in unread if r[0].startswith('W:'))
        folded = 'FILTER\tunread\nS:$0\nW:@0:$1\n'
        rows = render(folded)
        assert not any(r[0].startswith('P:') for r in rows)
        assert '1/2p' in next(r[1] for r in rows if r[0] == 'W:@0:$1')
        assert 'P:%1\t$0\n' == render(folded, target='S:$0')
        assert 'P:%1\t$1\n' == render(folded, target='W:@0:$1')
        assert render(folded, target='W:@1:$0') == ''
        assert render('FILTER\tsession\n', target='W:@0:$0') == ''
        assert render('FILTER\tunread\n', target='W:@2:$1') == 'W:@2:$1\t\n'
        assert render(target='S:$0') == 'S:$0\t\n'
        combined = 'FILTER\tsession\nFILTER_WINDOW\tORCH\nFILTER_TITLE\torch:api\n'
        rows = render(combined)
        assert ids(rows) == ['H:tree', 'S:$1', 'W:@0:$1', 'P:%1:$1']
        assert '+W+T' in rows[0][1]
        assert 'clean-worker' not in ''.join(r[1] for r in rows)
        for field in ('FILTER_WINDOW', 'FILTER_TITLE'):
            rows = render(f'{field}\t.*\n')
            assert ids(rows) == ['H:tree', 'V:empty'], 'text filters are literal, not regex'
        assert ids(render(default='session', title='orch:api')) == ids(render(combined))
        assert ids(render('FILTER\tall\nFILTER_WINDOW\t\nFILTER_TITLE\t\n', default='unread', window='absent', title='absent')) == all_ids
        assert ids(render('FILTER\tunread\n', notices='none')) == ['H:tree', 'V:empty']
        quick = ids(render(combined+'S:$1\n', switcher=True))
        assert 'P:%0:$0' in quick and 'P:%3:$1' in quick
        for width in (24, 30, 42, 80):
            row = render(combined+'DELETE\tW:@0:$1\t100\n', width=width)[0]
            assert len(row[1]) <= width-2, (width, row[1])
            assert 'DELETE' in row[1] and '+W+T' in row[1]
    print('ok - scope, unread, literal text, config overrides, linked identities, folds, compact counts, empty results and parent targets')


def live():
    executable = shutil.which('tmux')
    socket = f'canopy-filters-{os.getpid()}'
    env = {k: v for k, v in os.environ.items() if k not in ('TMUX', 'TMUX_PANE')}
    env['TERM'] = 'xterm-256color'
    process = master = None
    with tempfile.TemporaryDirectory(prefix='canopy-filters-live-') as folder:
        temp = Path(folder)
        selected, state_path = temp/'selected', temp/'state-path'
        output = bytearray()
        def tm(*args):
            result = sp.run([executable, '-L', socket, *args], env=env, capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, (args, result.stderr)
            return result.stdout.strip()
        def wait(predicate, message):
            deadline = time.monotonic()+8
            while time.monotonic() < deadline:
                if predicate(): return
                time.sleep(.04)
            raise AssertionError(message)
        def display(pane, fmt): return tm('display-message', '-p', '-t', pane, fmt)
        def run(name, *args):
            result = sp.run([str(ROOT/'scripts'/name), *args], env=script_env, text=True, capture_output=True, timeout=15)
            assert result.returncode == 0, (name, result.stderr)
            return result.stdout
        def screen(): return tm('capture-pane', '-p', '-t', sidebar)
        def menu(key='F'):
            output.clear(); tm('send-keys', '-t', sidebar, key)
            try:
                wait(lambda: b'Tree filters' in output, 'filter menu opens')
            except AssertionError:
                raise AssertionError(('filter menu opens',screen(),bytes(output[-2500:]))) from None
        def probe():
            selected.unlink(missing_ok=True)
            def selected_ready():
                if selected.exists() and selected.stat().st_size: return True
                tm('send-keys', '-t', sidebar, 'M-z');time.sleep(.08)
                return False
            wait(selected_ready, 'selection probe')
            return selected.read_text().split('|')
        try:
            first = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'one', '-n', 'Orchestrator', '-x', '160', '-y', '44', '-P', '-F', '#{pane_id}', 'sleep 600')
            worker = tm('new-window', '-d', '-t', 'one:', '-n', 'worker', '-P', '-F', '#{pane_id}', 'sleep 600')
            other = tm('new-session', '-d', '-s', 'two', '-x', '160', '-y', '44', '-P', '-F', '#{pane_id}', 'sleep 600')
            for p,t in ((first,'orch:api'),(worker,'worker:api'),(other,'orch:other')):
                tm('set-option','-p','-t',p,'allow-set-title','off');tm('select-pane','-t',p,'-T',t)
            tm('set-option','-g','default-shell','/bin/bash');tm('set-option','-g','status','off')
            tm('set-option','-g','escape-time','10')
            # Native prompt key mode otherwise inherits EDITOR/VISUAL.
            tm('set-option','-g','status-keys','emacs')
            for key,value in [('scope','global'),('transition','slot'),('preview','off'),('theme','mono'),('notifications','activity,bell')]:
                tm('set-option','-g','@tmux-canopy-'+key,value)
            script_env=env|{'TMUX':display(first,'#{socket_path},#{pid},0'),'TMUX_PANE':first}
            install_fzf_probe(temp,[f'''alt-y:execute-silent(printf '%s' "$TMUX_CANOPY_STATE" > {state_path})''',
                f"alt-z:execute-silent(printf '%s|%s|%s' {{1}} {{3}} {{q}} > {selected})"],script_env)
            master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',44,160,0,0))
            client=os.ttyname(slave)
            process=sp.Popen([executable,'-L',socket,'attach-session','-t','one'],env=env,stdin=slave,stdout=slave,stderr=slave,start_new_session=True)
            os.close(slave)
            def drain():
                try:
                    while data:=os.read(master,65536):output.extend(data)
                except OSError:pass
            threading.Thread(target=drain,daemon=True).start()
            wait(lambda:client in tm('list-clients','-F','#{client_tty}'),'client attached')
            script_env['TMUX_CANOPY_CLIENT']=client
            sp.run([str(ROOT/'tmux-canopy.tmux')],env=script_env,check=True,timeout=15)
            run('toggle',client,first,'42','global','T','Tab','slot')
            sidebar=next(r.split('|')[0] for r in tm('list-panes','-a','-F','#{pane_id}|#{@tmux_canopy}').splitlines() if r.endswith('|1'))
            script_env['TMUX_PANE']=sidebar
            wait(lambda:'[All]' in screen(),'initial header')
            def state_ready():
                if state_path.exists() and state_path.stat().st_size: return True
                tm('send-keys','-t',sidebar,'M-y');time.sleep(.08)
                return False
            wait(state_ready,'state path')
            state=Path(state_path.read_text());script_env['TMUX_CANOPY_STATE']=str(state)
            ui_pid=sp.check_output(['pgrep','-P',display(sidebar,'#{pane_pid}'),'-x','fzf'],text=True).strip()
            menu();os.write(master,b's');wait(lambda:'[Session]' in screen(),'session filter applied')
            assert 'two' not in screen()
            output.clear();menu();os.write(master,b'w')
            wait(lambda:b'Window name contains' in output,'window prompt');os.write(master,b'ORCH\r')
            wait(lambda:'FILTER_WINDOW\tORCH\n' in state.read_text(),'window text saved')
            wait(lambda:'worker' not in screen(),'nonmatching window removed')
            output.clear();menu();os.write(master,b't')
            wait(lambda:b'Pane title contains (empty clears)' in output,'title prompt');os.write(master,b'orch:api\r')
            wait(lambda:'FILTER_TITLE\torch:api\n' in state.read_text(),'title saved')
            wait(lambda:'+W+T' in screen(),'text filter header refreshed')
            saved=state.read_bytes();output.clear();menu();os.write(master,b't')
            wait(lambda:b'Pane title contains (empty clears)' in output,'title edit');os.write(master,b'\x1b');time.sleep(.4)
            assert state.read_bytes()==saved
            tm('send-keys','-t',sidebar,'/');tm('send-keys','-t',sidebar,'-l','sleep');time.sleep(.15)
            before=probe();menu('C-f');os.write(master,b'a')
            wait(lambda:'FILTER\tall\n' in state.read_text(),'scope changed while searching')
            time.sleep(.2);assert probe()==before
            tm('send-keys','-t',sidebar,'Escape');time.sleep(.4)
            print('ok - native filter menu/prompts, cancel, text composition, query/selection preservation and Ctrl-f')
            run('tree-filter','set-title','nothing-matches');wait(lambda:'No matches' in screen(),'empty result hint')
            menu();os.write(master,b'c');wait(lambda:'[All]' in screen() and 'worker' in screen(),'clear all recovers')
            # A collapsed window's active pane need not be the unread pane.
            urgent=tm('split-window','-d','-v','-t',worker,'-P','-F','#{pane_id}','sleep 600')
            worker_window=display(worker,'#{window_id}'); first_session=display(first,'#{session_id}')
            run('notify','set',worker_window,urgent,'activity')
            menu();os.write(master,b'u');wait(lambda:'[Unread]' in screen(),'unread mode')
            run('sidebar-action','collapse',f'W:{worker_window}:{first_session}')
            run('sidebar-action','activate',f'W:{worker_window}:{first_session}')
            wait(lambda:tm('list-clients','-F','#{pane_id}')==urgent,'filtered parent focuses unread descendant')
            wait(lambda:'No matches' in screen(),'focusing clears terminal notices')
            run('tree-filter','clear')
            print('ok - unread mode and collapsed parent activation target a matching pane, then clear read notifications')
            # Default settings can be restored after temporary per-sidebar overrides.
            tm('set-option','-g','@tmux-canopy-filter','session')
            run('tree-filter','defaults');wait(lambda:'[Session]' in screen(),'configured defaults')
            tm('switch-client','-c',client,'-t','two')
            wait(lambda:'one' not in screen() and 'two' in screen(),'current session follows owner')
            # Input remains literal through tmux prompts, labels, state and matching.
            sentinel=temp/'injected'
            hostile=f"x,#(touch {sentinel}); ' $HOME \\ y"
            run('tree-filter','set-title',hostile)
            wait(lambda:'No matches' in screen(),'literal filter rendered')
            menu();os.write(master,b't')
            wait(lambda:b'Pane title contains (empty clears)' in output,'literal initial prompt value')
            os.write(master,b'\x15'+hostile.encode()+b'\r');time.sleep(.3)
            assert not sentinel.exists() and hostile in state.read_text(), (sentinel.exists(), hostile, state.read_text(), bytes(output[-2500:]))
            run('tree-filter','clear')
            assert sp.check_output(['pgrep','-P',display(sidebar,'#{pane_pid}'),'-x','fzf'],text=True).strip()==ui_pid
            print('ok - empty recovery, defaults, owner session following, literal menu text and persistent fzf')
        finally:
            sp.run([executable,'-L',socket,'kill-server'],env=env,capture_output=True)
            if process is not None:process.wait(timeout=10)
            if master is not None:os.close(master)


if __name__=='__main__':
    snapshots()
    if '--snapshots-only' not in sys.argv:live()
