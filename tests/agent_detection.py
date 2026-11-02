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
from agent_kinds import is_headless_args, process_name  # noqa: E402


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
        fake_proc(proc, 51, comm="2.1.201",
                  cmdline=b"/home/u/.local/share/claude/versions/2.1.201\0")
        check(process_name(51, proc_root=str(proc)) == "claude",
              "standalone Claude version binary resolves to claude")
        fake_proc(proc, 52, comm="2_1_201", cmdline=b"")
        check(process_name(52, proc_root=str(proc)) == "claude",
              "underscore-separated Claude version comm resolves to claude")
        fake_proc(proc, 53, comm="127.0.0.1", cmdline=b"127.0.0.1\0")
        check(process_name(53, proc_root=str(proc)) == "127.0.0.1",
              "four-part IPv4 address is not mistaken for a Claude version")
        fake_proc(proc, 54, comm="node",
                  cmdline=b"/opt/homebrew/opt/node/bin/node\0/opt/homebrew/bin/gemini\0")
        check(process_name(54, proc_root=str(proc)) == "gemini",
              "Homebrew Node-hosted gemini resolves to gemini")
        fake_proc(proc, 55, comm="node",
                  cmdline=b"node\0/opt/homebrew/Cellar/gemini-cli/0.46.0/libexec/lib/node_modules/@google/gemini-cli/bundle/gemini.js\0")
        check(process_name(55, proc_root=str(proc)) == "gemini",
              "@google/gemini-cli bundle resolves to gemini")
        fake_proc(proc, 56, comm="node",
                  cmdline=b"node\0--use-system-ca\0/home/u/.local/share/cursor-agent/versions/1/index.js\0")
        check(process_name(56, proc_root=str(proc)) == "cursor-agent",
              "Node-hosted cursor-agent bundle resolves to cursor-agent")
        fake_proc(proc, 57, comm="bun",
                  cmdline=b"/usr/local/bin/bun\0/opt/node_modules/@anthropic-ai/claude-code/cli.js\0")
        check(process_name(57, proc_root=str(proc)) == "claude",
              "Bun-hosted @anthropic-ai/claude-code resolves to claude")
        fake_proc(proc, 58, comm="node",
                  cmdline=b"node\0/opt/bin/codex\0app-server\0--listen\0unix://\0")
        check(process_name(58, proc_root=str(proc)) == "codex-app-server",
              "Node-hosted codex app-server resolves to codex-app-server")
        fake_proc(proc, 59, comm="node", cmdline=b"node\0server.js\0gemini\0")
        check(process_name(59, proc_root=str(proc)) == "node",
              "an argument named gemini to another Node script stays node")
        fake_proc(proc, 60, comm="node", cmdline=b"node\0-e\0console.log('gemini')\0")
        check(process_name(60, proc_root=str(proc)) == "node",
              "node -e inline script stays node")
        check(is_headless_args("codex", ["node", "--use-system-ca", "/opt/bin/codex", "exec", "review"]),
              "Node-hosted codex exec is recognized as headless")
        check(not is_headless_args("codex", ["node", "/opt/bin/codex"]),
              "interactive Node-hosted codex is not headless")
        check(is_headless_args("gemini", ["node", "/opt/bin/gemini", "-p", "summarize"]),
              "Node-hosted gemini -p is recognized as headless")


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
    # Version-named standalone Claude resolves without spawning ps; Node-hosted
    # Gemini and MainThread/node Cursor Agent share one ps snapshot.
    probe = subprocess.run(["bash", "-c", f"""
set -u
source {script}
counter=$(mktemp)
ps() {{ printf x >> "$counter"; printf '%s\\n' \\
  '10 1 Mon Sep 28 18:47:49 2026 -zsh' '11 10 Mon Sep 28 18:54:08 2026 /opt/homebrew/opt/node/bin/node /opt/homebrew/bin/gemini' \\
  '20 1 Mon Sep 28 18:47:49 2026 -zsh' '21 20 Mon Sep 28 18:54:08 2026 /Users/me/.local/bin/agent --use-system-ca /Users/me/.local/share/cursor-agent/index.js' \\
  '30 1 Mon Sep 28 18:47:49 2026 -zsh' '31 30 Mon Sep 28 18:54:08 2026 /Users/me/.local/share/claude/versions/2_1_201' \\
  '40 1 Mon Sep 28 18:47:49 2026 -zsh' '41 40 Mon Sep 28 18:54:08 2026 node server.js gemini'; }}
out=''
canopy_resolve_pane_agent 30 2_1_201 >/dev/null
fast_calls=$(<"$counter")
out+="fast=$CANOPY_REPLY:${{#fast_calls}} "
for pair in 10:node 20:MainThread 30:zsh 40:node; do
  canopy_resolve_pane_agent "${{pair%%:*}}" "${{pair#*:}}" >/dev/null
  out+="${{pair%%:*}}=$CANOPY_REPLY "
done
if [[ ! -d /proc/self ]]; then
  canopy_process_identity 10 11 'Mon Sep 28 18:54:08 2026' gemini && out+='gemini-ok '
  canopy_process_identity 20 21 'Mon Sep 28 18:54:08 2026' cursor-agent && out+='cursor-ok '
  canopy_process_identity 30 31 'Mon Sep 28 18:54:08 2026' claude && out+='claude-ok '
  canopy_process_identity 40 41 'Mon Sep 28 18:54:08 2026' gemini || out+='arg-rejected '
else
  out+='gemini-ok cursor-ok claude-ok arg-rejected '
fi
calls=$(<"$counter"); rm -f "$counter"
printf '%scalls=%s' "$out" "${{#calls}}"
"""], capture_output=True, text=True, timeout=10)
    check(probe.returncode == 0 and probe.stdout ==
          "fast=claude:0 10=gemini 20=cursor-agent 30=claude 40= gemini-ok cursor-ok claude-ok arg-rejected calls=1",
          probe.stderr or probe.stdout)
    print("ok - version-named Claude and Node-hosted agents resolve and verify cleanly")

    # Synthetic Linux /proc/<pid>/task/*/children walk: resolves native,
    # version-named, Node/Python-hosted, multi-threaded, and codex-app-server
    # panes while rejecting editor-owned and cross-agent children with zero ps calls.
    with tempfile.TemporaryDirectory(prefix="canopy-proc-children-") as proc_dir:
        proc = Path(proc_dir)
        (proc / "self").mkdir()

        def add_proc(pid, comm, argv, children=(), extra_tid_children=None):
            pdir = proc / str(pid)
            tdir = pdir / "task" / str(pid)
            tdir.mkdir(parents=True)
            (pdir / "comm").write_text(comm + "\n", encoding="utf-8")
            if isinstance(argv, bytes):
                (pdir / "cmdline").write_bytes(argv)
            else:
                (pdir / "cmdline").write_bytes(b"\0".join(a.encode("utf-8") for a in argv) + (b"\0" if argv else b""))
            # Linux fs/proc/array.c formats children as "%d " with no trailing newline.
            (tdir / "children").write_text("".join(f"{c} " for c in children), encoding="utf-8")
            for tid, tchildren in (extra_tid_children or {}).items():
                etdir = pdir / "task" / str(tid)
                etdir.mkdir(parents=True)
                (etdir / "children").write_text("".join(f"{c} " for c in tchildren), encoding="utf-8")

        # 10: zsh -> node gemini
        add_proc(10, "zsh", ["-zsh"], children=(11,))
        add_proc(11, "MainThread", ["/usr/bin/node", "/usr/lib/node_modules/@google/gemini-cli/dist/index.js"])
        # 20: zsh -> multi-threaded carrier bash (child on worker tid 201) -> cursor-agent (no trailing NUL)
        add_proc(20, "zsh", ["-zsh"], children=(), extra_tid_children={201: (21,)})
        add_proc(21, "MainThread", b"/home/me/.local/bin/agent\0/home/me/.local/share/cursor-agent/index.js")
        # 30: zsh -> claude -> bash -c codex -> codex (must keep outer claude, not inner codex)
        add_proc(30, "zsh", ["-zsh"], children=(31,))
        add_proc(31, "2_1_201", ["/home/me/.local/share/claude/versions/2_1_201"], children=(32,))
        add_proc(32, "bash", ["bash", "-c", "codex"], children=(33,))
        add_proc(33, "codex", ["codex"])
        # 40: zsh -> nvim -> claude (editor-owned, must reject)
        add_proc(40, "zsh", ["-zsh"], children=(41,))
        add_proc(41, "nvim", ["nvim"], children=(42,))
        add_proc(42, "claude", ["claude"])
        # 50: zsh -> codex app-server (carrier) -> codex
        add_proc(50, "zsh", ["-zsh"], children=(51,))
        add_proc(51, "codex", ["/usr/local/bin/codex", "app-server"], children=(52,))
        add_proc(52, "codex", ["/usr/local/bin/codex"])
        # 60: zsh -> python3 hermes, 70: plain zsh
        add_proc(60, "zsh", ["-zsh"], children=(61,))
        add_proc(61, "python3", ["python3", "-m", "tui_gateway.entry"])
        add_proc(70, "zsh", ["-zsh"], children=())

        wrap_dir = proc / "bin"
        wrap_dir.mkdir()
        ps_counter = proc / "ps-calls"
        ps_counter.write_text("", encoding="utf-8")
        ps_stub = wrap_dir / "ps"
        ps_stub.write_text(f'#!/usr/bin/env bash\nprintf x >> "{ps_counter}"\nexit 1\n', encoding="utf-8")
        ps_stub.chmod(0o755)
        proc_env = {
            **os.environ,
            "CANOPY_PROC_ROOT": str(proc),
            "PATH": f"{wrap_dir}:{os.environ.get('PATH', '')}",
        }
        probe = subprocess.run(["bash", "-c", f"""
set -u
source {script}
out=''
for pair in 10:MainThread 20:MainThread 30:zsh 40:nvim 50:zsh 60:python3 70:zsh; do
  canopy_resolve_pane_agent "${{pair%%:*}}" "${{pair#*:}}" >/dev/null
  out+="${{pair%%:*}}=$CANOPY_REPLY "
done
printf '%s' "$out"
"""], env=proc_env, capture_output=True, text=True, timeout=10)
        check(probe.returncode == 0 and probe.stdout ==
              "10=gemini 20=cursor-agent 30=claude 40= 50=codex 60=hermes 70= ",
              probe.stderr or probe.stdout)
        check(ps_counter.read_text(encoding="utf-8") == "", "Linux /proc walk must not invoke ps")
    print("ok - Linux /proc children walk resolves pane agents without invoking ps")

    test_live_cursor_agent_identity()
    print("ok - process_identity finds live cursor-agent panes")
    test_live_agent_process_scan()
    print("ok - agent-process.py detects live cursor-agent panes")


if __name__ == "__main__":
    main()
