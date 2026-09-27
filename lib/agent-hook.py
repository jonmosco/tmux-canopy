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

spec = importlib.util.spec_from_file_location('canopy_codex_hook', Path(__file__).with_name('codex-hook.py'))
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)


def normalized(kind, event):
    name = event.get('hook_event_name') if kind in ('claude', 'gemini') else event.get('type')
    if not isinstance(name, str):
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
    return core.field(event.get('session_id'), 128)


# Claude Code subagents share their parent's session and pane; events fired
# inside one carry agent_id/agent_type. They are kept as a small list on the
# parent pane: id,type,status,updated,tool entries joined by ';'.
MAX_SUBAGENTS = 8
SUBAGENT_STATES = ('working', 'needs-input', 'done')
# Claude Code delivers a background subagent's result as a new turn, so a
# finished subagent is kept this long before a new prompt may drop it.
SUBAGENT_DONE_GRACE = 30


def subagent_id(kind, event):
    value = event.get('agent_id') if kind == 'claude' else None
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value) else ''


def list_field(value, limit):
    return re.sub(r'[;,]', ' ', core.field(value, limit)).strip()


def parse_subagents(text):
    entries = []
    for item in text.split(';'):
        parts = item.split(',')
        if (len(parts) == 5 and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', parts[0]) and
                parts[2] in SUBAGENT_STATES and parts[3].isdigit()):
            entries.append(parts)
    return entries


def format_subagents(entries):
    # Past the cap, forget finished subagents first, then the oldest.
    while len(entries) > MAX_SUBAGENTS:
        finished = [entry for entry in entries if entry[2] == 'done']
        entries.remove(finished[0] if finished else entries[0])
    return ';'.join(','.join(entry) for entry in entries)


def update_subagent(entries, agent, event, state, now):
    entry = next((item for item in entries if item[0] == agent), None)
    if entry is None:
        if state == 'subagent-stop':
            return
        entry = [agent, 'subagent', 'working', now, '']
        entries.append(entry)
    before = entry[:]
    entry[1] = list_field(event.get('agent_type'), 40) or entry[1]
    tool = list_field(event.get('tool_name'), 80)
    if state in ('subagent-stop', 'turn-ended'):
        entry[2], entry[4] = 'done', ''
    elif state == 'needs-input':
        entry[2], entry[4] = 'needs-input', tool
    elif state == 'clear-request' and entry[2] == 'needs-input' and entry[4] == tool:
        entry[2], entry[4] = 'working', ''
    # Routine tool calls only refresh a minute-old timestamp, so a busy
    # subagent does not redraw the sidebar on every tool call.
    if entry != before or int(now) - int(entry[3]) >= 60:
        entry[3] = now


def report(kind, event):
    result = normalized(kind, event)
    session = session_id(kind, event)
    if not result or not session:
        return
    state, name = result
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
    # OpenCode server plugins can receive events for other sessions. Once a
    # session is associated with a pane, never accept a different session.
    start = name in ('SessionStart', 'session_start', 'session.created')
    if current['session'] and current['session'] != session and not start:
        return
    if current['session'] != session and start:
        current = {key: '' for key in core.FIELDS}
    now = str(int(time.time()))
    agent = subagent_id(kind, event)
    subagents = parse_subagents(current['subagents'])
    if agent:
        update_subagent(subagents, agent, event, state, now)
    elif state == 'working':
        # A new prompt starts a new turn: subagents that finished a while ago
        # are dropped, recently finished and still running ones stay.
        subagents = [entry for entry in subagents if entry[2] != 'done' or
                     int(now) - int(entry[3]) < SUBAGENT_DONE_GRACE]
    elif state == 'session-ended':
        subagents = []
    values = dict(current)
    values.update(source=kind + '-hook', session=session, pane_pid=pid,
                  process_pid=process_pid, process_birth=process_birth,
                  subagents=format_subagents(subagents))
    # Only a request's own agent (or the main thread) can clear it.
    if state == 'clear-request' and current['status'] == 'needs-input' and \
            current['request_agent'] == agent and \
            (kind not in ('claude', 'gemini') or core.field(event.get('tool_name'), 80) == current['tool']):
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
            tool = core.field(props.get('permission'), 80)
        values['tool'] = tool
        values['summary'] = (core.field(event.get('message'), 300) or
                             core.field(detail.get('description'), 300) or
                             ('Approval requested' if tool else 'Input requested'))
        if agent:
            values['summary'] = core.field(f"{list_field(event.get('agent_type'), 40) or 'Subagent'}: {values['summary']}", 300)
        values['command'] = core.field(detail.get('command'), 500)
        values['request'] = hashlib.sha256(json.dumps([session, name, tool, detail],
                                                        sort_keys=True, default=str).encode()).hexdigest()[:24]
    else:
        values.update(tool='', summary='', command='', request='')
    if core.write(values):
        core.schedule_expiry(process_pid, process_birth, current_timer)
        core.refresh()


def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else ''
    if kind not in ('claude', 'opencode', 'gemini', 'pi', 'omp') or not os.environ.get('TMUX') or not re.fullmatch(r'%[0-9]+', core.PANE):
        return
    try:
        raw = sys.stdin.buffer.read(131073)
        if len(raw) > 131072:
            return
        event = json.loads(raw)
        if not isinstance(event, dict):
            return
        lock = 'tmux-canopy-agent-' + core.PANE[1:]
        if core.tmux('wait-for', '-L', lock).returncode:
            return
        try:
            report(kind, event)
        finally:
            core.tmux('wait-for', '-U', lock)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.TimeoutExpired):
        return


if __name__ == '__main__':
    main()
