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

PANE = os.environ.get("TMUX_PANE", "")
EVENTS = {"SessionStart", "UserPromptSubmit", "PermissionRequest",
          "PostToolUse", "Stop", "Interrupt", "SessionEnd"}
PREFIX = "@tmux_canopy_agent_"
FIELDS = ("source", "session", "turn", "pane_pid", "status", "tool",
          "summary", "command", "request", "updated", "process_pid", "process_birth")


def tmux(*args):
    return subprocess.run(("tmux", *args), text=True, capture_output=True,
                          timeout=3, check=False)


def field(value, limit=300):
    if not isinstance(value, str):
        return ""
    value = re.sub(r"[\x00-\x1f\x7f]+", " ", value).strip()
    return value[:limit] + ("…" if len(value) > limit else "")


def option(key):
    result = tmux("show-option", "-pqv", "-t", PANE, PREFIX + key)
    return result.stdout.rstrip("\n") if result.returncode == 0 else ""


def fingerprint(event):
    value = json.dumps([event.get("tool_name"), event.get("tool_input")],
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


def schedule_expiry(process_pid, process_birth):
    if not process_birth.isdigit():
        return  # Portable platforms retain manual refresh on report expiry.
    token = f"{process_pid}:{process_birth}"
    if option("timer") == token:
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


def process_identity(root):
    """Find the live Codex process in this pane, including nested shells."""
    try:
        root = int(root)
    except ValueError:
        return None
    if os.path.isdir("/proc/self"):
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
                        if stream.read().strip() != "codex":
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
                if os.path.basename(fields[2]) == "codex":
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
    current = {key: option(key) for key in FIELDS}
    if current["pane_pid"] != pid or current["process_pid"] != process_pid or current["process_birth"] != process_birth:
        current = {key: "" for key in FIELDS}
    if kind not in ("SessionStart", "UserPromptSubmit") and current["session"] not in ("", session):
        return
    if kind in ("PermissionRequest", "PostToolUse", "Stop", "Interrupt") and \
            current["turn"] and turn and current["turn"] != turn:
        return
    if kind == "PermissionRequest" and current["status"] in \
            ("turn-ended", "interrupted", "session-ended"):
        return
    values = dict(current)
    if kind == "PostToolUse":
        if current["status"] != "needs-input" or current["request"] != fingerprint(event):
            return
        status = "working"
    else:
        status = {"SessionStart": "ready", "UserPromptSubmit": "working",
                  "PermissionRequest": "needs-input", "Stop": "turn-ended",
                  "Interrupt": "interrupted", "SessionEnd": "session-ended"}[kind]
    values.update(source="codex-hook", session=session, pane_pid=pid,
                  process_pid=process_pid, process_birth=process_birth,
                  status=status, updated=str(int(time.time())))
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
        values["command"] = field(inputs.get("command"), 500)
        values["request"] = fingerprint(event)
    else:
        values.update(tool="", summary="", command="", request="")
    if write(values):
        schedule_expiry(process_pid, process_birth)
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
        if event.get("hook_event_name") == "Stop":
            # Codex requires a JSON object from a successful Stop hook.
            print("{}")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        # Hooks are observational; a reporter failure must never block Codex.
        return


if __name__ == "__main__":
    main()
