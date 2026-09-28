# Changelog

## Unreleased

### Added

- Opt-in `@tmux-canopy-animate` moving highlight on visible `WORKING` status words from a cached snapshot (no permanent daemon; inert when off or `mono`).
- `@tmux-canopy-appearance` with `classic` (default) and `lazygit` presets for sidebar chrome, structural glyphs, and tree guides.
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

- A finished background subagent no longer disappears the moment its result is delivered: the turn that delivers it no longer drops its **DONE** line, which now stays until the next prompt at least 30 seconds later.
- A subagent's permission request can no longer be cleared by an unrelated tool completion with the same tool name from the main thread or another subagent.
- Claude Code, Gemini CLI, OpenCode, Pi, and Oh My Pi lifecycle reports were silently dropped after the Codex reporter's helpers changed; `canopy doctor` now exercises every reporter's real report path so such drift fails loudly.
- Native Claude Code installs (`claude.exe`) are recognized as Claude agents on macOS.
- A global `detach-on-destroy on` is honored when the last session ends, so the dock is no longer briefly parked in an unrelated session (which resized its applications). The synchronize-panes toggle likewise reads an inherited global value.
- Right-aligned counts and pane continuation lines align correctly on macOS, whose awk measures UTF-8 text in bytes.

- TPM loads the legacy compatibility entrypoint without applying Canopy twice.
- Sidebar navigation preserves split proportions when a hidden window resizes to the active terminal, preventing content panes from collapsing to one column.

- Slot navigation uses native empty panes, fixing new-window follow failures on macOS caused by `sleep infinity`.

- Buffer names containing separators now retain their exact identity through preview, paste, and deletion.
- Configuration reloads restore obsolete bindings and disabled notification monitors, preserving later user overrides.
- Leaving search restores the full object list.
