"""Canonical names for agent executables and pane report sources."""
import os

KINDS = {
    'codex': 'codex',
    'claude': 'claude', 'claude-code': 'claude',
    'opencode': 'opencode',
    'gemini': 'gemini',
    'pi': 'pi', 'omp': 'omp',
    'agy': 'agy', 'antigravity': 'agy',
    'agent': 'cursor-agent',
    'crush': 'crush',
}

NAMES = {
    'codex': 'Codex', 'claude': 'Claude Code', 'opencode': 'OpenCode',
    'gemini': 'Gemini CLI', 'pi': 'Pi', 'omp': 'Oh My Pi',
    'agy': 'Antigravity', 'cursor-agent': 'cursor-agent',
    'crush': 'Crush',
}


def name_from_args(args):
    """Return the CLI name for an argv list.

    Pi and Oh My Pi are Node programs. When argv0 is ``node`` or ``nodejs``,
    a later argument that is the ``pi``/``omp`` launcher identifies the agent.
    Any other Node process stays ``node``.
    """
    names = []
    for arg in args or ():
        if isinstance(arg, bytes):
            arg = arg.decode('utf-8', 'replace')
        if arg:
            names.append(arg)
    if not names:
        return ''
    base = os.path.basename(names[0]).removesuffix('.exe')
    if base not in ('node', 'nodejs'):
        return base
    for arg in names[1:]:
        if arg.startswith('-'):
            continue
        token = os.path.basename(arg).removesuffix('.exe')
        if token in ('pi', 'omp'):
            return token
        normalized = arg.replace('\\', '/')
        if '/pi-coding-agent/' in normalized:
            return 'pi'
        if '/oh-my-pi/' in normalized:
            return 'omp'
    return base


def process_name(pid, proc_root='/proc'):
    """Return the executable basename used for agent kind matching.

    Prefer argv so Node-based CLIs still resolve: Cursor's ``agent`` (whose
    ``comm`` is often ``MainThread``) and Pi, whose executable is ``node``.
    Fall back to ``comm``.
    """
    base = f'{proc_root}/{pid}'
    try:
        argv = open(f'{base}/cmdline', 'rb').read().split(b'\0')
    except OSError:
        argv = []
    name = name_from_args(argv)
    if name:
        return name
    try:
        return open(f'{base}/comm', encoding='utf-8').read().strip().removesuffix('.exe')
    except OSError:
        return ''
