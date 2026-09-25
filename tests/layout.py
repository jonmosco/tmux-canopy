#!/usr/bin/env python3
"""Content-layout geometry, native fallback, slots, fit limits, and zoom guards."""
import os
from pathlib import Path
import shutil
import subprocess as sp

ROOT = Path(__file__).resolve().parents[1]


def main(position="left"):
    placement = ["-b"] if position == "left" else []
    dock_geometry = "0|0|42|44" if position == "left" else "118|0|42|44"
    executable = shutil.which('tmux')
    socket = f'tree-layout-test-{os.getpid()}-{position}'
    env = os.environ.copy()
    env.pop('TMUX', None)
    env.pop('TMUX_PANE', None)

    def tm(*args):
        result = sp.run([executable, '-L', socket, *args], env=env, text=True, capture_output=True, timeout=10)
        assert result.returncode == 0, (args, result.stderr)
        return result.stdout.strip()

    def display(pane, fmt):
        return tm('display-message', '-p', '-t', pane, fmt)

    def layout(target, mode):
        result = sp.run([str(ROOT / 'scripts/content-layout'), target, mode], env=script_env,
                        text=True, capture_output=True, timeout=10)
        assert result.returncode == 0, (mode, result.stderr)

    def geometry(pane):
        return display(pane, '#{pane_left}|#{pane_top}|#{pane_width}|#{pane_height}')

    try:
        pane = tm('-f', '/dev/null', 'new-session', '-d', '-s', 'layout', '-x', '160', '-y', '44',
                  '-P', '-F', '#{pane_id}', 'sleep 600')
        tm('set-option', '-g', 'status', 'off')
        script_env = env | {'TMUX': display(pane, '#{socket_path},#{pid},0'), 'TMUX_PANE': pane}
        dock = tm('split-window', '-d', '-h', *placement, '-f', '-l', '42', '-t', pane, '-P', '-F', '#{pane_id}', 'sleep 600')
        tm('set-option', '-p', '-t', dock, '@tmux_canopy', '1')
        extras = [tm('split-window', '-d', '-v', '-l', '6', '-t', pane, '-P', '-F', '#{pane_id}', 'sleep 600') for _ in range(3)]
        ids = set(tm('list-panes', '-t', pane, '-F', '#{pane_id}').splitlines())
        tm('select-pane', '-t', extras[1])
        modes = ('even-horizontal', 'even-vertical', 'main-horizontal', 'main-vertical', 'tiled',
                 'main-horizontal-mirrored', 'main-vertical-mirrored')
        for mode in modes:
            layout(pane, mode)
            assert geometry(dock) == dock_geometry, (mode, geometry(dock))
            assert display(extras[1], '#{pane_active}') == '1'
            assert set(tm('list-panes', '-t', pane, '-F', '#{pane_id}').splitlines()) == ids
            for content in [pane, *extras]:
                if position == 'left':
                    assert int(display(content, '#{pane_left}')) >= 43
                else:
                    assert int(display(content, '#{pane_left}')) + int(display(content, '#{pane_width}')) <= 117
        layout(pane, 'previous')
        assert display(pane, '#{@tmux_canopy_content_layout}') == modes[-2]
        print('ok - seven layouts and reverse cycling preserve dock ID/width, content IDs and focus')

        tm('resize-pane', '-Z', '-t', pane)
        layout(pane, 'next')
        assert display(pane, '#{window_zoomed_flag}') == '1'
        tm('resize-pane', '-Z', '-t', pane)
        for other in extras:
            tm('kill-pane', '-t', other)
        before = geometry(pane)
        layout(pane, 'next')
        assert geometry(pane) == before and geometry(dock) == dock_geometry
        print('ok - zoom refusal and single-content-pane layouts preserve geometry')

        tm('set-option', '-pu', '-t', dock, '@tmux_canopy')
        tm('set-option', '-p', '-t', dock, '@tmux_canopy_slot', '1')
        layout(pane, 'tiled')
        assert geometry(dock) == dock_geometry
        tm('kill-pane', '-t', dock)
        tm('split-window', '-d', '-h', '-t', pane, 'sleep 600')
        layout(pane, 'even-vertical')
        assert all(int(row.split('|')[0]) == 160 for row in tm('list-panes', '-t', pane, '-F', '#{pane_width}|#{pane_height}').splitlines())
        layout(pane, 'next')
        print('ok - stable slots stay fixed; windows without a dock retain native layouts')

        small = tm('new-window', '-d', '-t', 'layout:', '-P', '-F', '#{pane_id}', 'sleep 600')
        tm('set-option', '-w', '-t', small, 'window-size', 'manual')
        tm('resize-window', '-t', small, '-x', '24', '-y', '20')
        slot = tm('split-window', '-d', '-h', *placement, '-f', '-l', '12', '-t', small, '-P', '-F', '#{pane_id}', 'sleep 600')
        tm('set-option', '-p', '-t', slot, '@tmux_canopy_slot', '1')
        for _ in range(4):
            tm('split-window', '-d', '-v', '-l', '3', '-t', small, 'sleep 600')
        before = display(small, '#{window_layout}')
        layout(small, 'even-horizontal')
        assert display(small, '#{window_layout}') == before
        layout(small, 'next')
        assert display(small, '#{@tmux_canopy_content_layout}') == 'even-vertical'
        assert geometry(slot) == ('0|0|12|20' if position == 'left' else '12|0|12|20')
        print('ok - impossible presets are refused or skipped without disturbing the dock')
        tm('set-option', '-pu', '-t', slot, '@tmux_canopy_slot')
        tm('set-option', '-p', '-t', small, '@tmux_canopy_slot', '1')
        before = display(small, '#{window_layout}')
        layout(small, 'next')
        assert display(small, '#{window_layout}') == before
        print('ok - nonstandard dock ordering is refused without changing any pane')
    finally:
        sp.run([executable, '-L', socket, 'kill-server'], env=env, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    print('all content-layout tests passed')


if __name__ == '__main__':
    for position in ('left', 'right'):
        main(position)
