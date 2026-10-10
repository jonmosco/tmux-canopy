# tmux-canopy

[![Release](https://img.shields.io/github/v/release/jonmosco/tmux-canopy?sort=semver)](https://github.com/jonmosco/tmux-canopy/releases/latest) [![Test](https://github.com/jonmosco/tmux-canopy/actions/workflows/test.yml/badge.svg)](https://github.com/jonmosco/tmux-canopy/actions/workflows/test.yml)

**A tmux workspace tree and AI-agent monitor in one sidebar, with no daemon.**

Keep tmux. Keep your sessions. Keep your workflow. Canopy gives you the view from above: every session, window, pane, and agent at a glance.

Canopy keeps your sessions, windows, and panes in a persistent tree that follows you as you switch windows and sessions, with the same selection and the same folded branches. Turn on agent mode and the same tree shows what every Claude Code, Codex, OpenCode, Gemini, Cursor, Antigravity, Pi, GitHub Copilot CLI, Grok Build, Crush, and Hermes session is doing: which agents are working, which subagents they started, and which are waiting for you. Press `n` to jump straight to the next one that needs input.

## Preview

[![Canopy in tmux: the sidebar shows three projects, two subagents appear, another project's agent requests approval, and n jumps to it](docs/assets/canopy-demo.gif?v=4)](docs/assets/canopy-demo.gif?v=4)

**See every project. Spot the blocker. Jump to it with `n`.** This 19-second preview was recorded in a real tmux client with fictional projects and scripted agent events. [Watch the longer walkthrough](docs/assets/canopy-walkthrough.gif?v=4) for browsing, search, previews, Agents view, alerts, and floating popup mode. [View a still image](docs/assets/canopy-demo.png?v=4).

## Quick start

1. Install [tmux](https://github.com/tmux/tmux), [fzf](https://github.com/junegunn/fzf), and Bash 4.4+ (see [Requirements](#requirements-and-support)). With [TPM](https://github.com/tmux-plugins/tpm), add this before its `run '~/.tmux/plugins/tpm/tpm'` line:

   ```tmux
   set -g @plugin 'jonmosco/tmux-canopy'
   set -g @tmux-canopy-agents 'on'   # optional: monitor AI coding agents
   ```

2. Press **prefix + I** to install.
3. Press **prefix + T** to open the sidebar (with the default prefix: **Ctrl-b**, then **Shift-t**). Press `?` inside it for every key.

For agent status beyond process detection, run `~/.tmux/plugins/tmux-canopy/canopy setup` and pick your agents (see [AI agent monitoring](#ai-agent-monitoring)). [Manual installation](#install) needs no plugin manager.

## Features

- Sessions → windows → panes in tmux's own order, each window once, with numbered windows and panes, application icons, and an active-location marker. Directories and Git branches show as details; idle shells are dimmed so what is running stands out.
- Left or right placement; **left by default**.
- Floating **popup modal** mode or adaptive **auto** switching on smaller displays (`@tmux-canopy-mode`).
- Optional directory-grouped layout (`folders`), minimal and compact views, previews, and scrollable popup help.
- Optional Git branch labels for panes and directory groups, without polling or changing repository state.
- Global quick switching, including panes inside collapsed branches.
- Tree filters for the current session, unread notifications, window names, and pane titles.
- Create, rename, move, link, and delete tmux objects with native menus and direct keys.
- Zoom badges (`[Z]`), native pane/window zoom toggle, and automatic sidebar width balance when closing panes.
- Process trees attributed to panes, plus tmux buffer browsing with a system-clipboard yank action.
- AI agent monitoring: Track active agents across sessions with animated status badges, a dedicated Agents view (`4`), summary drawer (`i`), subagent trees, and a one-key jump (`n`) to panes waiting for user input or approval.
- Optional alerts: a desktop notification or tmux message when an agent needs input, finishes, or is interrupted, or when a pane rings the bell or goes quiet, skipped while you're watching that pane. On macOS, clicking one jumps to the agent's pane. No daemon; off by default.
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

Press **prefix + I** to install, then **prefix + T** to open Canopy.

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

### AI agent monitoring

With agent mode on, Canopy finds agents running in any pane of any session and shows their state in the tree:

- **Agents view (`4`):** only the sessions, windows, and panes that contain an agent, with a summary such as `◆1 ▷2` in the header.
- **Status on every agent pane:** working (an animated `▷`) and needs input (`!`). Folded windows and sessions roll these up as `◆` and `▷` counts.
- **Subagents:** listed under their parent pane while they run, each with its own status.
- **Summary footer:** the bottom of the Tree view counts every agent on the server, such as `Agents ◆1 ▷2`, so you can see who needs you without leaving your place in the tree.
- **Jump to blockers (`n`):** the next pane waiting for an approval, question, or input, across all sessions.
- **Summary drawer (`i`):** the selected agent's state, its age, and the pending request when the agent reports one.
- **Alerts (optional):** a desktop notification or tmux message when an agent needs input, finishes, or is interrupted, skipped while you're looking at that pane. Off by default; see [Alerts](#alerts).

Turn it on with `set -g @tmux-canopy-agents 'on'` **before** the Canopy line in your tmux configuration, then reload and reopen the sidebar. Press `A` in the sidebar to switch it on or off for just your client.

| Agent | Found by process | Lifecycle adapter | Needs input | Subagents |
|---|---|---|---|---|
| Claude Code | ✅ | ✅ hooks | ✅ | ✅ |
| Codex | ✅ | ✅ hooks | ✅ | ✅ |
| OpenCode | ✅ | ✅ plugin | ✅ permissions and questions | ✅ |
| Gemini CLI | ✅ | ✅ hooks | ✅ tool permissions | – |
| Cursor Agent (`agent`) | ✅ | ✅ hooks, partial | – no permission event | ✅ |
| Antigravity (`agy`) | ✅ | ✅ hooks | – no permission event | ✅ |
| Pi and Oh My Pi | ✅ | ✅ extension | ✅ extension prompts | – |
| GitHub Copilot CLI (`copilot`) | ✅ | ✅ hooks | ✅ permission and question prompts | – |
| Grok Build (`grok`) | ✅ | ✅ hooks | ✅ permission prompts | – |
| Crush | ✅ | – not yet; Crush exposes only a pre-tool hook | – | – |
| Hermes Agent (`hermes`) | ✅ | – not yet | – | – |

Process detection needs no setup: a running agent shows as `[process]` in the Agents view. An adapter adds its exact state (working, needs input, turn ended, and so on). Adapters are optional and observational: they never approve a request or block a tool. Install only the ones you want with `canopy setup`, or `canopy integration install <agent>` using `claude`, `codex`, `opencode`, `gemini`, `cursor-agent`, `agy`, `pi`, `omp`, `copilot`, or `grok`, then restart that agent inside tmux. `canopy integration status` lists what is installed. Adapters need Python 3. Agent-specific notes, including OpenCode's plugin and Antigravity's hook file, are in [Agent lifecycle adapters](docs/reference.md#agent-lifecycle-adapters).

### Alerts

Canopy can tell you when an agent needs input, finishes, or is interrupted, and when a pane rings the bell or goes quiet, even with the sidebar closed. Alerts are off until you turn them on, and Canopy changes no tmux option to provide them:

```tmux
set -g @tmux-canopy-alerts 'both'         # off, desktop, tmux, or both
set -g @tmux-canopy-alert-events 'agents' # optional: agents, bell, silence, activity, or all
set -g @tmux-canopy-alert-sound 'default' # optional: off, default, or a sound name
set -g @tmux-canopy-alert-detail 'brief'  # optional: full adds the agent's last reply
```

Each alert names the agent, the project, the session and window, and what the agent was doing:

```text
Claude Code needs input · shop-api
work:2 · Fix the flaky login test
Run the test suite: make test
```

A finished turn says how long it took (`Turn ended after 4m`). Set `alert-detail` to `full` to see the start of Claude Code's or Codex's last reply instead; it is off by default because notifications can show on a locked screen.

`alert-events` chooses what alerts. `agents` is the default. `bell` covers the many tools that ring the terminal bell when they finish, including Crush, which has no adapter yet. `silence` tells you when a pane stops printing, such as a build that has stalled or finished, and needs `silence` in `@tmux-canopy-notifications` (or tmux's own `monitor-silence`). `activity` alerts on any new output, which is noisy for most panes. A bell alert names the command and, with `alert-detail` set to `full`, shows the pane's last line of output:

```text
Bell from make · shop-api
work:3 build
make: *** [test] Error 2
```

- **`desktop`** sends a notification through [terminal-notifier](https://github.com/julienXX/terminal-notifier) or `osascript` on macOS, and `notify-send` on Linux.
- **`tmux`** shows a five-second message on every attached tmux client, which also works over SSH.
- No alert is sent while you're looking at that pane. With `set -g focus-events on`, an agent in a visible pane still alerts while you're in another application.
- Agent alerts come from lifecycle adapters, so agents shown only as `[process]` don't send them. A bell from the agent can stand in.

On macOS, install `terminal-notifier` (`brew install terminal-notifier`): clicking its notification brings your terminal forward on that pane. Without it, Canopy uses `osascript`, whose notifications appear as Script Editor and can't be clicked through. macOS asks each one for permission the first time. If `terminal-notifier` doesn't appear under System Settings → Notifications, open it once with `open "$(brew --prefix terminal-notifier)"/terminal-notifier.app` and allow it.

Run `canopy alerts test` to send a sample. It reports which notifier delivered it, or which one macOS refused. See [Alerts](docs/reference.md#alerts) for the details.

### Using as a popup

Canopy can run either as a docked sidebar split pane (the default) or inside a floating modal popup using `tmux display-popup`—ideal for smaller laptop screens, compact windows, or keeping your existing pane splits and layouts undisturbed.

#### Always open as a popup

To make **prefix + T** open Canopy in a floating popup:

```tmux
set -g @tmux-canopy-mode 'popup'
```

#### Adaptive auto mode for small screens

If you prefer the docked sidebar on large monitors but want Canopy to automatically switch to a popup when your terminal window is narrow (e.g., on a laptop screen or half-screen window):

```tmux
set -g @tmux-canopy-mode 'auto'
set -g @tmux-canopy-popup-threshold '100'  # column threshold (default: 100)
```

In `auto` mode:
- When the window width meets or exceeds the threshold (100 columns by default), Canopy docks as a sidebar.
- When the window width is below the threshold, or when the window is too narrow to fit both the sidebar and your content, Canopy automatically opens as a popup modal instead of refusing to open.

#### Customizing popup dimensions

You can adjust the size of the popup modal using percentages or column and line counts:

```tmux
set -g @tmux-canopy-popup-width '85%'   # default: 85%
set -g @tmux-canopy-popup-height '80%'  # default: 80%
```

#### How the popup works

- **Toggle:** Press **prefix + T** to open or close the popup.
- **Active highlight:** When opened, the selection bar automatically highlights your currently active window and pane.
- **Focus and switch:** Press `Enter` on any pane or window to switch to it and close the popup.
- **Dismiss:** Press `q`, `Esc`, or re-press **prefix + T** to close the popup without switching focus.
- **Preserved state:** Tree folds, active views (`1` Tree, `4` Agents, `2` Proc, `3` Buff), and search queries are remembered across popup sessions.
- **No daemon:** The popup is ephemeral; when closed, no background process or daemon remains.

### Defaults

Canopy opens on the **left**, follows its client across windows and sessions, and uses stable slots to keep application geometry steady when revisiting windows. It starts at 42 columns. Mouse resizing is live, with no fixed maximum; at least 40 columns are reserved for content.

Place settings **before** the `run-shell` line:

```tmux
set -g @tmux-canopy-mode 'sidebar'        # sidebar, popup, or auto (popup on narrow screens)
set -g @tmux-canopy-popup-threshold '100' # column width threshold for auto popup
set -g @tmux-canopy-popup-width '85%'     # popup width (% or columns)
set -g @tmux-canopy-popup-height '80%'    # popup height (% or lines)
set -g @tmux-canopy-position 'left'       # left or right
set -g @tmux-canopy-width '42'
set -g @tmux-canopy-scope 'global'        # global or window
set -g @tmux-canopy-transition 'slot'     # slot or move
set -g @tmux-canopy-resize-mode 'live'    # live, staged, or preset
set -g @tmux-canopy-max-width '0'         # 0 means no fixed cap
set -g @tmux-canopy-min-content-width '40'
set -g @tmux-canopy-density 'normal'    # normal, minimal, compact, or detailed
set -g @tmux-canopy-appearance 'quiet'    # quiet (default), folders, or ascii
set -g @tmux-canopy-animate 'on'          # off: disable the WORKING status animation
set -g @tmux-canopy-zoom-action 'refuse'   # refuse (default) or unzoom
set -g @tmux-canopy-alerts 'off'     # desktop, tmux, or both: alert when an agent needs you
set -g @tmux-canopy-alert-events 'agents' # add bell, silence, or activity for tmux's own alerts
set -g @tmux-canopy-alert-sound 'off' # or a sound name such as default or Glass
set -g @tmux-canopy-alert-detail 'brief' # full: include the agent's last reply
```

In `popup` mode (or `auto` mode when the window width is below `popup-threshold`), Canopy opens as a floating overlay via `tmux display-popup` without altering your window splits or pane geometry. Tree folds, active view, and filters are preserved across popup opens. Press `q` or `Esc` to close.

Reload your tmux configuration after changing settings. Close and reopen Canopy after changing position or startup appearance options.

## The sidebar at a glance

A sidebar with agent mode on, one agent waiting for approval, and a folded session:

```text
Tree · All                         ◆1 ▷1   ① ②
▾ ◈ acme                                   ③
   ▾ ▣ 0:server             api ⎇ main     ④ ⑤
   ●  ✳  1:claude                    !     ⑥ ⑦ ⑧
            Explore                  ▷     ⑨
            Plan                     !
             2:zsh                         ⑩
      ✳ 1:ui · claude      web ⎇ ui  ▷     ⑪

▾ ◈ notes
      ▣ 0:today · zsh                ●     ⑫

▸ ◈ scratch [2w]                           ⑬
───────────────────────────────────
 1 Tree   4 Agents   n Next                ⑭
```

| | What it shows | Keys |
|---|---|---|
| ① | **View and filter.** The open view (`Tree`, `Agents`, `Proc`, `Buff`) and the tree filter: `All`, `Session` (only the current session), or `Unread`. `+W` / `+T` means a window-name or pane-title filter is also on. | `1` Tree, `4` Agents, `2` Processes, `3` Buffers; `F` or `Ctrl-f` filters |
| ② | **Agent summary:** how many agents are in each state: `◆` needs input, `▷` working, `✓` ended, `○` found by process only. A narrow sidebar shows the most urgent state and the total instead, such as `◆1/3`. | `n` jump to the agent waiting |
| ③ | **Session**, a bold heading. Sessions are separated by a blank line. | `h` / `l` fold and unfold, `H` / `L` all |
| ④ | **Window**, in tmux's order; each window appears once. | `Enter` focus, `r` rename, `t` new window, `a` actions |
| ⑤ | **Directory and branch**, dim at the right of the highest row whose panes all share them: the session, a window, or a pane. | `canopy-branch`, `canopy-directory` at `prefix :` |
| ⑥ | **Your current pane** (green `●`). The highlighted row is what you are browsing; it can differ. | `Ctrl-o` jump back to your pane |
| ⑦ | **Pane:** application icon, pane index, and the command running in it. | `Enter` focus, `s` / `v` split, `z` zoom, `x` `x` delete |
| ⑧ | **Agent state** at the right edge: `!` needs input, `▷` working, `✓` turn ended. | `n` next agent that needs input, `i` agent summary |
| ⑨ | **Subagents** of the pane above, with their own state. They disappear when they finish. | |
| ⑩ | **An idle shell**, dimmed so running programs stand out. | |
| ⑪ | **A window with one pane**, on one row. The command follows `·` when the window has another name. | |
| ⑫ | **Unread output** (dim `●`); a bell or silence alert is amber. | `u` clear, `U` clear all |
| ⑬ | **Folded session**, with the number of windows inside. | `l` unfold |
| ⑭ | **Key hints.** | `f` hide or show |

Prefer panes grouped by directory, with tab headers and tree guides? Set `@tmux-canopy-appearance 'folders'`.

Press `g` in the sidebar for every symbol and color, and `?` for every key.

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
| `x`, then `x` | Confirm deletion of a pane, window, session, or paste buffer |
| `m` / `c` | Mark move source / cancel move mode |
| `u` / `U` | Clear selected / all notifications |
| `F` / `Ctrl-f` | Tree filters: All / Current session / Unread, plus window name and pane title |
| `Ctrl-g` | Search all sessions, windows and panes, including collapsed branches |
| `Ctrl-o` | Return the selection pointer to the current pane or its visible parent |
| `p` / `P` | Toggle preview / open enlarged terminal preview |
| `f` | Show / hide the footer |
| `[` / `]` | Previous / next width preset |
| `Ctrl-r` | Refresh |
| `?` | Scrollable help popup (wheel or `j`/`k` to scroll) |
| `g` | Scrollable symbol and color legend (wheel also works) |
| Mouse | In the tree, click selects, double-click focuses, and the wheel scrolls; in Help/Legend, the wheel scrolls (needs `set -g mouse on`) |
| `Ctrl-q` | Close the sidebar |
| `q` / `Esc` | Close the popup (in popup mode) |

Use your usual tmux pane navigation to return to the sidebar after focusing an application, such as `prefix + Left` or `prefix + Right`. In popup mode, pressing `Enter` focuses the target and automatically closes the popup.
When you leave the sidebar for a content pane, its selection pointer follows the active pane automatically.

With agent monitoring enabled, `4` opens Agents, `n` jumps to the next pane reporting needs-input, and `i` switches the drawer to an agent summary.

## Git branch context

Git branch labels are off by default. To show the branch of each pane's working directory in the Tree and quick switcher, set this in your tmux configuration:

```tmux
set -g @tmux-canopy-git-context 'branch'
```

To switch branch labels while tmux runs, type `canopy-branch` at the tmux command prompt (`prefix :`), or run `tmux canopy-branch` in a shell. It toggles the labels and refreshes every open sidebar. In the `quiet` appearance, the directory details beside them toggle the same way with `canopy-directory`, or with `set -g @tmux-canopy-directory 'off'`. These commands toggle because tmux cannot pass an argument through a command alias; for an explicit state, use `canopy details branch on` (or `off`, and `directory` for the directory) or the settings above.

Press `Ctrl-r` in the sidebar after changing a setting by hand or switching branches. Directory groups display `⎇ feature/name` (ASCII: `[git:feature/name]`); compact layouts show the branch beside the pane when space permits. The pane preview shows the full name even if a narrow tree omits it. A detached HEAD appears as `detached@<commit>`. This requires Git; if it is unavailable, no label is shown. Canopy reads Git metadata only on reload, once per distinct repository, and never runs `git status`, watches files, checks out branches, or creates worktrees. A `cd` without another tmux event may also require `Ctrl-r`.

## Customizing the look

The default appearance, `quiet`, follows tmux's own structure: sessions, windows, and panes in tmux's order, each window once, with directories and Git branches as dim details on the right. Sessions read as bold headings, a window holding one pane takes one row, and shells idling at their prompt are dimmed so what is running stands out. A compact `Tree · All` header replaces the view tabs, the active pane dot sits by its name, agent and unread marks sit at the right edge, and the footer shows key hints (`f` hides it). Set `@tmux-canopy-appearance 'folders'` to group panes by working directory with folder rows, view tabs, and tree guides instead, `ascii` for `quiet` without glyph-font requirements, or `@tmux-canopy-density 'minimal'` for the leanest rows. Reload the plugin after changing appearance, then reopen the sidebar. Application icons can be changed or hidden per app with options such as `@tmux-canopy-icon-codex` (`none` hides one); see [Icons](docs/reference.md#icons).

See the [configuration and command reference](docs/reference.md) for every control, appearance setting, notification option, and the architecture.

## How it works

- **No daemon.** Canopy is Bash, awk, and fzf, driven by tmux hooks. Between events, only bounded helpers run: the animation while an agent is visibly working, a sleeping timer per agent report that marks it stale, and one short-lived script per alert.
- **One snapshot per refresh.** A single tmux call collects every session, window, pane, and client. awk renders the tree, and fzf reloads in place, keeping your selection, search, and folded branches. A refresh typically takes tens of milliseconds.
- **Event-driven updates.** Focus changes, splits, renames, activity alerts, and agent reports trigger a short debounced reload. Hooks for ordinary panes are filtered inside tmux, so they start no shell at all.
- **Verified agent state.** A hook report counts only while its process ID and start time still match a live process in that pane, so a restarted or replaced agent never inherits old status. A report with no update for 15 minutes is shown as stale.
- **Owned by one client.** Each sidebar belongs to the client that opened it and follows that client across windows and sessions.

See [Architecture](docs/reference.md#architecture) for the details.

## Integration with your tmux configuration

Canopy wraps `prefix + n`, `p`, `0`–`9`, and `Tab` for smooth window navigation, `prefix + Space` for sidebar-aware layouts, and border mouse bindings for resizing. Set `@tmux-canopy-smooth-navigation 'off'` to opt out of navigation wrappers. Disabled or renamed bindings restore their previous definitions; later user changes are preserved. Notification monitors are also restored when disabled. Alerts add only Canopy's own hooks and options; they never turn on tmux monitoring or change `focus-events`.

## Current limitations

- Stable slots are optimized for one active sidebar owner per tmux server. Multiple simultaneous owners can affect each other’s window geometry.
- A directory-only change may need `Ctrl-r`; there is no shell prompt integration or polling loop.
- Activity means terminal output, not an AI agent’s task status. Without an [optional lifecycle adapter](docs/reference.md#agent-lifecycle-adapters), the agent drawer reads the selected pane’s current terminal screen and labels possible requests as unverified. Continuous logs can be noisy.
- Desktop alerts appear on the machine running tmux, so over SSH only the `tmux` alert mode reaches you. Only `terminal-notifier` alerts on macOS can be clicked through to the pane.
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
See [CONTRIBUTING.md](CONTRIBUTING.md) for how to report bugs and run the tests, and
[AGENTS.md](AGENTS.md) for notes aimed at AI coding agents.

## License

[Apache License, Version 2.0](LICENSE).
