# tmux-canopy

A persistent sidebar for navigating tmux sessions, windows, panes, processes, and buffers.

**One tree. One persistent sidebar. Every tmux session.**

Canopy moves the same sidebar pane as you switch windows and sessions, preserving your selection, search, and collapsed branches. It lives inside tmux and reserves space for your applications.

## Preview

[![Animated tmux-canopy demo showing navigation, readable notification badges, search, folding, and buffers](docs/assets/canopy-demo.gif)](docs/assets/canopy-demo.gif)

[View a still image](docs/assets/canopy-demo.png).

## Features

- Sessions → windows → panes tree with application icons and an active-location marker.
- Left or right placement; **left by default**.
- Width-aware directory grouping, optional minimal and compact views, previews, and scrollable popup help.
- Global quick switching, including panes inside collapsed branches.
- Tree filters for the current session, unread notifications, window names, and pane titles.
- Create, rename, move, link, and delete tmux objects with native menus.
- Process trees attributed to panes, plus tmux buffer browsing.
- Activity and bell notifications; optional silence monitoring.
- Live mouse resizing and keyboard width presets.
- One sidebar owned by the client that opened it; no daemon or agent service.

## Requirements and support

The tested platform is **Linux**, with:

- tmux **3.7c**
- fzf **0.74.4**
- Bash **4.4+** (locally tested with 5.3.9)
- Standard command-line utilities, including awk and procps `ps`
- `less` for the optional enlarged preview

Startup checks tmux capabilities and fzf options before splitting an application pane. Older tmux/fzf versions and macOS are not currently part of the tested support matrix. A Nerd Font is optional; use the `unicode` or `ascii` icon theme if glyphs are missing.

## Install

Install the requirements first, then clone the project:

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
set -g @tmux-canopy-icon-theme 'unicode'  # unicode, ascii, nerdfont, or auto
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
| `F` / `Ctrl-f` | Tree filters: All / Current session / Unread, plus window name and pane title |
| `Ctrl-g` | Search all sessions, windows and panes, including collapsed branches |
| `p` / `P` | Toggle preview / open enlarged preview |
| `[` / `]` | Previous / next width preset |
| `Ctrl-r` | Refresh |
| `?` | Scrollable help popup |
| `Ctrl-q` | Close the sidebar |

Use your usual tmux pane navigation to return to the sidebar after focusing an application, such as `prefix + Left` or `prefix + Right`.

The default Tree view uses one active-pane dot, shorter branch prefixes, and
directory labels that adapt to sidebar width. For the leanest view, set
`@tmux-canopy-density 'minimal'` and press `Ctrl-r` in the sidebar.

See the [configuration and command reference](docs/reference.md) for all controls, appearance settings, notifications, and architecture.

## Integration with your tmux configuration

Canopy wraps `prefix + n`, `p`, `0`–`9`, and `Tab` for smooth window navigation, `prefix + Space` for sidebar-aware layouts, and border mouse bindings for resizing. Set `@tmux-canopy-smooth-navigation 'off'` to opt out of navigation wrappers. Disabled or renamed bindings restore their previous definitions; later user changes are preserved. Notification monitors are also restored when disabled.

This restoration applies to settings first installed by the current version. When upgrading an older development checkout that already replaced bindings, start a fresh tmux server to establish clean ownership. Existing sessions can continue using the plugin; schedule that restart when convenient.

## Current limitations

- Stable slots are optimized for one active sidebar owner per tmux server. Multiple simultaneous owners can affect each other’s window geometry.
- A directory-only change may need `Ctrl-r`; there is no shell prompt integration or polling loop.
- Activity means terminal output, not an AI agent’s task status. Continuous logs can be noisy.
- Closing the sidebar returns its space but may not restore every previous pane proportion.
- Confirmed deletion has no undo.

Agent awareness and moving an open sidebar between edges are described in the [roadmap](ROADMAP.md).

## Development and release checks

Tests additionally require Python 3, ShellCheck, and procps utilities. Optional zsh/fish launch checks run when those shells are installed.

```bash
bash tests/run.sh
```

The same gate runs in GitHub Actions using pinned tmux/fzf versions. Tests use private tmux servers and do not modify your active sessions. See the [release checklist](docs/releasing.md) and [changelog](CHANGELOG.md).

## License

[Apache License, Version 2.0](LICENSE).
