#!/usr/bin/env python3
"""WORKING status animation frames; static when animate is off or theme is mono."""
import os
from pathlib import Path
import re
import subprocess as sp
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def animate(text, frame):
    record = f'P:%1\t{text}\tP:%1:$0\0'
    result = sp.run(
        ['awk', '-v', f'frame={frame}', '-f', str(ROOT / 'lib/animate.awk')],
        input=record, text=True, capture_output=True, check=True,
    )
    assert result.stdout.endswith('\0'), repr(result.stdout)
    return result.stdout[:-1].split('\t', 2)[1]


def main():
    word = '\x1b[1m\x1b[1;36mWORKING\x1b[0m\x1b[2m ·hook\x1b[0m'
    frames = [animate(f'codex {word}', frame) for frame in range(8)]
    assert all('WORKING' in re.sub(r'\x1b\[[0-9;]*m', '', frame) for frame in frames)
    assert any('\x1b[7m' in frame for frame in frames), frames
    assert len(set(frames)) > 1, frames
    # Band moves: first and later frames differ inside WORKING.
    assert frames[0] != frames[3]

    narrow = animate('claude \x1b[1m\x1b[1;36mwrk\x1b[0m\x1b[2m ·hook\x1b[0m', 1)
    assert '\x1b[7m' in narrow and 'wrk' in re.sub(r'\x1b\[[0-9;]*m', '', narrow)

    plain = animate('just a shell row', 2)
    assert plain == 'just a shell row'

    with tempfile.TemporaryDirectory(prefix='canopy-animate-frame-') as directory:
        state = Path(directory) / 'state'
        cache = Path(f'{state}.animate')
        frame_file = Path(f'{state}.animate.frame')
        cache.write_bytes(b'P:%1\tcodex WORKING\tP:%1\0')
        frame_file.write_text('2\n')
        result = sp.run(
            [str(ROOT / 'scripts/animate-frame')],
            env={**os.environ, 'TMUX_CANOPY_STATE': str(state)},
            capture_output=True, check=True,
        )
        assert result.stdout.endswith(b'\0')
        text = result.stdout.split(b'\t', 2)[1]
        assert b'WORKING' in text.replace(b'\x1b[7m', b'').replace(b'\x1b[27m', b'')
        assert b'\x1b[7m' in text

    with tempfile.TemporaryDirectory(prefix='canopy-animate-') as directory:
        env = os.environ.copy()
        env.pop('TMUX', None)
        socket = f'canopy-animate-{os.getpid()}'

        def tm(*args):
            result = sp.run(['tmux', '-L', socket, *args], env=env, capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, (args, result.stderr)
            return result.stdout.strip()

        try:
            pane = tm('-f', '/dev/null', 'new-session', '-d', '-P', '-F', '#{pane_id}', 'sleep 120')
            env['TMUX'] = tm('display-message', '-p', '-t', pane, '#{socket_path},#{pid},0')
            load = sp.run(['bash', str(ROOT / 'tmux-canopy.tmux')], env=env, capture_output=True, text=True, timeout=30)
            assert load.returncode == 0 and not load.stderr, load.stderr
            assert tm('show-option', '-gqv', '@tmux_canopy_animate') == 'off'
            tm('set-option', '-g', '@tmux-canopy-animate', 'on')
            load = sp.run(['bash', str(ROOT / 'tmux-canopy.tmux')], env=env, capture_output=True, text=True, timeout=30)
            assert load.returncode == 0, load.stderr
            assert tm('show-option', '-gqv', '@tmux_canopy_animate') == 'on'
            tm('set-option', '-g', '@tmux-canopy-animate', 'maybe')
            load = sp.run(['bash', str(ROOT / 'tmux-canopy.tmux')], env=env, capture_output=True, text=True, timeout=30)
            assert tm('show-option', '-gqv', '@tmux_canopy_animate') == 'off'
            print('ok - animate option defaults off and normalizes invalid values')
        finally:
            sp.run(['tmux', '-L', socket, 'kill-server'], capture_output=True)

    print('ok - WORKING/wrk highlight band advances across frames; plain rows stay static')


if __name__ == '__main__':
    main()
