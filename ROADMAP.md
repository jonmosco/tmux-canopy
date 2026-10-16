# Roadmap

Remaining work for tmux-canopy. This list does not promise a release date. The
[README](README.md#features) describes what is available today.

## Stabilization (done in 0.4.0)

New features were on hold until the existing ones were dependable:

- [x] Find flaky tests by running every suite repeatedly, and fix their causes
  rather than adding retries. Ten rounds of every suite found two: the mouse
  wheel (a real bug, fixed) and a Git test whose window names changed.
- [x] Check each lifecycle adapter, and `>`, against the real agent, including
  exit, restart, and pane reuse. Claude Code and Codex (approval answered with
  `>`), Antigravity, and Pi passed; OpenCode 2 never reported from its shared
  service (fixed). Gemini CLI could not sign in and is unchecked; Cursor Agent
  and Oh My Pi had no Canopy integration installed, and Copilot and Grok were
  not installed.
- [x] Count forks and tmux calls per refresh on a realistic server and compare
  with 0.2.0. On 10 sessions, 76 panes, and 6 working agents, a refresh starts
  14 programs and makes 6 tmux calls in about 140 ms in both versions (16 and 8
  in the Agents view); branch labels add one `git` per repository, with place
  labels or without.
- [x] Run the suite on Linux: CI runs it on Ubuntu 24.04 for every push.
- [x] Review the README, help, and legend against the code: every bound key
  is in help, the README, and the reference, every setting the code reads is
  documented, and the legend describes the current footers.

## Sidebar UX (done, unreleased)

- [x] Agent inspector as a fixed field card (state, trust, directory, optional
  git, place with green `●`), shared Terminal/Agent drawer at 25% height, `i`
  selects mode and `p` only toggles visibility.
- [x] Sticky browse pointer: content-pane focus updates `●` without moving the
  sidebar selection or rewriting the inspector; `Ctrl-o` / return-to-sidebar
  still jumps to the live pane.
- [x] Dim application icons by default; full color for the active content pane
  and for detected agents.
- [x] Opt-in Bash directory-change refresh (`@tmux-canopy-directory-refresh` and
  `scripts/directory-prompt.sh`); no polling. Ctrl-r remains the explicit refresh.
- [x] vim-tmux-navigator: Ctrl-h / Ctrl-l leave a dock toward the adjacent pane
  without changing the navigator's root bindings; Ctrl-h stays Backspace in search.

## Agent status reliability

- [ ] Extend lifecycle regression coverage beyond Codex to verify that agent
  exit, restart, and pane reuse cannot leave misleading status behind. Codex has
  real-process tests for these (`tests/codex_panel.py`) and Pi/Oh My Pi cover
  session replacement (`tests/agent_reporting.py`); Claude Code, Gemini CLI,
  OpenCode, Cursor Agent, and Antigravity still need the same real-process
  checks.

## Jump to an agent needing input

- [x] Implement global jump (`n`) to the next pane reporting needs-input across all
  sessions and windows, with wraparound and tree-order traversal.
- [ ] Test stale targets, agent exits, linked windows, and multiple clients.

## Additional subagent integrations

- [x] Report Antigravity (`agy`) subagents spawned via `invoke_subagent` and
  track their lifecycle (`manage_subagents`, `manage_task`, `Stop`).
- [x] Report Cursor Agent (`agent`) subagents via `subagentStart` / `subagentStop` hooks.
- [ ] Report Gemini CLI subagents if its integration exposes enough lifecycle
  and identity information.
- [ ] Report GitHub Copilot CLI and Grok Build subagents. Copilot's
  `subagentStart` has no agent ID to pair with `subagentStop`; Grok's
  subagents report from their own sessions with `subagentType`.

## Agent request panel and responses (backlog)

The Agent inspector and the dim line beneath a waiting pane already show the
request when a lifecycle adapter reports one (for example Claude Code and Codex
approvals, including Codex's proposed command). Inspecting a request from the
sidebar is done; the remaining work is structured choices and, where safe,
responding without leaving the tree.

- [ ] Show structured response choices when an integration supplies them, and
  make long requests scrollable at narrow sidebar widths.
- [ ] Define an optional integration contract for request identity, agent-session
  identity, target pane, request state, and supported response types. Distinguish
  structured requests from an ordinary terminal-output preview; do not infer
  actionable approval buttons from captured text alone.
- [ ] Add an explicit action to focus the request controls, choose a response or
  enter text, and submit it. Keep ordinary tree navigation separate from submission;
  cancelling returns to the tree with selection, query, and folds intact.
- [ ] Prefer an integration's supported response interface. Investigate targeted
  terminal input only where the integration can verify that the same agent and
  request still own the input; otherwise offer a jump to the original pane.
- [ ] Revalidate the target and pending request before sending. Prevent duplicate
  submissions and handle requests answered elsewhere, agent restarts, pane removal,
  and multiple clients without sending a response to a shell or replacement agent.
- [ ] Show sending, acknowledged, failed, or unknown outcomes. Wait for the agent's
  acknowledgement or lifecycle update before clearing needs-input; do not blindly
  retry a response whose delivery is uncertain.
- [ ] Add supported choice responses before free-text responses. Keep responses
  explicitly user-initiated and preserve the current content window/pane and
  sidebar geometry throughout.
- [ ] Test stale requests, focus and cancellation, literal response text, duplicate
  submissions, concurrent clients, acknowledgement failures, and narrow terminals.

## Send text to a pane

`>` sends a line to the selected pane, and an agent waiting on you shows its
request beneath its pane. Follow-ups:

- [ ] Prefill the prompt from a recent paste buffer, and send multiline text
  with bracketed paste (`paste-buffer -p`) for agents that accept it.
- [ ] For an agent waiting on an approval, offer its choices in a menu instead
  of free text, once an integration reports them (see the request panel above).

## Switch sidebar side without reopening

Left and right placement are supported today. Changing `@tmux-canopy-position`
currently takes effect when the sidebar is reopened.

- [ ] Add a **Switch sidebar side** action and documented keyboard shortcut to
  move the open sidebar between the left and right edges.
- [ ] Keep the same sidebar and fzf processes, preserving width, selection,
  search query, collapsed branches, and preview state.
- [ ] Carry the new side through window/session navigation and update stable
  slots consistently; define how the runtime choice relates to the configured
  default.
- [ ] Test both directions, content layouts, mouse resizing, and client
  ownership. Document the action in the README and built-in help.

## Alerts

Desktop and tmux alerts cover agents and tmux's bell, silence, and activity
alerts today (see the README). Remaining work:

- [ ] **Command finished (tmux 3.8+):** use the existing
  `@tmux_canopy_command` format hook to record when a pane's foreground
  command starts, and alert when the pane returns to its shell after a
  configurable minimum duration, naming the command and how long it ran.
  Older tmux has no equivalent hook; document that it needs 3.8.
- [ ] **Linux delivery:** verify `notify-send` against real notification
  services (GNOME, KDE, dunst, mako), and replace a pane's previous
  notification instead of stacking them (the
  `x-canonical-private-synchronous` hint, where supported).
- [ ] **Desktop alerts over SSH:** an explicit opt-in that sends terminal
  notification sequences (OSC 9, 777, or 99) so the alert appears on the
  machine you type on. It needs tmux's `allow-passthrough`, so the opt-in must
  say so rather than set it silently.
- [ ] **Choose agent events:** allow alerting on needs-input only, without
  finished or interrupted.

## Appearance and theme sources

Canopy already uses the terminal's default foreground/background and ANSI
palette for most of its UI, with a separate `mono` mode and configurable
selection background. The remaining work is to make theme sources explicit and
consistent across views:

- [ ] **tmux:** derive sidebar colors from the active tmux status, pane border,
  and message styles where available. Define clear fallbacks when those styles
  use `default` or omit a color.
- [ ] **Canopy:** allow an independent palette for text, selection, accents,
  notices, tree guides, preview, help, and the scrollbar. Provide documented
  defaults and user overrides without changing tmux or terminal settings.
- [ ] Apply the chosen source consistently across Tree, Processes, Buffers,
  Agents, previews, help, and popups. Keep agent state and unread notifications
  distinguishable without relying on color alone.
- [ ] Define precedence for explicit color overrides, theme-source selection,
  and `mono`; update a running sidebar when tmux styling changes without losing
  selection, query, folds, or preview state.
- [ ] Test light/dark terminal palettes, tmux themes with partial/default
  colors, 256-color/truecolor terminals, and monochrome output. Document what
  terminal colors can be inherited rather than queried reliably.

## Scope

Planned request controls would add user-initiated responses to agent requests.
Agent launching, task assignment,
automatic approval, inter-agent coordination, worktree provisioning, and a
dedicated orchestration API are outside this initial roadmap.

As work is implemented, remove completed items and document the shipped
behavior in the README and built-in help.
