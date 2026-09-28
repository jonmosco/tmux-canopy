#!/usr/bin/env python3
"""Opt-in, read-only Codex lifecycle reporter for tmux-canopy.

Configured as a Codex command hook. Never returns a decision to Codex.
"""
import hashlib
import json
import os
import re
import shlex
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))
from subagent_state import agent_id, list_field, next_entries

SEP = "\x1f"
PANE = os.environ.get("TMUX_PANE", "")
EVENTS = {"SessionStart", "UserPromptSubmit", "PermissionRequest",
          "PreToolUse", "PostToolUse", "Stop", "Interrupt", "SessionEnd",
          "SubagentStart", "SubagentStop"}
PREFIX = "@tmux_canopy_agent_"
FIELDS = ("source", "session", "turn", "pane_pid", "status", "tool",
          "summary", "command", "request", "updated", "process_pid", "process_birth",
          "request_agent", "subagents")


def tmux(*args):
    return subprocess.run(("tmux", *args), text=True, capture_output=True,
                          timeout=3, check=False)


def field(value, limit=300):
    if not isinstance(value, str):
        return ""
    value = re.sub(r"[\x00-\x1f\x7f]+", " ", value).strip()
    return value[:limit] + ("…" if len(value) > limit else "")


def read_options(keys):
    # One display-message call reads every field, instead of one
    # show-option subprocess per field. Stored values already run through
    # field(), which strips control bytes (including 0x1f) from anything
    # user-controlled, so \x1f is a safe field separator here.
    fmt = SEP.join(f"#{{{PREFIX}{key}}}" for key in keys)
    result = tmux("display-message", "-p", "-t", PANE, fmt)
    if result.returncode:
        return {key: "" for key in keys}
    values = result.stdout.rstrip("\n").split(SEP)
    values += [""] * (len(keys) - len(values))
    return dict(zip(keys, values))


def fingerprint(event):
    inputs = event.get("tool_input")
    if isinstance(inputs, dict):
        # PermissionRequest may add a human approval reason that tool events
        # omit. It describes the request, not the tool invocation.
        inputs = {key: item for key, item in inputs.items() if key != "description"}
    value = json.dumps([event.get("tool_name"), inputs],
                       sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def write(values):
    command = []
    for key in FIELDS:
        if command:
            command.append(";")
        command += ["set-option", "-pq", "-t", PANE, PREFIX + key,
                    str(values.get(key, ""))]
    return tmux(*command).returncode == 0


def refresh():
    subprocess.run((str(Path(__file__).resolve().parents[1] / "scripts" / "agent-refresh"),),
                   capture_output=True, timeout=3, check=False)


def schedule_expiry(process_pid, process_birth, current_timer):
    if not process_birth.isdigit():
        return  # Portable platforms retain manual refresh on report expiry.
    token = f"{process_pid}:{process_birth}"
    if current_timer == token:
        return
    tmux("set-option", "-pq", "-t", PANE, PREFIX + "timer", token)
    worker = Path(__file__).resolve().parents[1] / "scripts" / "agent-expiry"
    command = " ".join(shlex.quote(value) for value in (str(worker), PANE, token))
    tmux("run-shell", "-b", command)


def linux_stat(pid):
    try:
        raw = open(f"/proc/{pid}/stat", encoding="utf-8").read()
        fields = raw.rsplit(") ", 1)[1].split()
        return int(fields[1]), fields[19]
    except (OSError, IndexError, ValueError):
        return None


def process_identity(root, kind="codex"):
    """Find a live agent process in this pane, including nested shells."""
    names = {"codex": {"codex"}, "claude": {"claude", "claude-code"},
             "opencode": {"opencode"}, "gemini": {"gemini"},
             "pi": {"pi"}, "omp": {"omp"}}.get(kind, set())
    if not names:
        return None
    try:
        root = int(root)
    except ValueError:
        return None
    if os.path.isdir("/proc/self"):
        # Fast path: in normal hook execution, this process is a direct descendant
        # of the agent and the pane root shell. Walk up parents before scanning /proc.
        current = os.getppid()
        chain = []
        for _ in range(128):
            if current <= 1:
                break
            stat = linux_stat(current)
            if not stat:
                break
            try:
                with open(f"/proc/{current}/comm", encoding="utf-8") as stream:
                    pname = stream.read().strip().removesuffix(".exe")
            except OSError:
                pname = ""
            chain.append((current, pname, stat[1]))
            if current == root:
                for pid, name, birth in chain:
                    if name in names:
                        return pid, str(birth)
                break
            if stat[0] <= 0 or stat[0] == current:
                break
            current = stat[0]

        candidates = []
        try:
            entries = os.scandir("/proc")
        except OSError:
            return None
        with entries:
            for entry in entries:
                if not entry.name.isdigit():
                    continue
                try:
                    with open(f"{entry.path}/comm", encoding="utf-8") as stream:
                        if stream.read().strip().removesuffix(".exe") not in names:
                            continue
                except OSError:
                    continue
                pid = int(entry.name)
                stat = linux_stat(pid)
                if stat:
                    candidates.append((pid, stat[1]))
        stat_for = linux_stat
    else:
        try:
            records = subprocess.run(("ps", "-eo", "pid=,ppid=,comm="), text=True,
                                     capture_output=True, timeout=3, check=False).stdout.splitlines()
        except (OSError, subprocess.TimeoutExpired):
            return None
        parents = {}
        candidates = []
        for line in records:
            fields = line.split(None, 2)
            if len(fields) == 3 and fields[0].isdigit() and fields[1].isdigit():
                parents[int(fields[0])] = int(fields[1])
                if os.path.basename(fields[2]).removesuffix(".exe") in names:
                    candidates.append((int(fields[0]), ""))
        def stat_for(pid):
            return (parents[pid], "") if pid in parents else None
    matches = []
    for pid, birth in candidates:
        current = pid
        for depth in range(128):
            if current == root:
                matches.append((depth, pid, birth))
                break
            stat = stat_for(current)
            if not stat or stat[0] <= 0 or stat[0] == current:
                break
            current = stat[0]
    if not matches:
        return None
    # A hook normally runs below its Codex process. An external test hook can
    # still select the sole pane candidate, but ambiguity never gets reported.
    ancestry = set()
    current = os.getppid()
    for _ in range(128):
        if current in ancestry or current <= 1:
            break
        ancestry.add(current)
        stat = stat_for(current)
        if not stat:
            break
        current = stat[0]
    related = [item for item in matches if item[1] in ancestry]
    matches = related or matches
    if not related and len(matches) > 1:
        return None
    matches.sort()
    _, pid, birth = matches[0]
    if not birth:
        try:
            birth = subprocess.run(("ps", "-p", str(pid), "-o", "lstart="),
                                   text=True, capture_output=True, timeout=3,
                                   check=False).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return None
    return str(pid), birth

def report(event):
    kind = event.get("hook_event_name")
    session = field(event.get("session_id"), 128)
    turn = field(event.get("turn_id"), 128)
    if kind not in EVENTS or not session:
        return
    if kind == "SessionStart" and event.get("source") == "compact":
        return
    agent = agent_id(event)
    if kind in ("SubagentStart", "SubagentStop") and not agent:
        return
    meta = tmux("display-message", "-p", "-t", PANE,
                "#{pane_id}|#{pane_pid}|#{pane_dead}|#{@tmux_canopy}|#{@tmux_canopy_slot}")
    if meta.returncode:
        return
    pane, pid, dead, sidebar, slot = (meta.stdout.rstrip("\n").split("|") + [""] * 5)[:5]
    if pane != PANE or not pid.isdigit() or dead == "1" or sidebar == "1" or slot == "1":
        return
    identity = process_identity(pid)
    if identity is None:
        return
    process_pid, process_birth = identity
    combined = read_options(FIELDS + ("timer",))
    current_timer = combined.pop("timer")
    current = combined
    if current["pane_pid"] != pid or current["process_pid"] != process_pid or current["process_birth"] != process_birth:
        current = {key: "" for key in FIELDS}
    if kind == "SessionStart" and current["session"] != session:
        current = {key: "" for key in FIELDS}
    if kind not in ("SessionStart", "UserPromptSubmit") and current["session"] not in ("", session):
        return
    if kind in ("PermissionRequest", "PreToolUse", "PostToolUse", "Stop", "Interrupt") and \
            current["turn"] and turn and current["turn"] != turn:
        return
    if kind == "PermissionRequest" and current["status"] in \
            ("turn-ended", "interrupted", "session-ended"):
        return
    values = dict(current)
    now = str(int(time.time()))
    sub_state = ("subagent-start" if kind == "SubagentStart" else
                 "subagent-stop" if kind == "SubagentStop" else
                 "needs-input" if kind == "PermissionRequest" else
                 "clear-request" if kind in ("PreToolUse", "PostToolUse") else
                 "working" if kind == "UserPromptSubmit" else
                 "session-ended" if kind == "SessionEnd" else "")
    values["subagents"] = next_entries(current["subagents"], agent, event, sub_state, now)
    if kind in ("SubagentStart", "SubagentStop"):
        clears_request = (kind == "SubagentStop" and current["status"] == "needs-input" and
                          current["request_agent"] == agent)
        if values["subagents"] == current["subagents"] and not clears_request:
            return
        values.update(source="codex-hook", session=session, pane_pid=pid,
                      process_pid=process_pid, process_birth=process_birth,
                      status=current["status"] or "working",
                      updated=current["updated"] or now)
        if clears_request:
            values.update(status="working", updated=now, tool="", summary="",
                          command="", request="", request_agent="")
        if turn and not current["turn"]:
            values["turn"] = turn
        if write(values):
            schedule_expiry(process_pid, process_birth, current_timer)
            refresh()
        return
    if kind in ("PreToolUse", "PostToolUse"):
        if current["status"] != "needs-input" or current["request"] != fingerprint(event) or current["request_agent"] != agent:
            if values["subagents"] != current["subagents"]:
                values.update(source="codex-hook", session=session, pane_pid=pid,
                              process_pid=process_pid, process_birth=process_birth,
                              updated=current["updated"] or now)
                if write(values):
                    refresh()
            return
        status = "working"
    else:
        status = {"SessionStart": "ready", "UserPromptSubmit": "working",
                  "PermissionRequest": "needs-input", "Stop": "turn-ended",
                  "Interrupt": "interrupted", "SessionEnd": "session-ended"}[kind]
    values.update(source="codex-hook", session=session, pane_pid=pid,
                  process_pid=process_pid, process_birth=process_birth,
                  status=status, updated=now,
                  request_agent=agent if kind == "PermissionRequest" else "")
    if kind == "SessionStart":
        values["turn"] = ""
    elif turn:
        values["turn"] = turn
    if kind == "PermissionRequest":
        inputs = event.get("tool_input")
        if not isinstance(inputs, dict):
            inputs = {}
        values["tool"] = field(event.get("tool_name"), 80)
        values["summary"] = field(inputs.get("description"), 300) or \
            ("Approval requested for " + values["tool"])
        if agent:
            values["summary"] = field(f"{list_field(event.get('agent_type'), 40) or 'Subagent'}: {values['summary']}", 300)
        values["command"] = field(inputs.get("command"), 500)
        values["request"] = fingerprint(event)
    else:
        values.update(tool="", summary="", command="", request="")
    if write(values):
        schedule_expiry(process_pid, process_birth, current_timer)
        refresh()


def main():
    if not os.environ.get("TMUX") or not re.fullmatch(r"%[0-9]+", PANE):
        return
    try:
        raw = sys.stdin.buffer.read(131073)
        if len(raw) > 131072:
            return
        event = json.loads(raw)
        if not isinstance(event, dict):
            return
        lock = "tmux-canopy-agent-" + PANE[1:]
        if tmux("wait-for", "-L", lock).returncode:
            return
        try:
            report(event)
        finally:
            tmux("wait-for", "-U", lock)
        if event.get("hook_event_name") in ("Stop", "SubagentStop"):
            # Codex requires JSON from successful stop hooks.
            print("{}")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        # Hooks are observational; a reporter failure must never block Codex.
        return


if __name__ == "__main__":
    main()
