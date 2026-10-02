# Roadmap

Remaining work for tmux-canopy. This list does not promise a release date. The
[README](README.md#features) describes what is available today.

## Agent status reliability

- [ ] Extend lifecycle regression coverage beyond Codex to verify that agent
  exit, restart, and pane reuse cannot leave misleading status behind. Codex has
  real-process tests for these (`tests/codex_panel.py`) and Pi/Oh My Pi cover
  session replacement (`tests/agent_reporting.py`); Claude Code, Gemini CLI,
  OpenCode, Cursor Agent, and Antigravity still need the same real-process
  checks.

## Claude Code background sessions

A Claude Code session can run in the background and be viewed from a tmux pane
with `claude attach <id>`. Its hooks then run in the background process, which
has no `TMUX_PANE` or `TMUX`, so the reporter cannot tell which pane to update:
the pane shows `[process]` but no lifecycle state or subagents.

- [ ] When a hook report has no pane, find the pane whose process tree runs
  `claude attach` with the report's session ID (the attach argument is a
  prefix of `session_id`), using the default tmux server.
- [ ] Accept that attach client as the report's process identity, since the
  agent process itself is not under the pane.
- [ ] Test with a fake attach client: state and subagents reach the right pane,
  nothing is reported when no client is attached, and an attach client for a
  different session is ignored.

## Jump to an agent needing input

- [ ] Test stale targets, agent exits, linked windows, and multiple clients.

## Additional subagent integrations

- [ ] Report Gemini CLI subagents if its integration exposes enough lifecycle
  and identity information.

## Agent request panel and responses (backlog)

The agent summary already shows a read-only request description when a
lifecycle adapter reports one (for example Claude Code and Codex approvals,
including Codex's proposed command). The remaining work is to make
supported requests easier to inspect and, where safe, respond to them from the
sidebar.

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

## Send prompt to pane (backlog)

Allow sending text or prompts directly into a selected pane from the sidebar
without switching focus away from the active application.

- [ ] Add a **Send prompt to pane** item to the pane action menu and define an
  optional shortcut.
- [ ] Use a native tmux prompt (`command-prompt -p 'Prompt:'`) to accept the input,
  with an option to select or prefill from recent tmux paste buffers.
- [ ] Revalidate target pane existence and alive state (`pane_dead != 1`) before
  sending; safely ignore vanished or dead targets.
- [ ] Deliver input using native `send-keys -l` followed by `Enter` to preserve
  exact literal text, whitespace, and Unicode characters without command
  injection or shell expansion.
- [ ] Keep the invoking client's focus, sidebar geometry, selection, query, and
  preview state completely unchanged throughout the operation.
- [ ] Test prompt delivery with special characters, multiline input, cancelled
  prompts, dead panes, and background panes across multiple windows and sessions.

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

## Appearance and theme sources

Canopy already uses the terminal's default foreground/background and ANSI
palette for most of its UI, with a separate `mono` mode and configurable
selection background. The remaining work is to make theme sources explicit and
consistent across views:

- [ ] Keep the terminal palette usable on both light and dark themes without
  assuming a particular palette. Today a light terminal needs
  `@tmux-canopy-selection-background` set by hand (for example `254`); choose a
  default that reads on both, and test both.
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
