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
                   'StopFailure': 'interrupted', 'SessionEnd': 'session-ended'}
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
    current = {key: core.option(key) for key in core.FIELDS}
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
    if state == 'clear-request':
        if current['status'] != 'needs-input':
            return
        if kind in ('claude', 'gemini'):
            tool = core.field(event.get('tool_name'), 80)
            if tool != current['tool']:
                return
        state = 'working'
    values = dict(current)
    values.update(source=kind + '-hook', session=session, pane_pid=pid,
                  process_pid=process_pid, process_birth=process_birth,
                  status=state, updated=str(int(time.time())))
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
        values['command'] = core.field(detail.get('command'), 500)
        values['request'] = hashlib.sha256(json.dumps([session, name, tool, detail],
                                                        sort_keys=True, default=str).encode()).hexdigest()[:24]
    else:
        values.update(tool='', summary='', command='', request='')
    if core.write(values):
        core.schedule_expiry(process_pid, process_birth)
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
