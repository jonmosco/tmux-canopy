#!/usr/bin/env python3
"""Opt-in, observational lifecycle bridge for supported agent harnesses."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))
from subagent_state import agent_id, list_field, next_entries

spec = importlib.util.spec_from_file_location('canopy_codex_hook', Path(__file__).with_name('codex-hook.py'))
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def normalized(kind, event, event_name=None):
    name = (event_name if kind == 'agy' else
            event.get('hook_event_name') if kind in ('claude', 'gemini') else event.get('type'))
    if not isinstance(name, str):
        return None
    if kind == 'agy':
        if name == 'PreInvocation' and 'invocationNum' in event:
            return 'working', name
        if name == 'PostInvocation' and 'invocationNum' in event:
            return 'working', name
        if name == 'PostToolUse' and isinstance(event.get('toolCall'), dict):
            return 'working', name
        if name == 'Stop' and isinstance(event.get('fullyIdle'), bool):
            if not event['fullyIdle']:
                return 'working', name
            if event.get('error') or event.get('terminationReason') in ('error', 'max_steps_exceeded'):
                return 'interrupted', name
            return 'turn-ended', name
        return None
    if kind == 'claude':
        mapping = {'SessionStart': 'ready', 'UserPromptSubmit': 'working',
                   'PermissionRequest': 'needs-input', 'Stop': 'turn-ended',
                   'StopFailure': 'interrupted', 'SessionEnd': 'session-ended',
                   'SubagentStart': 'subagent-start', 'SubagentStop': 'subagent-stop'}
        if name == 'Notification' and event.get('notification_type') == 'permission_prompt':
            return 'needs-input', name
        if name == 'PostToolUse':
            return 'clear-request', name
    elif kind == 'gemini':
        mapping = {'SessionStart': 'ready', 'BeforeAgent': 'working',
                   'AfterAgent': 'turn-ended', 'SessionEnd': 'session-ended'}
        if name == 'Notification' and event.get('notification_type') == 'ToolPermission':
            return 'needs-input', name
        if name == 'AfterTool':
            return 'clear-request', name
    elif kind in ('pi', 'omp'):
        mapping = {'session_start': 'ready', 'agent_start': 'working',
                   'agent_end': 'turn-ended', 'session_shutdown': 'session-ended'}
    elif kind == 'opencode':
        mapping = {'session.created': 'ready', 'session.idle': 'turn-ended',
                   'permission.asked': 'needs-input', 'session.error': 'interrupted',
                   'session.deleted': 'session-ended'}
        if name == 'permission.replied':
            return 'clear-request', name
        if name == 'session.status':
            status = (event.get('properties') or {}).get('status') or {}
            state = status.get('type') if isinstance(status, dict) else status
            if state == 'busy':
                return 'working', name
            if state == 'idle':
                return 'turn-ended', name
    else:
        return None
    state = mapping.get(name)
    return (state, name) if state else None


def opencode_pane(session, event):
    """Resolve global OpenCode plugin events only to a uniquely verified pane."""
    props = event.get('properties') or {}
    if not isinstance(props, dict):
        return ''
    rows = core.tmux('list-panes', '-a', '-F',
                     '#{pane_id}|#{pane_pid}|#{pane_dead}|#{@tmux_canopy}|#{@tmux_canopy_slot}|#{pane_current_path}|#{@tmux_canopy_agent_source}|#{@tmux_canopy_agent_session}|#{@tmux_canopy_agent_pane_pid}|#{@tmux_canopy_agent_process_pid}|#{@tmux_canopy_agent_process_birth}')
    if rows.returncode:
        return ''
    bound, new_session = set(), set()
    for line in rows.stdout.splitlines():
        fields = (line.split('|') + [''] * 11)[:11]
        pane, root, dead, sidebar, slot, path, source, bound_session, bound_pane_pid, bound_process, bound_birth = fields
        if not root.isdigit() or dead == '1' or sidebar == '1' or slot == '1':
            continue
        if source == 'opencode-hook' and bound_session == session and bound_pane_pid == root:
            identity = core.process_identity(root, 'opencode')
            if identity and identity == (bound_process, bound_birth):
                bound.add(pane)
        elif event.get('type') == 'session.created':
            identity = core.process_identity(root, 'opencode')
            if not identity:
                continue
            info = props.get('info') or {}
            directory = info.get('directory') if isinstance(info, dict) else ''
            # Without the session's project directory there is no safe way to
            # distinguish this server event from another OpenCode session.
            if not isinstance(directory, str) or not directory:
                continue
            try:
                if os.path.realpath(path) != os.path.realpath(directory):
                    continue
            except (OSError, TypeError):
                continue
            new_session.add(pane)
    candidates = bound or new_session
    return next(iter(candidates)) if len(candidates) == 1 else ''


def session_id(kind, event):
    if kind == 'opencode':
        props = event.get('properties') or {}
        if not isinstance(props, dict):
            return ''
        info = props.get('info') or {}
        if not isinstance(info, dict):
            info = {}
        return core.field(props.get('sessionID') or info.get('id'), 128)
    if kind in ('pi', 'omp'):
        return core.field(event.get('session_id'), 128)
    if kind == 'agy':
        return core.field(event.get('conversationId'), 128)
    return core.field(event.get('session_id'), 128)


def subagent_id(kind, event):
    return agent_id(event) if kind == 'claude' else ''


def report(kind, event, event_name=None):
    is_contract = kind == 'contract'
    if kind == 'contract':
        agent_kind = event.get('agent')
        state = event.get('state')
        allowed = {'ready', 'working', 'needs-input', 'turn-ended', 'session-ended', 'interrupted'}
        if agent_kind not in ('claude', 'codex', 'opencode', 'gemini', 'pi', 'omp', 'agy') or state not in allowed:
            return
        request = event.get('request') if isinstance(event.get('request'), dict) else {}
        if state == 'needs-input' and not any(request.get(k) for k in ('id', 'summary', 'tool')):
            return
        event = {'session_id': event.get('session_id'), 'state': state,
                 'tool_name': request.get('tool'), 'tool_input': {'description': request.get('summary', ''),
                 'command': request.get('command', '')}, 'request': request, '_contract': True}
        kind = agent_kind
        result = (state, 'ContractReport')
    else:
        result = normalized(kind, event, event_name)
    session = session_id(kind, event)
    if not result or not session:
        return
    state, name = result
    if kind == 'opencode':
        target = opencode_pane(session, event)
        if not target:
            return
        core.PANE = target
    if kind == 'claude' and name == 'SessionStart' and event.get('source') == 'compact':
        return
    meta = core.tmux('display-message', '-p', '-t', core.PANE,
                     '#{pane_id}|#{pane_pid}|#{pane_dead}|#{@tmux_canopy}|#{@tmux_canopy_slot}')
    if meta.returncode:
        return
    pane, pid, dead, sidebar, slot = (meta.stdout.rstrip('\n').split('|') + [''] * 5)[:5]
    if pane != core.PANE or not pid.isdigit() or dead == '1' or sidebar == '1' or slot == '1':
        return
    identity = core.process_identity(pid, kind)
    if identity is None:
        return
    process_pid, process_birth = identity
    current = core.read_options(core.FIELDS + ('timer',))
    current_timer = current.pop('timer')
    if (current['source'] != kind + '-hook' or current['pane_pid'] != pid or
            current['process_pid'] != process_pid or current['process_birth'] != process_birth):
        current = {key: '' for key in core.FIELDS}
    # Events can be delayed across agent session resets. Once a session is
    # associated with a pane, only a fresh start may replace its identity.
    start = name in ('SessionStart', 'session_start', 'session.created', 'PreInvocation') or \
        (is_contract and state == 'ready')
    if current['session'] and current['session'] != session and not start:
        return
    if current['session'] != session and start:
        current = {key: '' for key in core.FIELDS}
    now = str(int(time.time()))
    agent = subagent_id(kind, event)
    values = dict(current)
    values.update(source=kind + '-hook', session=session, pane_pid=pid,
                  process_pid=process_pid, process_birth=process_birth,
                  subagents=next_entries(current['subagents'], agent, event, state, now))
    # Only a request's own agent (or the main thread) can clear it.
    if state == 'subagent-stop' and current['status'] == 'needs-input' and \
            current['request_agent'] == agent:
        state = 'working'
    elif state == 'clear-request' and current['status'] == 'needs-input' and \
            current['request_agent'] == agent and \
            (kind not in ('claude', 'gemini') or core.field(event.get('tool_name'), 80) == current['tool']):
        if kind == 'opencode':
            props = event.get('properties') or {}
            reply_id = core.field(props.get('permissionID') or props.get('requestID') or props.get('id'), 128) if isinstance(props, dict) else ''
            if not reply_id or reply_id != current['request']:
                return
        state = 'working'
    elif (agent and state != 'needs-input') or state in ('clear-request', 'subagent-start', 'subagent-stop'):
        # Subagent progress leaves the main thread's status and its age alone.
        if values['subagents'] == current['subagents']:
            return
        values['updated'] = current['updated'] or now
        if core.write(values):
            core.refresh()
        return
    values.update(status=state, updated=now, request_agent=agent if state == 'needs-input' else '')
    if state == 'needs-input':
        tool = core.field(event.get('tool_name'), 80)
        detail = event.get('tool_input') or event.get('details') or {}
        if not isinstance(detail, dict):
            detail = {}
        props = event.get('properties') or {}
        if kind == 'opencode' and isinstance(props, dict):
            tool = core.field(props.get('permission') or props.get('action'), 80)
            metadata = props.get('metadata') if isinstance(props.get('metadata'), dict) else {}
            detail = metadata
            if not event.get('message') and not detail.get('description') and tool:
                values['summary'] = core.field(f"{tool} permission requested", 300)
            patterns = props.get('patterns')
            if not detail.get('command') and isinstance(patterns, list):
                detail = dict(detail, command=', '.join(core.field(item, 120) for item in patterns if isinstance(item, str)))
        values['tool'] = tool
        values['summary'] = (core.field(event.get('message'), 300) or
                             core.field(detail.get('description'), 300) or
                             (core.field(f"{tool} permission requested", 300) if kind == 'opencode' and tool else
                              'Approval requested' if tool else 'Input requested'))
        if agent:
            values['summary'] = core.field(f"{list_field(event.get('agent_type'), 40) or 'Subagent'}: {values['summary']}", 300)
        values['command'] = core.field(detail.get('command'), 500)
        request_id = ''
        if is_contract:
            request_id = core.field((event.get('request') or {}).get('id'), 128) if isinstance(event.get('request'), dict) else ''
        elif kind == 'opencode':
            request_id = core.field(props.get('requestID') or props.get('permissionID') or props.get('id'), 128) if isinstance(props, dict) else ''
        values['request'] = request_id or hashlib.sha256(json.dumps([session, name, tool, detail],
                                                                     sort_keys=True, default=str).encode()).hexdigest()[:24]
    else:
        values.update(tool='', summary='', command='', request='')
    if core.write(values):
        core.schedule_expiry(process_pid, process_birth, current_timer)
        core.refresh()


def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else ''
    agy_event = sys.argv[2] if kind == 'agy' and len(sys.argv) > 2 else ''
    # The adapter is observational. It never registers PreToolUse and never
    # returns a permission decision that could authorize a tool.
    response = '{"decision": ""}' if agy_event == 'Stop' else '{}'
    if kind not in ('claude', 'opencode', 'gemini', 'pi', 'omp', 'agy') or not os.environ.get('TMUX') or not re.fullmatch(r'%[0-9]+', core.PANE):
        if kind == 'agy':
            print(response)
        return
    try:
        raw = sys.stdin.buffer.read(131073)
        if len(raw) > 131072:
            if kind == 'agy':
                print(response)
            return
        event = json.loads(raw) if raw.strip() else {}
        if not isinstance(event, dict):
            if kind == 'agy':
                print(response)
            return
        lock = 'tmux-canopy-agent-' + core.PANE[1:]
        if core.tmux('wait-for', '-L', lock).returncode:
            if kind == 'agy':
                print(response)
            return
        try:
            report(kind, event, agy_event)
        finally:
            core.tmux('wait-for', '-U', lock)
            if kind == 'agy':
                print(response)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.TimeoutExpired):
        if kind == 'agy':
            print(response)
        return


if __name__ == '__main__':
    main()
