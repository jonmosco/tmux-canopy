"""Shared tmux state mechanics for observational agent lifecycle reporters."""
import fcntl
import os
import re
import shlex
from pathlib import Path
import subprocess
import time

from agent_kinds import is_carrier, is_headless_args, name_from_args, process_args, process_name

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


PROC_ROOT = "/proc"


def linux_stat(pid, proc_root=None):
    base = proc_root or PROC_ROOT
    try:
        raw = open(f"{base}/{pid}/stat", encoding="utf-8").read()
        fields = raw.rsplit(") ", 1)[1].split()
        return int(fields[1]), fields[19]
    except (OSError, IndexError, ValueError):
        return None


# Executable names (as name_from_args reports them) for each reporting kind.
AGENT_NAMES = {"codex": {"codex"}, "claude": {"claude", "claude-code"},
               "opencode": {"opencode"}, "gemini": {"gemini"}, "pi": {"pi"},
               "omp": {"omp"}, "agy": {"agy", "antigravity"},
               "cursor-agent": {"agent"}, "copilot": {"copilot"}, "grok": {"grok"},
               "hermes": {"hermes"}}


def process_identity(root, kind="codex", caller_pid=None):
    """Find a live agent process in this pane, ignoring nested child agents."""
    names = AGENT_NAMES.get(kind, set())
    if not names:
        return None
    try:
        root = int(root)
    except ValueError:
        return None
    if caller_pid is None:
        caller_pid = os.getppid()
    use_proc = os.path.isdir(f"{PROC_ROOT}/self") if PROC_ROOT == "/proc" else os.path.isdir(PROC_ROOT)
    if use_proc:
        cache = {}

        def info_for(pid):
            if pid not in cache:
                stat = linux_stat(pid)
                if not stat:
                    cache[pid] = None
                else:
                    args = process_args(pid, PROC_ROOT)
                    name = name_from_args(args) or process_name(pid, PROC_ROOT)
                    cache[pid] = (stat[0], name, args, stat[1])
            return cache[pid]

        def all_candidates():
            result = []
            try:
                entries = os.scandir(PROC_ROOT)
            except OSError:
                return result
            with entries:
                for entry in entries:
                    if not entry.name.isdigit():
                        continue
                    pid = int(entry.name)
                    info = info_for(pid)
                    if info and info[1] in names:
                        result.append((pid, info[3]))
            return result
    else:
        records = process_table()
        if records is None:
            return None
        table, candidate_list = {}, []
        for line in records:
            fields = line.split(None, 2)
            if len(fields) == 3 and fields[0].isdigit() and fields[1].isdigit():
                pid, ppid, args = int(fields[0]), int(fields[1]), fields[2].split()
                name = name_from_args(args)
                table[pid] = (ppid, name, args, "")
                if name in names:
                    candidate_list.append((pid, ""))

        def info_for(pid):
            return table.get(pid)

        def all_candidates():
            return candidate_list

    def with_birth(pid, birth):
        if not birth:
            try:
                birth = subprocess.run(("ps", "-p", str(pid), "-o", "lstart="), text=True,
                                       capture_output=True, timeout=3, check=False).stdout.strip()
            except (OSError, subprocess.TimeoutExpired):
                return None
            if not birth:
                return None
        return str(pid), str(birth)

    chain, seen = [], set()
    current = caller_pid
    reached_root = False
    for _ in range(128):
        if current <= 1 or current in seen:
            break
        seen.add(current)
        info = info_for(current)
        if not info:
            break
        ppid, name, args, birth = info
        chain.append((current, name, args, birth))
        if current == root:
            reached_root = True
            break
        if ppid <= 0 or ppid == current:
            break
        current = ppid

    if reached_root:
        if any(not is_carrier(name, kind) for _, name, _, _ in chain):
            return None
        agent_indices = [i for i, (_, name, _, _) in enumerate(chain) if name in names]
        if agent_indices:
            if len(agent_indices) > 1:
                if agent_indices[-1] - agent_indices[0] != len(agent_indices) - 1:
                    return None
                if any(is_headless_args(kind, chain[i][2]) for i in agent_indices[:-1]):
                    return None
            pid, _, _, birth = chain[agent_indices[-1]]
            return with_birth(pid, birth)

    matches = []
    for pid, birth in all_candidates():
        current = pid
        for depth in range(128):
            if current != pid:
                info = info_for(current)
                if not info:
                    break
                if info[1] in names or not is_carrier(info[1], kind):
                    break
            if current == root:
                matches.append((depth, pid, birth))
                break
            info = info_for(current)
            if not info or info[0] <= 0 or info[0] == current:
                break
            current = info[0]
    if not matches:
        return None
    related = [item for item in matches if item[1] in seen]
    matches = related or matches
    if not related and len(matches) > 1:
        return None
    matches.sort()
    _, pid, birth = matches[0]
    return with_birth(pid, birth)


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


def ancestors():
    """(pid, argv) for each ancestor of this hook, nearest first."""
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
            yield current, args
            stat = linux_stat(current)
            if not stat:
                return
            current = stat[0]
        return
    table = {}
    for line in process_table() or ():
        fields = line.split(None, 2)
        if len(fields) == 3 and fields[0].isdigit() and fields[1].isdigit():
            table[int(fields[0])] = (int(fields[1]), fields[2].split())
    current = os.getppid()
    for _ in range(64):
        if current <= 1 or current not in table:
            return
        parent, args = table[current]
        yield current, args
        current = parent


def processes():
    """pid -> (ppid, argv) for every process."""
    table = {}
    if os.path.isdir("/proc/self"):
        for entry in os.scandir("/proc"):
            if not entry.name.isdigit():
                continue
            stat = linux_stat(entry.name)
            try:
                with open(f"/proc/{entry.name}/cmdline", "rb") as handle:
                    args = [part.decode("utf-8", "replace") for part in handle.read().split(b"\0") if part]
            except OSError:
                continue
            if stat:
                table[int(entry.name)] = (stat[0], args)
        return table
    for line in process_table() or ():
        fields = line.split(None, 2)
        if len(fields) == 3 and fields[0].isdigit() and fields[1].isdigit():
            table[int(fields[0])] = (int(fields[1]), fields[2].split())
    return table


def session_links(args):
    """Session ids an agent's argv runs, resumes, or attaches to."""
    links = set()
    for flag, value in zip(args, args[1:]):
        if flag in ("--resume", "-r", "--session-id", "attach"):
            value = os.path.basename(value).removesuffix(".jsonl")
            if len(value) >= 8:
                links.add(value)
    return links


def linked(left, right):
    # `claude attach` takes a session id prefix.
    return any(a.startswith(b) or b.startswith(a) for a in left for b in right)


def pane_from_ancestry(kind, session=""):
    """The pane a hook belongs to when it arrives without TMUX_PANE. Usually
    the pane whose root process is an ancestor of the agent that ran the hook.
    A Claude Code background session runs outside tmux, so its pane is instead
    the one whose agent client resumes or attaches to the same session; only a
    single such pane counts. Without TMUX, plain tmux reaches the default
    server; a hook from an agent outside tmux finds no pane."""
    names = AGENT_NAMES.get(kind, set())
    rows = tmux("list-panes", "-a", "-F", "#{pane_id}|#{pane_pid}|#{pane_dead}|#{@tmux_canopy}|#{@tmux_canopy_slot}")
    if rows.returncode or not names:
        return ""
    roots = {}
    for line in rows.stdout.splitlines():
        pane, root, dead, sidebar, slot = (line.split("|") + [""] * 5)[:5]
        if root.isdigit() and dead != "1" and sidebar != "1" and slot != "1":
            roots[int(root)] = pane
    found = False
    carried = True
    links = {session} if len(session) >= 8 else set()
    for pid, args in ancestors():
        name = name_from_args(args)
        if name in names:
            found = True
            links |= session_links(args)
        elif not is_carrier(name, kind):
            carried = False
        if found and pid in roots:
            return roots[pid] if carried else ""
    if not found or not links:
        return ""
    table = processes()
    panes = set()
    for pid, (_, args) in table.items():
        if name_from_args(args) not in names or not linked(session_links(args), links):
            continue
        current = pid
        for _ in range(64):
            if current != pid and current in table and not is_carrier(name_from_args(table[current][1]), kind):
                break
            if current in roots:
                panes.add(roots[current])
                break
            if current not in table or current <= 1:
                break
            current = table[current][0]
    return panes.pop() if len(panes) == 1 else ""


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
