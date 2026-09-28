"""Bounded, sanitized subagent state shared by lifecycle reporters."""
import re

MAX_SUBAGENTS = 8
SUBAGENT_STATES = ('working', 'needs-input', 'done')


def agent_id(event):
    value = event.get('agent_id')
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value) else ''


def list_field(value, limit):
    if not isinstance(value, str):
        return ''
    value = re.sub(r'[\x00-\x1f\x7f;,]+', ' ', value).strip()
    return value[:limit] + ('…' if len(value) > limit else '')


def parse_subagents(text):
    entries = []
    for item in text.split(';'):
        parts = item.split(',')
        if (len(parts) == 5 and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', parts[0]) and
                parts[2] in SUBAGENT_STATES and parts[3].isdigit()):
            entries.append(parts)
    return entries


def format_subagents(entries):
    while len(entries) > MAX_SUBAGENTS:
        entries.pop(0)
    return ';'.join(','.join(entry) for entry in entries)


def update_subagent(entries, agent, event, state, now):
    if state in ('subagent-stop', 'turn-ended'):
        entries[:] = [entry for entry in entries if entry[0] != agent]
        return
    entry = next((item for item in entries if item[0] == agent), None)
    if entry is None:
        entry = [agent, 'subagent', 'working', now, '']
        entries.append(entry)
    before = entry[:]
    entry[1] = list_field(event.get('agent_type'), 40) or entry[1]
    tool = list_field(event.get('tool_name'), 80)
    if state == 'needs-input':
        entry[2], entry[4] = 'needs-input', tool
    elif state == 'clear-request' and entry[2] == 'needs-input' and entry[4] == tool:
        entry[2], entry[4] = 'working', ''
    if entry != before or int(now) - int(entry[3]) >= 60:
        entry[3] = now


def next_entries(current, agent, event, state, now):
    # Drop entries left by older versions that retained completed children.
    entries = [entry for entry in parse_subagents(current) if entry[2] != 'done']
    if state == 'session-ended':
        entries = []
    elif agent:
        update_subagent(entries, agent, event, state, now)
    return format_subagents(entries)
