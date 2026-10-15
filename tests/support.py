"""Test-only instrumentation; production never accepts ambient fzf bindings."""
import shlex
import re
import shutil
import sys


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
