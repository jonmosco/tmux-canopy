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
        ['python3', str(ROOT / 'lib/animate.py'), str(frame)],
        input=record, text=True, capture_output=True, check=True,
    )
    assert result.stdout.endswith('\0'), repr(result.stdout)
    return result.stdout[:-1].split('\t', 2)[1]


# The same pattern sidebar-source uses to decide whether to start the animator.
BADGE_GREP = r'''badge=$'\e\\[1;36m(WORKING|wrk|\xe2\x96\xb7[0-9]*)\e\\[0m'; LC_ALL=C grep -aEq "$badge" "$1"'''


def badge_grep(path):
    return sp.run(['bash', '-c', BADGE_GREP, '_', str(path)], capture_output=True).returncode == 0


def main():
    word = '\x1b[1m\x1b[1;36mWORKING\x1b[0m\x1b[2m ·hook\x1b[0m'
    frames = [animate(f'codex {word}', frame) for frame in range(11)]
    assert all('WORKING' in re.sub(r'\x1b\[[0-9;]*m', '', frame) for frame in frames)
    assert any('\x1b[7m' in frame for frame in frames), frames
    assert len(set(frames)) > 1, frames
    # The band reaches the far end, reverses, and returns to the first frame.
    assert frames[0] != frames[3]
    assert frames[1] == frames[9] and frames[0] == frames[10], frames
    assert frames[5] != frames[6], frames

    narrow = animate('claude \x1b[1m\x1b[1;36mwrk\x1b[0m\x1b[2m ·hook\x1b[0m', 1)
    assert '\x1b[7m' in narrow and 'wrk' in re.sub(r'\x1b\[[0-9;]*m', '', narrow)

    plain = animate('just a shell row', 2)
    assert plain == 'just a shell row'

    marks = [animate('pi \x1b[1;36m▷\x1b[0m', frame) for frame in range(8)]
    plain_marks = [re.sub(r'\x1b\[[0-9;]*m', '', mark) for mark in marks]
    assert plain_marks == ['pi ●'] * 8, plain_marks
    assert len(set(marks)) > 1 and all('\x1b[7m' not in mark for mark in marks), marks
    assert marks[0] == marks[1] and marks[1] == marks[7] and marks[3] == marks[5], marks
    assert all('▷' not in mark for mark in plain_marks)

    # Only styled badges animate; plain text that happens to say wrk or
    # WORKING (a directory, a window title) stays untouched.
    for text in ('zsh ~/wrk', 'WORKING notes', 'vim \x1b[2m~/wrk\x1b[0m x', 'pi ▷ plain'):
        assert all(animate(text, frame) == text for frame in range(3)), text
    with tempfile.TemporaryDirectory(prefix='canopy-animate-grep-') as directory:
        plain = Path(directory) / 'plain'
        plain.write_bytes('P:%1\tzsh ~/wrk WORKING ▷\tP:%1\0'.encode())
        assert not badge_grep(plain), 'plain text must not start the animator'
        for styled in ('\x1b[1;36mwrk\x1b[0m', '\x1b[1;36m▷3\x1b[0m'):
            plain.write_bytes(f'P:%1\tx {styled}\tP:%1\0'.encode())
            assert badge_grep(plain), styled

    # A stale report's dim mark says what the agent last reported, not that it
    # is working now, so it neither animates nor starts the animator.
    stale = 'claude \x1b[2m▷\x1b[0m'
    assert all(animate(stale, frame) == stale for frame in range(4)), stale
    with tempfile.TemporaryDirectory(prefix='canopy-animate-stale-') as directory:
        cache = Path(directory) / 'stale'
        cache.write_bytes(f'P:%1\t{stale}\tP:%1\0'.encode())
        assert not badge_grep(cache), 'a stale mark must not start the animator'

    # A summary mark keeps its count.
    counted = animate('W \x1b[1;36m▷3\x1b[0m', 2)
    assert re.sub(r'\x1b\[[0-9;]*m', '', counted) == 'W ●3', counted

    # Every element repeats within the 40-frame period, so wrapping to 0 is seamless.
    busy = f'codex {word} x \x1b[1;36mwrk\x1b[0m \x1b[1;36m▷2\x1b[0m'
    assert animate(busy, 0) == animate(busy, 40) and animate(busy, 39) == animate(busy, 79)

    agy_marks = [animate('agy \x1b[1;36m▷\x1b[0m', frame) for frame in range(8)]
    assert [re.sub(r'\x1b\[[0-9;]*m', '', m) for m in agy_marks] == ['agy ●'] * 8

    multi = f'P:%1\tcodex {word}\tP:%1:$0\0P:%2\tshell\tP:%2:$0\0'
    result = sp.run(
        ['python3', str(ROOT / 'lib/animate.py'), '1'],
        input=multi, text=True, capture_output=True, check=True,
    )
    assert result.stdout.count('\0') == 2, repr(result.stdout)
    assert result.stdout.endswith('\0') and 'P:%2\tshell\tP:%2:$0\0' in result.stdout

    with tempfile.TemporaryDirectory(prefix='canopy-animate-frame-') as directory:
        state = Path(directory) / 'state'
        cache = Path(f'{state}.animate')
        frame_file = Path(f'{state}.animate.frame')
        cache.write_bytes(b'P:%1\tcodex \x1b[1m\x1b[1;36mWORKING\x1b[0m\tP:%1\0')
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

    with tempfile.TemporaryDirectory(prefix='canopy-animate-frames-') as directory:
        state = Path(directory) / 'state'
        cache = Path(f'{state}.animate')
        rows = f'P:%1\tcodex {word}\tP:%1\0P:%2\tshell\tP:%2\0'.encode()
        cache.write_bytes(rows)
        prefix = f'{cache}.f.test'
        sp.run(['python3', str(ROOT / 'lib/animate.py'), '--frames', '40', prefix],
               input=rows, capture_output=True, check=True)
        assert sorted(int(p.name.rsplit('.', 1)[1]) for p in Path(directory).glob('state.animate.f.test.*')) == list(range(40))
        Path(f'{cache}.prefix').write_text(prefix + '\n')
        env = {**os.environ, 'TMUX_CANOPY_STATE': str(state)}
        for frame in (0, 7, 39):
            Path(f'{state}.animate.frame').write_text(f'{frame}\n')
            served = sp.run([str(ROOT / 'scripts/animate-frame')], env=env, capture_output=True, check=True).stdout
            direct = sp.run(['python3', str(ROOT / 'lib/animate.py'), str(frame)],
                            input=rows, capture_output=True, check=True).stdout
            assert served == direct == Path(f'{prefix}.{frame}').read_bytes(), frame
        # A precomputed frame is served as-is; missing frames fall back to Python.
        Path(f'{prefix}.7').write_bytes(b'precomputed\0')
        Path(f'{state}.animate.frame').write_text('7\n')
        assert sp.run([str(ROOT / 'scripts/animate-frame')], env=env, capture_output=True, check=True).stdout == b'precomputed\0'
        Path(f'{prefix}.7').unlink()
        assert b'\x1b[7m' in sp.run([str(ROOT / 'scripts/animate-frame')], env=env, capture_output=True, check=True).stdout

    with tempfile.TemporaryDirectory(prefix='canopy-animate-mark-') as directory:
        state = Path(directory) / 'state'
        cache = Path(f'{state}.animate')
        frame_file = Path(f'{state}.animate.frame')
        cache.write_bytes('P:%124\t\x1b[96m󰀘\x1b[0m agy \x1b[1;36m▷\x1b[0m\tP:%124:$0\0'.encode('utf-8'))
        frame_file.write_text('4\n')
        result = sp.run(
            [str(ROOT / 'scripts/animate-frame')],
            env={**os.environ, 'TMUX_CANOPY_STATE': str(state)},
            capture_output=True, check=True,
        )
        assert result.stdout.endswith(b'\0')
        text = result.stdout.split(b'\t', 2)[1].decode('utf-8')
        assert '●' in text and '▷' not in text
        assert badge_grep(cache), 'styled working mark must start the animator'

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
            assert tm('show-option', '-gqv', '@tmux_canopy_animate') == 'on'
            tm('set-option', '-g', '@tmux-canopy-animate', 'off')
            load = sp.run(['bash', str(ROOT / 'tmux-canopy.tmux')], env=env, capture_output=True, text=True, timeout=30)
            assert load.returncode == 0, load.stderr
            assert tm('show-option', '-gqv', '@tmux_canopy_animate') == 'off'
            tm('set-option', '-g', '@tmux-canopy-animate', 'maybe')
            load = sp.run(['bash', str(ROOT / 'tmux-canopy.tmux')], env=env, capture_output=True, text=True, timeout=30)
            assert tm('show-option', '-gqv', '@tmux_canopy_animate') == 'on'
            print('ok - animate option defaults on and normalizes invalid values')

            # Test agent-animate readiness guard and search mode suppression
            import time
            tm('set-option', '-p', '-t', pane, '@tmux_canopy', '1')
            # The animation runs while focus is in another pane.
            content = tm('split-window', '-t', pane, '-P', '-F', '#{pane_id}', 'sleep 120')
            tm('select-pane', '-t', content)
            token = 'test-token-123'
            tm('set-option', '-p', '-t', pane, '@tmux_canopy_animate_token', token)
            state_file = Path(directory) / 'sidebar-state'
            cache_file = Path(f'{state_file}.animate')
            frame_file = Path(f'{state_file}.animate.frame')
            ready_file = Path(f'{state_file}.ready')
            search_file = Path(f'{state_file}.search')
            state_file.write_text('VIEW\ttree\n')
            cache_file.write_bytes(b'P:%1\tcodex \x1b[1m\x1b[1;36mWORKING\x1b[0m\tP:%1\0')

            animator = sp.Popen(
                ['bash', str(ROOT / 'scripts/agent-animate'), pane, token, str(state_file)],
                env=env, stdout=sp.DEVNULL, stderr=sp.DEVNULL,
            )
            try:
                # 1. While ready_file does not exist, animator must NOT advance frames
                time.sleep(0.35)
                assert frame_file.read_text().strip() == '0'
                # Frames are precomputed once and published under this token.
                prefix_file = Path(f'{cache_file}.prefix')
                assert prefix_file.read_text().strip().endswith('.f.' + token.replace('-', '_')), prefix_file
                assert len(list(Path(directory).glob('sidebar-state.animate.f.*'))) == 40

                # 2. Once ready_file exists, animator begins advancing frames
                ready_file.touch()
                time.sleep(0.35)
                frame_after_ready = int(frame_file.read_text().strip())
                assert frame_after_ready > 0, frame_after_ready

                # 3. When search_file exists, animator suppresses animation
                search_file.touch()
                time.sleep(0.15)
                frame_frozen = int(frame_file.read_text().strip())
                time.sleep(0.35)
                assert int(frame_file.read_text().strip()) == frame_frozen

                # 4. When search_file is removed, animation resumes
                search_file.unlink()
                time.sleep(0.35)
                assert int(frame_file.read_text().strip()) != frame_frozen
                print('ok - agent-animate respects ready guard and suppresses during search mode')

                # 5. A focused sidebar keeps animating at a third of the rate,
                # since each frame is a reload that could drop a click; full
                # speed returns when focus leaves.
                def advances(seconds):
                    start = int(frame_file.read_text().strip())
                    time.sleep(seconds)
                    return (int(frame_file.read_text().strip()) - start) % 40
                tm('select-pane', '-t', pane)
                time.sleep(0.2)
                focused = advances(1.8)
                tm('select-pane', '-t', content)
                time.sleep(0.2)
                unfocused = advances(1.8)
                assert 1 <= focused and focused * 2 < unfocused, (focused, unfocused)
                print('ok - agent-animate slows down while the sidebar has focus')
            finally:
                tm('set-option', '-pu', '-t', pane, '@tmux_canopy_animate_token')
                animator.wait(timeout=5)
            # Losing the token ends the animator, which removes its own frames.
            assert not Path(f'{cache_file}.prefix').exists()
            assert not list(Path(directory).glob('sidebar-state.animate.f.*'))

            # A new animator continues from the previous frame instead of 0.
            frame_file.write_text('17\n')
            tm('set-option', '-p', '-t', pane, '@tmux_canopy_animate_token', token)
            animator = sp.Popen(
                ['bash', str(ROOT / 'scripts/agent-animate'), pane, token, str(state_file)],
                env=env, stdout=sp.DEVNULL, stderr=sp.DEVNULL,
            )
            try:
                time.sleep(0.35)
                assert int(frame_file.read_text().strip()) >= 17
            finally:
                tm('set-option', '-pu', '-t', pane, '@tmux_canopy_animate_token')
                animator.wait(timeout=5)
            print('ok - agent-animate precomputes frames, cleans them up, and keeps the frame across restarts')
        finally:
            sp.run(['tmux', '-L', socket, 'kill-server'], capture_output=True)

    print('ok - WORKING/wrk highlight band advances; working mark breathes as a quiet cyan dot')


if __name__ == '__main__':
    main()
