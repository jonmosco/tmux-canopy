"""Canonical names for agent executables and pane report sources."""
import os

KINDS = {
    'codex': 'codex',
    'claude': 'claude', 'claude-code': 'claude',
    'opencode': 'opencode',
    'gemini': 'gemini',
    'pi': 'pi', 'omp': 'omp',
    'agy': 'agy',
    'agent': 'cursor-agent',
}

NAMES = {
    'codex': 'Codex', 'claude': 'Claude Code', 'opencode': 'OpenCode',
    'gemini': 'Gemini CLI', 'pi': 'Pi', 'omp': 'Oh My Pi',
    'agy': 'Antigravity', 'cursor-agent': 'cursor-agent',
}


def process_name(pid, proc_root='/proc'):
    """Return the executable basename used for agent kind matching.

    Prefer argv0 from cmdline so Node-based CLIs (Cursor's ``agent``, whose
    ``comm`` is often ``MainThread``) still resolve. Fall back to ``comm``.
    """
    base = f'{proc_root}/{pid}'
    try:
        argv0 = open(f'{base}/cmdline', 'rb').read().split(b'\0', 1)[0].decode(
            'utf-8', 'replace')
    except (OSError, UnicodeError):
        argv0 = ''
    name = os.path.basename(argv0).removesuffix('.exe')
    if name:
        return name
    try:
        return open(f'{base}/comm', encoding='utf-8').read().strip().removesuffix('.exe')
    except OSError:
        return ''
