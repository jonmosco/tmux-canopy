# tmux-canopy

A persistent sidebar for tmux that organizes your sessions, windows, and panes into a navigable tree - and optionally monitors AI coding agents across all of them.

**One sidebar follows you everywhere. No daemon. No config server. Just tmux.**

Canopy adds a persistent sidebar to tmux. It shows your sessions, windows, and panes as a tree and follows you as you switch between them - same sidebar, same selection, same collapsed branches.

Optionally, turn on agent awareness to monitor AI coding agents (Claude, Codex, OpenCode, Gemini, Cursor, and more) with live status, animated working indicators, and a one-key jump to any pane waiting for input.

## Preview

[![Animated tmux-canopy demo showing navigation, readable notification badges, search, folding, and buffers](docs/assets/canopy-demo.gif)](docs/assets/canopy-demo.gif)

[View a still image](docs/assets/canopy-demo.png).

## Features

- Sessions → windows → panes tree with application icons and an active-location marker.
- Left or right placement; **left by default**.
- Width-aware directory grouping, optional minimal and compact views, previews, and scrollable popup help.
- Global quick switching, including panes inside collapsed branches.
- Tree filters for the current session, unread notifications, window names, and pane titles.
- Create, rename, move, link, and delete tmux objects with native menus and direct keys.
- Zoom badges (`[Z]`), native pane/window zoom toggle, and automatic sidebar width balance when closing panes.
- Process trees attributed to panes, plus tmux buffer browsing with a system-clipboard yank action.
- AI agent monitoring: Track active agents across sessions with animated status badges, a dedicated Agents view (`4`), summary drawer (`i`), subagent trees, and a one-key jump (`n`) to panes waiting for user input or approval.
- Activity and bell notifications; optional silence monitoring.
- Live mouse resizing and keyboard width presets.
- One sidebar owned by the client that opened it; no daemon or agent service.

## Requirements and support

Tested on **Linux** and **macOS**, with:

- tmux **3.7c**
- fzf **0.74.4**
- Bash **4.4+** (locally tested with 5.3.9)
- Standard command-line utilities, including awk and `ps` (procps or macOS BSD `ps`)
- `less` for the optional enlarged preview

Startup checks tmux capabilities and fzf options before splitting an application pane. Older tmux/fzf versions are not currently part of the tested support matrix. The default Unicode icons are command-specific and do not require a Nerd Font. Set the `nerdfont` icon theme for additional app glyphs after enabling a Nerd Font in your terminal; use `ascii` if Unicode glyphs are missing.

## Install

Install the requirements first. If you use [TPM](https://github.com/tmux-plugins/tpm), add this before its `run '~/.tmux/plugins/tpm/tpm'` line:

```tmux
set -g @plugin 'jonmosco/tmux-canopy'
```

Press **prefix + I** to install, then **prefix + T** to open Canopy. Canopy's old and current `*.tmux` entrypoints coexist for older manual installations; TPM loads both safely.

For a manual installation, clone the project:

```bash
git clone https://github.com/jonmosco/tmux-canopy.git ~/.tmux/plugins/tmux-canopy
```

Add this to your tmux configuration (usually `~/.tmux.conf` or `~/.config/tmux/tmux.conf`):

```tmux
run-shell '~/.tmux/plugins/tmux-canopy/tmux-canopy.tmux'
```

Load it into a running tmux server:

```bash
tmux run-shell "$HOME/.tmux/plugins/tmux-canopy/tmux-canopy.tmux"
```

Press **prefix + T** to open it. With the default prefix, press **Ctrl-b**, release, then **Shift-t**. The same shortcut closes it.

Run `~/.tmux/plugins/tmux-canopy/canopy doctor` to check requirements and see every active tmux binding, option, and hook Canopy installs. Add the repository root to your `PATH` if you prefer the short `canopy` command.

### AI agent monitoring and navigation

Canopy includes built-in tracking for AI coding agents (Claude Code, OpenAI Codex, Google Antigravity `agy`, Cursor Agent, Gemini CLI, OpenCode, Pi, and Oh My Pi). It turns tmux into a unified cockpit for multi-agent workflows:

- **Track all running agents:** The dedicated **Agents view** (`4`) aggregates active agent panes across all windows and sessions.
- **Jump to blockers (`n`):** Press `n` from anywhere in Canopy to jump directly to the next pane waiting for user input, questions, or command approval.
- **Live status & subagents:** Real-time animated status pulses (`WORKING`, `WAITING`, `DONE`) and subagent hierarchy tracking in the summary drawer (`i`).
- **Two tiers of visibility:**
  - **Zero-config process detection:** Automatically identifies running agent processes with zero extra tools or configuration (`[process]`).
  - **Rich lifecycle adapters:** Optional lightweight hooks (`canopy integration install <agent>`) report exact turn states, tool executions, and child subagents without polling (`[state·hook]`).

To enable agent monitoring, add this **before** the Canopy `run-shell` line in your tmux configuration:

```tmux
set -g @tmux-canopy-agents 'on'
```

Reload the tmux configuration, then close and reopen any existing sidebar. You can also toggle agent mode on the fly per client by pressing `A` in the sidebar.

To add reported lifecycle state, install only the adapters you want with `canopy setup` or `canopy integration install codex` (also `claude`, `gemini`, `agy`, `pi`, `omp`, `opencode`, `cursor-agent`). Adapters show `[state·hook]`; Claude Code, Codex, OpenCode, and Cursor Agent adapters can also show subagents. The integration manager and reporters require Python 3. Use `canopy integration status` to inspect adapters or `canopy integration uninstall codex` to remove one. See [Agent integrations](docs/reference.md#agent-lifecycle-adapters).

For Antigravity, install or update Canopy's adapter from the installation directory:

```bash
./canopy integration install agy
./canopy integration status
```

The installer adds a named Canopy entry to `~/.gemini/config/hooks.json` and removes older Canopy `agy` hooks from `~/.gemini/antigravity-cli/settings.json`. Restart `agy` inside tmux, check its `/hooks` view, and press `4` in Canopy to see the Agents view. Antigravity's hooks report active invocations, tool activity, clean turn ends, and interruptions; they do not expose dedicated permission-request or subagent lifecycle events to Canopy.

OpenCode uses a plugin rather than a shell hook. `canopy integration install opencode` writes `~/.config/opencode/plugins/canopy-agent-state.js`. The plugin is ESM, so `~/.config/opencode/package.json` must contain `"type": "module"`. Restart OpenCode inside tmux afterward. The plugin subscribes to session, permission, and question events and observes prompt, tool, and permission hooks. It does not approve a permission or block a tool. A report is kept only when the session's directory matches one OpenCode pane.

### Defaults

Canopy opens on the **left**, follows its client across windows and sessions, and uses stable slots to keep application geometry steady when revisiting windows. It starts at 42 columns. Mouse resizing is live, with no fixed maximum; at least 40 columns are reserved for content.

Place settings **before** the `run-shell` line:

```tmux
set -g @tmux-canopy-position 'left'       # left or right
set -g @tmux-canopy-width '42'
set -g @tmux-canopy-scope 'global'        # global or window
set -g @tmux-canopy-transition 'slot'     # slot or move
set -g @tmux-canopy-resize-mode 'live'    # live, staged, or preset
set -g @tmux-canopy-max-width '0'         # 0 means no fixed cap
set -g @tmux-canopy-min-content-width '40'
set -g @tmux-canopy-density 'normal'    # normal, minimal, compact, or detailed
set -g @tmux-canopy-appearance 'default'  # default (folders + icons) or ascii
set -g @tmux-canopy-animate 'on'          # off: disable the WORKING status animation
set -g @tmux-canopy-zoom-action 'refuse'   # refuse (default) or unzoom
```

Reload your tmux configuration after changing settings. Close and reopen Canopy after changing position or startup appearance options.

## Essential controls

| Key | Action |
|---|---|
| `j` / `k`, arrows | Select an object |
| `Enter` | Focus the selected target |
| `h` / `l` | Collapse / expand |
| `H` / `L` | Collapse / expand all |
| `/`, then `Esc` | Search, then clear the search query |
| `1` / `2` / `3` | Tree / Processes / Buffers |
| `a` | Actions for the selected object |
| `z` | Toggle zoom on the selected pane or window |
| `b` | Break selected pane into its own window |
| `s` / `v` | Create horizontal / vertical split from selected node |
| `t` | Create new window in selected session |
| `S` / `N` | Create session / create named session with prompt |
| `r` | Rename selected session or window |
| `x`, then `x` | Confirm deletion of a pane, window, or session |
| `m` / `c` | Mark move source / cancel move mode |
| `u` / `U` | Clear selected / all notifications |
| `F` / `Ctrl-f` | Tree filters: All / Current session / Unread, plus window name and pane title |
| `Ctrl-g` | Search all sessions, windows and panes, including collapsed branches |
| `Ctrl-o` | Return the selection pointer to the current pane or its visible parent |
| `p` / `P` | Toggle preview / open enlarged terminal preview |
| `[` / `]` | Previous / next width preset |
| `Ctrl-r` | Refresh |
| `?` | Scrollable help popup |
| `g` | Scrollable symbol and color legend |
| `Ctrl-q` | Close the sidebar |

Use your usual tmux pane navigation to return to the sidebar after focusing an application, such as `prefix + Left` or `prefix + Right`.
When you leave the sidebar for a content pane, its selection pointer follows the active pane automatically.

With agent monitoring enabled, `4` opens Agents, `n` jumps to the next pane reporting needs-input, and `i` switches the drawer to an agent summary.

The default Tree view uses one active-pane dot, shorter branch prefixes, and
directory labels that adapt to sidebar width. For the leanest view, set
`@tmux-canopy-density 'minimal'` and press `Ctrl-r` in the sidebar.
The default appearance groups panes by working directory and uses folder and
application icons. Set `@tmux-canopy-appearance 'ascii'` for an ASCII-only view
without glyph-font requirements. Recognized app icons can be changed with
options such as `@tmux-canopy-icon-codex`; use `none` to hide one. See
[Icons](docs/reference.md#icons).

See the [configuration and command reference](docs/reference.md) for all controls, appearance settings, notifications, and architecture.

## Integration with your tmux configuration

Canopy wraps `prefix + n`, `p`, `0`–`9`, and `Tab` for smooth window navigation, `prefix + Space` for sidebar-aware layouts, and border mouse bindings for resizing. Set `@tmux-canopy-smooth-navigation 'off'` to opt out of navigation wrappers. Disabled or renamed bindings restore their previous definitions; later user changes are preserved. Notification monitors are also restored when disabled.

This restoration applies to settings first installed by the current version. When upgrading an older development checkout that already replaced bindings, start a fresh tmux server to establish clean ownership. Existing sessions can continue using the plugin; schedule that restart when convenient.

## Current limitations

- Stable slots are optimized for one active sidebar owner per tmux server. Multiple simultaneous owners can affect each other’s window geometry.
- A directory-only change may need `Ctrl-r`; there is no shell prompt integration or polling loop.
- Activity means terminal output, not an AI agent’s task status. Without an [optional lifecycle adapter](docs/reference.md#agent-lifecycle-adapters), the agent drawer reads the selected pane’s current terminal screen and labels possible requests as unverified. Continuous logs can be noisy.
- Closing the sidebar returns its space but may not restore every previous pane proportion.
- Confirmed deletion has no undo.

Moving an open sidebar between edges and other planned work are described in the [roadmap](ROADMAP.md).

## Development and release checks

Tests additionally require Python 3, ShellCheck, and procps utilities. Optional zsh/fish launch checks run when those shells are installed.

```bash
bash tests/run.sh
```

The same gate runs in GitHub Actions using pinned tmux/fzf versions. Tests use private tmux servers and do not modify your active sessions. See the [release checklist](docs/releasing.md) and [changelog](CHANGELOG.md).

## Contributing

Canopy is in active development. Bug reports, feature requests, and pull requests
are welcome - open an issue at
[github.com/jonmosco/tmux-canopy/issues](https://github.com/jonmosco/tmux-canopy/issues).

## License

[Apache License, Version 2.0](LICENSE).
