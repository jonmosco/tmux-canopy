# Notes for coding agents

Guidance for AI coding agents (Claude Code, Codex, Cursor, and others) working in this repository. Human contributors may find it useful too; see [CONTRIBUTING.md](CONTRIBUTING.md) for the general guide.

## What Canopy is

A tmux sidebar: a tree of sessions, windows, and panes, plus optional monitoring of AI coding agents. It is Bash, awk, and fzf driven by tmux hooks. Python 3 is used only by the optional agent adapters and the test suite. There is no daemon.

## Where things are

| Path | What it holds |
|---|---|
| `tmux-canopy.tmux` | Plugin entry point: options, key bindings, and tmux hooks |
| `scripts/` | One script per action or data source (`sidebar`, `tree-source`, `sidebar-action`, `agent-refresh`, ...) |
| `scripts/*-lib.sh`, `scripts/lib.sh` | Shared shell helpers |
| `lib/tree-render.awk` | Renders the tree from one tmux snapshot |
| `lib/agent-hook.py`, `lib/codex-hook.py` | Agent lifecycle adapters (hook reporters) |
| `lib/agent-process.sh`, `lib/agent-process.py` | Agent process detection |
| `tests/` | Python and Bash suites, each on its own private tmux server |
| `docs/reference.md` | Full configuration and architecture reference |

## Running the tests

```bash
bash tests/run.sh            # everything: syntax, ShellCheck, all suites
python3 tests/subagents.py   # a single suite
```

Requirements: tmux, fzf, Bash 4.4+, Python 3, and ShellCheck. On macOS, agent fixtures also need Homebrew coreutils (`gsleep`). Run the full suite before calling a change done, and add or update a test for any behavior change.

## Working with tmux safely

- The tests use private servers (`tmux -L <name>`) and never touch the user's sessions. Do the same for any manual check or demo, and kill the private server afterwards.
- Do not change, reload, or kill the user's own tmux server or edit their tmux configuration unless they ask you to.
- For UI changes, check the result in a real attached client on a private server (the tests do this with a pty). Some problems, such as focus races, only show up that way.

## Design principles

- **No daemon.** Work happens in response to tmux hooks or keys. A background worker must be short-lived and exit when it has nothing to do.
- **Enhance, never take over.** Canopy does not change the user's status line, their own options, or their key bindings. Hooks and bindings use Canopy's own indexes and restore what they replaced.
- **Respect the hot paths.** Refreshes, focus changes, and resize hooks run often:
  - Batch tmux queries into one `tmux` call (`\;`-separated) rather than one call per value.
  - Avoid `$(...)` in loops; helpers such as `canopy_client_key` and `canopy_pane_agent` return results in variables (`CANOPY_KEY`, `CANOPY_REPLY`) for this reason.
  - Filter hooks inside tmux with `if-shell -F` so unrelated events start no shell.
- **Bash 3.2 must still load `scripts/launch-lib.sh`**, so it can report the "Bash 4.4 required" error on stock macOS. Keep Bash 4-only syntax out of its top level.
- **Portable across macOS and Linux:** BSD and GNU tools, `ps` output differences (for example, `lstart` pads single-digit days), and no reliance on `/proc` outside the Linux paths.

## Style

- Match the surrounding code: its naming, comment density, and idioms. Comments explain why, not what.
- Keep scripts ShellCheck-clean.
- When behavior changes, update what users read: `README.md`, `docs/reference.md`, the in-app help and legend (`scripts/help`), and the `## Unreleased` section of `CHANGELOG.md`.

## Commits and pull requests

- Commit messages: a short, lowercase summary line; add a body when the reason is not obvious. Do not add a `Co-Authored-By` trailer.
- Leave opening issues and pull requests to the person you are working with.
