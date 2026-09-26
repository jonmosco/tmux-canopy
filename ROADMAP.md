# Roadmap

Planned work for tmux-canopy. Unchecked items are not implemented; this list does
not promise a release date. The [README](README.md#current-features) describes
what is available today.

## Agent awareness

Canopy already helps users find agent terminals, preview their output, inspect
pane processes, and move between projects. Its current activity, bell, and
silence badges report terminal events. They do not establish whether an agent
is working, waiting for input, or finished.

The agent preview is available through `i`. Without an integration, it reads
current pane metadata and visible screen text and labels possible prompts as
unverified. Optional Codex, Claude Code, Gemini CLI, OpenCode, Pi, and Oh My Pi
adapters report supported lifecycle events. The Agents view (`4`) lists panes
containing those detected processes; `[process]` means detection only, while
`·hook` identifies a recent hook report; `·plugin?` marks an OpenCode plugin
report whose pane/session association needs confirmation. Parent counts are process
counts, not task status.

The goal is to help users identify which agent needs attention while continuing
to use their existing tmux sessions, windows, panes, and tools.

### 1. Agent status on panes

- [x] Define pane metadata for agent identity, status, reporting source, and
  freshness.
- [x] Add optional Codex, Claude Code, Gemini CLI, OpenCode, Pi, and Oh My Pi
  lifecycle reporters. Each reports only events its harness actually exposes.
- [x] Display reported **working**, **approval**, **ready**, **turn ended**, and
  **unknown** states beside matching live agent panes, with readable text in
  monochrome mode and a visible source label.
- [ ] Handle agent exit, restart, stale reports, and pane removal without leaving
  misleading status behind.
- [ ] Verify that installations without an integration retain normal sidebar
  behavior and do not acquire a mandatory daemon or polling loop.

Design requirements:

- Keep agent lifecycle state separate from unread terminal notifications.
- Focusing a blocked agent may clear its unread badge, but **needs input** must
  remain until a subsequent lifecycle event changes it.
- Treat unsupported or stale state as unknown. Output, silence, process
  existence, and command icons alone do not establish task completion.
- Report only agents that can be associated with a tmux pane. Do not imply that
  internal agent subtasks are independently visible or controllable.

### 2. Attention summaries

- [ ] Aggregate agent status on window and session rows, including collapsed
  branches, so users can see summaries such as **2 need input**.
- [ ] Give input requests priority over working and finished indicators.
- [ ] Define counting for linked windows so repeated tree occurrences do not
  inflate totals within a session.
- [ ] Preserve row selection, search queries, and collapse state during updates.

### 3. Jump to the next agent needing input

- [ ] Add an action and documented shortcut to focus the next pane reporting
  **needs input** across sessions and windows.
- [ ] Define a predictable traversal order, wraparound behavior, and behavior
  when no agents need input.
- [ ] Use the existing client-aware navigation and width-preserving transitions.
- [ ] Test stale targets, agent exits, linked windows, and multiple clients.

### 4. Agent request panel and responses (backlog)

Explore a preview-like panel that shows what an agent needs and, for supported
integrations, lets the user respond without switching to the agent's window or
pane. The Codex hook supplies a first read-only request summary; response
controls still depend on a verified request and response contract.

- [ ] Expand the read-only Codex request panel showing the agent, session/window/pane,
  request text, relevant context (including a proposed command when supplied),
  and freshness. Available choices and narrow-width scrolling remain future work.
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
- [ ] Stage delivery: request display first, then supported choice responses, then
  free-text responses. Keep responses explicitly user-initiated and preserve the
  current content window/pane and sidebar geometry throughout.
- [ ] Test stale requests, focus and cancellation, literal response text, duplicate
  submissions, concurrent clients, acknowledgement failures, and narrow terminals.

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

Canopy currently uses the terminal's default foreground/background and ANSI
palette for most of its UI, with a separate `mono` mode and configurable
selection background. Add an explicit theme source so users can choose how the
sidebar fits their existing setup:

- [ ] **Terminal:** inherit the terminal's foreground/background and standard
  ANSI colors. Keep contrast readable on both light and dark palettes without
  assuming a specific terminal theme.
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

These features add visibility, navigation, and planned user-initiated responses
to agent requests. Agent launching, task assignment,
automatic approval, inter-agent coordination, worktree provisioning, and a
dedicated orchestration API are outside this initial roadmap.

As work is implemented, check off completed items and document the shipped
behavior in the README and built-in help.
