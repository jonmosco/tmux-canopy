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
codex_spec = importlib.util.spec_from_file_location("canopy_codex_hook", ROOT / "lib" / "codex-hook.py")
codex = importlib.util.module_from_spec(codex_spec)
codex_spec.loader.exec_module(codex)
assert codex.core is core, "all reporters use the shared reporting module"


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
            subagents = written.get("subagents", "")
            output = f"%4|{root}|0||0|{path}|{source}|{session}|{root}|{proc}|{birth}|{subagents}\n"
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


# Claude's Stop ends the turn, but listed background work keeps it working.
state = harness("claude")
send("claude", {"hook_event_name": "UserPromptSubmit", "session_id": "bg1"})
send("claude", {"hook_event_name": "Stop", "session_id": "bg1", "background_tasks": [
    {"id": "b1", "type": "shell", "status": "running", "command": "sleep 25"}]})
check(state["status"] == "working", f"Claude Stop with a running background task stays working: {state}")
send("claude", {"hook_event_name": "Stop", "session_id": "bg1", "background_tasks": [
    {"id": "b1", "type": "shell", "status": "completed"}], "session_crons": [{"id": "c1"}]})
check(state["status"] == "turn-ended", f"finished background work and crons end the turn: {state}")
send("claude", {"hook_event_name": "UserPromptSubmit", "session_id": "bg1"})
send("claude", {"hook_event_name": "Stop", "session_id": "bg1", "background_tasks": []})
check(state["status"] == "turn-ended", "Claude Stop with no background work ends the turn")
send("claude", {"hook_event_name": "UserPromptSubmit", "session_id": "bg1"})
send("claude", {"hook_event_name": "Stop", "session_id": "bg1"})
check(state["status"] == "turn-ended", "Claude Stop from versions without the field ends the turn")

# Claude reports one approval twice: PermissionRequest, then a permission_prompt
# Notification without a tool. Either order must leave a request that the
# approved tool's PostToolUse clears.
for order in ("request-first", "notification-first"):
    state = harness("claude")
    request = {"hook_event_name": "PermissionRequest", "session_id": "pp1", "tool_name": "Bash",
               "tool_input": {"command": "rm x", "description": "Remove x"}}
    notification = {"hook_event_name": "Notification", "session_id": "pp1", "notification_type": "permission_prompt",
                    "message": "Claude needs your permission to use Bash"}
    send("claude", {"hook_event_name": "UserPromptSubmit", "session_id": "pp1"})
    for event in ((request, notification) if order == "request-first" else (notification, request)):
        send("claude", event)
    check(state["status"] == "needs-input" and state["tool"] == "Bash" and state["summary"] == "Remove x" and
          state["command"] == "rm x", f"{order}: the request keeps its tool and details: {state}")
    send("claude", {"hook_event_name": "PostToolUse", "session_id": "pp1", "tool_name": "Bash"})
    check(state["status"] == "working" and not state["request"], f"{order}: approval clears the request: {state}")

# A long Claude conversation can move to a new session id (compaction, /clear,
# resume) inside the same process. The pane follows it instead of discarding
# every later report; another process, or a late event from the old session,
# still cannot take over.
state = harness("claude")
send("claude", {"hook_event_name": "SessionStart", "session_id": "long-1"})
send("claude", {"hook_event_name": "UserPromptSubmit", "session_id": "long-1"})
send("claude", {"hook_event_name": "SessionStart", "session_id": "long-2", "source": "compact"})
check(state["session"] == "long-2" and state["status"] == "working",
      f"a compact start adopts the new session id without resetting the turn: {state}")
send("claude", {"hook_event_name": "Stop", "session_id": "long-2"})
check(state["status"] == "turn-ended", f"reports under the new id are kept: {state}")
send("claude", {"hook_event_name": "UserPromptSubmit", "session_id": "long-3"})
check(state["session"] == "long-3" and state["status"] == "working",
      f"a new prompt from the same process adopts its session even with no start: {state}")
send("claude", {"hook_event_name": "Stop", "session_id": "long-2"})
check(state["session"] == "long-3" and state["status"] == "working", f"a late Stop from the old session is ignored: {state}")
same = core.process_identity
core.process_identity = lambda root, agent_kind="codex": ("9999", "456")
send("claude", {"hook_event_name": "SessionStart", "session_id": "other", "source": "compact"})
check(state["session"] == "long-3" and state["status"] == "working",
      f"a compact start from another process changes nothing: {state}")
core.process_identity = same

# Copilot CLI passes the event name as an argument; its payload is camelCase.
state = harness("copilot")
for name, event, expected in [
    ("sessionStart", {"sessionId": "k1", "source": "new"}, "ready"),
    ("userPromptSubmitted", {"sessionId": "k1", "prompt": "fix"}, "working"),
    ("notification", {"sessionId": "k1", "notification_type": "permission_prompt",
                      "message": "Allow shell command?"}, "needs-input"),
]:
    hook.report("copilot", event, name)
    check(state.get("status") == expected, f"Copilot {name} -> {expected}: {state}")
check(state["summary"] == "Allow shell command?", f"Copilot request summary: {state}")
hook.report("copilot", {"sessionId": "k1", "notification_type": "agent_idle"}, "notification")
check(state["status"] == "needs-input", "other Copilot notifications are not requests")
hook.report("copilot", {"sessionId": "k1", "toolName": "bash"}, "postToolUse")
check(state["status"] == "working" and not state["request"], "Copilot tool completion clears the request")
hook.report("copilot", {"sessionId": "k1", "error": "rate limited", "recoverable": True}, "errorOccurred")
check(state["status"] == "working", "a recoverable Copilot error keeps working")
hook.report("copilot", {"sessionId": "k1", "stopReason": "end_turn"}, "agentStop")
check(state["status"] == "turn-ended", "Copilot agentStop ends the turn")
hook.report("copilot", {"sessionId": "k1", "error": "fatal", "recoverable": False}, "errorOccurred")
check(state["status"] == "interrupted", "an unrecoverable Copilot error interrupts")
hook.report("copilot", {"sessionId": "k1", "reason": "user_exit"}, "sessionEnd")
check(state["status"] == "session-ended", "Copilot sessionEnd")

# Grok Build: Claude-style event names, camelCase fields, promptId per turn.
state = harness("grok")
send("grok", {"hook_event_name": "SessionStart", "sessionId": "x1"})
check(state.get("status") == "ready", f"Grok SessionStart: {state}")
send("grok", {"hook_event_name": "UserPromptSubmit", "sessionId": "x1", "promptId": "p1"})
check(state["status"] == "working" and state["turn"] == "p1", f"Grok prompt starts turn p1: {state}")
send("grok", {"hook_event_name": "Notification", "sessionId": "x1", "notificationType": "permission_prompt",
              "message": "Run npm test?"})
check(state["status"] == "needs-input" and state["summary"] == "Run npm test?", f"Grok permission prompt: {state}")
send("grok", {"hook_event_name": "PostToolUse", "sessionId": "x1", "promptId": "p1", "toolName": "run_terminal_command"})
check(state["status"] == "working", "Grok tool completion clears the request")
send("grok", {"hook_event_name": "Stop", "sessionId": "x1", "promptId": "p1", "reason": "end_turn",
              "backgroundTasks": [{"id": "t1", "type": "shell", "status": "running"}]})
check(state["status"] == "working", "Grok Stop with background work stays working")
send("grok", {"hook_event_name": "Stop", "sessionId": "x1", "promptId": "p1", "reason": "end_turn",
              "backgroundTasks": []})
check(state["status"] == "turn-ended", "Grok Stop ends the turn")
send("grok", {"hook_event_name": "UserPromptSubmit", "sessionId": "x1", "promptId": "p2"})
send("grok", {"hook_event_name": "StopCancelled", "sessionId": "x1", "promptId": "p1", "reason": "user_interrupt"})
check(state["status"] == "working", "a late report for an older Grok turn is ignored")
send("grok", {"hook_event_name": "Stop", "sessionId": "x1", "promptId": "p2", "reason": "end_turn",
              "subagentType": "explore"})
check(state["status"] == "working", "a Grok subagent's stop is not the pane's")
send("grok", {"hook_event_name": "StopCancelled", "sessionId": "x1", "promptId": "p2", "reason": "user_interrupt"})
check(state["status"] == "interrupted", "Grok StopCancelled interrupts the current turn")
send("grok", {"hook_event_name": "Stop", "sessionId": "x1", "reason": "shutdown"})
check(state["status"] == "interrupted", "Grok's session-closing Stop is not a turn end")
send("grok", {"hook_event_name": "SessionEnd", "sessionId": "x1"})
check(state["status"] == "session-ended", "Grok SessionEnd")
send("claude", {"hook_event_name": "UserPromptSubmit", "sessionId": "x1"})
check(state["status"] == "session-ended", "Grok runs Claude's hooks too; Claude-shaped reports without session_id are ignored")

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

# Pi and OMP report lifecycle, tool progress, extension UI prompts, and
# interrupted settles. Session restart must replace state rather than retain
# stale request metadata.
for kind in ("pi", "omp"):
    state = harness(kind)
    send(kind, {"type": "session_start", "session_id": kind + "-1"})
    check(state["status"] == "ready", f"{kind} startup")
    send(kind, {"type": "agent_start", "session_id": kind + "-1"})
    check(state["status"] == "working", f"{kind} turn start")
    send(kind, {"type": "tool_execution_start", "session_id": kind + "-1", "tool_name": "bash"})
    check(state["status"] == "working", f"{kind} tool execution keeps the turn fresh")
    send(kind, {"type": "ui_prompt_start", "session_id": kind + "-1", "tool_name": "confirm",
                "message": "Allow command?"})
    check(state["status"] == "needs-input" and state["summary"] == "Allow command?", f"{kind} UI prompt")
    send(kind, {"type": "ui_prompt_end", "session_id": kind + "-1"})
    check(state["status"] == "working" and not state["request"], f"{kind} prompt end clears request")
    send(kind, {"type": "agent_interrupted", "session_id": kind + "-1", "outcome": "aborted"})
    check(state["status"] == "interrupted", f"{kind} aborted settle")
    send(kind, {"type": "agent_start", "session_id": kind + "-1"})
    send(kind, {"type": "agent_end", "session_id": kind + "-1"})
    check(state["status"] == "turn-ended", f"{kind} turn end")
    send(kind, {"type": "agent_settled", "session_id": kind + "-1"})
    check(state["status"] == "turn-ended", f"{kind} settled turn")
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

# OpenCode task agents run as child sessions. Only a child whose parentID is
# the verified pane session is rendered; later child events resolve by child ID.
send("opencode", {"type": "session.created", "properties": {
    "sessionID": "child-1", "info": {"id": "child-1", "parentID": "o1",
    "agent": "explore", "title": "Find the config"}}})
check(state["session"] == "o1" and "child-1,explore: Find the config,unknown" in state.get("subagents", ""),
      f"OpenCode child session is retained on its parent: {state}")
send("opencode", {"type": "session.status", "properties": {
    "sessionID": "child-1", "status": {"type": "busy"}}})
check("child-1,explore: Find the config,working" in state.get("subagents", ""),
      f"OpenCode child busy is working: {state}")
send("opencode", {"type": "permission.updated", "properties": {
    "sessionID": "child-1", "id": "child-perm", "permission": "bash",
    "metadata": {"command": "rg config"}}})
check(state["status"] == "needs-input" and state["request_agent"] == "child-1" and
      "child-1,explore: Find the config,needs-input," in state.get("subagents", ""),
      f"OpenCode child permission is attributed to that child: {state}")
send("opencode", {"type": "permission.replied", "properties": {
    "sessionID": "child-1", "permissionID": "child-perm"}})
check(state["status"] == "working" and "child-1,explore: Find the config,working" in state.get("subagents", ""),
      f"matching OpenCode child reply clears only its request: {state}")
send("opencode", {"type": "session.status", "properties": {
    "sessionID": "child-1", "status": {"type": "idle"}}})
check("child-1,explore: Find the config,done" in state.get("subagents", ""),
      f"OpenCode child idle remains as done: {state}")
send("opencode", {"type": "session.status", "properties": {
    "sessionID": "child-1", "status": {"type": "busy"}}})
check("child-1,explore: Find the config,working" in state.get("subagents", ""),
      f"resumed OpenCode child returns to working: {state}")
send("opencode", {"type": "session.deleted", "properties": {"sessionID": "child-1"}})
check("child-1," not in state.get("subagents", ""), f"OpenCode child deletion removes it: {state}")
send("opencode", {"type": "session.updated", "properties": {
    "sessionID": "o1", "info": {"id": "o1", "directory": "/repo", "title": "Renamed parent"}}})
check(state["status"] == "working", "OpenCode parent metadata updates do not reset lifecycle state")

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

# OpenCode V2 public events use the same properties bag, plus permission/question
# ids and a location directory when session info is absent.
state = harness("opencode", "/repo")
send("opencode", {"type": "session.next.prompted", "location": {"directory": "/repo"},
                   "properties": {"sessionID": "v2"}})
check(state["session"] == "v2" and state["status"] == "working", "OpenCode V2 prompt binds by location")
send("opencode", {"type": "permission.v2.asked", "properties": {
    "sessionID": "v2", "id": "per_1", "action": "bash", "resources": ["make test"]}})
check(state["status"] == "needs-input" and state["request"] == "per_1" and
      state["command"] == "make test", "OpenCode V2 permission keeps its request id")
send("opencode", {"type": "permission.v2.replied", "properties": {
    "sessionID": "v2", "requestID": "per_1", "reply": "once"}})
check(state["status"] == "working" and not state["request"], "OpenCode V2 reply clears the matching request")
send("opencode", {"type": "question.v2.asked", "properties": {
    "sessionID": "v2", "id": "que_1", "questions": [{"question": "Which file?", "header": "file"}]}})
check(state["status"] == "needs-input" and state["request"] == "que_1" and
      state["summary"] == "Which file?", "OpenCode V2 question is needs-input")
send("opencode", {"type": "question.v2.rejected", "properties": {"sessionID": "v2", "requestID": "que_1"}})
check(state["status"] == "working" and not state["request"], "OpenCode V2 question rejection clears the request")
send("opencode", {"type": "session.next.step.failed", "data": {"sessionID": "v2", "error": {"message": "nope"}}})
check(state["status"] == "interrupted", "OpenCode V2 step failure is interrupted")
send("opencode", {"type": "session.status", "data": {"sessionID": "v2", "status": {"type": "idle"}}})
check(state["status"] == "turn-ended", "OpenCode V2 idle status ends the turn")

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

# Agent alerts: only transitions a user waits for start the delivery script,
# and only when @tmux-canopy-alerts covers agents. Its value rides along on the
# reporter's existing pane check, so it needs no tmux call of its own.
def alert_harness(kind, mode):
    state = harness(kind)
    plain, started = core.tmux, []

    def tmux(*args):
        result = plain(*args)
        if args[:1] == ("display-message",) and args[-1].startswith("#{pane_id}|"):
            return subprocess.CompletedProcess(args, 0, result.stdout.rstrip("\n") + "|" + mode + "\n", "")
        return result
    core.tmux = tmux
    # Recorded as (pane, event, kind, summary, mode); the full text is kept too.
    texts.clear()

    def start(argv, text):
        started.append((argv[1], argv[2], argv[3], text["CANOPY_ALERT_SUMMARY"], argv[4]))
        texts.append(text)
    core.start_alert = start
    return state, started


texts = []


state, started = alert_harness("claude", "both")
send("claude", {"hook_event_name": "SessionStart", "session_id": "a1"})
send("claude", {"hook_event_name": "Stop", "session_id": "a1"})
check(started == [], f"a turn that never started working does not alert: {started}")
send("claude", {"hook_event_name": "UserPromptSubmit", "session_id": "a1"})
send("claude", {"hook_event_name": "PermissionRequest", "session_id": "a1", "tool_name": "Bash",
                "tool_input": {"command": "rm x", "description": "Remove x"}})
send("claude", {"hook_event_name": "Notification", "session_id": "a1", "notification_type": "permission_prompt",
                "message": "Claude needs your permission to use Bash"})
check(started == [("%4", "needs-input", "claude", "Remove x", "both")],
      f"Claude's paired permission events alert once, with the request: {started}")
send("claude", {"hook_event_name": "PostToolUse", "session_id": "a1", "tool_name": "Bash"})
send("claude", {"hook_event_name": "Stop", "session_id": "a1"})
check(started[1:] == [("%4", "done", "claude", "", "both")], f"working to turn-ended alerts done: {started}")
send("claude", {"hook_event_name": "Stop", "session_id": "a1"})
check(len(started) == 2, f"a repeated Stop does not alert again: {started}")
send("claude", {"hook_event_name": "UserPromptSubmit", "session_id": "a1"})
send("claude", {"hook_event_name": "SubagentStart", "session_id": "a1", "agent_id": "s1", "agent_type": "Explore"})
send("claude", {"hook_event_name": "PermissionRequest", "session_id": "a1", "agent_id": "s1",
                "agent_type": "Explore", "tool_name": "Read", "tool_input": {"description": "Read y"}})
check(started[2:] == [("%4", "needs-input", "claude", "Explore: Read y", "both")],
      f"a subagent's request alerts with its name: {started}")

for mode in ("", "off", "bogus"):
    state, started = alert_harness("claude", mode)
    send("claude", {"hook_event_name": "UserPromptSubmit", "session_id": "a2"})
    send("claude", {"hook_event_name": "PermissionRequest", "session_id": "a2", "tool_name": "Bash"})
    send("claude", {"hook_event_name": "Stop", "session_id": "a2"})
    check(state["status"] == "turn-ended" and started == [], f"alerts stay off for {mode!r}: {started}")

state, started = alert_harness("codex", "desktop")
codex.report({"hook_event_name": "SessionStart", "session_id": "c1"})
codex.report({"hook_event_name": "UserPromptSubmit", "session_id": "c1", "turn_id": "t1"})
codex.report({"hook_event_name": "PermissionRequest", "session_id": "c1", "turn_id": "t1",
             "tool_name": "Bash", "tool_input": {"command": "make", "description": "Build"}})
codex.report({"hook_event_name": "PreToolUse", "session_id": "c1", "turn_id": "t1",
             "tool_name": "Bash", "tool_input": {"command": "make", "description": "Build"}})
codex.report({"hook_event_name": "Stop", "session_id": "c1", "turn_id": "t1"})
check(started == [("%4", "needs-input", "codex", "Build", "desktop"), ("%4", "done", "codex", "", "desktop")],
      f"Codex alerts on a request and on the end of a working turn: {started}")

state, started = alert_harness("claude", "tmux")
send("claude", {"hook_event_name": "UserPromptSubmit", "session_id": "a3"})
send("claude", {"hook_event_name": "StopFailure", "session_id": "a3"})
send("claude", {"hook_event_name": "StopFailure", "session_id": "a3"})
check(started == [("%4", "interrupted", "claude", "", "tmux")], f"an interrupted turn alerts once: {started}")
send("claude", {"hook_event_name": "SessionStart", "session_id": "a4"})
send("claude", {"hook_event_name": "StopFailure", "session_id": "a4"})
check(len(started) == 1, f"an interruption with no turn in progress stays quiet: {started}")

state, started = alert_harness("codex", "both")
codex.report({"hook_event_name": "SessionStart", "session_id": "c2"})
codex.report({"hook_event_name": "UserPromptSubmit", "session_id": "c2", "turn_id": "t1"})
codex.report({"hook_event_name": "Interrupt", "session_id": "c2", "turn_id": "t1"})
check(started == [("%4", "interrupted", "codex", "", "both")], f"Codex interruption alerts: {started}")

# The text rides in the environment: the request's command, the agent's last
# reply on a finished turn, and the seconds since it last started working.
state, started = alert_harness("claude", "desktop")
send("claude", {"hook_event_name": "UserPromptSubmit", "session_id": "a5"})
state["updated"] = str(int(state["updated"]) - 125)
send("claude", {"hook_event_name": "PermissionRequest", "session_id": "a5", "tool_name": "Bash",
                "tool_input": {"command": "make test", "description": "Run the tests"}})
check(texts[-1]["CANOPY_ALERT_COMMAND"] == "make test" and texts[-1]["CANOPY_ALERT_ELAPSED"] == "",
      f"a request carries its command: {texts[-1]}")
send("claude", {"hook_event_name": "PostToolUse", "session_id": "a5", "tool_name": "Bash"})
state["updated"] = str(int(state["updated"]) - 125)
send("claude", {"hook_event_name": "Stop", "session_id": "a5", "last_assistant_message": "All tests pass.\n\nDone."})
check(texts[-1]["CANOPY_ALERT_REPLY"] == "All tests pass. Done." and texts[-1]["CANOPY_ALERT_ELAPSED"] in ("125", "126"),
      f"a finished turn carries the reply and its duration: {texts[-1]}")
send("claude", {"hook_event_name": "UserPromptSubmit", "session_id": "a5"})
send("claude", {"hook_event_name": "StopFailure", "session_id": "a5", "last_assistant_message": "partial"})
check(texts[-1]["CANOPY_ALERT_REPLY"] == "", f"only a finished turn carries a reply: {texts[-1]}")

state, started = alert_harness("codex", "tmux")
codex.report({"hook_event_name": "SessionStart", "session_id": "c3"})
codex.report({"hook_event_name": "UserPromptSubmit", "session_id": "c3", "turn_id": "t1"})
codex.report({"hook_event_name": "Stop", "session_id": "c3", "turn_id": "t1", "last_assistant_message": "Fixed it."})
check(texts[-1]["CANOPY_ALERT_REPLY"] == "Fixed it.", f"Codex passes its last reply: {texts[-1]}")

print("ok - agent alerts fire once per transition, only when enabled")
