#!/usr/bin/env python3
"""Animate WORKING / wrk status words in NUL-delimited fzf rows.

Usage: animate.py FRAME < cache            one frame to stdout
       animate.py --frames N PREFIX < cache  write PREFIX.0 .. PREFIX.N-1
"""
import os
import re
import sys

# Only the renderer's live working badges animate: the theme accent, the word
# (or the working mark with an optional count), then a reset. Plain text such
# as a ~/wrk directory or a WORKING window title never matches, nor does the
# dim mark of a stale report, which only says what an agent last reported.
DEFAULT_ACCENT = '\033[1;36m'
SGR_RE = re.compile(r'^\x1b\[[0-9;]+m$')
# Step intensity (faint -> normal -> bold -> normal -> faint) after the accent
# escape so 8-color, 256-color, and truecolor accents all breathe cleanly.
STYLES = ['\033[22;2m', '\033[22;2m', '\033[22m', '\033[22m',
          '\033[22;1m', '\033[22m', '\033[22m', '\033[22;2m']
# LCM of the WORKING band (10), wrk band (4) and STYLES (8) periods.
PERIOD = 40


def accent_escape(env=None):
    value = (os.environ if env is None else env).get('CANOPY_COLOR_ACCENT_ANSI', '')
    return value if SGR_RE.match(value) else DEFAULT_ACCENT


def badge_pattern(accent=None):
    chosen = accent if accent and SGR_RE.match(accent) else accent_escape()
    return re.compile(rf'({re.escape(chosen)})(WORKING|wrk|▷)([0-9]*)(\x1b\[0m)')


def animate_word(word, frame):
    length = len(word)
    band = 1 if length <= 3 else 2
    positions = length - band + 1
    if positions <= 1:
        return word
    cycle = 2 * (positions - 1)
    phase = frame % cycle
    start = phase if phase < positions else cycle - phase
    out = []
    for i, char in enumerate(word):
        if start <= i < start + band:
            out.append(f'\033[7m{char}\033[27m')
        else:
            out.append(char)
    return ''.join(out)


def animate_badge(match, frame):
    style, word, count, reset = match.groups()
    if word == '▷':
        return f'{style}{STYLES[frame % 8]}●{count}{reset}'
    return f'{style}{animate_word(word, frame)}{count}{reset}'


def render(rows, frame, pattern=None):
    badge_re = badge_pattern() if pattern is None else pattern
    out = []
    for row in rows:
        fields = row.split('\t', 2)
        if len(fields) >= 2:
            fields[1] = badge_re.sub(lambda m: animate_badge(m, frame), fields[1])
            row = '\t'.join(fields)
        out.append(row + '\0')
    return ''.join(out)


def read_rows():
    data = sys.stdin.buffer.read().decode('utf-8', errors='replace')
    rows = data.split('\0')
    if rows and rows[-1] == '':
        rows.pop()
    return rows


def main(argv):
    pattern = badge_pattern()
    if len(argv) > 3 and argv[1] == '--frames':
        count = int(argv[2]) if argv[2].isdigit() else PERIOD
        prefix = argv[3]
        rows = read_rows()
        for frame in range(count):
            path = f'{prefix}.{frame}'
            tmp = f'{path}.tmp'
            with open(tmp, 'wb') as handle:
                handle.write(render(rows, frame, pattern).encode('utf-8'))
            os.replace(tmp, path)
        return
    frame = int(argv[1]) if len(argv) > 1 and argv[1].isdigit() else 0
    sys.stdout.write(render(read_rows(), frame, pattern))
    sys.stdout.flush()


if __name__ == '__main__':
    main(sys.argv)
