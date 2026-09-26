"""Test-only instrumentation; production never accepts ambient fzf bindings."""
import shlex
import shutil


def install_fzf_probe(directory, bindings, env, extra_options=()):
    binary = shutil.which('fzf')
    folder = directory / 'fzf-probe-bin'
    folder.mkdir(exist_ok=True)
    wrapper = folder / 'fzf'
    options = [*extra_options, *(arg for binding in bindings for arg in ('--bind', binding))]
    wrapper.write_text('#!/bin/bash\nexec ' + shlex.quote(binary) + ' ' + shlex.join(options) + ' "$@"\n')
    wrapper.chmod(0o755)
    env['PATH'] = str(folder) + ':' + env['PATH']
