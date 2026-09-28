#!/usr/bin/env python3
"""Lifecycle semantics and the optional normalized agent-report contract."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("canopy_agent_hook", ROOT / "lib" / "agent-hook.py")
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)
core = hook.core


def harness(kind, path="/repo"):
    written = {}
    core.PANE = "%4"
    core.FIELDS = ("source", "session", "turn", "pane_pid", "status", "tool", "summary",
                   "command", "request", "updated", "process_pid", "process_birth", "request_agent", "subagents")
    core.process_identity = lambda root, agent_kind="codex": (str(int(root) + 1), "123") if root in ("4000", "5000") else None
    core.refresh = lambda: None
    core.schedule_expiry = lambda *args: None
    core.read_options = lambda fields: dict((key, written.get(key, "")) for key in fields)

    def tmux(*args):
        output = ""
        if args[:1] == ("display-message",):
            if args[-1].startswith("#{pane_id}|"):
                output = f"{core.PANE}|4000|0||\n"
            else:
                output = "\x1f".join(written.get(key.strip("{}"), "") for key in args[-1].split("\x1f")) + "\n"
        elif args[:2] == ("list-panes", "-a"):
            source = written.get("source", "")
            session = written.get("session", "")
            root = written.get("pane_pid", "4000")
            proc = written.get("process_pid", "")
            birth = written.get("process_birth", "")
            output = f"%4|{root}|0||0|{path}|{source}|{session}|{root}|{proc}|{birth}\n"
        for i, arg in enumerate(args[:-5]):
            if arg == "set-option":
                written[args[i + 4].removeprefix(core.PREFIX)] = args[i + 5]
        return subprocess.CompletedProcess(args, 0, output, "")

    core.tmux = tmux
    return written


def send(kind, event):
    hook.report(kind, event)


def check(condition, message):
    assert condition, message


# Gemini permission requests clear only on the matching tool completion.
state = harness("gemini")
for event, expected in [
    ({"hook_event_name": "SessionStart", "session_id": "g1"}, "ready"),
    ({"hook_event_name": "BeforeAgent", "session_id": "g1"}, "working"),
    ({"hook_event_name": "Notification", "session_id": "g1", "notification_type": "ToolPermission",
      "tool_name": "run_shell_command", "details": {"description": "run tests"}}, "needs-input"),
]:
    send("gemini", event)
    check(state.get("status") == expected, f"Gemini {event['hook_event_name']} -> {expected}: {state}")
send("gemini", {"hook_event_name": "AfterTool", "session_id": "g1", "tool_name": "read_file"})
check(state["status"] == "needs-input", "unrelated Gemini tool does not clear request")
send("gemini", {"hook_event_name": "AfterTool", "session_id": "g1", "tool_name": "run_shell_command"})
check(state["status"] == "working" and not state["request"], "matching Gemini tool clears request")
send("gemini", {"hook_event_name": "AfterAgent", "session_id": "g1"})
check(state["status"] == "turn-ended", "Gemini final response ends turn")
send("gemini", {"hook_event_name": "SessionEnd", "session_id": "g1"})
check(state["status"] == "session-ended", "Gemini session shutdown reported")
send("gemini", {"hook_event_name": "SessionStart", "session_id": "g2"})
send("gemini", {"hook_event_name": "AfterAgent", "session_id": "g1"})
check(state["session"] == "g2" and state["status"] == "ready", "late Gemini event cannot overwrite new session")

# Pi and OMP expose only coarse lifecycle events, but every transition and
# session restart must replace state rather than retain stale request metadata.
for kind in ("pi", "omp"):
    state = harness(kind)
    send(kind, {"type": "session_start", "session_id": kind + "-1"})
    check(state["status"] == "ready", f"{kind} startup")
    send(kind, {"type": "agent_start", "session_id": kind + "-1"})
    check(state["status"] == "working", f"{kind} turn start")
    send(kind, {"type": "agent_end", "session_id": kind + "-1"})
    check(state["status"] == "turn-ended", f"{kind} turn end")
    send(kind, {"type": "session_start", "session_id": kind + "-2"})
    check(state["session"] == kind + "-2" and state["status"] == "ready", f"{kind} new session replaces old")
    send(kind, {"type": "agent_end", "session_id": kind + "-1"})
    check(state["session"] == kind + "-2" and state["status"] == "ready", f"{kind} late event cannot overwrite new session")
    send(kind, {"type": "session_shutdown", "session_id": kind + "-2"})
    check(state["status"] == "session-ended", f"{kind} shutdown")

# OpenCode global events bind only on a session.created event whose directory
# matches the pane, then resolve later events by the verified session identity.
state = harness("opencode", "/repo")
send("opencode", {"type": "session.created", "properties": {
    "sessionID": "o1", "info": {"id": "o1", "directory": "/repo"}}})
check(state["session"] == "o1" and state["status"] == "ready", "OpenCode binds matching project session")
send("opencode", {"type": "permission.asked", "properties": {
    "sessionID": "o1", "id": "perm-1", "permission": "bash",
    "metadata": {"command": "make test"}}})
check(state["status"] == "needs-input" and state["request"] == "perm-1" and
      state["command"] == "make test", "OpenCode request details and identity are retained")
send("opencode", {"type": "permission.replied", "properties": {
    "sessionID": "o1", "permissionID": "other"}})
check(state["status"] == "needs-input", "unmatched OpenCode reply does not clear pending request")
send("opencode", {"type": "permission.replied", "properties": {
    "sessionID": "o1", "permissionID": "perm-1"}})
check(state["status"] == "working" and not state["request"], "matching OpenCode reply clears request")
send("opencode", {"type": "permission.asked", "properties": {
    "sessionID": "foreign", "id": "perm-2", "permission": "bash"}})
check(state["session"] == "o1" and state["status"] == "working", "foreign OpenCode session is ignored")

state = harness("opencode", "/repo")
original_tmux = core.tmux
def ambiguous_tmux(*args):
    if args[:2] == ("list-panes", "-a"):
        return subprocess.CompletedProcess(args, 0,
            "%4|4000|0||0|/repo|||||\n%5|5000|0||0|/repo|||||\n", "")
    return original_tmux(*args)
core.tmux = ambiguous_tmux
send("opencode", {"type": "session.created", "properties": {
    "sessionID": "ambiguous", "info": {"id": "ambiguous", "directory": "/repo"}}})
check(not state.get("session"), "ambiguous OpenCode project panes are ignored")

# The optional common contract validates lifecycle/request shape, associates it
# with the live supported process in this pane, and clears request data on state change.
state = harness("pi")
send("contract", {"agent": "pi", "session_id": "custom-1", "state": "ready"})
check(state["status"] == "ready", "contract session ready")
send("contract", {"agent": "pi", "session_id": "custom-1", "state": "needs-input",
                  "request": {"id": "r1", "tool": "shell", "summary": "Confirm command", "command": "make"}})
check(state["status"] == "needs-input" and state["request"] == "r1" and state["summary"] == "Confirm command",
      "contract request detail")
send("contract", {"agent": "pi", "session_id": "custom-1", "state": "working"})
check(state["status"] == "working" and not state["request"], "contract clears request on progress")
send("contract", {"agent": "unknown", "session_id": "x", "state": "working"})
check(state["session"] == "custom-1", "contract rejects unknown process kind")

# Cursor Agent: conversation_id session key, camelCase events, no needs-input.
state = harness("cursor-agent")
send("cursor-agent", {"hook_event_name": "sessionStart", "conversation_id": "c1"})
check(state.get("status") == "ready" and state.get("session") == "c1", "cursor-agent sessionStart")
send("cursor-agent", {"hook_event_name": "beforeSubmitPrompt", "conversation_id": "c1"})
check(state.get("status") == "working", "cursor-agent beforeSubmitPrompt")
send("cursor-agent", {"hook_event_name": "subagentStart", "conversation_id": "c1",
                      "subagent_id": "s1", "subagent_type": "explore"})
check("s1," in state.get("subagents", "") and "explore" in state.get("subagents", ""),
      f"cursor-agent subagentStart: {state}")
send("cursor-agent", {"hook_event_name": "subagentStop", "conversation_id": "c1",
                      "subagent_id": "s1", "subagent_type": "explore"})
check("s1," not in state.get("subagents", ""), f"cursor-agent subagentStop by id: {state}")
send("cursor-agent", {"hook_event_name": "subagentStart", "conversation_id": "c1",
                      "subagent_id": "s2", "subagent_type": "shell"})
send("cursor-agent", {"hook_event_name": "subagentStop", "conversation_id": "c1",
                      "subagent_type": "shell"})  # id omitted — unique type fallback
check("s2," not in state.get("subagents", ""), f"cursor-agent subagentStop by type: {state}")
send("cursor-agent", {"hook_event_name": "stop", "conversation_id": "c1"})
check(state.get("status") == "turn-ended", "cursor-agent stop")
send("cursor-agent", {"hook_event_name": "sessionEnd", "conversation_id": "c1"})
check(state.get("status") == "session-ended" and not state.get("subagents"),
      "cursor-agent sessionEnd clears subagents")
send("cursor-agent", {"hook_event_name": "sessionStart", "conversation_id": "c2"})
send("cursor-agent", {"hook_event_name": "stop", "conversation_id": "c1"})
check(state.get("session") == "c2" and state.get("status") == "ready",
      "late cursor-agent event cannot overwrite new session")
# session_id fallback when conversation_id absent
state = harness("cursor-agent")
send("cursor-agent", {"hook_event_name": "sessionStart", "session_id": "legacy-1"})
check(state.get("session") == "legacy-1", "cursor-agent session_id fallback")

# main() must decide the Cursor Agent permission response by parsing stdin
# before any TMUX/pane gating, since Cursor can treat a missing allow as a
# block. Exercise the real entry point (not hook.report()) as a subprocess.
AGENT_HOOK = ROOT / "lib" / "agent-hook.py"


def run_hook(kind, event, tmux=None, tmux_pane=None):
    env = dict(os.environ)
    env.pop("TMUX", None)
    env.pop("TMUX_PANE", None)
    if tmux is not None:
        env["TMUX"] = tmux
    if tmux_pane is not None:
        env["TMUX_PANE"] = tmux_pane
    result = subprocess.run([sys.executable, str(AGENT_HOOK), kind], input=json.dumps(event),
                             capture_output=True, text=True, env=env, timeout=10)
    check(result.returncode == 0, f"agent-hook {kind} exits cleanly: {result.stderr}")
    return result.stdout


check(run_hook("cursor-agent", {"hook_event_name": "subagentStart", "conversation_id": "c1"}) ==
      '{"permission":"allow"}\n',
      "main() allows cursor-agent subagentStart with TMUX/TMUX_PANE unset")
check(run_hook("cursor-agent", {"hook_event_name": "subagentStart", "conversation_id": "c1"},
               tmux="", tmux_pane="not-a-pane") == '{"permission":"allow"}\n',
      "main() allows cursor-agent subagentStart with invalid TMUX/TMUX_PANE")
check(run_hook("cursor-agent", {"hook_event_name": "sessionStart", "conversation_id": "c1"}) == '{}\n',
      "main() prints inert default for other cursor-agent events (e.g. sessionStart)")


class FakeStdin:
    def __init__(self, data):
        self.buffer = io.BytesIO(data)


def call_main_with_failing_report(kind, event):
    """Exercise the real hook.main() in-process with a stubbed report() that
    raises, and a stubbed core.tmux() that simulates a successful lock
    acquire/release without touching a real tmux server. Regression check
    for the double-emit bug: report() raising must still yield exactly one
    emit()."""
    original_report, original_tmux, original_pane = hook.report, core.tmux, core.PANE
    original_argv, original_stdin = sys.argv, sys.stdin
    original_tmux_env, original_pane_env = os.environ.get("TMUX"), os.environ.get("TMUX_PANE")

    def failing_report(*args, **kwargs):
        raise ValueError("forced failure for double-emit regression test")

    def fake_tmux(*args):
        returncode = 0 if args[:1] == ("wait-for",) else 1
        return subprocess.CompletedProcess(args, returncode, "", "")

    hook.report = failing_report
    core.tmux = fake_tmux
    core.PANE = "%4"
    os.environ["TMUX"] = "real"
    os.environ.pop("TMUX_PANE", None)
    sys.argv = ["agent-hook.py", kind]
    sys.stdin = FakeStdin(json.dumps(event).encode())
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            hook.main()
    finally:
        hook.report, core.tmux, core.PANE = original_report, original_tmux, original_pane
        sys.argv, sys.stdin = original_argv, original_stdin
        if original_tmux_env is None:
            os.environ.pop("TMUX", None)
        else:
            os.environ["TMUX"] = original_tmux_env
        if original_pane_env is None:
            os.environ.pop("TMUX_PANE", None)
        else:
            os.environ["TMUX_PANE"] = original_pane_env
    return buf.getvalue()


output = call_main_with_failing_report(
    "cursor-agent", {"hook_event_name": "subagentStart", "conversation_id": "c1"})
check(output == '{"permission":"allow"}\n',
      f"main() emits exactly one line when report() raises: {output!r}")

print("ok - Gemini, Pi/OMP, OpenCode lifecycle edges and common report contract")
