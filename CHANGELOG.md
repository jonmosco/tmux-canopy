# Changelog

## Unreleased

### Changed

- The mouse wheel now scrolls the Help and Legend popups three lines at a time. Clicks do not run commands, and mouse reporting is restored when the popup closes.
- The README demo is now a shorter real-tmux agent workflow with a smaller sidebar, balanced content panes, and smaller text, plus a walkthrough of browsing, search, previews, Agents view, quiet appearance, and popup mode. Both recordings are reproducible from `docs/demo/record.py` using fictional fixtures.

- Clicking a sidebar row while another pane has focus keeps the clicked row selected, as file-tree sidebars do. Previously the sidebar usually jumped back to the active pane's row. Entering the sidebar from the keyboard still selects the active pane's row.
- The mouse wheel scrolls the sidebar's tree without moving the selection; previously every wheel event moved the selection one row, which made trackpad scrolling race through the list.
- The preview drawer starts hidden. Press `p` to open it. `@tmux-canopy-preview auto` still shows it when the sidebar is tall enough.
- Press `A` in the sidebar to turn agent mode on or off for this client. Tree stays available. `@tmux-canopy-agents` is only the default until a client chooses. Integrations stay installed when the mode is off.
- The Agents tab sits beside Tree (`Tree Agents Proc Buff`) instead of after Buffers.
- Lazygit rows drop the window index, window icon, and `·hook` label. Working and needs-input are a `▷` or `!` at the row edge. The full status remains in the drawer.
- Pi and Oh My Pi are no longer labeled `node` when Node is only the runtime. Other Node processes stay `node`.
- Pi's sidebar icon is π, the mark used on [pi.dev](https://pi.dev/). Oh My Pi uses the same π in yellow, matching the orange accent on its [icon](https://github.com/can1357/oh-my-pi/blob/main/assets/icon.svg).
- Nerd Font agent icons use Codicons where those marks exist: Claude, OpenAI/Codex, Cursor, and Gemini's four-point star. OpenCode stays a code glyph because its logo is a pixel wordmark. Antigravity keeps an orbit glyph.
- Refreshes are faster. With Pi or other Node panes open, a refresh no longer re-reads the process table once per Node pane (about 870 ms down to about 60 ms with three such panes), and every refresh makes fewer tmux calls.
- Moving focus renders the tree once instead of twice, and `Ctrl-o` also refreshes the list as it moves the pointer.
- Resizing or splitting ordinary panes no longer starts a shell; Canopy's hooks check for a sidebar inside tmux first. Bursts of pane-command changes in agent mode share one refresh.
- The `WORKING` animation precomputes its frames, starts far fewer processes per frame, loops without a visible jump, and keeps its position across refreshes.
- Subagent lines in the default appearance use the same marks as their pane: `▷` working (animated) and `!` needs input, with the age at the edge. `classic` keeps the status words.
- In the Buffers view, `x` arms deletion and a second `x` within five seconds deletes the buffer, as for panes, windows, and sessions. The actions menu item is now **Delete (arm)**.
- Unnamed windows and panes show a dimmed placeholder name.

### Added

- Hermes Agent (`hermes`) is detected as an agent, including its standard installer, whose launcher runs Hermes as a Python process with no process named `hermes`. It appears in the Agents view, the footer, and the drawer with a `⚕` icon (`@tmux-canopy-icon-hermes` overrides it), as `[process]` until it has a lifecycle adapter.
- Optional `@tmux-canopy-appearance 'quiet'` keeps the directory-grouped tree and its actions but subdues guides, shortens the header to `Tree · All` with a compact agent count, puts the active pane dot by its name, and moves agent/unread attention to the right edge. The Tree footer becomes key hints. `default` is unchanged; ASCII icons and mono styling still work.
- Optional `@tmux-canopy-git-context 'branch'` displays read-only per-pane Git branches in the Tree, quick switcher, and pane preview. It is off by default, makes at most one branch lookup per repository per tree reload, supports linked worktrees and detached HEAD, and never polls, runs `git status`, or changes a repository. Press `Ctrl-r` after a branch or directory-only change.
- Alerts: `set -g @tmux-canopy-alerts 'desktop'`, `'tmux'`, or `'both'` sends a desktop notification or a tmux message when an agent with a lifecycle adapter needs input, finishes its turn, or is interrupted. `@tmux-canopy-alert-events` adds tmux's own `bell`, `silence`, and `activity` alerts (default `agents`). Off by default. No alert is sent while you are looking at that pane, and Canopy changes no tmux option to provide it. On macOS, clicking a `terminal-notifier` alert brings your terminal forward on that pane, and `osascript` takes over when `terminal-notifier` is not allowed to notify. Each alert names the agent or command, the project, the session and window, and the pane's topic, with the request and its command, how long the turn took, or what the tmux alert means. `@tmux-canopy-alert-sound` adds an optional sound, and `@tmux-canopy-alert-detail 'full'` adds the start of Claude Code's or Codex's last reply, or a pane's last line of output. `canopy alerts test` sends a sample and reports which notifier delivered it, and `canopy doctor` lists the notifiers found.
- Adaptive floating popup mode via `@tmux-canopy-mode 'popup'` or `'auto'`. In popup mode, Canopy displays as an ephemeral floating modal using `tmux display-popup` instead of splitting windows. In `'auto'` mode, Canopy automatically uses a popup when terminal width is below `@tmux-canopy-popup-threshold` (default `100`), or when the window is too narrow for content and sidebar. State (active view, folds, footer, search query) is cached per client and restored across invocations without any permanent background processes. Opening or reopening the popup automatically highlights the active pane and window. Supports closing via `q`, `Esc`, re-toggle, or focus selection (`Enter`).
- GitHub Copilot CLI (`copilot`) and Grok Build (`grok`) are detected as agents and have optional lifecycle adapters: `canopy integration install copilot grok` writes a hooks file Canopy owns into `~/.copilot/hooks/` and `~/.grok/hooks/`. Both report working, needs-input (permission prompts), turn ended, interrupted, and session end. `@tmux-canopy-icon-copilot` and `@tmux-canopy-icon-grok` override their icons.
- Agents run inside a sandbox wrapper (`bwrap`, `firejail`, `sandbox-exec`, `nono`, `fence`, `landrun`, `nsjail`, `minijail0`, `unshare`) are detected; the wrapper is treated like a shell between the pane and the agent.
- Crush (Charm's `crush`) is detected as an agent: it appears in the Agents view, the footer, and the drawer with its own icon (`@tmux-canopy-icon-crush` overrides it). It has no lifecycle adapter yet, because Crush's released hooks cannot report a finished turn or a request for input.
- With agent mode on, a footer at the bottom of the Tree view counts every agent on the server (`Agents ◆1 ▷2`) and reminds you that `n` jumps to the one waiting. Without agent mode, the footer counts your sessions, windows, and panes instead (`◈ 3 sessions  ▣ 8 windows  ▹ 14 panes`), showing visible/total while a tree filter hides some. Press `f` to hide or show it, or set `@tmux-canopy-footer 'off'`. It lives only in the sidebar; your status line is untouched.
- OpenCode's adapter loads in V2 as well as V1. It subscribes to the public event stream and observes prompt, tool, and permission hooks without approving a request or blocking a tool. Reinstall with `canopy integration install opencode` and restart OpenCode.
- Pi and Oh My Pi adapters report tool execution, extension UI prompts as needs-input, and aborted or errored settles as interrupted. Reinstall with `canopy integration install pi` (and `omp`) so the extension file is replaced.
- Cursor Agent (`cursor-agent`) process detection and optional lifecycle adapter for the `agent` CLI via `~/.cursor/hooks.json`.
- `@tmux-canopy-animate` (on by default) adds a moving highlight on visible `WORKING` status words from a cached snapshot (no permanent daemon; inert when off or `mono`).
- `@tmux-canopy-appearance`: `default` groups panes by working directory with folder and application icons, `ascii` is the same layout without glyph-font requirements, and `classic` keeps the older tree for existing setups.
- Tree reload on `after-split-window` so newly created panes appear without waiting for another focus change.
- TPM installation path and a `canopy` command for tmux diagnostics and optional agent integration setup, status, and removal.
- Doctor output lists Canopy-owned tmux bindings, options, hooks, and optional agent integration states.
- Claude Code subagents appear as read-only child lines of their pane with type, status (working, needs input, done), and age; a waiting subagent counts toward attention roll-ups and `n`, and its approval request is attributed to it. Requires reinstalling the Claude integration for the new `SubagentStart`/`SubagentStop` hooks.
- Antigravity (`agy`) subagents spawned via `invoke_subagent` appear as read-only child lines of their pane with their role and status, resolving conversation IDs from on-disk session metadata. Terminating subagents via `manage_subagents` removes them immediately, and fully idle stops transition active subagents to completed before they are pruned on the next prompt.
- Doctor runs a reporter self-test and lists agent processes in tmux panes with the age of their last report, explaining missing reports.
- Detect OpenCode, Gemini CLI, Pi, and Oh My Pi in the Agents view and read-only drawer; distinguish process detection, unverified screen hints, and optional lifecycle reports.
- Optional Claude Code, Gemini CLI, OpenCode, Pi, and Oh My Pi lifecycle adapters with example configurations, pane/process identity checks, and source-aware row labels.
- Reported Codex lifecycle labels on Tree and Agents pane rows, with foreground-command or process-ancestry, pane-PID, and freshness checks; stale reports show unknown.
- A scrollable symbol and color legend on `g`, with responsive layout and explanations for tree markers, pane labels, notifications, and filters.
- Codex and Claude Code read-only preview prototype, toggled with `i` in the existing drawer; it summarizes selected pane metadata and labels possible requests inferred from visible terminal text.
- Optional Codex CLI lifecycle hook reports turn state and approval requests to the drawer, with pane/session checks and stale-report handling.
- The active-location dot stays visible on the nearest collapsed window or session and returns to the pane row when expanded.
- Leaving or returning focus to the sidebar, or pressing `Ctrl-o`, moves the pointer to the current pane or its visible parent without activating a different pane.
- Agents view (`4`) groups panes with detected Codex or Claude processes beneath their sessions and windows, with agent counts on parent rows.


- Tree filters for All, Current session, and Unread, with optional window-name and pane-title filters, native controls, and matching-pane navigation.
- Ctrl-g global quick switcher searches sessions, windows, and panes inside collapsed branches without changing tree state.
- Optional compact rows for single-pane windows via `@tmux-canopy-compact-single-panes`.
- Persistent client-owned sidebar with tree, process, and buffer views.
- Left/right placement, stable slots, live mouse resizing, and width presets.
- Responsive help, shared-directory grouping, colored application icons, and selection highlighting.
- Apache 2.0 license, public installation instructions, and automated release checks.

### Changed

- Sidebar reloads from `cleanup refresh` skip clients mid window-transition so slot creation does not flash a stale tree.
- Antigravity now uses its documented `PreInvocation`, `PostToolUse`, and `Stop` hooks in a named `~/.gemini/config/hooks.json` entry. Reinstalling the integration removes the older unsupported hook entries from Antigravity CLI settings. Its reporter never grants tool permission; verified permission and subagent states are unavailable until Antigravity exposes those events.
- Agent awareness is opt-in through `@tmux-canopy-agents on`; the default sidebar focuses on tmux navigation, processes, and buffers. Agent tabs, controls, labels, scans, and pane-command monitoring are hidden until enabled.

- Show a tmux session glyph instead of the inline dash; retain Unicode, ASCII, and custom-icon fallbacks.

- Bind Codex reports to the live process and refresh expiring reports; accelerate the Agents view process scan on Linux.
- Stabilize multiline sidebar selection coverage with fzf’s local state API.

- Simplified Tree rows with one active marker, emphasized parent names, shorter prefixes, compact counts, adaptive directory labels, and grouping for adjacent panes sharing a directory.
- Added a `minimal` density preset that combines single-pane windows and keeps multi-pane windows to one line per pane.
- Show ordinary pane counts only on collapsed windows, aligned to the right edge; expanded shared-directory groups have no count.


- Notifications use one amber badge beside each affected pane, with counts on collapsed branches and full types in previews.

### Fixed

- On macOS and other systems without `/proc`, Pi and Oh My Pi, which run under `node`, failed Canopy's process check, so their lifecycle reports never showed as verified status, and the Agents view listed them as `node`. A hosted agent is now checked and listed by its kind.
- With Codex 0.159 and later, whose shared `app-server` daemon runs every hook with the `TMUX_PANE` of the pane that started it, a Codex session started in another pane took over that first pane's status. Canopy now routes a daemon-run hook by its session: to the pane already following it, or to the only Codex pane in the session's directory. When two Codex panes share a directory, it reports nothing rather than guess.
- After you approved a Claude Code permission prompt, the pane could stay marked needs input (`!`) until the turn ended. Claude reports each prompt twice, and its second report has no tool name, so it replaced the request with one that the approved tool's completion could not clear.
- Claude Code showed **turn ended** while a `run_in_background` shell or background subagent was still running, because `Stop` fires when the turn ends. Canopy now reads the event's `background_tasks` and keeps the agent **working** until the work finishes.
- A stale agent report (no update for 15 minutes) animated like a working agent; its dim mark now stays still, so only agents reporting work right now move.
- Loading or reloading the plugin took 1.2–1.5 seconds and started about 250 tmux processes; it now reads tmux state once and writes in a few batched calls (about 0.2 seconds, under 10 processes).
- An agent started by an editor or another foreground app, such as an OpenCode or Claude plugin inside Neovim, no longer makes that pane count as an agent pane; agents run from a shell or a runtime like `node` are still found. Hook reports are unaffected.
- Rows with wide characters (CJK, fullwidth forms, emoji) no longer push their right-edge marks, such as fold counts, unread dots, and the current-pane marker, past the sidebar edge.
- Opening the sidebar no longer deletes parked slots in other windows. The split hook was treating the not-yet-tagged dock as "no sidebars" and discarding those slots, so a later visit could not restore the original split ratio.
- A finished background subagent no longer disappears the moment its result is delivered: the turn that delivers it no longer drops its **DONE** line, which now stays until the next prompt at least 30 seconds later.
- A subagent's permission request can no longer be cleared by an unrelated tool completion with the same tool name from the main thread or another subagent.
- Claude Code, Gemini CLI, OpenCode, Pi, and Oh My Pi lifecycle reports were silently dropped after the Codex reporter's helpers changed; `canopy doctor` now exercises every reporter's real report path so such drift fails loudly.
- Native Claude Code installs (`claude.exe`) are recognized as Claude agents on macOS.
- On macOS, hook-reported agent states were ignored on days 1–9 of each month, because `ps` pads single-digit days in process start times and the identity check compared them literally.
- Subagents now appear in the default appearance; they were only drawn in `classic`. Compact density shows a count such as `+2` on the pane row instead.
- Text that merely contains `wrk` or `WORKING`, such as a `~/wrk` directory or a window title, no longer starts or animates the working indicator.
- The animation now requires `python3` rather than checking for `perl`, which it no longer uses.
- Mouse clicks, scrolling, and keys in the sidebar were sometimes ignored while an agent was working: each frame of the `WORKING` animation reloads the list, and fzf drops input that arrives during a reload (about one click in five). While the sidebar has focus, the animation now runs slower and holds still for about two seconds after any input.
- A global `detach-on-destroy on` is honored when the last session ends, so the dock is no longer briefly parked in an unrelated session (which resized its applications). The synchronize-panes toggle likewise reads an inherited global value.
- Right-aligned counts and pane continuation lines align correctly on macOS, whose awk measures UTF-8 text in bytes.

- TPM loads the legacy compatibility entrypoint without applying Canopy twice.
- Sidebar navigation preserves split proportions when a hidden window resizes to the active terminal, preventing content panes from collapsing to one column.

- Slot navigation uses native empty panes, fixing new-window follow failures on macOS caused by `sleep infinity`.

- Buffer names containing separators now retain their exact identity through preview, paste, and deletion.
- Configuration reloads restore obsolete bindings and disabled notification monitors, preserving later user overrides.
- Leaving search restores the full object list.
