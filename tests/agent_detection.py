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
        check(process_name(46, proc_root=str(proc)) == "pi",
              "node hosting pi-coding-agent is pi")


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
    core = load("canopy_codex_hook", ROOT / "lib" / "codex-hook.py")
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
    test_live_cursor_agent_identity()
    print("ok - process_identity finds live cursor-agent panes")
    test_live_agent_process_scan()
    print("ok - agent-process.py detects live cursor-agent panes")


if __name__ == "__main__":
    main()
