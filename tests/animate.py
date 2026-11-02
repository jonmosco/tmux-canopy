#!/usr/bin/env python3
"""WORKING status animation frames; static when animate is off or theme is mono."""
import os
from pathlib import Path
import json
import re
import subprocess as sp
import tempfile

from support import install_agent_fixture

ROOT = Path(__file__).resolve().parents[1]


def animate(text, frame, accent=None):
    record = f'P:%1\t{text}\tP:%1:$0\0'
    run_env = os.environ.copy()
    if accent is None:
        run_env.pop('CANOPY_COLOR_ACCENT_ANSI', None)
    else:
        run_env['CANOPY_COLOR_ACCENT_ANSI'] = accent
    result = sp.run(
        ['python3', str(ROOT / 'lib/animate.py'), str(frame)],
        input=record, text=True, capture_output=True, check=True, env=run_env,
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
    assert len(set(marks)) == 3 and all('\x1b[7m' not in mark for mark in marks), marks
    assert marks[0] == marks[1] and marks[1] == marks[7] and marks[3] == marks[5], marks
    assert marks[2] != marks[4], marks
    assert all('▷' not in mark for mark in plain_marks)

    # Hex and 256-color theme accents animate identically; non-accent text stays static.
    hex_accent = '\x1b[38;2;163;190;140m'
    hex_word = f'\x1b[1m{hex_accent}WORKING\x1b[0m\x1b[2m ·hook\x1b[0m'
    hex_frames = [animate(f'codex {hex_word}', frame, accent=hex_accent) for frame in range(4)]
    assert any('\x1b[7m' in frame and hex_accent in frame for frame in hex_frames), hex_frames
    hex_marks = [animate(f'pi {hex_accent}▷2\x1b[0m', frame, accent=hex_accent) for frame in range(8)]
    assert [re.sub(r'\x1b\[[0-9;]*m', '', m) for m in hex_marks] == ['pi ●2'] * 8
    assert len(set(hex_marks)) == 3 and all(hex_accent in m for m in hex_marks), hex_marks
    # With a hex accent active, an unrelated cyan span is ordinary text, not a live badge.
    cyan_span = 'note \x1b[1;36mWORKING\x1b[0m \x1b[1;36m▷\x1b[0m'
    assert all(animate(cyan_span, frame, accent=hex_accent) == cyan_span for frame in range(3))

    idx_accent = '\x1b[38;5;183m'
    idx_narrow = animate(f'claude \x1b[1m{idx_accent}wrk\x1b[0m', 1, accent=idx_accent)
    assert '\x1b[7m' in idx_narrow and idx_accent in idx_narrow, idx_narrow

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
        # animate-frame fallback also picks up cache.accent when env lacks CANOPY_COLOR_ACCENT_ANSI.
        cache.write_bytes(b'P:%1\tcodex \x1b[1m\x1b[38;2;163;190;140mWORKING\x1b[0m\tP:%1\0')
        Path(f'{cache}.accent').write_text('38;2;163;190;140\n')
        clean_env = {k: v for k, v in os.environ.items() if k != 'CANOPY_COLOR_ACCENT_ANSI'}
        clean_env['TMUX_CANOPY_STATE'] = str(state)
        hex_fallback = sp.run([str(ROOT / 'scripts/animate-frame')], env=clean_env, capture_output=True, check=True).stdout
        assert b'\x1b[38;2;163;190;140m' in hex_fallback and b'\x1b[7m' in hex_fallback, hex_fallback

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

            # End-to-end: under ansi theme with a hex accent inherited from tmux,
            # sidebar-source detects the hex working badge and passes the accent
            # across tmux run-shell (whose server env has no CANOPY_COLOR_*).
            tm('set-option', '-g', '@tmux-canopy-animate', 'on')
            tm('set-option', '-g', '@tmux-canopy-theme', 'ansi')
            tm('set-option', '-g', '@tmux-canopy-agents', 'on')
            tm('set-option', '-g', 'pane-active-border-style', 'fg=#a3be8c')
            load = sp.run(['bash', str(ROOT / 'tmux-canopy.tmux')], env=env, capture_output=True, text=True, timeout=30)
            assert load.returncode == 0, load.stderr
            bin_dir = Path(directory) / 'agent-bin'
            bin_dir.mkdir(exist_ok=True)
            codex_bin = bin_dir / 'codex'
            install_agent_fixture(codex_bin)
            codex_pane = tm('split-window', '-t', content, '-P', '-F', '#{pane_id}', f"exec '{codex_bin}' 120")
            for payload in (
                {'hook_event_name': 'SessionStart', 'session_id': 'hex-anim'},
                {'hook_event_name': 'UserPromptSubmit', 'session_id': 'hex-anim'},
            ):
                hook_res = sp.run(
                    [str(ROOT / 'scripts/codex-hook')],
                    input=json.dumps(payload), text=True, capture_output=True, timeout=10,
                    env={**env, 'TMUX_PANE': codex_pane},
                )
                assert hook_res.returncode == 0, hook_res.stderr
            hex_state = Path(directory) / 'hex-sidebar-state'
            hex_state.write_text('VIEW\ttree\n')
            source_env = {k: v for k, v in env.items()
                          if not k.startswith('CANOPY_COLOR_') and k not in ('CANOPY_THEME', 'CANOPY_THEME_FROZEN')}
            source_env.update(
                TMUX_PANE=pane,
                TMUX_CANOPY_STATE=str(hex_state),
                TMUX_CANOPY_RECORD_FORMAT='nul',
                TMUX_CANOPY_UI_HEADER='1',
            )
            src = sp.run(
                [str(ROOT / 'scripts/sidebar-source'), '--stable', '--read0'],
                env=source_env, capture_output=True, check=True, timeout=15,
            )
            assert b'\x1b[38;2;163;190;140m\xe2\x96\xb7\x1b[0m' in src.stdout, src.stdout
            hex_cache = Path(f'{hex_state}.animate')
            assert Path(f'{hex_cache}.accent').read_text().strip() == '38;2;163;190;140'
            live_token = tm('show-option', '-pqv', '-t', pane, '@tmux_canopy_animate_token')
            assert live_token, 'hex working badge must schedule agent-animate'
            try:
                prefix_path = Path(f'{hex_cache}.prefix')
                deadline = time.time() + 5.0
                while time.time() < deadline and not prefix_path.exists():
                    time.sleep(0.05)
                assert prefix_path.exists(), 'run-shell agent-animate must publish precomputed hex frames'
                Path(f'{hex_state}.animate.frame').write_text('4\n')
                rendered_frame = sp.run(
                    [str(ROOT / 'scripts/animate-frame')],
                    env=source_env, capture_output=True, check=True, timeout=10,
                ).stdout
                assert b'\x1b[38;2;163;190;140m\x1b[22;1m\xe2\x97\x8f\x1b[0m' in rendered_frame, rendered_frame
            finally:
                tm('set-option', '-pu', '-t', pane, '@tmux_canopy_animate_token')
                time.sleep(0.25)
            print('ok - ansi hex accent schedules and animates across tmux run-shell')
        finally:
            sp.run(['tmux', '-L', socket, 'kill-server'], capture_output=True)

    print('ok - WORKING/wrk highlight band advances; working mark breathes in active theme accent')


if __name__ == '__main__':
    main()
