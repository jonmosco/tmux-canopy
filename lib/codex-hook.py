#!/usr/bin/env python3
"""Opt-in, read-only Codex lifecycle reporter for tmux-canopy.

Configured as a Codex command hook. Never returns a decision to Codex.
"""
import fcntl
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
from agent_kinds import name_from_args, process_name
from subagent_state import agent_id, list_field, next_entries
import agent_reporting as core

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


def pane_lock(pane_id):
    """Acquire a per-pane file lock. The kernel releases it on process death."""
    lock_dir = os.environ.get("TMPDIR", "/tmp")
    try:
        fd = open(os.path.join(lock_dir, f"tmux-canopy-agent-{pane_id}.lock"), "w")
        for _ in range(6):
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except (OSError, IOError):
                time.sleep(0.25)
        fd.close()
        return None
    except (OSError, IOError):
        return None


def pane_unlock(fd):
    if fd:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
            fd.close()
        except (OSError, IOError):
            pass


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


def start_alert(argv, text):
    # Detached with no shared pipes: agents wait for their hook's output to
    # close, and delivery must never hold that up. Text travels in the
    # environment, which other users cannot read the way they can read argv.
    try:
        subprocess.Popen(argv, env=os.environ | text, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        pass


def alert(mode, current, values, kind, reply=""):
    """Announce only the transitions a user waits for. Repeated reports of the
    same state stay quiet, so Claude's paired permission events alert once."""
    if mode not in ("desktop", "tmux", "both"):
        return
    previous, status = current["status"], values["status"]
    if status == "needs-input" and previous != "needs-input":
        event = "needs-input"
    elif status == "turn-ended" and previous in ("working", "needs-input"):
        event = "done"
    elif status == "interrupted" and previous in ("working", "needs-input"):
        event = "interrupted"
    else:
        return
    text = {"CANOPY_ALERT_SUMMARY": values["summary"], "CANOPY_ALERT_COMMAND": values["command"],
            "CANOPY_ALERT_REPLY": field(reply, 600) if event == "done" else "", "CANOPY_ALERT_ELAPSED": ""}
    # Time since the agent last started working: its prompt or last approval.
    if event != "needs-input" and current["updated"].isdigit() and values["updated"].isdigit():
        text["CANOPY_ALERT_ELAPSED"] = str(max(0, int(values["updated"]) - int(current["updated"])))
    start_alert((str(Path(__file__).resolve().parents[1] / "scripts" / "alert"),
                 PANE, event, kind, mode), text)


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
             "pi": {"pi"}, "omp": {"omp"}, "agy": {"agy", "antigravity"},
             "cursor-agent": {"agent"}, "copilot": {"copilot"}, "grok": {"grok"}}.get(kind, set())
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
            stat = core.linux_stat(current)
            if not stat:
                break
            chain.append((current, process_name(current), stat[1]))
            if current == root:
                for pid, name, birth in chain:
                    if name in names:
                        return str(pid), str(birth)
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
                if process_name(entry.name) not in names:
                    continue
                pid = int(entry.name)
                stat = linux_stat(pid)
                if stat:
                    candidates.append((pid, stat[1]))
        stat_for = linux_stat
    else:
        records = process_table()
        if records is None:
            return None
        parents = {}
        candidates = []
        for line in records:
            fields = line.split(None, 2)
            if len(fields) == 3 and fields[0].isdigit() and fields[1].isdigit():
                parents[int(fields[0])] = int(fields[1])
                if name_from_args(fields[2].split()) in names:
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

_TABLE = None


def process_table():
    """Every process as a "pid ppid args" line, read once per hook run."""
    global _TABLE
    if _TABLE is None:
        # args= exposes argv0 for Node CLIs whose comm is a thread name.
        try:
            _TABLE = subprocess.run(("ps", "-eo", "pid=,ppid=,args="), text=True,
                                    capture_output=True, timeout=3, check=False).stdout.splitlines()
        except (OSError, subprocess.TimeoutExpired):
            return None
    return _TABLE


def hook_ancestors():
    """Argument lists of this hook's ancestors, nearest first."""
    if os.path.isdir("/proc/self"):
        current = os.getppid()
        for _ in range(64):
            if current <= 1:
                return
            try:
                with open(f"/proc/{current}/cmdline", "rb") as handle:
                    args = [part.decode("utf-8", "replace") for part in handle.read().split(b"\0") if part]
            except OSError:
                return
            yield args
            stat = linux_stat(current)
            if not stat:
                return
            current = stat[0]
        return
    table = {}
    for line in core.process_table() or ():
        fields = line.split(None, 2)
        if len(fields) == 3 and fields[0].isdigit() and fields[1].isdigit():
            table[int(fields[0])] = (int(fields[1]), fields[2].split())
    current = os.getppid()
    for _ in range(64):
        if current <= 1 or current not in table:
            return
        parent, args = table[current]
        yield args
        current = parent


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
    if not os.environ.get("TMUX") or not re.fullmatch(r"%[0-9]+", core.PANE):
        return
    try:
        raw = sys.stdin.buffer.read(131073)
        if len(raw) > 131072:
            return
        event = json.loads(raw)
        if not isinstance(event, dict):
            return
        if from_app_server():
            core.PANE = app_server_pane(event)
            if not core.PANE:
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
