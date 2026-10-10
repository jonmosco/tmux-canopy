#!/usr/bin/env python3
"""Opt-in, read-only Codex lifecycle reporter for tmux-canopy.

Configured as a Codex command hook. Never returns a decision to Codex.
"""
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))
from subagent_state import agent_id, list_field, next_entries
import agent_reporting as core

EVENTS = {"SessionStart", "UserPromptSubmit", "PermissionRequest",
          "PreToolUse", "PostToolUse", "Stop", "Interrupt", "SessionEnd",
          "SubagentStart", "SubagentStop"}


def fingerprint(event):
    inputs = event.get("tool_input")
    if isinstance(inputs, dict):
        # PermissionRequest may add a human approval reason that tool events
        # omit. It describes the request, not the tool invocation.
        inputs = {key: item for key, item in inputs.items() if key != "description"}
    value = json.dumps([event.get("tool_name"), inputs],
                       sort_keys=True, ensure_ascii=True, default=str)
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def hook_ancestors():
    """Argument lists of this hook's ancestors, nearest first."""
    return (args for _, args in core.ancestors())


def from_app_server():
    """Codex 0.159+ runs hooks in a shared app-server daemon. The daemon keeps
    the environment of the pane that started it, so TMUX_PANE names that pane
    for every Codex window on the machine."""
    for args in hook_ancestors():
        if "app-server" in args[1:3] and any(os.path.basename(arg) == "codex" for arg in args[:2]):
            return True
    return False


def app_server_pane(event):
    """The pane a daemon-run hook belongs to: the pane already bound to this
    session, or, for a session starting, the only Codex pane in its cwd. Two
    candidates mean no report rather than a guess."""
    session = core.field(event.get("session_id"), 128)
    directory = event.get("cwd") if isinstance(event.get("cwd"), str) else ""
    if not session:
        return ""
    bound, unbound, rebound = [], [], []
    for candidate in core.agent_panes("codex", ("source", "session", "process_pid", "process_birth")):
        pane, path = candidate["pane"], candidate["path"]
        source, owner = candidate["source"], candidate["session"]
        pid, birth, identity = candidate["process_pid"], candidate["process_birth"], candidate["identity"]
        live = source == "codex-hook" and owner and identity == (pid, birth)
        if live and owner == session:
            bound.append(pane)
            continue
        if core.same_directory(path, directory):
            (rebound if live else unbound).append(pane)
    if bound:
        return bound[0] if len(bound) == 1 else ""
    if event.get("hook_event_name") not in ("SessionStart", "UserPromptSubmit"):
        return ""
    # A pane already following another session can start a new one (/new).
    candidates = unbound or rebound
    return candidates[0] if len(candidates) == 1 else ""


def report(event):
    field, tmux = core.field, core.tmux
    process_identity, read_options, write = core.process_identity, core.read_options, core.write
    schedule_expiry, refresh, alert, fields = core.schedule_expiry, core.refresh, core.alert, core.FIELDS
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
    meta = tmux("display-message", "-p", "-t", core.PANE,
                "#{pane_id}|#{pane_pid}|#{pane_dead}|#{@tmux_canopy}|#{@tmux_canopy_slot}|#{@tmux_canopy_agent_alerts}")
    if meta.returncode:
        return
    pane, pid, dead, sidebar, slot, alerts = (meta.stdout.rstrip("\n").split("|") + [""] * 6)[:6]
    if pane != core.PANE or not pid.isdigit() or dead == "1" or sidebar == "1" or slot == "1":
        return
    identity = process_identity(pid)
    if identity is None:
        return
    process_pid, process_birth = identity
    combined = read_options(fields + ("timer",))
    current_timer = combined.pop("timer")
    current = combined
    if current["pane_pid"] != pid or current["process_pid"] != process_pid or current["process_birth"] != process_birth:
        current = {key: "" for key in fields}
    if kind == "SessionStart" and current["session"] != session:
        current = {key: "" for key in fields}
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
        alert(alerts, current, values, "codex", event.get("last_assistant_message"))
        refresh()


def main():
    try:
        raw = sys.stdin.buffer.read(131073)
        if len(raw) > 131072:
            return
        event = json.loads(raw)
        if not isinstance(event, dict):
            return
        if from_app_server():
            core.PANE = app_server_pane(event) if os.environ.get("TMUX") else ""
        elif not re.fullmatch(r"%[0-9]+", core.PANE):
            # No pane in the environment: find it from the process tree.
            core.PANE = core.pane_from_ancestry("codex", core.field(event.get("session_id"), 128))
        if not re.fullmatch(r"%[0-9]+", core.PANE):
            if event.get("hook_event_name") in ("Stop", "SubagentStop"):
                print("{}")
            return
        lock_fd = core.pane_lock(core.PANE[1:])
        if not lock_fd:
            return
        try:
            report(event)
        finally:
            core.pane_unlock(lock_fd)
        if event.get("hook_event_name") in ("Stop", "SubagentStop"):
            # Codex requires JSON from successful stop hooks.
            print("{}")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        # Hooks are observational; a reporter failure must never block Codex.
        return


if __name__ == "__main__":
    main()
