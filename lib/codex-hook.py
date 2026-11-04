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
from subagent_state import agent_id, format_subagents, list_field, next_entries, parse_subagents, update_subagent
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


def json_dict(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except ValueError:
            return {}
    return {}


def apply_collab_tool(subagents, event, kind, now):
    """Reflect parent multi-agent collaboration tool calls in child rows."""
    if kind != "PostToolUse":
        return subagents, set()
    raw_tool = event.get("tool_name")
    base_tool = raw_tool.rsplit(".", 1)[-1] if isinstance(raw_tool, str) else ""
    if base_tool not in ("spawn_agent", "close_agent", "interrupt_agent",
                         "send_input", "send_message", "followup_task", "resume_agent"):
        return subagents, set()
    inputs = json_dict(event.get("tool_input"))
    resp = json_dict(event.get("tool_response"))
    entries = parse_subagents(subagents)
    removed = set()
    if base_tool == "spawn_agent":
        spawned = agent_id({"agent_id": resp.get("agent_id") or resp.get("id")})
        role = inputs.get("agent_type") or inputs.get("role") or resp.get("agent_role") or resp.get("role") or ""
        if isinstance(role, str) and role.strip().lower() == "default":
            role = ""
        task = (inputs.get("task_name") or resp.get("task_name") or
                resp.get("nickname") or resp.get("agent_nickname") or "")
        if isinstance(task, str) and "/" in task:
            task = task.strip("/").rsplit("/", 1)[-1]
        label = list_field(role or task, 40)
        if spawned:
            existing = next((item for item in entries if item[0] == spawned), None)
            if existing is None:
                update_subagent(entries, spawned, {"agent_type": label or "subagent"}, "subagent-start", now)
            elif label and existing[1] == "subagent":
                existing[1], existing[3] = label, now
    elif base_tool in ("close_agent", "interrupt_agent"):
        target = (inputs.get("id") or inputs.get("agent_id") or inputs.get("target") or
                  inputs.get("task_name") or resp.get("agent_id") or resp.get("id") or "")
        if isinstance(target, str) and target.strip():
            target = target.strip()
            short = target.strip("/").rsplit("/", 1)[-1] if "/" in target else target
            kept = []
            for entry in entries:
                if entry[0] in (target, short) or entry[1] in (target, short):
                    removed.add(entry[0])
                else:
                    kept.append(entry)
            entries = kept
            checked = agent_id({"agent_id": target})
            if checked:
                removed.add(checked)
    else:
        target = (inputs.get("id") or inputs.get("agent_id") or inputs.get("target") or
                  inputs.get("task_name") or resp.get("agent_id") or resp.get("id") or "")
        if isinstance(target, str) and target.strip():
            target = target.strip()
            short = target.strip("/").rsplit("/", 1)[-1] if "/" in target else target
            matched = False
            for entry in entries:
                if entry[0] in (target, short) or entry[1] in (target, short):
                    entry[2], entry[4], entry[3] = "working", "", now
                    matched = True
            if not matched:
                checked = agent_id({"agent_id": target})
                if checked:
                    update_subagent(entries, checked, {}, "working", now)
    return format_subagents(entries), removed


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
    agent = agent_id(event)
    directory = event.get("cwd") if isinstance(event.get("cwd"), str) else ""
    if not session:
        return ""
    bound, child, unbound, rebound = [], [], [], []
    for candidate in core.agent_panes("codex", ("source", "session", "process_pid", "process_birth",
                                                "subagents", "request_agent")):
        pane, path = candidate["pane"], candidate["path"]
        source, owner = candidate["source"], candidate["session"]
        pid, birth, identity = candidate["process_pid"], candidate["process_birth"], candidate["identity"]
        subagents, req_agent = candidate["subagents"], candidate["request_agent"]
        live = source == "codex-hook" and owner and identity == (pid, birth)
        if live and owner == session:
            bound.append(pane)
            continue
        if live and ((req_agent and req_agent in (session, agent)) or
                     any(entry[0] in (session, agent) for entry in parse_subagents(subagents) if entry[0])):
            child.append(pane)
            continue
        if core.same_directory(path, directory):
            (rebound if live else unbound).append(pane)
    if bound:
        return bound[0] if len(bound) == 1 else ""
    if child:
        return child[0] if len(child) == 1 else ""
    if event.get("hook_event_name") not in ("SessionStart", "UserPromptSubmit") or agent:
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
    tracked = {entry[0] for entry in parse_subagents(current["subagents"])}
    if not agent and current["session"] and session != current["session"] and (
            session in tracked or session == current["request_agent"]):
        agent = session
    if agent:
        # Codex child sessions emit their own conversation_id as session_id on
        # turn, tool, and stop hooks while SubagentStart carries parent_thread_id.
        if current["session"] and session not in (current["session"], agent) and \
                agent not in tracked and agent != current["request_agent"]:
            return
        owner_session = current["session"] or session
    else:
        if kind == "SessionStart" and current["session"] != session:
            current = {key: "" for key in fields}
        if kind not in ("SessionStart", "UserPromptSubmit") and current["session"] not in ("", session):
            return
        if kind in ("PermissionRequest", "PreToolUse", "PostToolUse", "Stop", "Interrupt") and \
                current["turn"] and turn and current["turn"] != turn:
            return
        owner_session = session
    if kind == "PermissionRequest" and current["status"] in \
            ("turn-ended", "interrupted", "session-ended"):
        return
    values = dict(current)
    now = str(int(time.time()))
    sub_stop = kind == "SubagentStop" or (bool(agent) and kind in ("Stop", "Interrupt", "SessionEnd"))
    sub_start = kind == "SubagentStart" or (bool(agent) and kind in ("SessionStart", "UserPromptSubmit"))
    sub_only = sub_stop or sub_start
    sub_state = ("subagent-stop" if sub_stop else
                 "subagent-start" if sub_start else
                 "needs-input" if kind == "PermissionRequest" else
                 "clear-request" if kind in ("PreToolUse", "PostToolUse") else
                 "working" if kind == "UserPromptSubmit" else
                 "turn-ended" if kind == "Stop" else
                 "interrupted" if kind == "Interrupt" else
                 "session-ended" if kind == "SessionEnd" else "")
    values["subagents"] = next_entries(current["subagents"], agent, event, sub_state, now)
    removed_agents = set()
    if not agent and kind in ("PreToolUse", "PostToolUse"):
        values["subagents"], removed_agents = apply_collab_tool(values["subagents"], event, kind, now)
    if sub_only:
        clears_request = (current["status"] == "needs-input" and current["request_agent"] == agent)
        if values["subagents"] == current["subagents"] and not clears_request:
            return
        values.update(source="codex-hook", session=owner_session, pane_pid=pid,
                      process_pid=process_pid, process_birth=process_birth,
                      status=current["status"] or "working",
                      updated=current["updated"] or now)
        if clears_request:
            values.update(status="working", updated=now, tool="", summary="",
                          command="", request="", request_agent="")
        if turn and not current["turn"] and session == owner_session:
            values["turn"] = turn
        if write(values):
            schedule_expiry(process_pid, process_birth, current_timer)
            refresh()
        return
    if kind in ("PreToolUse", "PostToolUse"):
        clears_request = (
            current["status"] == "needs-input" and (
                (current["request"] == fingerprint(event) and current["request_agent"] == agent) or
                (bool(removed_agents) and current["request_agent"] in removed_agents)
            )
        )
        if not clears_request:
            if current["status"] == "working" and not agent:
                values["tool"] = field(event.get("tool_name"), 80) if kind == "PreToolUse" else ""
            if values["subagents"] != current["subagents"] or values["tool"] != current["tool"]:
                values.update(source="codex-hook", session=owner_session, pane_pid=pid,
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
    values.update(source="codex-hook", session=owner_session, pane_pid=pid,
                  process_pid=process_pid, process_birth=process_birth,
                  status=status, updated=now,
                  request_agent=agent if kind == "PermissionRequest" else "")
    if kind == "SessionStart":
        values["turn"] = ""
    elif turn and not agent:
        values["turn"] = turn
    if kind == "PermissionRequest":
        inputs = event.get("tool_input")
        if not isinstance(inputs, dict):
            inputs = {}
        questions = inputs.get("questions")
        asked = (questions[0].get("question") or questions[0].get("header") or ""
                 if isinstance(questions, list) and questions and isinstance(questions[0], dict)
                 else inputs.get("question") if isinstance(inputs.get("question"), str) else "")
        values["tool"] = field(event.get("tool_name"), 80) or ("question" if asked else "")
        is_question = values["tool"] in ("AskUserQuestion", "ask_user_question", "ask_question",
                                         "ask_user", "request_user_input", "question")
        values["summary"] = (field(inputs.get("description") or asked, 300) or
                             ("Question requested" if is_question else "Approval requested for " + values["tool"]))
        if agent:
            agent_label = list_field(event.get("agent_type"), 40)
            if agent_label.lower() == "default":
                agent_label = ""
            if not agent_label:
                existing = next((item[1] for item in parse_subagents(values["subagents"]) if item[0] == agent), "")
                if existing and existing != "subagent":
                    agent_label = existing
            values["summary"] = field(f"{agent_label or 'Subagent'}: {values['summary']}", 300)
        values["command"] = field(inputs.get("command"), 500)
        values["request"] = fingerprint(event)
    else:
        tool = field(event.get("tool_name"), 80) if (kind == "PreToolUse" and not agent) else ""
        err = event.get("error") if kind == "Interrupt" else None
        err_text = ((err.get("message") or err.get("error") or "" if isinstance(err, dict)
                     else err if isinstance(err, str) else "") or
                    (event.get("message") if kind == "Interrupt" and isinstance(event.get("message"), str) else ""))
        summary = field(err_text, 300) if (kind == "Interrupt" and not agent) else ""
        values.update(tool=tool, summary=summary, command="", request="")
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
