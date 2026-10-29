#!/usr/bin/env python3
"""Cursor Agent detection must use argv0 when /proc comm is a Node thread name."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
from agent_kinds import process_name  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def fake_proc(root, pid, *, comm, cmdline, ppid=1, birth="99"):
    entry = root / str(pid)
    entry.mkdir()
    (entry / "comm").write_text(comm + "\n")
    (entry / "cmdline").write_bytes(cmdline if isinstance(cmdline, bytes) else cmdline.encode())
    # Minimal /proc/<pid>/stat: pid (comm) state ppid ... starttime at field 22 (index 19 after ') ')
    # Format: "pid (comm) R ppid ..." with starttime as field 22 overall → index 19 in post-) fields
    padding = " ".join(["0"] * 17)
    (entry / "stat").write_text(f"{pid} ({comm}) R {ppid} {padding} {birth}\n")


def test_process_name_prefers_argv0():
    with tempfile.TemporaryDirectory(prefix="canopy-proc-") as directory:
        proc = Path(directory)
        fake_proc(proc, 42, comm="MainThread",
                  cmdline=b"/home/user/.local/bin/agent\0--use-system-ca\0index.js\0")
        check(process_name(42, proc_root=str(proc)) == "agent",
              "argv0 basename wins over Node MainThread comm")
        fake_proc(proc, 43, comm="claude", cmdline=b"")
        check(process_name(43, proc_root=str(proc)) == "claude",
              "empty cmdline falls back to comm")
        fake_proc(proc, 44, comm="node",
                  cmdline=b"/usr/bin/node\0/opt/app/index.js\0")
        check(process_name(44, proc_root=str(proc)) == "node",
              "ordinary node process stays node")
        fake_proc(proc, 45, comm="node",
                  cmdline=b"/usr/bin/node\0/Users/testuser/.pi/agent/install/releases/0.87.1/node_modules/.bin/pi\0")
        check(process_name(45, proc_root=str(proc)) == "pi",
              "node hosting the pi launcher is pi")
        fake_proc(proc, 46, comm="node",
                  cmdline=b"node\0/opt/pi-coding-agent/dist/cli.js\0")
        fake_proc(proc, 47, comm="python3.14",
                  cmdline=b"/home/u/.hermes/tools/python-3.14.7/bin/python3\0-I\0-c\0"
                          b"import sys; from hermes_cli.main import main; main()\0-p\0default\0")
        check(process_name(47, proc_root=str(proc)) == "hermes", "Hermes' installer launcher is hermes")
        fake_proc(proc, 48, comm="python3", cmdline=b"python3\0-m\0tui_gateway.entry\0")
        check(process_name(48, proc_root=str(proc)) == "hermes", "Hermes' TUI gateway is hermes")
        fake_proc(proc, 49, comm="python3", cmdline=b"python3\0-c\0print(1)\0")
        check(process_name(49, proc_root=str(proc)) == "python3", "other Python stays python3")
        fake_proc(proc, 50, comm="python3", cmdline=b"python3\0app.py\0hermes\0")
        check(process_name(50, proc_root=str(proc)) == "python3", "an argument named hermes is not Hermes")
        check(process_name(46, proc_root=str(proc)) == "pi",
              "node hosting pi-coding-agent is pi")


def test_nested_agent_isolation():
    """Nested child agents and editor-owned agents cannot hijack a pane's identity."""
    core = load("canopy_agent_reporting_nested", ROOT / "lib" / "agent_reporting.py")
    with tempfile.TemporaryDirectory(prefix="canopy-nested-") as directory:
        proc = Path(directory)
        # Pane 100 (-zsh): interactive claude (200) spawns subshell bash (250) ->
        # nested claude (300), codex (302), and grok (304); also direct headless claude -p (306).
        fake_proc(proc, 100, comm="zsh", cmdline=b"-zsh\0", ppid=1, birth="10")
        fake_proc(proc, 200, comm="claude", cmdline=b"claude\0", ppid=100, birth="20")
        fake_proc(proc, 210, comm="sh", cmdline=b"sh\0-c\0agent-hook claude\0", ppid=200, birth="21")
        fake_proc(proc, 250, comm="bash", cmdline=b"bash\0-c\0claude\0", ppid=200, birth="25")
        fake_proc(proc, 300, comm="claude", cmdline=b"claude\0", ppid=250, birth="30")
        fake_proc(proc, 301, comm="sh", cmdline=b"sh\0-c\0agent-hook claude\0", ppid=300, birth="31")
        fake_proc(proc, 302, comm="codex", cmdline=b"codex\0exec\0review\0", ppid=250, birth="32")
        fake_proc(proc, 304, comm="grok", cmdline=b"grok\0", ppid=250, birth="34")
        fake_proc(proc, 306, comm="claude", cmdline=b"claude\0-p\0summarize\0", ppid=200, birth="36")
        # Pane 400 (-zsh): interactive codex (401), sibling codex app-server (402),
        # and direct headless codex exec (403).
        fake_proc(proc, 400, comm="zsh", cmdline=b"-zsh\0", ppid=1, birth="40")
        fake_proc(proc, 401, comm="codex", cmdline=b"codex\0", ppid=400, birth="41")
        fake_proc(proc, 402, comm="codex", cmdline=b"codex\0app-server\0--listen\0unix://\0", ppid=400, birth="42")
        fake_proc(proc, 403, comm="codex", cmdline=b"codex\0exec\0fix\0", ppid=401, birth="43")
        # Pane 500 (-zsh): self-relaunch gemini wrapper (501) -> gemini child (502).
        fake_proc(proc, 500, comm="zsh", cmdline=b"-zsh\0", ppid=1, birth="50")
        fake_proc(proc, 501, comm="gemini", cmdline=b"gemini\0", ppid=500, birth="51")
        fake_proc(proc, 502, comm="gemini", cmdline=b"gemini\0--max-old-space-size=4096\0", ppid=501, birth="52")
        # Pane 600 (nvim): editor spawning claude (601).
        fake_proc(proc, 600, comm="nvim", cmdline=b"nvim\0", ppid=1, birth="60")
        fake_proc(proc, 601, comm="claude", cmdline=b"claude\0", ppid=600, birth="61")

        orig_proc = core.PROC_ROOT
        try:
            core.PROC_ROOT = str(proc)
            check(core.process_identity(100, "claude", caller_pid=210) == ("200", "20"),
                  "parent claude hook resolves to parent claude")
            check(core.process_identity(100, "claude", caller_pid=9999) == ("200", "20"),
                  "external scan resolves to parent claude despite nested children")
            check(core.process_identity(100, "claude", caller_pid=301) is None,
                  "nested subshell claude hook is rejected")
            check(core.process_identity(100, "claude", caller_pid=306) is None,
                  "direct headless claude -p child hook is rejected")
            check(core.process_identity(100, "codex", caller_pid=302) is None,
                  "cross-agent codex inside claude is rejected")
            check(core.process_identity(100, "codex", caller_pid=9999) is None,
                  "external scan rejects codex inside claude")
            check(core.process_identity(100, "claude", caller_pid=304) is None,
                  "cross-agent grok running claude compatibility hook inside claude is rejected")
            check(core.process_identity(400, "codex", caller_pid=401) == ("401", "41"),
                  "interactive codex resolves to 401")
            check(core.process_identity(400, "codex", caller_pid=402) == ("401", "41"),
                  "codex app-server sibling resolves to interactive codex 401")
            check(core.process_identity(400, "codex", caller_pid=9999) == ("401", "41"),
                  "external scan ignores codex app-server sibling and nested codex exec")
            check(core.process_identity(400, "codex", caller_pid=403) is None,
                  "direct headless codex exec child is rejected")
            check(core.process_identity(500, "gemini", caller_pid=502) == ("501", "51"),
                  "self-relaunch gemini wrapper resolves to outermost gemini PID")
            check(core.process_identity(500, "gemini", caller_pid=9999) == ("501", "51"),
                  "external scan resolves self-relaunch gemini wrapper to outermost PID")
            check(core.process_identity(600, "claude", caller_pid=601) is None,
                  "claude inside nvim is rejected")
            check(core.process_identity(600, "claude", caller_pid=9999) is None,
                  "external scan rejects claude inside nvim")
        finally:
            core.PROC_ROOT = orig_proc

    # Exercise the non-/proc process_table() path with the same tree.
    orig_proc, orig_table, orig_run = core.PROC_ROOT, core._TABLE, core.subprocess.run
    try:
        core.PROC_ROOT = "/nonexistent-proc"
        core._TABLE = [
            "100 1 -zsh",
            "200 100 claude",
            "210 200 sh -c agent-hook claude",
            "250 200 bash -c claude",
            "300 250 claude",
            "301 300 sh -c agent-hook claude",
            "302 250 codex exec review",
            "304 250 grok",
            "306 200 claude -p summarize",
            "400 1 -zsh",
            "401 400 codex",
            "402 400 codex app-server --listen unix://",
            "403 401 codex exec fix",
            "500 1 -zsh",
            "501 500 gemini",
            "502 501 gemini --max-old-space-size=4096",
            "600 1 nvim",
            "601 600 claude",
        ]
        core.subprocess.run = lambda argv, **kw: subprocess.CompletedProcess(argv, 0, f"birth-{argv[2]}\n", "")
        check(core.process_identity(100, "claude", caller_pid=210) == ("200", "birth-200"),
              "ps table: parent claude hook resolves to parent claude")
        check(core.process_identity(100, "claude", caller_pid=9999) == ("200", "birth-200"),
              "ps table: external scan resolves to parent claude")
        check(core.process_identity(100, "claude", caller_pid=301) is None,
              "ps table: nested subshell claude hook is rejected")
        check(core.process_identity(100, "claude", caller_pid=306) is None,
              "ps table: direct headless claude -p child is rejected")
        check(core.process_identity(100, "codex", caller_pid=302) is None,
              "ps table: cross-agent codex inside claude is rejected")
        check(core.process_identity(100, "claude", caller_pid=304) is None,
              "ps table: cross-agent grok running claude hook is rejected")
        check(core.process_identity(400, "codex", caller_pid=402) == ("401", "birth-401"),
              "ps table: codex app-server sibling resolves to interactive codex")
        check(core.process_identity(400, "codex", caller_pid=403) is None,
              "ps table: direct headless codex exec child is rejected")
        check(core.process_identity(500, "gemini", caller_pid=502) == ("501", "birth-501"),
              "ps table: self-relaunch gemini wrapper resolves to outermost PID")
        check(core.process_identity(600, "claude", caller_pid=601) is None,
              "ps table: claude inside nvim is rejected")
    finally:
        core.PROC_ROOT, core._TABLE, core.subprocess.run = orig_proc, orig_table, orig_run


def test_live_cursor_agent_identity():
    """Reproduce the real failure: pane shows agent, but comm is MainThread."""
    panes = subprocess.run(
        ("tmux", "list-panes", "-a", "-F", "#{pane_id}|#{pane_pid}|#{pane_current_command}"),
        text=True, capture_output=True, timeout=5, check=False)
    if panes.returncode:
        print("skip - no tmux server for live cursor-agent identity check")
        return
    targets = []
    for line in panes.stdout.splitlines():
        pane, pid, command = (line.split("|") + [""] * 3)[:3]
        if command == "agent" and pid.isdigit():
            targets.append((pane, pid))
    if not targets:
        print("skip - no live agent panes for identity check")
        return
    core = load("canopy_agent_reporting", ROOT / "lib" / "agent_reporting.py")
    for pane, pid in targets:
        identity = core.process_identity(pid, "cursor-agent")
        check(identity is not None,
              f"process_identity({pid}, cursor-agent) for {pane} must find argv0=agent "
              f"(comm is often MainThread under Node)")
        agent_pid, _birth = identity
        check(process_name(int(agent_pid)) == "agent",
              f"matched pid {agent_pid} must resolve to executable name agent")


def test_live_agent_process_scan():
    # Same pane field layout as scripts/tree-source (root pid at index 16).
    sep = "\x1f"
    fmt = sep.join([
        "P", "#{pane_id}", "#{window_id}", "#{pane_index}", "#{pane_current_command}",
        "#{pane_title}", "#{pane_current_path}", "#{pane_dead}", "#{@tmux_canopy}",
        "#{@tmux_canopy_slot}", "#{@tmux_canopy_notice_pane_activity}",
        "#{@tmux_canopy_notice_pane_bell}", "#{@tmux_canopy_notice_pane_silence}",
        "#{@tmux_canopy_target}", "#{@tmux_canopy_target_session}", "#{pane_last}",
        "#{pane_pid}", "#{@tmux_canopy_agent_source}", "#{@tmux_canopy_agent_session}",
        "#{@tmux_canopy_agent_pane_pid}", "#{@tmux_canopy_agent_status}",
        "#{@tmux_canopy_agent_updated}", "#{@tmux_canopy_agent_process_pid}",
        "#{@tmux_canopy_agent_process_birth}", "#{@tmux_canopy_agent_subagents}",
    ])
    panes = subprocess.run(
        ("tmux", "list-panes", "-a", "-F", fmt),
        text=True, capture_output=True, timeout=5, check=False)
    if panes.returncode:
        print("skip - no tmux server for agent-process scan")
        return
    agent_panes = {
        line.split(sep)[1]
        for line in panes.stdout.splitlines()
        if line.startswith("P" + sep) and (line.split(sep) + [""] * 5)[4] == "agent"
    }
    if not agent_panes:
        print("skip - no live agent panes for agent-process scan")
        return
    result = subprocess.run(
        [sys.executable, str(ROOT / "lib" / "agent-process.py")],
        input=panes.stdout, text=True, capture_output=True, timeout=5, check=False)
    check(result.returncode == 0, f"agent-process.py failed: {result.stderr}")
    found = {
        line.split("\x1f")[1]
        for line in result.stdout.splitlines()
        if line.startswith("A\x1f") and line.endswith("\x1fcursor-agent")
    }
    check(agent_panes <= found,
          f"agent-process.py must emit cursor-agent for panes {sorted(agent_panes)}; got {sorted(found)}")


def main():
    test_process_name_prefers_argv0()
    test_nested_agent_isolation()
    print("ok - nested and cross-agent child invocations cannot hijack parent panes")
    script = ROOT / "lib" / "agent-process.sh"
    probe = subprocess.run(["bash", "-c", f"""
set -u
source {script}
ps() {{ printf '%s\n' '10 1 Mon Sep 28 18:47:49 2026 -zsh' '11 10 Mon Sep 28 18:54:08 2026 pi'; }}
export -f ps
canopy_pane_agent 10
"""], capture_output=True, text=True, timeout=10)
    check(probe.returncode == 0 and probe.stdout.strip() == "pi", probe.stderr or probe.stdout)
    print("ok - process_name prefers argv0 over Node MainThread comm")
    # Several node panes share one ps snapshot: lookups return through
    # CANOPY_REPLY, so no subshell discards the cache and re-runs ps.
    probe = subprocess.run(["bash", "-c", f"""
set -u
source {script}
counter=$(mktemp)
ps() {{ printf x >> "$counter"; printf '%s\n' \
  '10 1 Mon Sep 28 18:47:49 2026 -zsh' '11 10 Mon Sep 28 18:54:08 2026 node /opt/bin/pi --x' \
  '20 1 Mon Sep 28 18:47:49 2026 -zsh' '21 20 Mon Sep 28 18:54:08 2026 node /lib/oh-my-pi/cli.js' \
  '30 1 Mon Sep 28 18:47:49 2026 -zsh' '31 30 Mon Sep 28 18:54:08 2026 node server.js'; }}
canopy_load_ps_snapshot
out=''
for root in 10 20 30; do canopy_pane_agent "$root" >/dev/null; out+="$root=$CANOPY_REPLY "; done
canopy_ps_snapshot_lines >/dev/null
calls=$(<"$counter"); rm -f "$counter"
printf '%scalls=%s pids=%s' "$out" "${{#calls}}" "${{#CANOPY_KIND_PIDS[@]}}"
"""], capture_output=True, text=True, timeout=10)
    check(probe.returncode == 0 and probe.stdout == "10=pi 20=omp 30= calls=1 pids=2",
          probe.stderr or probe.stdout)
    print("ok - node pane relabeling reads the process table once")
    # Hermes runs as Python, so its pane lookup, the Agents view's process
    # list, and the ps identity check go by its kind, not its process name.
    probe = subprocess.run(["bash", "-c", f"""
set -u
source {script}
ps() {{ printf '%s\n' \
  '10 1 Mon Sep 28 18:47:49 2026 -zsh' '11 10 Mon Sep 28 18:54:08 2026 /u/.hermes/tools/python-3.14.7/bin/python3 -I -c import sys; from hermes_cli.main import main; main() -p default' \
  '20 1 Mon Sep 28 18:47:49 2026 -zsh' '21 20 Mon Sep 28 18:54:08 2026 python3.14 -m tui_gateway.entry' \
  '22 21 Mon Sep 28 18:54:09 2026 node /u/.hermes/ui/tui.js' \
  '30 1 Mon Sep 28 18:47:49 2026 -zsh' '31 30 Mon Sep 28 18:54:08 2026 python3 manage.py runserver' \
  '40 1 Mon Sep 28 18:47:49 2026 -zsh' '41 40 Mon Sep 28 18:54:08 2026 node /opt/bin/pi --x'; }}
canopy_load_ps_snapshot
out=''
for root in 10 20 30 40; do canopy_pane_agent "$root" >/dev/null; out+="$root=$CANOPY_REPLY "; done
canopy_ps_snapshot_lines >/dev/null
lines=$CANOPY_REPLY
[[ $lines == *'11 10 hermes'* && $lines == *'31 30 python3'* ]] && out+='listed '
if [[ ! -d /proc/self ]]; then
  canopy_process_identity 10 11 'Mon Sep 28 18:54:08 2026' hermes && out+='hermes-verified '
  canopy_process_identity 40 41 'Mon Sep 28 18:54:08 2026' pi && out+='pi-verified '
  canopy_process_identity 30 31 'Mon Sep 28 18:54:08 2026' hermes || out+='python-rejected'
else
  out+='hermes-verified pi-verified python-rejected'
fi
printf '%s' "$out"
"""], capture_output=True, text=True, timeout=10)
    check(probe.returncode == 0 and probe.stdout ==
          "10=hermes 20=hermes 30= 40=pi listed hermes-verified pi-verified python-rejected",
          probe.stderr or probe.stdout)
    print("ok - Hermes under Python is found, listed, and verified by its kind")
    # macOS ps pads single-digit days in lstart ("Oct  1"); a hook-recorded
    # start time must still match the parsed snapshot on days 1-9.
    if not Path("/proc/self").exists():
        probe = subprocess.run(["bash", "-c", f"""
set -u
source {script}
ps() {{ printf '%s\n' \
  '10 1 Thu Oct  1 07:06:21 2026 -zsh' \
  '11 10 Thu Oct  1 07:06:22 2026 claude' \
  '12 11 Thu Oct  1 07:06:23 2026 bash -c codex' \
  '13 12 Thu Oct  1 07:06:24 2026 codex' \
  '20 1 Thu Oct  1 07:06:21 2026 nvim' \
  '21 20 Thu Oct  1 07:06:22 2026 claude'; }}
canopy_process_identity 10 11 'Thu Oct  1 07:06:22 2026' claude && echo padded
canopy_process_identity 10 11 'Thu Oct  1 07:06:23 2026' claude || echo different
canopy_process_identity 10 13 'Thu Oct  1 07:06:24 2026' codex || echo cross-rejected
canopy_process_identity 20 21 'Thu Oct  1 07:06:22 2026' claude || echo editor-rejected
canopy_resolve_pane_agent 10 zsh >/dev/null && echo "resolved=$CANOPY_REPLY"
canopy_resolve_pane_agent 20 nvim >/dev/null || echo editor-pane-rejected
"""], capture_output=True, text=True, timeout=10)
        check(probe.stdout.split() == [
            "padded", "different", "cross-rejected", "editor-rejected",
            "resolved=claude", "editor-pane-rejected",
        ], probe.stderr or probe.stdout)
        print("ok - process identity matches ps start times with padded single-digit days")
    test_live_cursor_agent_identity()
    print("ok - process_identity finds live cursor-agent panes")
    test_live_agent_process_scan()
    print("ok - agent-process.py detects live cursor-agent panes")


if __name__ == "__main__":
    main()
