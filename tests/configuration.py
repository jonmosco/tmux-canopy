#!/usr/bin/env python3
"""Reload restores owned configuration without clobbering later user edits."""
import os
import re
from pathlib import Path
import subprocess as sp
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    socket = f'canopy-config-test-{os.getpid()}'
    env = os.environ.copy()
    env.pop('TMUX', None)
    env.pop('TMUX_PANE', None)

    def tm(*args):
        result = sp.run(['tmux', '-L', socket, *args], env=env, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, (args, result.stderr)
        return result.stdout.strip()

    def binding(key):
        lines = tm('list-keys', '-T', 'prefix', '-F', '#{key_string}|#{key_repeat}|#{key_note}|#{key_command}')
        return next((line for line in lines.splitlines() if line.startswith(key+'|')), '')

    def load():
        result = sp.run(['bash', str(ROOT/'tmux-canopy.tmux')], env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0 and not result.stderr, result.stderr

    try:
        pane = tm('-f', '/dev/null', 'new-session', '-d', '-P', '-F', '#{pane_id}', 'sleep 180')
        env['TMUX'] = tm('display-message', '-p', '-t', pane, '#{socket_path},#{pid},0')
        tm('bind-key', '-r', '-N', 'my "navigation" $note', 'n', 'display-message', 'original; #{version} $literal')
        tm('bind-key', 'T', 'display-message', 'original T')
        tm('unbind-key', 'Tab')
        original_n, original_t = binding('n'), binding('T')
        tm('set-window-option', '-g', 'monitor-activity', 'off')
        tm('set-window-option', '-g', 'monitor-bell', 'on')
        tm('set-window-option', '-g', 'monitor-silence', '17')
        tm('set-window-option', '-g', 'window-status-activity-style', 'fg=blue')
        tm('set-option', '-g', '@tmux-canopy-notifications', 'all')
        load()
        with tempfile.TemporaryDirectory(prefix='canopy-agent-option-') as directory:
            state = Path(directory) / 'state'
            state.touch()
            source_env = env | {'TMUX_PANE': pane, 'TMUX_CANOPY_STATE': str(state),
                                'TMUX_CANOPY_HEADER': '1'}

            def source(*args):
                result = sp.run([str(ROOT / 'scripts/tree-source'), *args], env=source_env,
                                capture_output=True, text=True, timeout=15)
                assert result.returncode == 0, result.stderr
                return result.stdout

            def ui_options():
                result = sp.run(['bash', '-c',
                                 'source "$1"; source "$2"; sidebar_ui_options "$3"; printf "%s\\n" "${SIDEBAR_FZF_ARGS[@]}"',
                                 'bash', str(ROOT / 'scripts/lib.sh'), str(ROOT / 'scripts/ui-options.sh'), pane],
                                env=source_env, capture_output=True, text=True, timeout=15)
                assert result.returncode == 0, result.stderr
                return result.stdout

            # Agent mode controls whether the Agents view can be rendered.
            agent_mode = lambda text: 'agent mode off' not in re.sub(r'\x1b\[[0-9;]*m', '', text)
            assert not agent_mode(source()) and 'Agents' not in source('--agents')
            assert source('--needs-input') == ''
            binds = ui_options()
            assert '--bind=4:' in binds and '--bind=n:' in binds and '--bind=A:' in binds
            assert '--bind=z:' in binds and '--bind=N:' in binds and '--bind=b:' in binds
            assert 'scroll-up:offset-up,scroll-down:offset-down' in binds
            assert 'unbind(F,f,g,h,H,A,i,j,k,l,L,m,c,r,x,u,U,w,a,p,P,1,2,3,4,[,],s,v,t,S,N,n,z,b,>,?)' in binds
            assert 'rebind(F,f,g,h,H,A,i,j,k,l,L,m,c,r,x,u,U,w,a,p,P,1,2,3,4,[,],s,v,t,S,N,n,z,b,>,?)' in binds
            assert '--bind=ctrl-t:' in binds
            tm('set-option', '-g', '@tmux-canopy-agents', 'on')
            load()
            assert 'Agents · All' in re.sub(r'\x1b\[[0-9;]*m', '', source('--agents'))
            client = '/dev/ttys-agent-test'
            key = sp.check_output(['cksum'], input=client.encode()).split()[0].decode()
            tm('set-option', '-g', '@tmux_canopy_agents_' + key, 'off')
            hidden = sp.run([str(ROOT / 'scripts/tree-source')], env=source_env | {'TMUX_CANOPY_CLIENT': client},
                            capture_output=True, text=True, timeout=15)
            assert hidden.returncode == 0 and not agent_mode(hidden.stdout), hidden.stderr
            tm('set-option', '-g', '@tmux_canopy_agents_' + key, 'on')
            tm('set-option', '-g', '@tmux-canopy-agents', 'off')
            load()
            shown = sp.run([str(ROOT / 'scripts/tree-source')], env=source_env | {'TMUX_CANOPY_CLIENT': client},
                           capture_output=True, text=True, timeout=15)
            assert shown.returncode == 0 and agent_mode(shown.stdout), shown.stderr
            assert not agent_mode(source())
            print('ok - agent mode follows the client toggle and the global default')
        assert tm('show-option', '-gqv', '@tmux_canopy_icon_theme') == 'unicode'
        tm('set-option', '-g', '@tmux-canopy-icon-theme', 'nerdfont')
        load()
        assert tm('show-option', '-gqv', '@tmux_canopy_icon_theme') == 'nerdfont'
        tm('set-option', '-g', '@tmux-canopy-icon-theme', 'auto')
        load()
        assert tm('show-option', '-gqv', '@tmux_canopy_icon_theme') == 'unicode'
        # quiet is the default appearance; ascii is quiet without glyphs.
        assert tm('show-option', '-gqv', '@tmux_canopy_appearance') == 'quiet'
        tm('set-option', '-g', '@tmux-canopy-appearance', 'ascii')
        load()
        assert tm('show-option', '-gqv', '@tmux_canopy_appearance') == 'quiet'
        assert tm('show-option', '-gqv', '@tmux_canopy_icon_theme') == 'ascii'
        tm('set-option', '-g', '@tmux-canopy-icon-theme', 'auto')
        tm('set-option', '-g', '@tmux-canopy-appearance', 'default')
        load()
        assert tm('show-option', '-gqv', '@tmux_canopy_icon_theme') == 'unicode'
        assert tm('show-option', '-gqv', '@tmux_canopy_appearance') == 'quiet'
        # folders keeps the directory-grouped tree; places is still accepted.
        for name in ('folders', 'places'):
            tm('set-option', '-g', '@tmux-canopy-appearance', name)
            load()
            assert tm('show-option', '-gqv', '@tmux_canopy_appearance') == 'places', name
        tm('set-option', '-g', '@tmux-canopy-appearance', 'quiet')
        load()
        assert tm('show-option', '-gqv', '@tmux_canopy_appearance') == 'quiet'
        assert tm('show-option', '-gqv', '@tmux_canopy_icon_theme') == 'unicode'
        tm('set-option', '-g', '@tmux-canopy-appearance', 'unexpected')
        load()
        assert tm('show-option', '-gqv', '@tmux_canopy_appearance') == 'quiet'
        tm('set-option', '-g', '@tmux-canopy-appearance', 'nope')
        load()
        assert tm('show-option', '-gqv', '@tmux_canopy_appearance') == 'quiet'
        assert tm('show-option', '-gqv', '@tmux_canopy_animate') == 'on'
        tm('set-option', '-g', '@tmux-canopy-animate', 'off')
        load()
        assert tm('show-option', '-gqv', '@tmux_canopy_animate') == 'off'
        tm('set-option', '-g', '@tmux-canopy-animate', 'maybe')
        load()
        assert tm('show-option', '-gqv', '@tmux_canopy_animate') == 'on'
        assert 'navigate' in binding('n') and 'toggle' in binding('T')
        assert 'global' in binding('T') and 'slot' in binding('T')
        installed = binding('n')
        load()
        assert binding('n') == installed
        tm('set-option', '-g', '@tmux-canopy-smooth-navigation', 'off')
        tm('set-option', '-g', '@tmux-canopy-last-window-key', 'off')
        tm('set-option', '-g', '@tmux-canopy-key', 'Y')
        tm('set-option', '-g', '@tmux-canopy-notifications', 'none')
        load()
        assert binding('n') == original_n, (binding('n'), original_n)
        assert binding('T') == original_t
        assert binding('Tab') == ''
        assert 'toggle' in binding('Y')
        assert tm('show-window-option', '-gv', 'monitor-activity') == 'off'
        assert tm('show-window-option', '-gv', 'monitor-bell') == 'on'
        assert tm('show-window-option', '-gv', 'monitor-silence') == '17'
        assert tm('show-window-option', '-gv', 'window-status-activity-style') == 'fg=blue'
        print('ok - original commands, notes, repeat flags and absent keys restore on disable/key change')
        tm('set-option', '-g', '@tmux-canopy-smooth-navigation', 'on')
        tm('set-option', '-g', '@tmux-canopy-notifications', 'all')
        load()
        tm('bind-key', 'n', 'display-message', 'later user command')
        tm('set-window-option', '-g', 'monitor-silence', '42')
        tm('set-window-option', '-g', 'window-status-activity-style', 'fg=red')
        later = binding('n')
        load()
        assert binding('n') == later
        assert tm('show-window-option', '-gv', 'monitor-silence') == '42'
        assert tm('show-window-option', '-gv', 'window-status-activity-style') == 'fg=red'
        tm('set-option', '-g', '@tmux-canopy-smooth-navigation', 'off')
        tm('set-option', '-g', '@tmux-canopy-notifications', 'none')
        load()
        assert binding('n') == later
        assert tm('show-window-option', '-gv', 'monitor-silence') == '42'
        assert tm('show-window-option', '-gv', 'window-status-activity-style') == 'fg=red'
        print('ok - later user bindings and monitor settings survive reload and disable')

        # A reload clears whatever sits at Canopy's own hook and alias indexes,
        # including entries an older version left there, and nothing else.
        tm('set-hook', '-g', 'after-select-window[9042]', 'display-message stale-canopy-hook')
        tm('set-hook', '-g', 'after-select-window[42]', 'display-message user-hook')
        tm('set-hook', '-g', 'after-select-window[8999]', 'display-message user-hook-below')
        tm('set-option', '-s', 'command-alias[9150]', 'stale-canopy=display-message stale')
        tm('set-option', '-s', 'command-alias[42]', 'mine=display-message mine')
        tm('set-option', '-g', '@tmux-canopy-notifications', 'activity,bell')
        tm('set-option', '-g', '@tmux-canopy-alerts', 'tmux')
        tm('set-option', '-g', '@tmux-canopy-alert-events', 'agents,silence')
        load()
        hooks, aliases = tm('show-hooks', '-g'), tm('show-options', '-s', 'command-alias')
        assert '[9042]' not in hooks and 'command-alias[9150]' not in aliases, (hooks, aliases)
        assert 'after-select-window[42]' in hooks and 'after-select-window[8999]' in hooks, hooks
        assert 'command-alias[42]' in aliases and 'command-alias[9100]' in aliases, aliases
        assert 'alert-silence[9002]' in hooks and 'after-select-window[9002]' in hooks, hooks
        # Hooks a setting no longer needs go with it.
        tm('set-option', '-g', '@tmux-canopy-notifications', 'none')
        tm('set-option', '-g', '@tmux-canopy-alerts', 'off')
        load()
        hooks = tm('show-hooks', '-g')
        assert 'alert-silence[9002]' not in hooks and 'after-select-window[9002]' not in hooks, hooks
        assert 'after-select-window[42]' in hooks and 'after-select-window[9004]' in hooks, hooks
        print('ok - a reload clears only Canopy-indexed hooks and aliases, including stale ones, and keeps the user\'s')

        # Each checked setting keeps a valid value and falls back to its default
        # for anything else, as when unset.
        published = {'mode': ('@tmux_canopy_mode', 'sidebar', 'popup'),
                     'popup-threshold': ('@tmux_canopy_popup_threshold', '100', '120'),
                     'popup-width': ('@tmux_canopy_popup_width', '85%', '90'),
                     'popup-height': ('@tmux_canopy_popup_height', '80%', '70%'),
                     'animate': ('@tmux_canopy_animate', 'on', 'off'),
                     'resize-mode': ('@tmux_canopy_resize_mode', 'live', 'staged'),
                     'notification-target': ('@tmux_canopy_notification_target', 'sidebar', 'both'),
                     'alerts': ('@tmux_canopy_alerts', 'off', 'desktop'),
                     'alert-detail': ('@tmux_canopy_alert_detail', 'brief', 'full'),
                     'icon-theme': ('@tmux_canopy_icon_theme', 'unicode', 'ascii')}
        for value_kind in ('bad', 'good'):
            for setting, (option, default, good) in published.items():
                tm('set-option', '-g', f'@tmux-canopy-{setting}', '0%' if value_kind == 'bad' and setting.startswith('popup-') else
                   'bogus' if value_kind == 'bad' else good)
            for setting in ('width', 'scope', 'transition'):
                tm('set-option', '-g', f'@tmux-canopy-{setting}', 'bogus' if value_kind == 'bad' else
                   {'width': '30%', 'scope': 'window', 'transition': 'move'}[setting])
            load()
            for setting, (option, default, good) in published.items():
                expected = default if value_kind == 'bad' else good
                assert tm('show-option', '-gqv', option) == expected, (setting, value_kind, tm('show-option', '-gqv', option))
            toggle = next(line for line in tm('list-keys', '-T', 'prefix').splitlines() if 'scripts/toggle' in line)
            expected_args = "'42' 'global'" if value_kind == 'bad' else "'30%' 'window'"
            assert expected_args in toggle and ("'slot'" if value_kind == 'bad' else "'move'") in toggle, (value_kind, toggle)
        for setting in list(published) + ['width', 'scope', 'transition']:
            tm('set-option', '-gu', f'@tmux-canopy-{setting}')
        load()
        print('ok - checked settings keep valid values and fall back to their defaults otherwise')
    finally:
        sp.run(['tmux', '-L', socket, 'kill-server'], env=env, stdout=sp.DEVNULL, stderr=sp.DEVNULL)


if __name__ == '__main__':
    main()
