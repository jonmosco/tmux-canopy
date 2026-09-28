# Configuration and command reference

See the [README](../README.md) for installation, defaults, and supported platforms.

## Current features

- Sessions → windows → panes hierarchy
- Real, fixed-width, full-height pane on the left (default) or right edge
- One active pane marker and emphasized parent names, independent of the sidebar selection
- Vim-style collapse and expand controls
- Normal and fuzzy-filter modes
- Session/window metadata and live pane previews
- Context-aware creation of sessions, windows, and pane splits
- Stateful two-stage movement with source and destination visible in one tree
- Move windows across sessions; move panes left/right/above/below or into a new window
- New objects inherit the selected pane's working directory
- Switching without closing the sidebar
- Configurable window-local or global-follow scope
- In global mode, moves the same sidebar pane across windows and sessions
- Dynamic open and close behavior from the same binding
- Sidebar panes are excluded from the hierarchy and pane counts
- Client ownership prevents one client's window changes from pulling another client's sidebar
- Cached sidebar ownership avoids scanning every pane during normal navigation
- Optional stable-slot transitions preserve content-pane dimensions across window switches
- Atomic sidebar-aware next, previous, last, and numeric window selection reduces intermediate redraws
- Per-client transition guards prevent fallback hooks from moving the sidebar back to a stale source window
- Cross-session hooks resolve the owning client's live pane and reject stale sidebar/slot targets
- Provider-neutral notification badges sourced only from live content panes
- Native activity, bell, and optional silence providers
- Event-driven, debounced refresh with session/window/pane aggregation
- Read state clears when the affected window is focused, with selected/all manual clearing
- Native session/window rename and confirmed pane/window/session deletion
- Context-sensitive native action menus for sessions, windows, and panes
- Window reorder, cross-session link/unlink, layouts, pane rotation, and guarded synchronized input
- Pane zoom, swap, break-to-window, dead-pane respawn, and object information popups
- Switchable Tree, pane-attributed Processes, and tmux Buffers views; optional detected Agents view
- ANSI semantic colors, compact tree guides, width-aware paths, dynamic mode tabs, and adaptive preview
- Responsive fixed or percentage widths with minimum sidebar/content constraints
- Staged one-shot mouse resizing and compact/default/wide width presets
- Geometry-stable window switches with debounced, owner-only active-location refreshes
- Zoom guards with optional unzoom-and-restore behavior
- Hook-driven orphan cache, target, and stable-slot cleanup
- No daemon, background API, database, required agent hooks, or compiled binary

## Requirements

- tmux with the required popup/menu, literal command prompts, full-height split, environment, `run-shell -C`, and numeric-format capabilities (tested with 3.7c; checked before opening)
- Bash 4.4 or newer
- fzf with NUL/multiline input, stable IDs, whole-item highlighting and the required actions (tested with 0.74.4; the actual UI options are checked before opening)
- A procps-compatible `ps` for the Processes view
- `less` for the optional enlarged preview popup

### Upgrading from tmux-tree-sidebar

Update the startup path to `tmux-canopy/tmux-canopy.tmux` and change configuration
options from `@tmux-tree-sidebar-*` to `@tmux-canopy-*`. The previous
`tmux-tree-sidebar.tmux` entrypoint remains as a compatibility launcher. On load,
legacy settings are copied only when the corresponding Canopy option is unset;
explicit Canopy settings take precedence. Subsequent configuration changes should
use the new option names.

Internal environment variables now use `TMUX_CANOPY_*` and runtime options use
`@tmux_canopy*`. Close existing sidebars before upgrading, then reload the plugin
and reopen them. Application panes can remain running throughout the upgrade.

## Usage

The default binding is `prefix + T`. With tmux’s default prefix, press `Ctrl-b`, then `Shift-t`.

- When no sidebar exists, the binding opens it at the configured edge (left by default) and focuses it, regardless of which pane was active.
- When the sidebar is open, the same binding closes it from any pane.
- `Ctrl-q` also closes the sidebar from inside it.
- After focusing a target with `Enter`, use your pane-navigation binding to return to the sidebar (for example, `prefix + Left` or `prefix + Right`).

| Key | Action |
|---|---|
| `1` / `2` / `3` | Switch to Tree, Processes, or Buffers view |
| `j` / `k` or arrows | Move selection |
| `h` / Left | Collapse the selected node or pane's window |
| `l` / Right | Expand the selected session or window |
| `H` / Shift-h | Collapse all sessions and windows in Tree or Agents view |
| `L` / Shift-l | Expand all sessions and windows in Tree or Agents view |
| `Enter` | Focus a tree/process target, paste a buffer, or complete move/link placement |
| `a` | Open the selected object's native action menu |
| `p` | Toggle the preview drawer on/off without closing the sidebar |
| `Shift-p` | Open an enlarged read-only preview popup (`q` closes; arrows scroll) |
| `prefix + Space` | Cycle content layouts while leaving the sidebar fixed |
| `m` | Mark the selected window or pane as the move source; press again to cancel |
| `c` | Cancel move mode |
| `r` | Rename the selected session or window |
| `x`, `x` | Arm and confirm deletion of the selected pane, window, or session within five seconds |
| `u` | Clear notifications for the selected pane/window/session |
| `U` | Clear all sidebar notifications |
| `[` / `]` | Select the previous or next width preset |
| `w` | Cycle width presets |
| `s` | Create a horizontal split from the selected node |
| `v` | Create a vertical split from the selected node |
| `t` | Create a window in the selected node's session |
| `S` | Create the next available `session-N` session |
| `/` | Enter fuzzy-filter mode |
| `F` / `Ctrl-f` | Open Tree filters; Ctrl-f also works while searching |
| `Ctrl-g` | Open the global quick switcher, including collapsed panes |
| `Esc` | Leave fuzzy search; keep Tree filters |
| `Ctrl-r` | Refresh |
| `?` | Open scrollable Help; `j`/`k` or arrows scroll, Space pages, `q`/Esc closes |
| `g` | Open the scrollable legend of tree symbols, colors, badges, and labels |
| `Ctrl-q` | Close |
| `prefix + T` | Toggle the sidebar open or closed |

Tree navigation starts in a normal mode so navigation and creation keys remain available. Press `/` before typing a fuzzy query; normal-mode letter bindings are temporarily disabled while filtering. Expanded state lasts for the lifetime of each sidebar process.

With `@tmux-canopy-agents on`, `4` opens Agents, `n` jumps to the next pane reporting needs-input, and `i` toggles the agent summary drawer.

`H` collapses every branch, leaving only session rows; `L` opens every branch again. These commands affect the whole tree, including linked windows, and leave move/link/delete state intact. They do nothing in Processes or Buffers view. While searching, uppercase `H` and `L` are ordinary search text.

Creation is relative to the selected object. Selecting a session or window resolves its active non-sidebar pane; selecting a pane uses that pane directly. Splits and new windows inherit that pane's working directory. Creation focuses the new object while leaving the sidebar visible; use `prefix + h` to return to it.

Help opens in an overlay sized for your terminal, with highlighted command keys and wrapped descriptions. Narrow views stack each key above its description; wider views align them side by side. Use `b` to page back and `g`/`G` for the beginning/end. The sidebar keeps its current view behind the overlay, and all pane sizes stay unchanged. Running `scripts/help --render` directly also supports Help in the current terminal.

Press `g` in the sidebar to open the same responsive overlay as a legend. It explains the selection pointer, active-location dot, unread badges, tree guides, pane command/title/directory, and filter markers. An amber dot means unread terminal output, not that an agent needs input. Run `scripts/help --legend --print 80` to read the legend outside tmux.

### Tree filters

Press **F** (or **Ctrl-f**, including while searching) to choose:

- **All sessions** — the complete tree, subject to any text rules.
- **Current session** — the owning client's current session; follows session changes.
- **Unread** — panes with activity, bell, or silence notifications, plus their parents.
  Window-only alerts remain visible if the reporting pane has gone away. Focusing
  a window clears its terminal notifications, so it can disappear from this view.
  These notifications do not establish whether an agent needs input.
- **Window contains / Pane title contains** — optional, case-insensitive literal
  substrings. Both rules combine with the selected view; an empty response clears
  that rule. Punctuation is literal, with no glob or regular-expression syntax.
  Native prompt keys follow tmux settings; Ctrl-c cancels.
- **Clear all filters** — show everything, including clearing both text rules.
- **Use configured defaults** — discard temporary overrides and read the options below.

The Tree header shows **All**, **Session**, or **Unread**. **+W** and **+T** indicate
active window-name and pane-title rules; open the filter menu to inspect or edit
those values. Very narrow sidebars abbreviate the scope to A/S/U. No matches shows
an explicit hint to reopen the filter menu. Counts show matching/total objects.

Selecting a filter returns to Tree view. Filters survive window changes and view
switches for the lifetime of that sidebar; Processes and Buffers remain independent.
`/` searches the rendered filtered tree, and **j/k/arrows** traverse those results.
**Enter** on a session/window focuses a matching descendant, including inside a
collapsed branch. Tree folds and search queries are preserved; selection stays on
its object while that object remains visible. Actions on a window still affect
that whole window, including content excluded by a filter.

**Ctrl-g** always searches all sessions/windows/panes. Native tmux next/previous
window bindings also retain their normal scope. Filters do not turn a multi-pane
window into a compact single-pane row merely because only one pane matches.

Optional startup/configuration defaults:

```tmux
set -g @tmux-canopy-filter 'all' # all, session, unread
set -g @tmux-canopy-filter-window '' # e.g. Orchestrator
set -g @tmux-canopy-filter-title '' # e.g. orch:
```

Reload configuration and press Ctrl-r to read changed defaults. A menu choice
keeps precedence until **Use configured defaults** or the sidebar is reopened.

### Global quick switcher

Press **Ctrl-g** from any sidebar view, including while filtering. Type to search
all sessions, windows, and content panes in the current tmux server. Each result
includes its session/window context; pane results also match command, title, and
full working directory. Linked windows have a result in each session.

**Enter** focuses the result; **Esc** or **Ctrl-q** cancels. This popup takes a fresh
snapshot when opened and has a read-only preview. It preserves the sidebar's
view, query, selection, and folds. Switching is navigation only, even with a
pending move or link; that operation stays pending. Removed targets are ignored.

### Compact single-pane windows

Set `@tmux-canopy-compact-single-panes` to `on`, then press **Ctrl-r**. The default
is `off`. A window containing exactly one content pane becomes one line with its
window name, application icon, command, and notification badge. The directory
appears when the sidebar is wide enough. The `minimal` density enables this
automatically.
Sidebar and slot panes do not count; filtering does not change pane counts.

The combined row keeps its window identity: **Enter** focuses the sole content
pane, **r** renames the window, and **a** opens window actions. Multi-pane windows
retain the normal hierarchy. The setting works with every density and preserves
saved folds, which apply again when compact mode is disabled or a second content
pane is added. Use the quick switcher to preview or focus any pane individually.

### Native object actions

Press `a` for a context-sensitive `tmux display-menu`.

- **Session:** new window, rename, information, and guarded deletion.
- **Window:** focus, rename, reorder, move/link marking, unlink, layouts, rotate panes, guarded synchronized input, information, and deletion.
- **Pane:** focus, zoom, swap, move, break into a window, dead-pane respawn, information, and deletion.

Linked window occurrences carry both stable window and session IDs internally, so unlink removes only the selected session occurrence. Linked and synchronized windows display `[linked:N]` and `[SYNC]` badges. Enabling synchronized input requires confirmation; disabling it is immediate. Respawn is limited to panes tmux reports as dead.

### Views

The same long-running fzf process switches among three built-in sources, plus Agents when enabled:

1. **Tree** — sessions, windows, panes, creation, movement, and native object actions.
2. **Processes** — one `ps` snapshot attributed beneath each live tmux pane PID. `Enter` focuses the owning pane; `a` offers validated `TERM` and confirmed `KILL` actions.
3. **Buffers** — native tmux paste buffers with previews. `Enter` pastes into the sidebar's current content target; `a` can paste, yank to the system clipboard, or delete.
4. **Agents (opt-in)** — only sessions, windows, and panes containing a live Codex, Claude Code, OpenCode, Gemini CLI, Antigravity (agy), Pi, or Oh My Pi process. The header summarizes unique agent panes by reported state: `◆` needs input, `▷` working, `✓` ready/ended, and `○` detected without a verified current state (including stale reports). An active subagent can raise its parent's priority but is not counted as another pane. Linked window occurrences are counted once. The header shortens the view tabs as needed, then shows the leading state and total (such as `◆2/5`) when space is tight. ASCII uses `!`, `+`, `d`, and `o` instead. Parent rows count detected agent panes. Tree folds and native object actions still work, and `i` opens the selected pane's agent summary. Tree filters do not narrow this view; `/` searches the visible agents. A process being present does not establish whether an agent is working or needs input. Ctrl-r refreshes the process inventory.

Process signals are revalidated immediately before delivery by walking the current parent chain back to the owning `#{pane_pid}`. Stale or reused PIDs are ignored.

Yanking a buffer pipes its bytes to the system clipboard through the first available tool: `pbcopy` (macOS; wrapped in `reattach-to-user-namespace` if present), `clip.exe` (WSL), `wl-copy` (Wayland), `xsel`/`xclip` (X11), or `putclip` (Cygwin). Set `@tmux-canopy-copy-command` to override the detected command entirely. If no tool is found, the sidebar reports it rather than failing silently.

### Moving windows and panes

Press `m` on a window or pane. The source remains visible with a `⇢` marker while you navigate the same stateful hierarchy.

- For a window, select any node in the destination session and press `Enter`. The window is moved to the next free index in that session.
- For a pane, select a destination pane or window and press `Enter`. A native tmux menu chooses left, right, above, below, or break into a new window.
- Press `m` on the marked source or `c` anywhere to cancel.

Ordinary `Enter` or double-click navigation does not synchronously reload the list inside the window transition. After focus settles, an owner-only background refresh updates the active markers. Native tmux keyboard, mouse, window creation, **pane splits**, and session changes use the same family of refresh paths; `after-split-window` forces a tree reload so a new pane appears immediately rather than only after the next focus change. Structural move operations still reload after completion.

The green `●` identifies the current content pane and its window/session occurrence; the highlighted row/pointer identifies the object you are browsing. These are independent while you browse in the sidebar. When you leave it for a content pane, switch panes, or return focus to the sidebar, its pointer jumps to the current content pane, or its nearest visible window/session row when folded. Press `Ctrl-o` to do the same at any time. This clears an active search query but leaves folds and tree filters intact. If filters hide the location entirely, it rings the bell. A collapsed active window/session retains its green marker. Entering the sidebar retains the last content pane (using native `pane_last` or the remembered target), instead of marking the sidebar as the working pane.

Focus refreshes wait for approximately 75 ms of stable focus before rendering. Repeated events share one short-lived worker per sidebar; unchanged locations do not reload. The worker resolves the owning client's live session/window/pane rather than trusting stale hook targets, waits out guarded transitions, validates ownership again before publishing, and remembers linked-session occurrences. Expiring claims recover after an interrupted worker. This is event-driven, not a permanent polling process.

Use the Window actions menu to mark a window for linking, then select a destination session/object and press `Enter`. Unlike move, link keeps the source occurrence. Use the linked occurrence's action menu to unlink only that session.

The operation uses stable tmux IDs and never overwrites an occupied window index. The same sidebar process remains alive, follows the moved object in global mode, clears move state after success, and reloads the hierarchy.

## Failure diagnostics and launch behavior

Opening performs preflight checks **before unzooming or splitting application panes**: required executables/helper files, tmux capabilities, the actual fzf options/bindings, and private temporary-state creation. Closing an existing sidebar does not depend on those checks succeeding.

- Use **`a`, then `D`** for **Diagnostics** in Tree, Processes, or Buffers. The popup shows versions, dependency/capability results, and the owning client's last recorded failure.
- If the sidebar cannot open, run `./canopy doctor` from the repository root or `scripts/doctor` from a regular tmux pane. It infers the owner only when one client is using that pane. For an ambiguous context, use `scripts/doctor --report CLIENT_TTY PANE_ID`; `--check` provides a preflight-only exit status.
- `canopy doctor` also reports whether `mouse`, `escape-time`, and `default-terminal` are set in a way that could degrade Canopy's mouse resizing, single-key bindings, or ANSI colors. This is informational only: it never changes a setting, and prints nothing when a value is already fine.
- A nonzero data-source exit publishes an informational retry row, not partial source output. **Ctrl-r retries in the same fzf process**. A search query is retained; press Escape to clear it and reveal the error row, then `a` opens diagnostics.
- Unexpected fzf failures report a fixed exit-code summary to the live owner. Normal Ctrl-q/Ctrl-c aborts, successful acceptance, and handled sidebar termination signals are not reported as failures.
- Only the most recent fixed, bounded failure summary and timestamp are kept per owner, in `@tmux_canopy_failure_*` tmux options. These are operational records, not secret storage. No raw stderr, environment dumps, buffer samples, previews, or terminal captures are retained as diagnostics. The source dispatcher stages records in memory, never in diagnostic files.

The sidebar deliberately ignores `FZF_DEFAULT_OPTS`, `FZF_DEFAULT_OPTS_FILE`, and `FZF_DEFAULT_COMMAND`. Customize its documented tmux options instead. Actions use `/bin/sh`, and pane/popup startup uses direct argv rather than the user's default-shell command syntax. Script paths are protected across shell quoting, tmux parsing/format expansion, and fzf bindings; spaces, quotes, dollar signs, commas, and literal tmux-format text in installation paths are tested.

Rename prompts preserve commas and treat responses as data, not executable tmux commands or format jobs. A temporary native object option carries the response until it can be applied with literal-format escaping; normal completion, cancellation and handled termination clean it up. Buffer menus use a fixed title so a format-like buffer name is never evaluated as a menu format. Switching views also works when the current view is empty.

After upgrading, reload the plugin/configuration, then **close and reopen an already-running sidebar once** to activate the new fzf environment isolation and bindings. Existing processes continue using their original startup arguments.

### Directory-change refresh investigation

No prompt integration or polling is installed. An isolated tmux 3.7c probe confirmed that `cd` updates `pane_current_path` without changing focus or emitting a dedicated directory hook. OSC 7 updates `pane_path`, but does not trigger `pane-title-changed`; OSC 2 title changes do. The existing focus-location deduplication therefore cannot alone detect a directory-only change. See [the investigation and proposed opt-in design](directory-refresh.md). Ctrl-r remains the explicit refresh mechanism.

## Configuration

Set options before loading the plugin:

```tmux
set -g @tmux-canopy-key 'T'
set -g @tmux-canopy-position 'left' # or 'right'
set -g @tmux-canopy-width '42' # or '25%'
set -g @tmux-canopy-min-width '24'
set -g @tmux-canopy-max-width '0' # no fixed cap; content minimum still applies
set -g @tmux-canopy-min-content-width '40'
set -g @tmux-canopy-resize-mode 'live'
set -g @tmux-canopy-width-presets '30,42,48'
set -g @tmux-canopy-zoom-action 'refuse' # or 'unzoom'
set -g @tmux-canopy-scope 'global'
set -g @tmux-canopy-transition 'slot'
set -g @tmux-canopy-smooth-navigation 'on'
set -g @tmux-canopy-last-window-key 'Tab'
set -g @tmux-canopy-notifications 'activity,bell'
set -g @tmux-canopy-notification-target 'sidebar'
set -g @tmux-canopy-silence-seconds '30'
set -g @tmux-canopy-icon-theme 'auto' # Unicode by default; choose nerdfont explicitly
set -g @tmux-canopy-appearance 'classic' # or 'lazygit'
set -g @tmux-canopy-theme 'ansi'
set -g @tmux-canopy-density 'normal'
set -g @tmux-canopy-compact-single-panes 'off' # optional combined window/pane rows
set -g @tmux-canopy-selection-style 'subtle'
set -g @tmux-canopy-preview 'auto'
set -g @tmux-canopy-preview-height '35%'
set -g @tmux-canopy-copy-command ''        # override the detected clipboard command
```

Position defaults to `left`; set `@tmux-canopy-position 'right'` for the right
edge. Missing or invalid values use `left`. The setting is read when opening a
sidebar. Close and reopen an existing sidebar to change sides; its position
otherwise stays consistent through window/session navigation, slot transitions,
content layouts, and last-content-pane cleanup.

Width may be a terminal-column count or percentage. The result is clamped between `min-width` and `max-width`, while `min-content-width` prevents the sidebar from squeezing the application area below a usable size. If the window cannot satisfy both minimums, opening is refused; an already-open sidebar closes if a later terminal resize makes those constraints impossible. Percentage widths are recalculated after terminal/window resize events; interactive sidebar resizing remains the preferred runtime width for fixed-width configurations. Temporary narrow-window clamps do not overwrite that preference: it is restored when space permits. Each inactive slot is clamped to its own window's available space. When switching to a window too narrow for both minimums, the dock stays parked in its previous window and follows again into a window that fits.

For mouse resizing that follows the pointer and can grow beyond 48 columns,
use `@tmux-canopy-resize-mode 'live'` and `@tmux-canopy-max-width '0'`.
A zero maximum removes the fixed upper limit; `min-content-width` still reserves
room for application panes. Reload the plugin after changing the resize mode.
The final mouse width is saved for navigation and terminal resizing.

Resize modes control redraw behavior:

| Mode | Behavior |
|---|---|
| `staged` | On the left, the border stays still until release, producing one application resize. On the right, dragging uses native live resizing and saves the final width on release. |
| `preset` | Mouse release snaps to the nearest configured width; `[`/`]`/`w` select presets directly. |
| `live` | Default. Native tmux per-column dragging. This continuously redraws terminal applications and retains the debounced `after-resize-pane` compatibility hook. |

On the left, staged and preset modes defer sidebar resizing until release. On the right, all modes use native live dragging; preset mode snaps to the nearest width on release. This preserves ordinary vertical and horizontal content-border resizing where tmux cannot identify the shared right-sidebar border from mouse-down coordinates. Release may land inside the sidebar or a content pane; the chosen width is saved and follows the sidebar across windows and sessions. A committed resize updates the active sidebar, runtime width, and inactive stable slots once. Staged and preset modes do not launch a shell for each column of mouse movement. Width presets are comma-separated terminal-column values.

Opening on a zoomed pane is refused by default. Set `zoom-action` to `unzoom` to temporarily unzoom, create the sidebar, and restore the original pane's zoom when the sidebar closes.

The scope has two modes:

| Scope | Behavior |
|---|---|
| `window` | The sidebar remains attached to the tmux window where it was opened. Switching elsewhere hides it until that window is selected again. |
| `global` (default) | The same sidebar pane follows its owning client whenever that client changes tmux windows or sessions. |

`global` provides the appearance of a sidebar on every window without launching one fzf process per window. The sidebar records the client that opened it, so another attached tmux client does not pull it to a different window. Reload tmux after changing the scope.

Transition modes:

| Transition | Behavior |
|---|---|
| `move` | Move the sidebar with `join-pane`; inactive windows regain full width but applications resize on every switch. |
| `slot` (default) | Lazily create a fixed-width placeholder in visited windows and exchange it with the one sidebar process using `swap-pane`; content dimensions stay stable after the first visit. |

In slot mode, staged and preset resizing commit the live width and all inactive placeholders once. Default `live` mode propagates the final width to inactive placeholders after a 200 ms debounce. Applications in those windows redraw while inactive, so later switching remains resize-free. Closing the sidebar removes all placeholders and restores full-width layouts.

### Navigation fast paths

Keyboard navigation, tree activation, and fallback follow hooks share `scripts/navigation.sh`. Each request batches client, target, and pane metadata into one tmux invocation instead of issuing per-field queries. Relative next/previous/last/index targets are resolved against the owning client's session, even when another client attached more recently.

- An already-current pane with an up-to-date target and width performs no mutations.
- A same-window pane change only updates the target and selects the pane, unless its sidebar width needs repair.
- Same-session window changes do not call `switch-client`.
- Structural changes acquire the per-client transition lock, reread metadata under that lock, and batch layout/selection commands. Nested follow hooks return while the transition guard is set.
- Window/session selection settles before a fresh destination snapshot and slot exchange. This matters with `aggressive-resize`: hidden windows may retain old terminal dimensions, and tmux's automatic sizing occurs after the selection command queue.
- Destination slots are reused; width correction is queued with the swap. The preferred width—not a pane width accidentally crushed by automatic sizing—is authoritative. Slot initialization batches its option/title writes. Warm switches remain resize-free when the window dimensions and preferred width have not changed.

These paths do not synchronously reload fzf; a separate debounced worker publishes settled active-location changes without moving the sidebar cursor. Structural navigation suppresses intermediate notification-clear hooks and schedules at most one quiet clear for the final destination when it has unread state. Windows with no unread state do not start notification-clear processes.

### Empty windows and native fallback

When the last regular pane exits (`exit`, Ctrl-D, or `kill-pane`), an internal sidebar or inactive slot no longer keeps that window alive. The existing sidebar is parked without selecting a window or changing window history; internal leftovers are removed, **tmux chooses its normal successor**, and the same sidebar/fzf follows that choice. Confirmed deletion of the last pane from the sidebar uses this path too. No temporary windows or replacement fzf processes are created.

- Background slot-only windows are cleaned without stealing browsing focus.
- A regular dead pane retained by `remain-on-exit` still counts as content; it is not automatically destroyed.
- The previous regular pane is preferred over the first pane when an internal slot/dock was active in the destination.
- `detach-on-destroy` remains tmux-owned. With `off`, the dock can follow native fallback into another session. With `on`, finishing the owning session detaches normally and closes its dock without borrowing space from another session. Existing minimum-width constraints still apply.
- Native layout notifications are filtered in tmux before starting a worker. There is no polling, and ordinary resizing of windows with content starts no empty-window worker.

This concerns **last-content removal**. An explicit native `kill-window` or `kill-session` deliberately kills all their panes, including any sidebar; a process already killed by tmux cannot be preserved.

### Snapshot rendering and stable selection

The Tree source collects configuration, sessions, window occurrences, panes, and clients in one batched tmux invocation. `lib/tree-render.awk` reads UI state once, builds relationships and notification totals in memory, then emits a complete tree. There are no per-row tmux queries, collapse-state greps, or hostname processes. Control bytes in names, paths, titles and custom icons are replaced before parsing; display text cannot inject snapshot fields or ANSI controls.

The sidebar uses `reload-sync` to replace completed lists rather than displaying partial builds. Each row has an action token, visible text, and a hidden stable identity. `--track --id-nth=3` preserves selection through renames, changing badges, and reloads. Linked pane identities include their session occurrence; Enter and collapse use that occurrence without changing the native pane action token. If the selected object disappears, fzf falls back to a remaining row. Search examines the visible text, not the hidden IDs, and queries survive refreshes.

This is an on-demand snapshot, not a polling daemon or a persistent metadata cache. Standalone source callers retain the legacy two-column, newline-delimited output; `sidebar-source --stable` enables the hidden identity column. Add `--read0` for NUL-delimited records, where visible text may contain a newline. New sidebar processes select this protocol through `TMUX_CANOPY_RECORD_FORMAT=nul` and fzf `--read0`; all views and reloads use it consistently. Old running sidebars retain flattened newline records until reopened, so upgrading scripts does not corrupt their lists. Reopen an existing sidebar after upgrading its fzf bindings.

### Notifications

Notification sources are comma-separated:

| Source | Badge | Trigger |
|---|---|---|
| `activity` | Amber `●` (`*` in ASCII) | Output appears in another tmux window |
| `bell` | Amber bell (`B` in ASCII) | An application emits a terminal bell |
| `silence` | Amber `◷` (`~` in ASCII) | A monitored window is silent for the configured interval |
| `none` | — | Disable notification hooks |
| `all` | all | Enable every native provider |

Choose exactly where native alerts are presented:

| `@tmux-canopy-notification-target` | Behavior |
|---|---|
| `sidebar` | Show alerts only in the sidebar and suppress tmux's activity/bell status styles |
| `status` | Keep tmux status-bar alerts and disable sidebar alert hooks/rendering |
| `both` | Show alerts in both places |

The default is `sidebar`. Original `window-status-activity-style`, `window-status-bell-style`, and alert-action values are saved and restored when switching modes. The `status` and `both` modes set configured alert actions to `other` so tmux actually marks background windows. Custom status formats that explicitly contain `#F`, `#{window_flags}`, or alert conditionals must omit those expressions if strict sidebar-only display is desired; tmux does not expose a separate hook-only alert flag.

Native tmux alert hooks record provider state only when tmux supplies a live, non-sidebar, non-placeholder pane and its owning window. Events without a valid open terminal pane are ignored. No process scanner, Git poller, agent API, or external desktop event can create a notification in the default model.

A single bold amber badge sits immediately after the name. Expanded branches show badges on affected panes, without repeating the alert on their ancestors. Collapsed windows count unread panes; collapsed sessions count unread windows. Counts appear only above one, and multiple providers on one target count once. A bell takes priority over activity, then silence; previews list all recorded types. A window-level alert with no remaining flagged pane stays visible on the window until cleared. The green active-location marker is unchanged.

The hooks record provider state on the affected pane and window. Press `u` to clear the selected pane's window, window, or whole session; press `U` to clear all unread state. The tree aggregates unread windows into session rows and clears transient state when the owning client focuses that window. Sidebar, placeholder, dead, missing and wrong-window event sources are ignored.

Notification clearing uses one metadata snapshot and one batch of necessary mutations, rather than traversing panes once per provider. Native selection hooks check unread flags before launching a shell and share a window-scoped clear claim. Navigation suppresses intermediate hooks and requests one final quiet clear. Manual sidebar clear actions use their existing single reload rather than scheduling a second refresh.

Changed notifications share one short-lived 120 ms refresh worker. The claim is acquired inside tmux's command queue; duplicate events are rechecked there before changing state. Claims expire after two seconds so a killed worker cannot permanently block future refreshes. Distinct pane-only options (`@tmux_canopy_notice_pane_*`) prevent panes from inheriting a window's aggregate unread badge; the previous pane option names are maintained and cleared for compatibility. Unread state is still server-wide, not per-client.

The option model is provider-neutral: each provider owns a namespaced pane/window state key while rendering and aggregation are centralized. Optional Git and agent adapters can be added later without changing sidebar movement, slots, or tree navigation. Git state will remain persistent metadata rather than clear-on-focus unread state.

### Appearance

`@tmux-canopy-appearance` selects sidebar chrome. The default `classic` look keeps
today's tree: `▸`/`▾` folds, `├─`/`└─` guides, bracketed tabs (`[Tree] Proc Buff · All`),
and session/window glyphs only when you set `@tmux-canopy-icon-session` /
`@tmux-canopy-icon-window`. Set `lazygit` for section-style tabs (`╭─ Tree Proc Buff ─ All`),
rounded end branches (`╰─`), cyan fold chevrons, and default session/window glyphs
(Nerd Font when `@tmux-canopy-icon-theme` is `nerdfont`, otherwise Unicode/`S`/`W` in ASCII).
Icon theme still controls application glyphs. Close and reopen the sidebar after
changing appearance; `Ctrl-r` alone does not restyle a running fzf process.

`ansi` uses the terminal's standard palette for application icons, active panes,
notifications, and pending operations; `mono` disables source styling. Density
may be `minimal`, `normal`, `compact`, or `detailed`:

- **Normal (default):** At 31 columns or fewer, rows show commands and statuses.
  From 32 to 55 columns, directory names appear inline once per adjacent group.
  At 56 columns or more, the directory moves to a subdued second line. Shared
  directories appear once on the window row when all visible panes match, or
  beneath the first pane of a matching adjacent group. A directory uses its
  basename, adding parent names when two distinct paths would be ambiguous;
  wide views also show one parent for context. Titles appear when room permits.
- **Minimal:** Single content pane windows combine window and pane into one row.
  Multi-pane windows keep one row per pane; directory lines and ordinary
  pane counts are hidden. Filtered pane counts appear on collapsed windows.
  Titles appear only when they fit. This preset includes the effect of
  `@tmux-canopy-compact-single-panes on`.
- **Compact:** One line per pane, retaining each shortened directory inline.
- **Detailed:** Two lines per pane, retaining the full path, pane index, and
  useful title. Long lines are clipped; the preview provides more room.

The active pane has one green dot. Its session and window names are bold; fzf's
highlight and cyan pointer identify the selected row. A minimal combined window
row carries the dot when it contains the active pane. Classic appearance omits
default session and window icons to leave room for names; lazygit shows them.
Explicitly configured icons remain in both. Expanded branches omit pane/client
totals unless a Tree filter is active.
An ordinary collapsed window shows a muted pane count at the right edge when
it hides more than one pane. Expanded windows, including adjacent panes that
share one directory label, show no pane count. A collapsed filtered window
shows matched and total panes beside its name.
Collapsed branches keep counts that explain hidden children and notifications.
Linked and synchronized state remains visible. Every displayed object keeps its
stable action identity. The full directory is available in pane preview and
Ctrl-g global quick switch. Tree search matches the directory text shown in
its current width; Ctrl-g searches full paths even when they are hidden.

Paths use the terminal's default foreground with dim styling rather than a
fixed light text color. Lines do not wrap or horizontally scroll on selection.
fzf handles final ANSI/Unicode cell clipping. To change density at runtime, set
`@tmux-canopy-density` and press `Ctrl-r`; the selected object remains selected.

Selection styles are `subtle`, `solid`, `reverse`, or `pointer`. The default subtle
style uses a muted gray background and a cyan pointer while preserving icon and
notification colors. Set `@tmux-canopy-selection-background` to a 0–255 palette
index or `#RRGGBB` to customize it (default `236`; for light terminals, try `254`).
`pointer` keeps selection text unchanged, `reverse` uses reverse video, and `solid`
uses a cyan background. Monochrome mode also disables fzf UI colors. The header shows `Tree`, `Proc`, and `Buff`; enabling agent awareness adds `Agents`.
In classic appearance, brackets mark the active view and the Tree filter follows as
`· All`, `· Session`, or `· Unread` (`|` in ASCII). Lazygit appearance uses a leading
`╭─` section mark and `─` before the filter label instead of brackets and `·`. Labels
shorten when space is tight, while the enabled view shortcuts remain in help.
Pending `MOVE`, `LINK`, or `DELETE` operations remain visible. The search input appears
only after `/` and disappears on `Esc`; fzf counters and the top separator are
hidden. Classic tree rows use `├─`, `└─`, and `│` guides; lazygit uses `╰─` for the
last sibling. Colored application icons apply in both appearances.

### Preview

Preview may be `auto`, `on`, or `off`. Auto starts hidden below 28 rows so the object list remains useful; `p` toggles it on/off in navigation mode without closing the sidebar. Set `@tmux-canopy-preview 'off'` to start hidden and open it only when needed. While editing a search query, `p`/`P` remain text input, like the other letter shortcuts.

The drawer keeps a consistent configured height (35% by default) while browsing. Output is **clipped, not wrapped**: a source terminal row remains one preview row, with terminal-cell/ANSI handling delegated to fzf rather than byte truncation. Pane previews have a compact two-line heading and use `FZF_PREVIEW_LINES`/`FZF_PREVIEW_COLUMNS` to fit the available drawer. Shell/log snapshots show recent physical rows through the cursor, rather than a fixed 80-line dump or mostly empty screen bottom. Alternate-screen TUIs and common full-screen commands show a cursor-centered slice of the current screen, without shell scrollback. `[recent crop]` or `[screen crop]` identifies a cropped snapshot.

`Shift-p` opens an 85%-wide, 80%-high native tmux popup for the selected object. It uses `less -R -S` in secure mode: arrows scroll vertically/horizontally and `q` closes it. TUI snapshots include the whole current screen; shell snapshots include up to 300 recent physical rows. Popup sizing uses its own PTY dimensions, not the narrow drawer's inherited dimensions. Buffers and session/window/process metadata can also be inspected there.

The **agent summary** is a read-only view for detected Codex, Claude Code, OpenCode, Gemini CLI, Antigravity (agy), Pi, and Oh My Pi processes. Press `i` while selecting a pane to switch the existing drawer from terminal preview to an agent summary; press `i` again to return. The summary automatically follows whichever supported agent is in the selected pane. Press `p` to hide or show the drawer. The choice belongs to the sidebar pane and lasts until it closes. A single-content-pane window also resolves to its pane. `Shift-p` continues to open the enlarged terminal preview.

The summary detects a supported agent command in the pane or its process descendants and shows its title and directory. Without an integration, it checks the visible screen for likely approval wording and labels any match **possible input requested (unverified)**. It does not inspect transcripts, agent configuration, or hidden terminal history. Without a supported agent process, the drawer explains that no agent was found.

### Agent lifecycle adapters

Agent awareness is disabled by default. Set `@tmux-canopy-agents 'on'` before loading Canopy, reload the tmux configuration, then close and reopen existing sidebars. This enables the Agents view, agent process detection, inline status and subagent lines, the summary drawer, `n`/`i`/`4`, and the pane-command monitor where tmux supports it. Setting the option to `off` and reloading removes those UI controls and the monitor. Existing agent integrations remain installed until removed with `canopy integration uninstall`; their reporters may still receive events, but Canopy does not display their state while awareness is off.

Adapters are optional and observational. Agent rows distinguish `[process]` (executable detected) from a colored status word — `WORKING`, `NEEDS INPUT`, `READY`, `TURN ENDED`, `SESSION ENDED`, `INTERRUPTED`, or `UNKNOWN` — followed by a dim `·hook` origin marker for fresh lifecycle reports. Below 36 columns the word abbreviates to `wrk`, `req`, `rdy`, `end`, `int`, or `?`. OpenCode uses `·plugin?` because its server plugin may see sessions other than the one displayed in a pane. A pane with a live status also shows how long it's been since that report — `<1m`, `2m`, `1h4m`, and so on — right-aligned at the row's edge, the same way a collapsed window's hidden pane count is shown; it's simply omitted on narrower terminals instead of crowding out the status word. The drawer labels visible-screen request hints **unverified**. A hook report is tied to the pane PID, live agent process PID and start time, and agent session; a stale report becomes **unknown** after 15 minutes. Approval means a request was reported, not that a human still needs to act. Turn ended does not establish task completion.

A collapsed window or session rolls up its descendants' hook-reported agent state into one badge, separate from unread terminal notifications, in priority order: an amber `◆` (`!` in ASCII) with a count means at least one descendant needs input (approval requested or interrupted); otherwise a cyan `▷` (`+` in ASCII) means descendants are working; otherwise a dim `✓` (`d` in ASCII) means descendants finished (ready, turn ended, or session ended). Reports the drawer calls unknown are not counted. This summary appears in both Tree and Agents views, disappears once every affected pane is expanded into view (each pane already carries its own `NEEDS INPUT`/`WORKING` status word there), and is unaffected by clearing unread notifications.

Claude Code and Codex subagents appear as read-only lines beneath their parent pane in Tree and Agents views, each with its type (`Explore`, `general-purpose`, a custom agent profile), a status word (`WORKING`, `NEEDS INPUT`, or `UNKNOWN` once its last report is 15 minutes old), and the time since that report. `SubagentStart` and `SubagentStop` supply the child identity and lifecycle. Claude Code can also tag tool and permission events with the subagent's `agent_id`. Codex currently documents `agent_id` for child start and stop; Canopy attributes a Codex tool or permission event to a child only when that event actually includes the ID. A tagged subagent approval request is attributed in the drawer. The matching tool event clears it, and stopping that subagent also clears it. A subagent waiting on input counts toward the `◆` roll-up and is a target for `n`; selecting its line focuses the parent pane. A stopped subagent disappears immediately; running background subagents stay, and at most eight are kept per pane. Subagent lines require multi-line rows and are omitted in compact density. Reinstall an older Claude or Codex integration with `canopy integration install claude codex` to add the two subagent hooks; `canopy integration status` reports `partial` until then.

Press `n` from any view to jump straight to the next pane reporting needs-input (approval requested or interrupted), across every session and window, ignoring active Tree filters — the same "search everything" scope `Ctrl-g` already uses. Detection always runs at Agents-view strength, so an agent running under a wrapper shell is found even from the Tree view. Order follows the tree's own natural session/window/pane order; a linked window contributes one entry per session it's linked into. Repeated presses wrap back to the first match after the last, and `n` does nothing when no agent currently needs input.

From the repository root, run `./canopy setup` to choose optional integrations from detected CLIs; enter `detected` to install all found CLIs. `./canopy doctor` checks tmux and shows installed integration states. It also runs each reporter's real report path against a stubbed tmux, so a broken reporter fails loudly there instead of silently in a hook, and lists agent processes found in tmux panes with the age of their last report. An agent with no report usually predates its integration install and needs a restart; Codex also requires trusting new hooks via `/hooks`. `./canopy integration status` shows each executable, config path, and installation state. Explicit commands work without a prompt: `./canopy integration install codex claude`, `./canopy integration install gemini --dry-run`, and `./canopy integration uninstall codex`. Add the repository root to `PATH` to use `canopy` without `./`. Python 3 is required for the integration manager and reporters.

The installer merges its own command hooks into existing Codex, Claude, and Gemini JSON, preserving unrelated settings and hooks. Antigravity uses a named Canopy entry in `~/.gemini/config/hooks.json`; installing or uninstalling it also removes Canopy's older entries from `~/.gemini/antigravity-cli/settings.json`. It installs dedicated Pi, Oh My Pi, and OpenCode extension/plugin files. Existing files with different content are left untouched. Repeating an install is safe; uninstall removes only Canopy's matching hook commands or unmodified dedicated files. Before changing an existing JSON file, Canopy writes a timestamped `.canopy-backup-*` copy and replaces the file atomically. JSON formatting may be normalized. Invalid JSON is left untouched; use the manual examples below in that case. Restart or reload the affected agent after installing or uninstalling its integration, and use Codex `/hooks` to review and trust its hook definition.

For manual setup, merge [claude-hooks.example.json](claude-hooks.example.json) into your existing `~/.claude/settings.json` (or `$CLAUDE_CONFIG_DIR/settings.json`). For Gemini CLI, merge [gemini-hooks.example.json](gemini-hooks.example.json) into `~/.gemini/settings.json`. For Antigravity (`agy`), add the named entry in [agy-hooks.example.json](agy-hooks.example.json) to `~/.gemini/config/hooks.json`; remove any older Canopy `agy` commands from `~/.gemini/antigravity-cli/settings.json`. Replace the example absolute path in each file and keep other hook entries. These adapters require Python 3 and a supported agent running inside tmux. See the official [Claude Code hooks](https://code.claude.com/docs/en/hooks), [Gemini CLI hooks](https://geminicli.com/docs/hooks/reference/), and [Antigravity hooks](https://www.antigravity.google/docs/hooks/) contracts.

Antigravity's documented hooks support Canopy's observational `PreInvocation`, `PostToolUse`, and `Stop` reports. A fully idle stop appears as **turn ended**; a stop with background work still active remains **working**. Its hook contract does not expose a permission-request or subagent lifecycle event, so Canopy cannot show verified Antigravity needs-input or subagent rows. Canopy never registers a `PreToolUse` hook or sends an allow/deny tool decision. Reinstall an earlier Antigravity integration with `canopy integration install agy`, then restart `agy` and check `/hooks`.

For Pi, copy [pi-canopy.extension.ts](pi-canopy.extension.ts) into `~/.pi/agent/extensions/`, set its reporter path, and reload Pi. For Oh My Pi, put a separate copy in its extension directory and set `kind` to `omp`. The extension reports session start, agent start/end, and shutdown; it does not claim to know whether a permission prompt is waiting. For OpenCode, copy [opencode-canopy.plugin.js](opencode-canopy.plugin.js) into `~/.config/opencode/plugins/`, set its reporter path, and restart OpenCode. The plugin uses official session and permission events. A server plugin may observe more than one OpenCode session, so Canopy binds the first reported session to the pane and ignores other session IDs. Check the drawer source when using shared OpenCode servers; ambiguous session association is a current limitation.

### Codex hook setup

Codex CLI can optionally report lifecycle events to the selected pane's agent drawer. `./canopy integration install codex` merges Canopy's hooks into `~/.codex/hooks.json`, or `$CODEX_HOME/hooks.json` when `CODEX_HOME` is set. It includes `SubagentStart` and `SubagentStop` so Codex children appear under their parent pane. For manual setup, copy [the example hook configuration](codex-hooks.example.json) there, replace every `/absolute/path/to/tmux-canopy` with your installation's absolute path, and merge its `hooks` object with any hooks you already use. Python 3 is required for this optional script. Codex enables hooks by default; if your `config.toml` explicitly has `[features] hooks = false`, change it to `true`. Restart Codex inside tmux, then use `/hooks` to review and trust the new definition. See [OpenAI's hook documentation](https://learn.chatgpt.com/docs/hooks) for the event contract and trust flow.

The reporter stores only bounded status, tool name, optional approval description and command, session/turn identity, pane PID, Codex process PID/start time, and update time in tmux pane options. It never approves, denies, sends input, or changes agent permissions. A `PermissionRequest` appears as **Approval requested (hook report)**: the event does not prove a person must respond, because another reviewer may approve automatically. A matching `PreToolUse` clears it if Codex delivers that event after approval; otherwise a matching `PostToolUse` clears it when the tool finishes. A new prompt, turn end, interruption, or session end also clears it. Matching ignores the optional human approval description, which may be absent from later tool events. A report older than 15 minutes becomes **Unknown (report stale)**. If the pane or Codex process changes, the report is ignored. `Stop` means **Turn ended**, not task finished. Claude Code and Codex without hooks continue to show the unverified screen summary.

Tree and Agents pane rows show a bold colored status word for fresh reports, such as `WORKING` or `NEEDS INPUT`, with a dim `·hook` origin marker; finished/unknown states render dim and unbolded so they recede visually. In the Agents view, `[process]` means executable detection only. Labels require matching pane and process identities plus a recent hook report; screen hints never become row status. Hook events refresh rows without switching views; a bounded expiry worker refreshes when a report becomes stale. tmux 3.8 and later also monitor pane command changes once per second; tmux 3.7c refreshes on focus changes and Ctrl-r. The drawer shows the report source, request details when available, and unverified screen hints otherwise. On Linux, the Agents view uses an optional Python 3 `/proc` scan; it falls back to `ps` when Python or `/proc` is unavailable.

Previews are on-demand snapshots, not continuously polled terminals. Neither preview mode resizes the real application, moves panes, or replaces the sidebar's fzf process. Reopen an already-running sidebar after upgrading to pick up the new no-wrap setting and `Shift-p` binding.

### Content layouts

`prefix + Space` (currently **Ctrl-a Space**) cycles content-only layouts: even-horizontal, even-vertical, main-horizontal, main-vertical, tiled, and the two mirrored main layouts. The sidebar's width, full height, and configured left/right edge stay fixed. The sidebar's **Layouts** action menu uses the same mechanism. With one content pane, there is nothing to rearrange; without a sidebar/slot, ordinary native layout commands are used.

The implementation generates one checksummed native layout for the existing panes and applies it directly—no temporary windows, pane recreation, or whole-window layout followed by a repair. Stable placeholder slots are protected too. Layouts that cannot fit are skipped during cycling or refused for explicit selection. Zoomed windows are left alone; unzoom before cycling. Multiple docks or a dock already reordered by other commands are refused rather than risking an application's position; reopen a displaced sidebar to restore normal ordering.

This protection covers `prefix + Space` and the sidebar layout menu. Direct native `select-layout`, the native Meta-number preset bindings, and `rotate-window` still operate on the whole window.

### Icons

Application icons retain command-aware colors: blue editors and Kubernetes tools, yellow Node/Python and Claude, red Git/npm/OpenShift, cyan SSH/Codex/Antigravity/system monitors, white Gemini, and magenta pi/OpenCode. In Unicode and Nerd Font themes, shells and unknown commands show their names without a default icon; ASCII retains its plain pane marker. The green active-location dot remains separate from the cyan selection pointer. Tree guides, paths, inactive tabs, and metadata are dimmed; yellow marks notifications and delete/dead-pane warnings. The gutter is blank and scrollbars use a thin, dim line. These styles apply to Nerd Font, Unicode, and ASCII glyph themes; `theme=mono` disables source styling and uses fzf’s monochrome interface.

Icon themes:

| Theme | Behavior |
|---|---|
| `nerdfont` | Nerd Font glyphs for recognized apps; requires a Nerd Font in the displaying terminal |
| `unicode` | Command-aware Unicode symbols with no Nerd Font dependency |
| `ascii` | Plain ASCII markers |
| `auto` | Use Unicode (the default); font availability cannot be inferred from the tmux server |

Session and window names omit default icons in classic appearance to leave room for
names; the lazygit appearance shows them. Explicitly configured icons remain in both.
Recognized pane commands retain app glyphs, while shells and unknown commands leave that slot blank so names stay aligned. The Unicode theme uses compact symbols such as `✎` for editors, `◇` for Git, `✦` for Claude, and `◈` for Codex. The Nerd Font theme uses `◇` for Claude and `◈` for Codex because these shapes work with older Nerd Fonts; other recognized apps keep their Nerd Font glyphs. Set `@tmux-canopy-icon-session`, `@tmux-canopy-icon-window`, or `@tmux-canopy-icon-pane` to override the corresponding structural icon.

Override a recognized app's icon with `@tmux-canopy-icon-<app>`; set it to `none` to leave its icon slot blank. These options work with every icon theme and take effect after `Ctrl-r` in the sidebar. For example:

```tmux
set -g @tmux-canopy-icon-claude '✦'
set -g @tmux-canopy-icon-codex 'none'
```

| Option suffix | Commands covered |
|---|---|
| `nvim`, `vim` | `nvim`; `vim`, `vi` |
| `shell` | `bash`, `zsh`, `fish`, `sh` |
| `node`, `python` | `node`, `npm`, `npx`; `python`, `python3` |
| `git`, `ssh`, `kubectl` | `git`, `lazygit`, `hunk`; `ssh`; `kubectl`, `oc`, `k9s` |
| `claude`, `codex`, `gemini` | `claude`, `claude-code`; `codex`; `gemini` |
| `pi`, `omp`, `opencode` | Each matching command |
| `antigravity` | `agy`, `antigravity` |
| `make`, `top` | `make`, `cmake`, `ninja`; `top`, `htop`, `btop` |

The existing `@tmux-canopy-icon-pane` controls the fallback for unrecognized commands. App override values are scrubbed of control bytes before rendering; keep them to one terminal glyph for alignment.

For Nerd Font icons, install and select a recent Nerd Font or Symbols Nerd Font on the computer displaying the terminal. A font found on the tmux server does not establish that a local or remote terminal can render it. If a symbol appears as a question mark, select the `unicode` or `ascii` theme, or update the terminal font and keep `nerdfont` explicitly selected. Reload the tmux configuration after changing the theme.

Generic activity can be noisy for log tails. Use `bell`, `activity,bell`, or `none` according to the desired signal level. Use `notification-target status` to return alert presentation to the normal tmux status bar without collecting sidebar unread state. Silence monitoring is only enabled when `silence` or `all` is configured.

When smooth navigation is enabled, the plugin wraps `prefix + n`, `prefix + p`, `prefix + 0` through `prefix + 9`, and the configurable last-window key (`prefix + Tab` by default). It resolves the destination, moves the sidebar, updates ownership state, and selects the destination in one tmux command queue. The fallback hooks still handle status-bar clicks, `choose-tree`, external `select-window` calls, and session changes. Set smooth navigation to `off` to restore the previous bindings, or set the last-window key to `off` to restore only that binding. Changing the toggle key also restores its previous binding. Reloads preserve user changes made after Canopy installed its bindings. Notification monitors are restored when their providers are disabled. Ownership restoration applies to bindings/settings first installed by this version; settings overwritten by older versions cannot be reconstructed, so start a fresh tmux server when upgrading those installations.

## Architecture

| Component | Responsibility |
|---|---|
| `tmux-canopy.tmux` | Configuration, toggle binding, and window/session hooks |
| `scripts/toggle` | Create or close the invoking client's sidebar |
| `scripts/follow` | Move an existing sidebar pane to the client's selected or newly created window |
| `scripts/navigate` | Dispatch next/previous/last/numeric window navigation |
| `scripts/navigation.sh` | Shared batched navigation, fast paths, and guarded layout/selection transactions |
| `scripts/sync-width` | Debounce legacy live-mode resizes and synchronize inactive slots |
| `scripts/resize` | Commit one-shot and preset widths to the sidebar and slots |
| `scripts/mouse-resize` | Detect sidebar-border drags and commit on mouse release |
| `scripts/refresh-sidebar` | Remember the live content target and debounce owner-only active-location updates |
| `scripts/responsive-width` | Re-clamp fixed/percentage widths after terminal resizing |
| `scripts/cleanup` | Repair stale ownership/targets and remove orphan slots |
| `scripts/reap-empty` | Finish content-empty windows while preserving the dock and native successor selection |
| `scripts/notify` | Validate/deduplicate events, batch unread clears, and coalesce refresh workers |
| `scripts/notification-lib.sh` | Native hook predicates and expiring clear claims |
| `scripts/tree-filter` | Tree filter menu, literal text prompts, and per-sidebar overrides |
| `scripts/view-header` | Render dynamic view tabs and operation mode state |
| `scripts/sidebar-source` | Publish complete in-memory view snapshots or a recoverable error row |
| `scripts/launch-lib.sh` | Shell/tmux quoting, preflight checks, and bounded owner-targeted failures |
| `scripts/ui-options.sh` | Shared preflight and runtime fzf options/bindings |
| `scripts/doctor` | CLI and contextual-popup diagnostics |
| `scripts/sidebar-action` | Dispatch view-specific focus, buffer, process, and action-menu operations |
| `scripts/sidebar-preview` | Dispatch and row-budget object, process, pane, and buffer previews |
| `scripts/pane-preview` | Capture recent shell rows or the active TUI screen without resizing |
| `scripts/preview-popup` | Open an owner-targeted enlarged read-only snapshot |
| `scripts/content-layout` | Cycle/apply content-only layouts with native fallback |
| `lib/content-layout.awk` | Generate checksummed layouts with a fixed full-height dock |
| `scripts/process-source` | Index one process snapshot and render descendants for all content panes |
| `scripts/buffer-source` | List native tmux buffers |
| `scripts/buffer-lib.sh` | Buffer identity tokens and system-clipboard command detection |
| `scripts/info` | Render session/window/pane metadata in a native popup |
| `scripts/sidebar` | Own the long-running fzf process and its temporary state |
| `scripts/tree-source` | Collect one batched, sanitized metadata snapshot |
| `lib/tree-render.awk` | Render hierarchy, badges, state and occurrence-aware row identities |
| `scripts/tree-action` | Navigate, create, rename, delete, move, and manage selected objects |
| `scripts/tree-preview` | Render metadata and captured pane output |
| `scripts/help` | Display responsive, scrollable Help in an overlay or the current pane |
| `scripts/lib.sh` | Shared sidebar ownership and pane helpers |

Stable tmux IDs (`$session`, `@window`, and `%pane`) are used internally. Display names are presentation only and can be renamed without invalidating the selected object.

## Development

Run syntax checks and the isolated tmux integration suite:

```bash
bash tests/run.sh
```

The process suite uses synthetic snapshots without a tmux server. It checks descendant and sibling order, pane attribution, linked-pane deduplication, deep trees and cycles, provider failures, and stable newline/NUL records. It also verifies that 50 panes and 10,000 processes use one process query and one graph renderer.

The integration suite starts a private tmux server and verifies:

- full-height placement on either edge, with left as the default
- configured width
- pane identity preservation while following windows
- client-scoped ownership and toggling
- notification destination and manual clearing
- native rename and confirmed deletion
- window reorder and link/unlink occurrence behavior
- pane zoom/swap/layout/synchronization and dead-pane respawn
- process and buffer source dispatch
- dynamic view headers and ANSI-styled tree rendering
- orphan cache and slot cleanup
- percentage/min/max width behavior
- staged mouse commits, preset cycling, and live-mode compatibility
- zoom refusal and unzoom restoration

The width suite reproduces stale 510-column hidden windows with a 211-column attached client and `aggressive-resize on`. It checks native/scripted and cross-session switches, committed widths, narrow-window clamping, terminal shrink/grow, transition guards, percentage widths, numeric format boundaries, and persistent sidebar/fzf process identity.

The additional navigation suite requires Python 3 for its test harness only (not for the sidebar). It starts tmux with `-f /dev/null`, attaches real PTY clients, runs the actual fzf sidebar, and verifies no-op and same-window command counts, next/previous/last navigation, cross-session and linked-window targets, stale hook targets, client-specific relative navigation, native new-window following, window-local scope, navigation with the sidebar closed, fzf PID preservation, and zero application `SIGWINCH` signals during warmed slot switches.

The rendering suite additionally verifies snapshot field safety, linked-row uniqueness, collapse state, real fzf tracking through rename/notification/filter reloads, session-correct linked-pane activation, deleted-selection fallback, notification source validation, a 20-event concurrent burst producing one refresh, one quiet clear per guarded navigation, and expired-worker recovery.

The focus suite uses real client keystrokes and SGR mouse clicks to check live pane/window/session markers, remembered content on sidebar focus, pointer return on same-pane departure and pane switches, clearing a search when jumping to the active pane, collapsed branches, rapid pane-switch coalescing, stale hook targets, new windows, linked-session occurrences, and refresh isolation between two sidebar owners.

The preview suite checks row budgets, real fzf no-wrap rendering with ANSI/Unicode, the `p` toggle, fixed drawer height, alternate-screen capture, popup safety, and zero application resize signals from previews. It also exercises actual Ctrl-a Space keystrokes against the persistent sidebar. The layout suite covers all presets, reverse cycling, focus/ID preservation, slots, single content panes, zoom refusal, native fallback, and insufficient space.

The multiline suite checks NUL framing and legacy compatibility, one identity per two-line pane, aligned/subdued paths, no spacer rows, real second-line mouse selection, one-object keyboard movement, path filtering, reload/density-change tracking, and Enter targeting a non-first content pane.

The launch suite copies the project to a path containing spaces, quotes, dollar signs, commas, parentheses and literal tmux-format text. It tests missing/incompatible fzf, damaged installations and unusable TMPDIR without geometry/zoom changes; Bash/zsh/fish default shells when installed; hostile ambient fzf defaults; real provider failure/recovery with preserved fzf/query; empty-view switching; diagnostics menus; native hooks/toggle bindings; runtime fzf failures; owner-only failure delivery; and literal buffer names/rename responses, including tmux command/format-job injection attempts. Test-only wrappers inject probe bindings; production does not accept ambient fzf bindings.

The lifecycle suite exercises real shell exit and Ctrl-D, native pane killing and confirmed last-pane deletion, retained-dead panes, background slot-only windows, warm multi-pane destinations, linked-window closure, session fallback/detachment, unrelated client detachment, and sidebar/fzf PID preservation in global/window scope and slot/move modes. Final-session detachment must not send resize signals to an unrelated application.

The filter suite checks linked/current-session scope, unread aggregation, literal
text matching, configuration overrides, empty results, compact eligibility, narrow
headers, native menus/prompts, and matching-descendant navigation.

The quick-switch suite exercises the actual popup with collapsed branches, compact
rows, linked-session targets, pending operations, cancellation, and deleted targets.
It verifies that sidebar state and the running fzf process survive navigation.

The buffer suite checks encoded identities, preview/paste/delete targeting, Unicode and separator-bearing names. The configuration suite checks binding/monitor restoration and later user overrides.

None of these suites alters the developer's active tmux server.

## Prototype limitations

- tmux pane geometry is column-based rather than animated. Staged mode on the left eliminates intermediate application redraws, with the border jumping to its final position on release. Right-side mouse dragging uses native live resizing; the final width is saved on release.
- `move` transition mode changes layouts on every switch. `slot` mode incurs one initial resize when a window first receives a placeholder and one final resize when placeholders are removed.
- Generic `activity` notifications intentionally treat any output as attention; continuous log windows may be noisy.
- Stable slots are currently optimized for one active sidebar owner per tmux server. Multi-client slot arbitration still needs a formal policy. Detached-client cleanup now uses the actual hook client (and has an unrelated-detach regression test), but this is not a claim of complete multi-client geometry arbitration.
- Closing the sidebar returns its space to adjacent panes, but tmux may not reproduce every prior pane proportion exactly.
- Directory-only changes still need an explicit refresh; no prompt notifier or polling is installed. See the directory-refresh investigation above.
- The hierarchy refreshes after navigation rather than subscribing to tmux control-mode events.
- Tree expansion is session/window based; panes are leaves.
- Multi-selection, bulk movement, and undo are not implemented.
- Deletion is intentionally irreversible after the second `x`; there is no trash or undo layer.
- New sessions currently use the first available automatic name (`session-1`, `session-2`, and so on); rename it afterward with `r`.

## License

Licensed under the [Apache License, Version 2.0](../LICENSE).
