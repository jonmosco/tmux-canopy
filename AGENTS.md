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
- **Enhance, never take over.** Canopy does not change what the user's status line shows. Where a feature needs a tmux option set, such as alert monitoring for sidebar notifications, save the user's value, keep the visible result the same, and restore it when the feature is turned off (`canopy_owned_option` in `scripts/config-lib.sh` does this). Hooks and bindings use Canopy's own indexes and restore what they replaced.
- **Light on the user's system.** Start as few processes as possible and call external tools only when Bash, awk, or tmux itself cannot do the job. See [Keep processes and tools to a minimum](#keep-processes-and-tools-to-a-minimum).
- **Bash 3.2 must still load `scripts/launch-lib.sh`**, so it can report the "Bash 4.4 required" error on stock macOS. Keep Bash 4-only syntax out of its top level.
- **Portable across macOS and Linux:** BSD and GNU tools, `ps` output differences (for example, `lstart` pads single-digit days), and no reliance on `/proc` outside the Linux paths.

## Keep processes and tools to a minimum

Canopy runs on every refresh, focus change, and resize, on the user's own machine, so every process it starts is paid for over and over. Treat a new fork or a new tool as a cost that needs a reason.

- **Prefer Bash builtins and awk** to external commands: parameter expansion and `[[ ]]` instead of `sed`, `cut`, `basename`, or `grep` on a variable; `read` and `mapfile` instead of `cat` or `head`; `printf -v now '%(%s)T' -1` or `$EPOCHREALTIME` instead of `date`.
- **No `$(...)` in loops or per-row code.** Each one forks a subshell, and a subshell also throws away anything the function cached. Return results in variables instead, as `canopy_client_key` (`CANOPY_KEY`) and `canopy_pane_agent` (`CANOPY_REPLY`) do.
- **One tmux call per batch.** Chain commands with `\;`, and read several values with one `display-message` format, rather than one `show-option` per value. Let `tree-render.awk` do aggregation instead of looping over tmux in the shell. During plugin load there may be no session yet, where `display-message` fails: use `canopy_load_state` and `canopy_queue` in `scripts/config-lib.sh`, which also keep each batch under tmux's command-size limit.
- **Decide inside tmux when you can.** Gate hooks with `if-shell -F` and tmux formats so events that do not concern Canopy start no shell at all, and debounce bursts with the existing claim pattern (`scripts/notify`, `scripts/agent-refresh`).
- **No new runtime dependencies.** The sidebar needs only tmux, fzf, Bash, awk, and standard system tools such as `ps`. Python 3 is optional and limited to agent adapters, the animation, and the tests; check for an optional tool with `command -v` and degrade gracefully without it.
- **No polling.** React to events; a background worker must be bounded and exit when it has nothing left to do.
- **Measure when it matters.** Time a path with `$EPOCHREALTIME` on a private tmux server with realistic panes, and count forks or tmux calls before and after; the tests' tmux wrappers show how to count calls.

## Style

- Match the surrounding code: its naming, comment density, and idioms. Comments explain why, not what.
- Keep scripts ShellCheck-clean.
- When behavior changes, update what users read: `README.md`, `docs/reference.md`, the in-app help and legend (`scripts/help`), and the `## Unreleased` section of `CHANGELOG.md`.

## Commits and pull requests

- Commit messages: a short, lowercase summary line; add a body when the reason is not obvious. Do not add a `Co-Authored-By` trailer.
- Leave opening issues and pull requests to the person you are working with.
