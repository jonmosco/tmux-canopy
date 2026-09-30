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
from subagent_state import (agent_id, list_field, next_entries, parse_subagents,
                             resolve_cursor_stop_id, with_cursor_subagent_fields)

spec = importlib.util.spec_from_file_location('canopy_codex_hook', Path(__file__).with_name('codex-hook.py'))
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def normalized(kind, event, event_name=None):
    if kind in ('agy', 'antigravity'):
        kind = 'agy'
    name = (event_name if kind == 'agy' else
            event.get('hook_event_name') if kind in ('claude', 'gemini', 'cursor-agent') else event.get('type'))
    if not isinstance(name, str):
        return None
    if kind == 'agy':
        if name == 'PreInvocation' and 'invocationNum' in event:
            return 'working', name
        if name == 'PostInvocation' and 'invocationNum' in event:
            return 'working', name
        if name == 'PostToolUse' and ('stepIdx' in event or isinstance(event.get('toolCall'), dict)):
            return 'working', name
        if name == 'Stop':
            if event.get('fullyIdle') is False:
                return 'working', name
            if event.get('error') or event.get('terminationReason') in ('error', 'max_steps_exceeded'):
                return 'interrupted', name
            if isinstance(event.get('fullyIdle'), bool) or 'executionNum' in event or 'terminationReason' in event:
                return 'turn-ended', name
            return None
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
                   'tool_execution_start': 'working',
                   'agent_end': 'turn-ended', 'agent_settled': 'turn-ended',
                   'agent_interrupted': 'interrupted', 'session_shutdown': 'session-ended'}
        if name == 'ui_prompt_start':
            return 'needs-input', name
        if name == 'ui_prompt_end':
            return 'clear-request', name
    elif kind == 'opencode':
        mapping = {'session.created': 'ready', 'session.updated': 'subagent-update', 'session.idle': 'turn-ended',
                    'session.error': 'interrupted', 'session.deleted': 'session-ended',
                    'permission.asked': 'needs-input', 'permission.updated': 'needs-input', 'permission.v2.asked': 'needs-input',
                   'question.asked': 'needs-input', 'question.v2.asked': 'needs-input',
                   'session.next.prompted': 'working', 'session.next.prompt.admitted': 'working',
                   'session.next.step.started': 'working', 'session.next.tool.called': 'working',
                   'session.next.step.failed': 'interrupted'}
        if name in ('permission.replied', 'permission.v2.replied',
                    'question.replied', 'question.v2.replied',
                    'question.rejected', 'question.v2.rejected'):
            return 'clear-request', name
        if name == 'session.status':
            status = opencode_payload(event).get('status') or {}
            state = status.get('type') if isinstance(status, dict) else status
            if state in ('busy', 'retry'):
                return 'working', name
            if state == 'idle':
                return 'turn-ended', name
    elif kind == 'cursor-agent':
        mapping = {'sessionStart': 'ready', 'beforeSubmitPrompt': 'working',
                   'stop': 'turn-ended', 'sessionEnd': 'session-ended',
                   'subagentStart': 'subagent-start', 'subagentStop': 'subagent-stop'}
    else:
        return None
    state = mapping.get(name)
    return (state, name) if state else None


def opencode_payload(event):
    """V1 bus events use properties; some V2 encodings use data."""
    if not isinstance(event, dict):
        return {}
    for key in ('properties', 'data'):
        body = event.get(key)
        if isinstance(body, dict):
            return body
    return event


def opencode_directory(event):
    props = opencode_payload(event)
    info = props.get('info') if isinstance(props.get('info'), dict) else {}
    location = event.get('location') if isinstance(event.get('location'), dict) else {}
    directory = info.get('directory') or location.get('directory') or props.get('directory') or ''
    return directory if isinstance(directory, str) else ''


def opencode_info(event):
    info = opencode_payload(event).get('info')
    return info if isinstance(info, dict) else {}


def opencode_parent_session(event):
    return core.field(opencode_info(event).get('parentID'), 128)


def opencode_pane(session, event):
    """Resolve global OpenCode plugin events only to a uniquely verified pane."""
    directory = opencode_directory(event)
    rows = core.tmux('list-panes', '-a', '-F',
                      '#{pane_id}|#{pane_pid}|#{pane_dead}|#{@tmux_canopy}|#{@tmux_canopy_slot}|#{pane_current_path}|#{@tmux_canopy_agent_source}|#{@tmux_canopy_agent_session}|#{@tmux_canopy_agent_pane_pid}|#{@tmux_canopy_agent_process_pid}|#{@tmux_canopy_agent_process_birth}|#{@tmux_canopy_agent_subagents}')
    if rows.returncode:
        return ''
    bound, child, new_session = set(), set(), set()
    for line in rows.stdout.splitlines():
        fields = (line.split('|') + [''] * 12)[:12]
        pane, root, dead, sidebar, slot, path, source, bound_session, bound_pane_pid, bound_process, bound_birth, subagents = fields
        if not root.isdigit() or dead == '1' or sidebar == '1' or slot == '1':
            continue
        if source == 'opencode-hook' and bound_session == session and bound_pane_pid == root:
            identity = core.process_identity(root, 'opencode')
            if identity and identity == (bound_process, bound_birth):
                bound.add(pane)
        elif source == 'opencode-hook' and any(entry[0] == session for entry in parse_subagents(subagents)):
            identity = core.process_identity(root, 'opencode')
            if identity and identity == (bound_process, bound_birth):
                child.add(pane)
        elif (not bound_session or
              (source == 'opencode-hook' and bound_process and
               core.process_identity(root, 'opencode') != (bound_process, bound_birth))) and directory:
            identity = core.process_identity(root, 'opencode')
            if not identity:
                continue
            # Without a project directory there is no safe way to distinguish
            # this server event from another OpenCode session.
            try:
                if os.path.realpath(path) != os.path.realpath(directory):
                    continue
            except (OSError, TypeError):
                continue
            new_session.add(pane)
    candidates = bound or child or new_session
    return next(iter(candidates)) if len(candidates) == 1 else ''


def session_id(kind, event):
    if kind == 'opencode':
        props = opencode_payload(event)
        info = props.get('info') if isinstance(props.get('info'), dict) else {}
        return core.field(props.get('sessionID') or info.get('id') or event.get('sessionID'), 128)
    if kind in ('pi', 'omp'):
        return core.field(event.get('session_id'), 128)
    if kind == 'agy':
        return core.field(event.get('conversationId'), 128)
    if kind == 'cursor-agent':
        return core.field(event.get('conversation_id') or event.get('session_id'), 128)
    return core.field(event.get('session_id'), 128)


def subagent_id(kind, event, current=None):
    if kind == 'claude':
        return agent_id(event)
    if kind == 'cursor-agent':
        return resolve_cursor_stop_id(event, current['subagents'] if current else '')
    if kind == 'opencode' and current:
        session = session_id(kind, event)
        info = opencode_info(event)
        if session and info.get('parentID') == current['session']:
            return session
        if session and any(entry[0] == session for entry in parse_subagents(current['subagents'])):
            return session
    return ''


def with_opencode_subagent_fields(event):
    """Copy OpenCode child-session metadata into the shared subagent schema."""
    out = dict(event)
    info = opencode_info(event)
    label = list_field(info.get('agent'), 40)
    title = list_field(info.get('title'), 40)
    if label and title:
        label = list_field(f'{label}: {title}', 40)
    if label or title:
        out['agent_type'] = label or title
    props = opencode_payload(event)
    if not out.get('tool_name') and isinstance(props, dict):
        out['tool_name'] = props.get('permission') or props.get('action') or props.get('tool') or ''
    return out


def report(kind, event, event_name=None):
    if kind in ('agy', 'antigravity'):
        kind = 'agy'
    is_contract = kind == 'contract'
    if kind == 'contract':
        agent_kind = event.get('agent')
        state = event.get('state')
        allowed = {'ready', 'working', 'needs-input', 'turn-ended', 'session-ended', 'interrupted'}
        if agent_kind not in ('claude', 'codex', 'opencode', 'gemini', 'pi', 'omp', 'agy', 'cursor-agent') or state not in allowed:
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
        # A child session is owned by its already-verified parent pane. Creation
        # supplies parentID; later child events resolve through stored child IDs.
        target = opencode_pane(opencode_parent_session(event) or session, event)
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
    start = name in ('SessionStart', 'session_start', 'session.created', 'PreInvocation', 'sessionStart') or \
        (is_contract and state == 'ready')
    agent = subagent_id(kind, event, current)
    child_event = kind == 'opencode' and bool(agent)
    if kind == 'opencode' and name == 'session.updated' and not child_event:
        return
    if not child_event:
        if current['session'] and current['session'] != session and not start:
            return
        if current['session'] != session and start:
            current = {key: '' for key in core.FIELDS}
    now = str(int(time.time()))
    stored_session = current['session'] if child_event else session
    if kind == 'opencode' and agent:
        if name in ('session.created', 'session.updated'):
            state = 'subagent-update'
        elif name == 'session.deleted':
            state = 'subagent-stop'
        elif name in ('session.idle', 'session.error') or (name == 'session.status' and state == 'turn-ended'):
            state = 'subagent-done'
    if kind == 'cursor-agent':
        subagent_event = with_cursor_subagent_fields(event)
    elif kind == 'opencode':
        subagent_event = with_opencode_subagent_fields(event)
        if state == 'clear-request' and agent:
            entry = next((item for item in parse_subagents(current['subagents']) if item[0] == agent), None)
            if entry:
                subagent_event['tool_name'] = entry[4]
    else:
        subagent_event = event
    values = dict(current)
    values.update(source=kind + '-hook', session=stored_session, pane_pid=pid,
                  process_pid=process_pid, process_birth=process_birth,
                  subagents=next_entries(current['subagents'], agent, subagent_event, state, now))
    # Only a request's own agent (or the main thread) can clear it.
    if state == 'subagent-stop' and current['status'] == 'needs-input' and \
            current['request_agent'] == agent:
        state = 'working'
    elif state == 'clear-request' and current['status'] == 'needs-input' and \
            current['request_agent'] == agent and \
            (kind not in ('claude', 'gemini') or core.field(event.get('tool_name'), 80) == current['tool']):
        if kind == 'opencode':
            props = opencode_payload(event)
            reply_id = core.field(props.get('permissionID') or props.get('requestID') or props.get('id'), 128)
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
        props = opencode_payload(event) if kind == 'opencode' else {}
        if kind == 'opencode':
            tool = core.field(props.get('permission') or props.get('action') or props.get('tool'), 80)
            metadata = props.get('metadata') if isinstance(props.get('metadata'), dict) else {}
            detail = metadata
            questions = props.get('questions')
            if isinstance(questions, list) and questions and isinstance(questions[0], dict):
                asked = questions[0].get('question') or questions[0].get('header') or ''
                if asked and not detail.get('description'):
                    detail = dict(detail, description=asked)
            if not event.get('message') and not detail.get('description') and tool:
                values['summary'] = core.field(f"{tool} permission requested", 300)
            patterns = props.get('resources') if isinstance(props.get('resources'), list) else props.get('patterns')
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
    if kind == 'antigravity':
        kind = 'agy'
    agy_event = sys.argv[2] if kind == 'agy' and len(sys.argv) > 2 else ''
    # The adapter is observational. It never registers PreToolUse and never
    # returns a permission decision that could authorize a tool.
    response = '{"decision": ""}' if agy_event == 'Stop' else '{}'
    # Cursor Agent requires an explicit allow response for subagentStart (and
    # only that event); every other reply is the inert default below.
    # Cursor can treat a missing allow as a block, so stdin is read/parsed
    # (bounded, same as always) and this decision is made before any
    # TMUX/pane gating below, ensuring every exit path for a subagentStart
    # event — including missing TMUX or an invalid pane — prints allow.
    cursor_response = '{}'

    def emit():
        if kind == 'agy':
            print(response)
        elif kind == 'cursor-agent':
            print(cursor_response)

    try:
        raw = sys.stdin.buffer.read(131073)
        oversized = len(raw) > 131072
        # Oversized stdin cannot be parsed into an event, so cursor_response
        # never leaves its inert '{}' default for this request.
        event = {} if oversized else (json.loads(raw) if raw.strip() else {})
    except (OSError, ValueError):
        oversized, event = False, None
    if not isinstance(event, dict):
        emit()
        return
    if kind == 'cursor-agent' and event.get('hook_event_name') == 'subagentStart':
        cursor_response = '{"permission":"allow"}'
    if (oversized or
            kind not in ('claude', 'opencode', 'gemini', 'pi', 'omp', 'agy', 'cursor-agent') or
            not os.environ.get('TMUX') or not re.fullmatch(r'%[0-9]+', core.PANE)):
        emit()
        return
    # Exactly one emit() must run past this point, however report() exits:
    # a single try/except/finally, followed by one unconditional emit().
    try:
        lock_fd = core.pane_lock(core.PANE[1:])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        lock_fd = None
    if not lock_fd:
        emit()
        return
    try:
        report(kind, event, agy_event)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.TimeoutExpired):
        pass
    finally:
        core.pane_unlock(lock_fd)
    emit()


if __name__ == '__main__':
    main()
