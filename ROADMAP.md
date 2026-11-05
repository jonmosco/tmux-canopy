# Roadmap

Remaining work for tmux-canopy. This list does not promise a release date. The
[README](README.md#features) describes what is available today, and the
[changelog](CHANGELOG.md) records what has shipped.

## Agent status reliability

- [ ] Extend lifecycle regression coverage beyond Codex to verify that agent
  exit, restart, and pane reuse cannot leave misleading status behind. Codex has
  real-process tests for these (`tests/codex_panel.py`) and Pi/Oh My Pi cover
  session replacement (`tests/agent_reporting.py`), and Claude Code has them in
  `tests/claude_lifecycle.py` (exit, restart by the same shell, session
  replacement, and pane reuse); Gemini CLI, OpenCode, Cursor Agent, and
  Antigravity still need the same real-process checks. A manual pass for 0.4.0
  found Claude Code and Codex (approval answered with `>`), Antigravity, and Pi
  correct, and fixed OpenCode 2 never reporting from its shared service. Gemini CLI could not sign in, Cursor Agent
  and Oh My Pi had no Canopy integration installed, and Copilot and Grok were
  not installed, so those were not checked.

## Jump to an agent needing input

Global jump (`n`) ships today. Remaining work:

- [ ] Extend multi-client jump tests (`tests/jump_agent.py` covers longest-waiting order, unread fallback, stale targets, agent exits, and linked windows).

## Additional subagent integrations

Antigravity, Cursor Agent, Claude Code, and Codex subagents are reported today.
Remaining work:

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
palette for most of its UI, with a separate `mono` mode, configurable selection
background, tmux-inherited colors (`@tmux-canopy-theme 'ansi'`, with `'fixed'`
as the escape hatch), built-in presets, and per-role overrides. The remaining
work is to make theme sources explicit and consistent across views:

- [ ] Apply the chosen source consistently across Tree, Processes, Buffers,
  Agents, previews, help, and popups. Keep agent state and unread notifications
  distinguishable without relying on color alone. (Tree + fzf chrome +
  Processes/Buffers header accents land with the tmux inherit work; remaining
  surfaces still use fixed ANSI where they paint.)
- [ ] Define precedence for explicit color overrides, theme-source selection,
  and `mono`; update a running sidebar when tmux styling changes without losing
  selection, query, folds, or preview state. (Precedence and open-only sampling
  are done; live restyle without reopen is not.)
- [ ] Test light/dark terminal palettes, tmux themes with partial/default
  colors, 256-color/truecolor terminals, and monochrome output. Document what
  terminal colors can be inherited rather than queried reliably. (Parser and
  private-tmux inherit/fixed/mono coverage added; expand as themes appear.)

## Scope

Planned request controls would add user-initiated responses to agent requests.
Agent launching, task assignment,
automatic approval, inter-agent coordination, worktree provisioning, and a
dedicated orchestration API are outside this initial roadmap.

As work is implemented, remove completed items and document the shipped
behavior in the README and built-in help.
