#!/usr/bin/env python3
"""Proportional layout restoration and refusal of stale or unsafe snapshots."""
import os
from pathlib import Path
import shutil
import subprocess as sp

ROOT = Path(__file__).resolve().parents[1]
socket = f'canopy-scaling-test-{os.getpid()}'
env = os.environ.copy()
env.pop('TMUX', None)
env.pop('TMUX_PANE', None)


def tm(*args):
    result = sp.run([shutil.which('tmux'), '-L', socket, *args], env=env,
                    text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, (args, result.stderr)
    return result.stdout.strip()


def layout():
    return tm('display-message', '-p', '#{window_layout}')


def restore(saved):
    sp.run([str(ROOT / 'scripts/restore-window-layout'), pane, saved],
           env=script_env, check=True, timeout=10)


try:
    pane = tm('-f', '/dev/null', 'new-session', '-d', '-x', '510', '-y', '100',
              '-P', '-F', '#{pane_id}', 'sleep 600')
    tm('set-option', '-g', 'status', 'off')
    tm('set-option', '-w', 'window-size', 'manual')
    script_env = env | {'TMUX': tm('display-message', '-p', '#{socket_path},#{pid},0')}
    other = tm('split-window', '-d', '-h', '-l', '409', '-P', '-F', '#{pane_id}', 'sleep 600')
    bottom = tm('split-window', '-d', '-v', '-t', other, '-l', '74', '-P', '-F', '#{pane_id}', 'sleep 600')
    original = layout()
    restore(original)
    assert layout() == original, 'unchanged geometry should be a no-op'
    tm('resize-window', '-x', '211', '-y', '60')
    assert tm('display-message', '-p', '-t', pane, '#{pane_width}') == '1'
    restore(original)
    assert tm('display-message', '-p', '-t', pane, '#{pane_width}') == '41'
    assert tm('display-message', '-p', '-t', other, '#{pane_width}|#{pane_height}') == '169|14'
    assert tm('display-message', '-p', '-t', bottom, '#{pane_width}|#{pane_height}') == '169|45'
    print('ok - native layout restoration retains asymmetric nested splits and pane IDs')

    tm('resize-window', '-x', '180', '-y', '50')
    tm('resize-pane', '-Z', '-t', pane)
    zoomed = layout()
    restore(original)
    assert layout() == zoomed and tm('display-message', '-p', '#{window_zoomed_flag}') == '1'
    tm('resize-pane', '-Z', '-t', pane)
    tm('kill-pane', '-t', bottom)
    changed = layout()
    restore(original)
    assert layout() == changed, 'deleted pane snapshot was applied'
    replacement = tm('split-window', '-d', '-v', '-t', other, '-P', '-F', '#{pane_id}', 'sleep 600')
    changed = layout()
    restore(original)
    assert layout() == changed, 'same count but different pane IDs accepted'
    print('ok - zoomed windows and changed pane inventories are left untouched')

    parser = ['awk', '-f', str(ROOT / 'lib/scale-layout.awk')]
    for invalid in ('broken', '0000,10x4,0,0{', original.replace('510x100', '0x100')):
        result = sp.run(parser, input=invalid + '\n' + layout() + '\n', text=True, capture_output=True)
        assert result.returncode != 0 and not result.stdout
    print('ok - malformed layout snapshots are rejected')
finally:
    sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)
