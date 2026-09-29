"""Bounded, sanitized subagent state shared by lifecycle reporters."""
import re

MAX_SUBAGENTS = 8
SUBAGENT_STATES = ('unknown', 'working', 'needs-input', 'done')


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
    if state == 'subagent-stop':
        entries[:] = [entry for entry in entries if entry[0] != agent]
        return
    entry = next((item for item in entries if item[0] == agent), None)
    if entry is None:
        entry = [agent, 'subagent', 'unknown' if state == 'subagent-update' else 'working', now, '']
        entries.append(entry)
    before = entry[:]
    entry[1] = list_field(event.get('agent_type'), 40) or entry[1]
    tool = list_field(event.get('tool_name'), 80)
    if state == 'needs-input':
        entry[2], entry[4] = 'needs-input', tool
    elif state == 'clear-request' and entry[2] == 'needs-input' and entry[4] == tool:
        entry[2], entry[4] = 'working', ''
    elif state == 'working':
        entry[2], entry[4] = 'working', ''
    elif state == 'subagent-done':
        entry[2], entry[4] = 'done', ''
    if entry != before or int(now) - int(entry[3]) >= 60:
        entry[3] = now


def cursor_agent_id(event):
    value = event.get('subagent_id')
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value) else ''


def with_cursor_subagent_fields(event):
    """Copy Cursor field names into the Claude-shaped keys update_subagent expects."""
    out = dict(event)
    if not out.get('agent_type') and isinstance(out.get('subagent_type'), str):
        out['agent_type'] = out['subagent_type']
    return out


def resolve_cursor_stop_id(event, current_text):
    """Prefer subagent_id; else unique live child matching subagent_type."""
    direct = cursor_agent_id(event)
    if direct:
        return direct
    wanted = list_field(event.get('subagent_type'), 40)
    if not wanted:
        return ''
    matches = [entry[0] for entry in parse_subagents(current_text)
               if entry[2] != 'done' and entry[1] == wanted]
    return matches[0] if len(matches) == 1 else ''


def next_entries(current, agent, event, state, now):
    entries = parse_subagents(current)
    if state == 'session-ended':
        entries = []
    elif agent:
        update_subagent(entries, agent, event, state, now)
    else:
        # Completed children remain visible until the parent advances, then a
        # fresh parent event clears the previous turn's finished child rows.
        entries = [entry for entry in entries if entry[2] != 'done']
    return format_subagents(entries)
