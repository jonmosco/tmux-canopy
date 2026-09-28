# Roadmap

Remaining work for tmux-canopy. This list does not promise a release date. The
[README](README.md#features) describes what is available today.

## Agent status reliability

- [ ] Extend lifecycle regression coverage beyond Codex to verify that agent
  exit, restart, and pane reuse cannot leave misleading status behind.

## Jump to an agent needing input

- [ ] Test stale targets, agent exits, linked windows, and multiple clients.

## Additional subagent integrations

- [ ] Report Gemini CLI and OpenCode subagents if their integrations expose
  enough lifecycle and identity information.

## Agent request panel and responses (backlog)

The agent summary already shows a read-only Codex request description and
proposed command when a hook supplies them. The remaining work is to make
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

## Working-state animation

- [x] Animate the **WORKING** status word with a moving highlight band while an
  agent works, opt-in via `@tmux-canopy-animate`.
- [x] Redraw frames from a cached snapshot (awk only) instead of a full source
  reload, driven by a bounded worker that starts only when a working row is
  drawn and exits when none remain, the sidebar is not visible, or its pane
  closes. Target about 6–7 frames per second.
- [x] Keep the no-daemon rule: no ticker without a visible working agent, and
  static output (and all tests) when the option is off or the theme is `mono`.

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
  assuming a particular palette.
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
