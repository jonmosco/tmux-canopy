#!/usr/bin/env python3
"""Animate WORKING / wrk status words in NUL-delimited fzf rows."""
import re
import sys

frame = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 0
WORKING_RE = re.compile(r'WORKING|wrk')
MARK = b'\xe2\x96\xb7'.decode('utf-8')
STYLES = ['\033[2;36m', '\033[2;36m', '\033[36m', '\033[36m',
          '\033[1;36m', '\033[36m', '\033[36m', '\033[2;36m']


def animate_word(word):
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


def animate_mark():
    return f'{STYLES[frame % 8]}●\033[0m'


data = sys.stdin.buffer.read().decode('utf-8', errors='replace')
rows = data.split('\0')
if rows and rows[-1] == '':
    rows.pop()
for row in rows:
    fields = row.split('\t', 2)
    if len(fields) >= 2:
        fields[1] = WORKING_RE.sub(lambda m: animate_word(m.group()), fields[1])
        fields[1] = fields[1].replace(MARK, animate_mark())
        row = '\t'.join(fields)
    sys.stdout.write(row + '\0')
sys.stdout.flush()
