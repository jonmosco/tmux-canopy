#!/usr/bin/env python3
"""Exercise optional integration ownership and TPM-style entrypoint loading."""
import json
import os
from pathlib import Path
import pty
import subprocess as sp
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args, env, ok=True):
    result = sp.run(args, env=env, capture_output=True, text=True, timeout=30)
    if ok:
        assert result.returncode == 0, (args, result.stdout, result.stderr)
    return result


with tempfile.TemporaryDirectory(prefix="canopy-setup-") as temp:
    home = Path(temp)
    env = os.environ.copy()
    env["HOME"] = temp
    env["CODEX_HOME"] = str(home / "custom codex")
    env["CLAUDE_CONFIG_DIR"] = str(home / "custom claude")
    env["PI_CODING_AGENT_DIR"] = str(home / "custom pi")
    env["XDG_CONFIG_HOME"] = str(home / "config")
    env.pop("TMUX", None)
    env.pop("TMUX_PANE", None)
    codex = Path(env["CODEX_HOME"]) / "hooks.json"
    codex.parent.mkdir(parents=True)
    codex.write_text(json.dumps({"notify": ["user"], "hooks": {"Stop": [{"hooks": [{"command": "/usr/bin/other", "type": "command"}]}]}}))
    claude_link = Path(env["CLAUDE_CONFIG_DIR"]) / "settings.json"
    claude_target = home / "dotfiles" / "claude-settings.json"
    claude_link.parent.mkdir(parents=True)
    claude_target.parent.mkdir(parents=True)
    claude_target.write_text('{"theme": "dark"}\n')
    claude_link.symlink_to(claude_target)

    cli = str(ROOT / "canopy")
    before = codex.read_text()
    run(cli, "integration", "install", "codex", "--dry-run", env=env)
    assert codex.read_text() == before
    run(cli, "integration", "install", "codex", "claude", "gemini", "pi", "omp", "opencode", env=env)
    first = codex.read_text()
    data = json.loads(first)
    assert data["notify"] == ["user"]
    assert claude_link.is_symlink() and json.loads(claude_target.read_text())["theme"] == "dark"
    assert any(action["command"] == "/usr/bin/other" for group in data["hooks"]["Stop"] for action in group["hooks"])
    assert str(ROOT / "scripts" / "codex-hook") in first
    codex.write_text(first.replace(str(ROOT), "/previous/install"))
    assert "outdated path" in run(cli, "integration", "status", "codex", env=env).stdout
    run(cli, "integration", "install", "codex", "claude", "gemini", "pi", "omp", "opencode", env=env)
    assert codex.read_text() == first
    result = run(cli, "integration", "status", env=env)
    assert all(f"{kind:9} installed" in result.stdout for kind in ("codex", "claude", "gemini", "pi", "omp", "opencode"))
    plugin = Path(env["XDG_CONFIG_HOME"]) / "opencode/plugins/canopy-agent-state.js"
    plugin.write_text(plugin.read_text() + "\n// user change\n")
    result = run(cli, "integration", "uninstall", "opencode", env=env, ok=False)
    assert result.returncode != 0 and "review it manually" in result.stderr
    plugin.write_text(plugin.read_text().removesuffix("\n// user change\n"))
    run(cli, "integration", "uninstall", "codex", "claude", "gemini", "pi", "omp", "opencode", env=env)
    restored = json.loads(codex.read_text())
    assert restored["notify"] == ["user"]
    assert restored["hooks"] == {"Stop": [{"hooks": [{"command": "/usr/bin/other", "type": "command"}]}]}
    assert claude_link.is_symlink() and json.loads(claude_target.read_text()) == {"theme": "dark"}
    assert not plugin.exists()
    assert list(codex.parent.glob("hooks.json.canopy-backup-*"))
    print("ok - integrations install idempotently, preserve unrelated settings, and uninstall only owned entries")

    for answer in ("", "all"):
        master, slave = pty.openpty()
        try:
            os.write(master, (answer + "\n").encode())
            result = sp.run([cli, "setup"], env=env, stdin=slave,
                            capture_output=True, text=True, timeout=30)
            assert result.returncode == 0, (result.stdout, result.stderr)
            assert "Agents to install" in result.stdout
        finally:
            os.close(slave)
            os.close(master)
        if not answer:
            assert json.loads(codex.read_text()) == restored
    status = run(cli, "integration", "status", env=env).stdout
    assert all(f"{kind:9} installed" in status for kind in ("codex", "claude", "gemini", "pi", "omp", "opencode"))
    run(cli, "integration", "uninstall", "codex", "claude", "gemini", "pi", "omp", "opencode", env=env)
    assert json.loads(codex.read_text()) == restored
    print("ok - dry-run, interactive setup cancellation, all-agent setup and removal")

    codex.write_text("{invalid")
    result = run(cli, "integration", "install", "codex", env=env, ok=False)
    assert result.returncode != 0 and codex.read_text() == "{invalid"
    print("ok - invalid JSON and modified extension files are left untouched")

    socket = f"canopy-tpm-test-{os.getpid()}"
    tm = lambda *args: run("tmux", "-L", socket, *args, env=env).stdout.strip()
    try:
        pane = tm("-f", "/dev/null", "new-session", "-d", "-P", "-F", "#{pane_id}", "sleep 120")
        env["TMUX"] = tm("display-message", "-p", "-t", pane, "#{socket_path},#{pid},0")
        for entrypoint in sorted(ROOT.glob("*.tmux")):
            if entrypoint.name.startswith("tmux-"):
                run(str(entrypoint), env=env)
        assert tm("show-option", "-gqv", "@tmux_canopy_loaded_path") == str(ROOT)
        keys = tm("list-keys", "-T", "prefix")
        assert "scripts/toggle" in keys
        doctor = run(cli, "doctor", env=env, ok=False)
        assert "Canopy-owned tmux configuration" in doctor.stdout
        assert "Agent integrations:" in doctor.stdout
        assert "binding: prefix + T" in doctor.stdout
        assert "monitor-activity" in doctor.stdout
        print("ok - TPM-style loading uses one Canopy entrypoint and doctor reports owned tmux settings")
    finally:
        sp.run(("tmux", "-L", socket, "kill-server"), env=env, capture_output=True)
