# tmux-canopy

[![Release](https://img.shields.io/github/v/release/jonmosco/tmux-canopy?sort=semver)](https://github.com/jonmosco/tmux-canopy/releases/latest) [![Test](https://github.com/jonmosco/tmux-canopy/actions/workflows/test.yml/badge.svg)](https://github.com/jonmosco/tmux-canopy/actions/workflows/test.yml)

**A tmux workspace tree and AI-agent monitor in one sidebar, with no daemon.**

Keep tmux. Keep your sessions. Keep your workflow. Canopy gives you the view from above: every session, window, pane, and agent at a glance.

Canopy keeps your sessions, windows, and panes in a persistent tree that follows you as you switch windows and sessions, with the same selection and the same folded branches. Turn on agent mode and the same tree shows what every Claude Code, Codex, OpenCode, Gemini, Cursor, Antigravity, Pi, GitHub Copilot CLI, Grok Build, Crush, and Hermes session is doing: which agents are working, which subagents they started, and which are waiting for you. Press `n` to jump straight to the next one that needs input.

## Preview

[![Canopy demo: build a tmux workspace, open the sidebar, toggle agent monitoring, view help, browse the tree, and jump to a waiting agent](docs/assets/canopy-demo.gif?v=10)](docs/assets/canopy-demo.gif?v=10)

<a id="requirements-and-support"></a>
<a id="install"></a>

## Quick start

**Requirements:** Linux or macOS with **tmux** (tested with 3.7c), **fzf** (tested with 0.74.4), **Bash 4.4+** (tested with 5.3.9), standard `awk` and `ps`, and `less` for the optional enlarged preview. Default Unicode icons need no Nerd Font.

1. With [TPM](https://github.com/tmux-plugins/tpm), add this before its `run '~/.tmux/plugins/tpm/tpm'` line:

   ```tmux
   set -g @plugin 'jonmosco/tmux-canopy'
   set -g @tmux-canopy-agents 'on'   # optional: monitor AI coding agents
   ```

2. Press **prefix + I** to install.
3. Press **prefix + T** to open or close the sidebar (with the default prefix: **Ctrl-b**, then **Shift-t**). Press `?` inside it for context-sensitive actions and the full key reference.

For rich agent lifecycle state (working, needs-input, subagents), run `~/.tmux/plugins/tmux-canopy/canopy setup` and pick your agents (see [AI agent monitoring](#ai-agent-monitoring)). Run `~/.tmux/plugins/tmux-canopy/canopy doctor` to verify requirements and inspect active bindings, options, and hooks.

<details>
<summary><strong>Manual installation (without TPM)</strong></summary>

Clone the repository:

```bash
git clone https://github.com/jonmosco/tmux-canopy.git ~/.tmux/plugins/tmux-canopy
```

Add this to `~/.tmux.conf` (or `~/.config/tmux/tmux.conf`):

```tmux
run-shell '~/.tmux/plugins/tmux-canopy/tmux-canopy.tmux'
```

Load it into a running tmux server:

```bash
tmux run-shell "$HOME/.tmux/plugins/tmux-canopy/tmux-canopy.tmux"
```

Add `~/.tmux/plugins/tmux-canopy` to your `PATH` if you want the short `canopy` CLI command.
</details>

<a id="features"></a>

## The sidebar at a glance

A sidebar with agent mode on, one agent waiting for approval, and a folded session:

```text
Tree · All                         ◆1 ▷1   ① ②
▾ ◈ acme ─────────────────────────────     ③
   ▾ ▣ 0:server             api ⎇ main     ④ ⑤
   ●  ✳  1:claude                    !     ⑥ ⑦ ⑧
            Explore                  ▷     ⑨
            Plan                     !
             2:zsh                         ⑩
      ✳ 1:ui · claude      web ⎇ ui  ▷     ⑪
▾ ◈ notes ────────────────────────────
      ▣ 0:today · zsh                ●     ⑫
▸ ◈ scratch [2w] ─────────────────────     ⑬
───────────────────────────────────
 ◆ Claude Code waiting  n go  > reply      ⑭
```

| | What it shows | Keys |
|---|---|---|
| ① | **View and filter.** Open view (`Tree`, `Agents`, `Processes`, `Buffers`) and filter (`All`, `Session`, or `Unread`; `+W` / `+T` when window-name or pane-title filters are active). | `1` Tree, `4` Agents, `2` Processes, `3` Buffers; `F` or `Ctrl-f` filters |
| ② | **Agent summary.** Counts by state: `◆` needs input, `▷` working, `✓` ended, `○` process-only (or `◆1/3` when narrow). Processes and Buffers views show row counts here. | `n` jump to the agent waiting |
| ③ | **Session heading**, followed by a dim rule. Your current session has a tmux-green glyph and cyan name. | `h` / `l` fold and unfold, `H` / `L` all |
| ④ | **Window**, in tmux's order; each window appears once. | `Enter` focus, `r` rename, `t` new window, `a` actions |
| ⑤ | **Directory and branch**, dim at the right of the highest row whose panes all share them (session, window, or pane). | `canopy-branch`, `canopy-directory` at `prefix :` |
| ⑥ | **Your current pane** (green `●`). The highlighted row is what you are browsing; switching content panes does not move your browse cursor. | `Ctrl-o` jump back to your pane |
| ⑦ | **Pane:** application icon, pane index, and running command. | `Enter` focus, `s` / `v` split, `z` zoom, `x` `x` delete |
| ⑧ | **Agent state** at the right edge: `!` needs input, `▷` working, `✓` turn ended. A waiting agent shows its question or command on a dim line beneath. | `n` next waiting agent, `i` Agent inspector, `>` send reply |
| ⑨ | **Subagents** of the pane above, each with its own state while running. | |
| ⑩ | **An idle shell**, dimmed so running programs stand out. | |
| ⑪ | **A single-pane window**, shown on one row. | |
| ⑫ | **Unread output** (dim `●`); a bell or silence alert is amber. | `u` clear, `U` clear all |
| ⑬ | **Folded session**, with the number of windows inside. | `l` unfold |
| ⑭ | **Action footer:** view-specific hints (or an urgent waiting-agent / pending-action prompt). | `f` hide or show |

Press `g` in the sidebar for the full symbol and color legend, and `?` for the interactive help popup.

## Essential controls

### Navigate & filter

| Key | Action |
|---|---|
| `j` / `k`, `Ctrl-j` / `Ctrl-k`, arrows | Move selection down / up |
| `Enter` | Focus the selected target (and close the popup in popup mode) |
| `h` / `l` | Collapse / expand selected branch |
| `H` / `L` | Collapse / expand all branches |
| `Ctrl-h` / `Ctrl-l` | Focus the pane to the left / right from a dock (`Ctrl-h` stays Backspace while searching) |
| `Ctrl-o` | Return selection highlight to your active pane (or its visible parent) |
| `/`, then `Esc` | Filter rows by search query, then clear |
| `Ctrl-g` | Global quick switcher across all sessions, windows, and panes (including folded branches) |
| `1` / `2` / `3` / `4` | Switch view: Tree / Processes / Buffers / Agents |
| `F` / `Ctrl-f` | Cycle tree filters: All / Current session / Unread, plus window name and pane title |
| Mouse | Click selects, double-click focuses, wheel scrolls (`set -g mouse on`) |

### Sessions, windows & panes

| Key | Action |
|---|---|
| `a` | Open action menu for the selected object |
| `s` / `v` | Split selected pane horizontally / vertically |
| `t` | Create new window in the selected session |
| `S` / `N` | Create session named for the git repo (or `session-N`) / prompt for session name |
| `r` | Rename selected session or window |
| `z` | Toggle zoom (`[Z]`) on the selected pane or window |
| `b` | Break selected pane into its own window |
| `m` / `c` | Mark source for move or link / cancel move mode |
| `x`, then `x` | Confirm deletion of a pane, window, session, or paste buffer |
| `u` / `U` | Clear unread notifications on selected target / all targets |

### AI agents

| Key | Action |
|---|---|
| `A` | Toggle agent mode on or off for this client |
| `4` | Open the dedicated Agents view |
| `n` | Jump to the next agent needing input (or unread completed agent) across all sessions |
| `>` | Send a line of text to the selected pane without leaving your current pane |
| `i` | Switch the bottom drawer between **Terminal preview** and **Agent inspector** |

### Sidebar & help

| Key | Action |
|---|---|
| `p` / `P` | Show or hide the preview drawer / open enlarged terminal preview in `less` |
| `[` / `]` / `w` | Narrower / wider / cycle width presets |
| `f` | Show or hide the action footer |
| `?` | Open scrollable Help (starts with actions for the current view and selection) |
| `g` | Open scrollable symbol and color Legend |
| `Ctrl-r` | Refresh tree and preview |
| `Ctrl-q` (`q` / `Esc` in popup) | Close Canopy |

## AI agent monitoring

Turn agent monitoring on globally with `set -g @tmux-canopy-agents 'on'` in `.tmux.conf`, or toggle it per client with `A` in the sidebar.

- **Status & subagents in the tree:** Working agents show an animated `▷`, waiting agents show `!` with the pending command or question on a dim line underneath, and folded windows/sessions roll counts up as `◆` and `▷`. Running subagents appear indented beneath their parent pane.
- **Jump (`n`) and inline reply (`>`):** Press `n` to jump to the next agent waiting for input (or the next unread finished agent if none are waiting) across all sessions. Press `>` to send a prompt or confirmation to the selected pane without switching focus; the preview refreshes immediately.
- **Agent inspector (`i`):** Press `i` to switch the bottom drawer (default height **25%**, toggled with `p`) between **Terminal preview** and **Agent inspector**. The inspector renders a structured card showing agent state, verification trust, working directory, optional Git repo/branch with an on-demand worktree dirty summary (`N changed (+A −D)`), location (`session:window` with a green `●` for your active pane), and any active permission request or question. See [Preview and Agent inspector](docs/reference.md#preview) for details.

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

**Process detection vs. lifecycle adapters:** Process detection works out of the box (showing `[process]` in the Agents view). Lifecycle adapters are optional, observational hooks/plugins (requiring Python 3) that report exact state (`working`, `needs-input`, `turn-ended`) without ever approving or blocking tools. Install them interactively with:

```bash
~/.tmux/plugins/tmux-canopy/canopy setup
```

Or manage individual agents with `canopy integration install <agent>` (`claude`, `codex`, `opencode`, `gemini`, `cursor-agent`, `agy`, `pi`, `omp`, `copilot`, `grok`) and `canopy integration status`. Restart running agents inside tmux after installing an adapter. See [Agent lifecycle adapters](docs/reference.md#agent-lifecycle-adapters).

## Configuration

Place settings in `~/.tmux.conf` **before** the plugin’s `run-shell` or TPM line:

```tmux
set -g @tmux-canopy-position 'left'          # left or right
set -g @tmux-canopy-width '42'               # sidebar width in columns
set -g @tmux-canopy-mode 'sidebar'           # sidebar, popup, or auto
set -g @tmux-canopy-scope 'global'           # global or window
set -g @tmux-canopy-appearance 'quiet'       # quiet, folders, or ascii
set -g @tmux-canopy-density 'normal'         # normal, minimal, compact, detailed
set -g @tmux-canopy-labels 'tmux'            # tmux or places (preview)
set -g @tmux-canopy-git-context 'off'        # off or branch
set -g @tmux-canopy-directory-refresh 'off'  # on + source scripts/directory-prompt.sh
set -g @tmux-canopy-footer 'on'              # on or off
set -g @tmux-canopy-preview 'off'            # on or off
set -g @tmux-canopy-preview-height '25%'     # drawer height
```

See the [full configuration reference](docs/reference.md#configuration) for every option.

### Display mode (`sidebar`, `popup`, or `auto`)

Canopy docks as a 42-column left sidebar by default. Use `popup` for a floating `tmux display-popup` that never alters pane geometry, or `auto` to dock on wide windows and switch to a popup below a width threshold:

```tmux
set -g @tmux-canopy-mode 'auto'            # sidebar, popup, or auto
set -g @tmux-canopy-popup-threshold '100'  # auto switches below this width
set -g @tmux-canopy-popup-width '85%'      # percentage or columns
set -g @tmux-canopy-popup-height '80%'     # percentage or lines
```

See [Display modes](docs/reference.md#display-modes).

### Appearance, themes, and Git context

- **Layout styles (`@tmux-canopy-appearance`):**
  - `quiet` (default): follows tmux's session → window → pane order, collapses single-pane windows into one row, dims idle shells, and places directory/branch details on the right.
  - `folders`: groups panes by working directory with boxed view titles and tree guides.
  - `ascii`: `quiet` layout using plain ASCII symbols instead of Unicode glyphs (or set `@tmux-canopy-icons 'nerdfont'` if your terminal uses a Nerd Font).
- **Color themes (`@tmux-canopy-theme`):** `ansi` (default) inherits accent, border, and selection colors from your tmux theme; `fixed` uses Canopy's classic palette; `mono` disables color. See [Appearance](docs/reference.md#appearance) and [Icons](docs/reference.md#icons).
- **Git branch context (`@tmux-canopy-git-context 'branch'`):** Shows `⎇ branch` (or `detached@<commit>`) in the tree and quick switcher, and adds an on-demand worktree dirty summary (`N changed (+A −D)`) to the Agent inspector (`i`). Toggle branch or directory details live from the tmux command prompt (`prefix :`) with `canopy-branch` and `canopy-directory`. Canopy reads Git metadata without holding index locks (`--no-optional-locks`) and never modifies repository state.

### Alerts

Canopy can notify you when an agent needs input, finishes, or is interrupted—or when a pane rings the bell or goes silent—even when the sidebar is closed. Alerts are off by default and skipped while you are looking at that pane:

```tmux
set -g @tmux-canopy-alerts 'both'         # off, desktop, tmux, or both
set -g @tmux-canopy-alert-events 'agents' # agents, bell, silence, activity, or all
set -g @tmux-canopy-alert-sound 'default' # off, default, or a sound name
set -g @tmux-canopy-alert-detail 'brief'  # brief or full (includes last reply/line)
```

```text
Claude Code needs input · shop-api
work:2 · Fix the flaky login test
Run the test suite: make test
```

- **`desktop`** uses [terminal-notifier](https://github.com/julienXX/terminal-notifier) or `osascript` on macOS, and `notify-send` on Linux. On macOS, install `terminal-notifier` (`brew install terminal-notifier`) so clicking a notification focuses your terminal and switches straight to that pane.
- **`tmux`** shows a 5-second status message on attached clients (works over SSH).
- Run `canopy alerts test` to send a test notification and verify delivery. See [Alerts](docs/reference.md#alerts).

## How it works & limitations

- **No daemon.** Canopy is Bash, awk, and fzf driven by tmux hooks. Between events, only short-lived bounded helpers run.
- **One snapshot per refresh.** A single tmux call collects every session, window, pane, and client; `awk` renders the tree and `fzf` reloads in place in tens of milliseconds.
- **Event-driven & verified.** Hooks for ordinary panes are gated inside tmux with `if-shell -F` so they start no shell at all. Agent hook reports are verified against the live pane process ID and start time, so a restarted agent never inherits stale state.
- **Clean tmux integration.** Canopy wraps `prefix + n`, `p`, `0`–`9`, `Tab`, and `Space` for sidebar-aware navigation and layouts (disable with `@tmux-canopy-smooth-navigation 'off'`), and restores previous bindings and options when turned off.
- **Limitations:**
  - Only one client can own a docked sidebar per tmux server; other clients can use `@tmux-canopy-mode 'popup'`.
  - A `cd` inside a shell without another tmux event needs `Ctrl-r` to update the directory label unless you enable the opt-in prompt notifier (`@tmux-canopy-directory-refresh 'on'`).
  - Desktop alerts run on the tmux host; over SSH, use `@tmux-canopy-alerts 'tmux'`.
  - Confirmed deletions (`x` then `x`) have no undo.

See [Architecture](docs/reference.md#architecture) and the [roadmap](ROADMAP.md) for more details.

## Development, contributing, and license

Run the full test suite (syntax checks, ShellCheck, and isolated integration suites on private tmux servers):

```bash
bash tests/run.sh
```

Bug reports, feature requests, and pull requests are welcome at [github.com/jonmosco/tmux-canopy/issues](https://github.com/jonmosco/tmux-canopy/issues). See [CONTRIBUTING.md](CONTRIBUTING.md), [AGENTS.md](AGENTS.md), [docs/releasing.md](docs/releasing.md), and [CHANGELOG.md](CHANGELOG.md).

Licensed under the [Apache License, Version 2.0](LICENSE).
