# Changelog

## Unreleased

### Changed

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

- Crush (Charm's `crush`) is detected as an agent: it appears in the Agents view, the footer, and the drawer with its own icon (`@tmux-canopy-icon-crush` overrides it). It has no lifecycle adapter yet, because Crush's released hooks cannot report a finished turn or a request for input.
- With agent mode on, a footer at the bottom of the Tree view counts every agent on the server (`Agents ◆1 ▷2`) and reminds you that `n` jumps to the one waiting. Without agent mode, the footer counts your sessions, windows, and panes instead (`◈ 3 sessions  ▣ 8 windows  ▹ 14 panes`), showing visible/total while a tree filter hides some. Press `f` to hide or show it, or set `@tmux-canopy-footer 'off'`. It lives only in the sidebar; your status line is untouched.
- OpenCode's adapter loads in V2 as well as V1. It subscribes to the public event stream and observes prompt, tool, and permission hooks without approving a request or blocking a tool. Reinstall with `canopy integration install opencode` and restart OpenCode.
- Pi and Oh My Pi adapters report tool execution, extension UI prompts as needs-input, and aborted or errored settles as interrupted. Reinstall with `canopy integration install pi` (and `omp`) so the extension file is replaced.
- Cursor Agent (`cursor-agent`) process detection and optional lifecycle adapter for the `agent` CLI via `~/.cursor/hooks.json`.
- Opt-in `@tmux-canopy-animate` moving highlight on visible `WORKING` status words from a cached snapshot (no permanent daemon; inert when off or `mono`).
- `@tmux-canopy-appearance`: `default` groups panes by working directory with folder and application icons, `ascii` is the same layout without glyph-font requirements, and `classic` keeps the older tree for existing setups.
- Tree reload on `after-split-window` so newly created panes appear without waiting for another focus change.
- TPM installation path and a `canopy` command for tmux diagnostics and optional agent integration setup, status, and removal.
- Doctor output lists Canopy-owned tmux bindings, options, hooks, and optional agent integration states.
- Claude Code subagents appear as read-only child lines of their pane with type, status (working, needs input, done), and age; a waiting subagent counts toward attention roll-ups and `n`, and its approval request is attributed to it. Requires reinstalling the Claude integration for the new `SubagentStart`/`SubagentStop` hooks.
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

- Opening the sidebar no longer deletes parked slots in other windows. The split hook was treating the not-yet-tagged dock as "no sidebars" and discarding those slots, so a later visit could not restore the original split ratio.
- A finished background subagent no longer disappears the moment its result is delivered: the turn that delivers it no longer drops its **DONE** line, which now stays until the next prompt at least 30 seconds later.
- A subagent's permission request can no longer be cleared by an unrelated tool completion with the same tool name from the main thread or another subagent.
- Claude Code, Gemini CLI, OpenCode, Pi, and Oh My Pi lifecycle reports were silently dropped after the Codex reporter's helpers changed; `canopy doctor` now exercises every reporter's real report path so such drift fails loudly.
- Native Claude Code installs (`claude.exe`) are recognized as Claude agents on macOS.
- On macOS, hook-reported agent states were ignored on days 1–9 of each month, because `ps` pads single-digit days in process start times and the identity check compared them literally.
- Subagents now appear in the default appearance; they were only drawn in `classic`. Compact density shows a count such as `+2` on the pane row instead.
- Text that merely contains `wrk` or `WORKING`, such as a `~/wrk` directory or a window title, no longer starts or animates the working indicator.
- The animation now requires `python3` rather than checking for `perl`, which it no longer uses.
- A global `detach-on-destroy on` is honored when the last session ends, so the dock is no longer briefly parked in an unrelated session (which resized its applications). The synchronize-panes toggle likewise reads an inherited global value.
- Right-aligned counts and pane continuation lines align correctly on macOS, whose awk measures UTF-8 text in bytes.

- TPM loads the legacy compatibility entrypoint without applying Canopy twice.
- Sidebar navigation preserves split proportions when a hidden window resizes to the active terminal, preventing content panes from collapsing to one column.

- Slot navigation uses native empty panes, fixing new-window follow failures on macOS caused by `sleep infinity`.

- Buffer names containing separators now retain their exact identity through preview, paste, and deletion.
- Configuration reloads restore obsolete bindings and disabled notification monitors, preserving later user overrides.
- Leaving search restores the full object list.
