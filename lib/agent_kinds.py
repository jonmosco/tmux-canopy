"""Canonical names for agent executables and pane report sources."""
import os
import re

# Standalone Claude Code builds report their version (dots or underscores,
# e.g. 2.1.201 or 2_1_201) as kernel comm / pane_current_command.
CLAUDE_VERSION_RE = re.compile(r'^(\d+\.\d+\.\d+|\d+_\d+_\d+)(?:[-+][0-9A-Za-z._-]+)?$')

KINDS = {
    'codex': 'codex',
    'claude': 'claude', 'claude-code': 'claude',
    'opencode': 'opencode',
    'gemini': 'gemini',
    'pi': 'pi', 'omp': 'omp',
    'agy': 'agy', 'antigravity': 'agy',
    'agent': 'cursor-agent', 'cursor-agent': 'cursor-agent',
    'crush': 'crush',
    'copilot': 'copilot',
    'grok': 'grok',
    'hermes': 'hermes', 'hermes-agent': 'hermes',
}

NODE_VALUE_FLAGS = frozenset((
    '-r', '--require', '--import', '--loader', '--experimental-loader', '-C', '--conditions',
))
NODE_EVAL_FLAGS = frozenset(('-e', '--eval', '-p', '--print'))
HOSTED_BINS = {
    'pi': 'pi', 'omp': 'omp',
    'claude': 'claude', 'claude-code': 'claude',
    'codex': 'codex',
    'gemini': 'gemini',
    'opencode': 'opencode',
    'copilot': 'copilot',
    'grok': 'grok',
    'cursor-agent': 'cursor-agent',
    'agy': 'agy', 'antigravity': 'agy',
    'crush': 'crush',
}
HOSTED_PACKAGES = (
    ('/pi-coding-agent/', 'pi'),
    ('/oh-my-pi/', 'omp'),
    ('/@anthropic-ai/claude-code/', 'claude'),
    ('/@google/gemini-cli/', 'gemini'),
    ('/gemini-cli/', 'gemini'),
    ('/@openai/codex/', 'codex'),
    ('/cursor-agent/', 'cursor-agent'),
    ('/@github/copilot/', 'copilot'),
    ('/opencode-ai/', 'opencode'),
    ('/node_modules/opencode/', 'opencode'),
)

# Shells, launchers, runtimes, and sandbox wrappers an agent may run under and
# still belong to its pane. A sandbox wrapper usually stays the agent's parent. Any other process in between (an editor such as nvim, or lazygit)
# owns the agent, so the pane is not reported as that agent.
CARRIERS = frozenset((
    'sh', 'bash', 'zsh', 'fish', 'dash', 'ksh', 'mksh', 'tcsh', 'csh', 'nu', 'xonsh', 'elvish', 'pwsh',
    'login', 'su', 'sudo', 'doas', 'env', 'nice', 'nohup', 'time', 'timeout', 'script', 'stdbuf',
    'caffeinate', 'direnv', 'mise', 'asdf', 'nix', 'nix-shell', 'devbox', 'node', 'nodejs', 'bun',
    'deno', 'npx', 'npm', 'pnpm', 'yarn', 'tsx', 'ts-node', 'uv', 'uvx', 'pipx', 'poetry', 'ruby',
    'bundle', 'cargo', 'make', 'just',
    'bwrap', 'firejail', 'sandbox-exec', 'nono', 'fence', 'landrun', 'nsjail', 'minijail0', 'unshare',
    'codex-app-server',
))


def is_claude_version(name):
    return bool(name and CLAUDE_VERSION_RE.match(name))


def is_carrier(name, kind=None):
    name = name.lstrip('-')
    if name in CARRIERS or is_python(name):
        return True
    if is_claude_version(name):
        return kind in (None, 'claude')
    return KINDS.get(name) == kind if kind else name in KINDS


def _hosted_script_index(names):
    skip_next = False
    for index, arg in enumerate(names[1:], 1):
        if skip_next:
            skip_next = False
            continue
        if arg in NODE_VALUE_FLAGS:
            skip_next = True
            continue
        if arg in NODE_EVAL_FLAGS or arg.startswith(('--eval=', '--print=')):
            return None
        if arg.startswith('-'):
            continue
        return index
    return None


def is_headless_args(kind, args):
    """Whether argv[1:] runs a non-interactive one-shot command for kind."""
    names = [arg.decode('utf-8', 'replace') if isinstance(arg, bytes) else arg
             for arg in (args or ()) if arg]
    if not names:
        return False
    base = os.path.basename(names[0]).removesuffix('.exe')
    if base in ('node', 'nodejs', 'bun'):
        index = _hosted_script_index(names)
        rest = names[index + 1:] if index is not None else []
    else:
        rest = names[1:]
    if kind in ('claude', 'gemini', 'cursor-agent', 'copilot', 'grok', 'pi', 'omp'):
        if '-p' in rest or '--print' in rest:
            return True
        if kind in ('pi', 'omp') and '--mode' in rest:
            return True
    elif kind == 'codex':
        for arg in rest:
            if not arg.startswith('-'):
                return arg in ('exec', 'e')
    elif kind == 'opencode':
        for arg in rest:
            if not arg.startswith('-'):
                return arg == 'run'
    return False


NAMES = {
    'codex': 'Codex', 'claude': 'Claude Code', 'opencode': 'OpenCode',
    'gemini': 'Gemini CLI', 'pi': 'Pi', 'omp': 'Oh My Pi',
    'agy': 'Antigravity', 'cursor-agent': 'cursor-agent',
    'crush': 'Crush', 'copilot': 'Copilot CLI', 'grok': 'Grok Build', 'hermes': 'Hermes',
}


def is_python(name):
    return name in ('python', 'Python') or (name.startswith('python') and name[6:].replace('.', '').isdigit())


def hermes_args(args):
    # ps splits a -c launcher's source into words, so look at every argument.
    if any('hermes_cli' in arg for arg in args):
        return True
    for index, arg in enumerate(args):
        if arg.startswith('-'):
            if arg == '-m' and index + 1 < len(args) and args[index + 1].split('.')[0] == 'tui_gateway':
                return True
            continue
        # The first operand is the script; anything after it is its arguments.
        return os.path.basename(arg).removesuffix('.exe') in ('hermes', 'hermes-agent')
    return False


def name_from_args(args):
    """Return the CLI name for an argv list.

    Node/Bun-hosted CLIs (Pi, Oh My Pi, Gemini CLI, npm Claude/Codex/Copilot,
    etc.) resolve from their first script operand; any other Node process stays
    ``node``. Hermes is a Python program whose installer shim runs
    ``python3 -I -c <launcher importing hermes_cli>``, and whose TUI runs
    ``python3 -m tui_gateway``; any other Python stays itself. Standalone
    Claude Code binaries report their version as comm/argv0.
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
    if base == 'codex' and 'app-server' in names[1:3]:
        return 'codex-app-server'
    if is_claude_version(base):
        return 'claude'
    if is_python(base):
        return 'hermes' if hermes_args(names[1:]) else base
    if base not in ('node', 'nodejs', 'bun'):
        return base
    index = _hosted_script_index(names)
    if index is None:
        return base
    # Only the first script operand identifies the hosted program.
    arg = names[index]
    token = os.path.basename(arg).removesuffix('.exe')
    kind = HOSTED_BINS.get(token, '')
    if not kind:
        normalized = '/' + arg.replace('\\', '/').lstrip('/')
        for segment, candidate in HOSTED_PACKAGES:
            if segment in normalized:
                kind = candidate
                break
    if kind == 'codex' and 'app-server' in names[index + 1:index + 3]:
        return 'codex-app-server'
    return kind or base


def process_args(pid, proc_root='/proc'):
    """Return the decoded argv list for pid from /proc."""
    try:
        raw = open(f'{proc_root}/{pid}/cmdline', 'rb').read().split(b'\0')
        return [part.decode('utf-8', 'replace') for part in raw if part]
    except OSError:
        return []


def process_name(pid, proc_root='/proc'):
    """Return the executable basename used for agent kind matching.

    Prefer argv so Node-based CLIs still resolve: Cursor's ``agent`` (whose
    ``comm`` is often ``MainThread``) and Node-hosted CLIs whose executable is
    ``node``. Fall back to ``comm``.
    """
    name = name_from_args(process_args(pid, proc_root))
    if name:
        return name
    try:
        comm = open(f'{proc_root}/{pid}/comm', encoding='utf-8').read().strip().removesuffix('.exe')
        return 'claude' if is_claude_version(comm) else comm
    except OSError:
        return ''
