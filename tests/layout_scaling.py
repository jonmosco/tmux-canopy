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

    def scale(saved, current):
        return sp.run(parser, input=f'{saved}\n{current}\n', text=True, capture_output=True)

    # A server reports one of two formats and cannot be asked for the other:
    # tmux 3.7c the checksummed string, tmux 3.8 JSON. Both must read the same,
    # including a saved snapshot taken before the server was upgraded.
    V1_WIDE = 'f09b,120x30,0,0{60x30,0,0,0,59x30,61,0,1}'
    V1_NARROW = 'abcd,100x30,0,0{50x30,0,0,0,49x30,51,0,1}'
    V2_WIDE = ('{"V":2,"L":{"t":"h","w":120,"h":30,"x":0,"y":0,"c":['
               '{"t":"p","w":60,"h":30,"x":0,"y":0,"l":0,"i":0,"I":"%0"},'
               '{"t":"p","w":59,"h":30,"x":61,"y":0,"a":true,"i":1,"I":"%1"}]}}')
    V2_NARROW = ('{"V":2,"L":{"t":"h","w":100,"h":30,"x":0,"y":0,"c":['
                 '{"t":"p","w":50,"h":30,"x":0,"y":0,"l":0,"i":0,"I":"%0"},'
                 '{"t":"p","w":49,"h":30,"x":51,"y":0,"a":true,"i":1,"I":"%1"}]}}')
    expected = scale(V1_WIDE, V1_NARROW).stdout
    assert expected.strip(), 'the checksummed format still scales'
    for saved, current in ((V2_WIDE, V2_NARROW), (V1_WIDE, V2_NARROW), (V2_WIDE, V1_NARROW)):
        assert scale(saved, current).stdout == expected, (saved[:40], current[:40])
    # Key order is tmux's choice, not part of the format.
    reordered = ('{"L":{"w":120,"t":"h","h":30,"y":0,"x":0,"c":['
                 '{"I":"%0","t":"p","h":30,"w":60,"x":0,"y":0},'
                 '{"t":"p","w":59,"h":30,"x":61,"y":0,"I":"%1"}]},"V":2}')
    assert scale(reordered, V2_NARROW).stdout == expected, 'reordered keys'
    # Negative offsets are written with %d and must still be consumed.
    assert scale(V2_WIDE.replace('"x":0,"y":0,"c"', '"x":-2,"y":-1,"c"'),
                 V2_NARROW).stdout == expected, 'negative offsets'
    assert scale(V2_WIDE, V2_WIDE).returncode != 0, 'an unchanged window needs no layout'
    print('ok - both tmux layout formats scale to the same result')

    # The checksummed format cannot describe a floating pane, and tmux drops
    # floaters when it writes that format, so such a window is left alone.
    def with_floater(text):
        return text.replace(']}}', ',{"t":"p","w":20,"h":7,"x":4,"y":2,"i":2,"z":0,"I":"%2"}]}}')
    assert scale(with_floater(V2_WIDE), with_floater(V2_NARROW)).returncode != 0, 'floating pane'
    print('ok - windows holding a floating pane are left untouched')

    live = layout()
    for invalid in ('broken', '0000,10x4,0,0{', '{"V":2,"L":', live[:-3],
                    V1_WIDE.replace('120x30', '0x30'),
                    V2_WIDE + 'xx', V2_WIDE.replace('"w":120', '"w":0'),
                    V2_WIDE.replace(',"I":"%0"', '')):
        result = scale(invalid, V2_NARROW)
        assert result.returncode != 0 and not result.stdout, invalid[:60]
    print('ok - malformed layout snapshots are rejected')
finally:
    sp.run(['tmux', '-L', socket, 'kill-server'], env=env, capture_output=True)
