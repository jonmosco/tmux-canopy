"""Test-only instrumentation; production never accepts ambient fzf bindings."""
import os
import shlex
import re
import shutil
import sys

# tmux asks its client terminal for colors and capabilities when it attaches,
# and forwards a pane's own color queries (fzf asks) to that terminal. A real
# terminal always answers; a bare pty never does, which leaves the pane
# unpainted until something resizes it. These are the queries tmux sends and
# canned replies for a dark xterm-like terminal.
TERMINAL_REPLIES = {
    b'\x1b]10;?\x1b\\': b'\x1b]10;rgb:cccc/cccc/cccc\x1b\\',
    b'\x1b]11;?\x1b\\': b'\x1b]11;rgb:1111/1111/1111\x1b\\',
    b'\x1b[c': b'\x1b[?62;c',
    b'\x1b[>c': b'\x1b[>1;10;0c',
    b'\x1b[>q': b'\x1bP>|xterm(388)\x1b\\',
    b'\x1b[?996n': b'\x1b[?997;1n',
}


class TerminalAnswers:
    """Answer terminal queries found in the output tmux writes to a pty client."""

    def __init__(self, master_fd):
        self.master_fd = master_fd
        self.tail = b''

    def feed(self, data):
        data = self.tail + data
        for query, reply in TERMINAL_REPLIES.items():
            for _ in range(data.count(query)):
                os.write(self.master_fd, reply)
            data = data.replace(query, b'')
        # A query split across two reads completes on the next feed.
        self.tail = data[-16:]


def install_agent_fixture(destination):
    # Apple's protected sleep cannot be copied and renamed into a fake agent.
    name = 'gsleep' if sys.platform == 'darwin' else 'sleep'
    binary = shutil.which(name)
    if binary is None:
        raise RuntimeError(f'{name} is required for agent fixtures (macOS: brew install coreutils)')
    shutil.copy(binary, destination)


def install_fzf_probe(directory, bindings, env, extra_options=()):
    binary = shutil.which('fzf')
    folder = directory / 'fzf-probe-bin'
    folder.mkdir(exist_ok=True)
    wrapper = folder / 'fzf'
    options = [*extra_options, *(arg for binding in bindings for arg in ('--bind', binding))]
    wrapper.write_text('#!/bin/bash\nexec ' + shlex.quote(binary) + ' ' + shlex.join(options) + ' "$@"\n')
    wrapper.chmod(0o755)
    env['PATH'] = str(folder) + ':' + env['PATH']


def highlighted_spans(text):
    """Selected text, independent of a particular palette/default style."""
    underline = reverse = background = False
    parts = re.split(r'\x1b\[([0-9;]*)m', text)
    for index, part in enumerate(parts):
        if index % 2 == 0:
            if part and (underline or reverse or background):
                yield part
            continue
        codes = [int(code or 0) for code in part.split(';')]
        offset = 0
        while offset < len(codes):
            code = codes[offset]
            if code == 0:
                underline = reverse = background = False
            elif code in (4, 24):
                underline = code == 4
            elif code in (7, 27):
                reverse = code == 7
            elif code == 49:
                background = False
            elif 40 <= code <= 47 or 100 <= code <= 107:
                background = True
            elif code in (38, 48) and offset + 1 < len(codes):
                background = background or code == 48
                offset += 2 if codes[offset + 1] == 5 else 4
            offset += 1
