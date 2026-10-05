"""Shared tmux state mechanics for observational agent lifecycle reporters."""
import fcntl
import os
import re
import shlex
from pathlib import Path
import subprocess
import time

from agent_kinds import name_from_args, process_name

SEP = "\x1f"
PANE = os.environ.get("TMUX_PANE", "")
PREFIX = "@tmux_canopy_agent_"
FIELDS = ("source", "session", "turn", "pane_pid", "status", "tool",
          "summary", "command", "request", "updated", "process_pid",
          "process_birth", "request_agent", "subagents")


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
    # Stored values run through field(), which removes the separator from
    # user-controlled text, so one display-message call can fetch every field.
    fmt = SEP.join(f"#{{{PREFIX}{key}}}" for key in keys)
    result = tmux("display-message", "-p", "-t", PANE, fmt)
    if result.returncode:
        return {key: "" for key in keys}
    values = result.stdout.rstrip("\n").split(SEP)
    values += [""] * (len(keys) - len(values))
    return dict(zip(keys, values))


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
    # Detached with no shared pipes: hook output must never wait for delivery.
    try:
        subprocess.Popen(argv, env=os.environ | text, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        pass


def alert(mode, current, values, kind, reply=""):
    """Announce transitions a user waits for; repeated state stays quiet."""
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
    if event != "needs-input" and current["updated"].isdigit() and values["updated"].isdigit():
        text["CANOPY_ALERT_ELAPSED"] = str(max(0, int(values["updated"]) - int(current["updated"])))
    start_alert((str(Path(__file__).resolve().parents[1] / "scripts" / "alert"),
                 PANE, event, kind, mode), text)


def schedule_expiry(process_pid, process_birth, current_timer):
    if not process_birth.isdigit():
        return
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
             "opencode": {"opencode"}, "gemini": {"gemini"}, "pi": {"pi"},
             "omp": {"omp"}, "agy": {"agy", "antigravity"},
             "cursor-agent": {"agent"}, "copilot": {"copilot"}, "grok": {"grok"}}.get(kind, set())
    if not names:
        return None
    try:
        root = int(root)
    except ValueError:
        return None
    if os.path.isdir("/proc/self"):
        current = os.getppid()
        chain = []
        for _ in range(128):
            if current <= 1:
                break
            stat = linux_stat(current)
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
                if not entry.name.isdigit() or process_name(entry.name) not in names:
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
        parents, candidates = {}, []
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
    ancestry, current = set(), os.getppid()
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
            birth = subprocess.run(("ps", "-p", str(pid), "-o", "lstart="), text=True,
                                   capture_output=True, timeout=3, check=False).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            return None
    return str(pid), birth


_TABLE = None


def process_table():
    """Every process as a "pid ppid args" line, read once per hook run."""
    global _TABLE
    if _TABLE is None:
        try:
            _TABLE = subprocess.run(("ps", "-eo", "pid=,ppid=,args="), text=True,
                                    capture_output=True, timeout=3, check=False).stdout.splitlines()
        except (OSError, subprocess.TimeoutExpired):
            return None
    return _TABLE


def agent_panes(kind, fields=()):
    """Return live, eligible agent panes from one tmux snapshot.

    Callers supply only the stored report fields their routing policy needs;
    they retain ownership of session and directory preference policy.
    """
    base = ("pane", "root", "dead", "sidebar", "slot", "path")
    formats = ("#{pane_id}", "#{pane_pid}", "#{pane_dead}", "#{@tmux_canopy}",
               "#{@tmux_canopy_slot}", "#{pane_current_path}")
    formats += tuple(f"#{{@tmux_canopy_agent_{field}}}" for field in fields)
    rows = tmux("list-panes", "-a", "-F", "|".join(formats))
    if rows.returncode:
        return []
    candidates = []
    names = base + tuple(fields)
    for line in rows.stdout.splitlines():
        values = (line.split("|") + [""] * len(names))[:len(names)]
        pane = dict(zip(names, values))
        if (not pane["root"].isdigit() or pane["dead"] == "1" or
                pane["sidebar"] == "1" or pane["slot"] == "1"):
            continue
        identity = process_identity(pane["root"], kind)
        if identity:
            pane["identity"] = identity
            candidates.append(pane)
    return candidates


def same_directory(left, right):
    if not left or not right:
        return False
    try:
        return os.path.realpath(left) == os.path.realpath(right)
    except (OSError, ValueError, TypeError):
        return False
