# Changelog

## Unreleased

### Added

- Tree filters for All, Current session, and Unread, with optional window-name and pane-title filters, native controls, and matching-pane navigation.
- Ctrl-g global quick switcher searches sessions, windows, and panes inside collapsed branches without changing tree state.
- Optional compact rows for single-pane windows via `@tmux-canopy-compact-single-panes`.
- Persistent client-owned sidebar with tree, process, and buffer views.
- Left/right placement, stable slots, live mouse resizing, and width presets.
- Responsive help, shared-directory grouping, colored application icons, and selection highlighting.
- Apache 2.0 license, public installation instructions, and automated release checks.

### Changed

- Simplified Tree rows with one active marker, emphasized parent names, shorter prefixes, compact counts, adaptive directory labels, and grouping for adjacent panes sharing a directory.
- Added a `minimal` density preset that combines single-pane windows and keeps multi-pane windows to one line per pane.


- Notifications use one amber badge beside each affected pane, with counts on collapsed branches and full types in previews.

### Fixed

- Sidebar navigation preserves split proportions when a hidden window resizes to the active terminal, preventing content panes from collapsing to one column.

- Slot navigation uses native empty panes, fixing new-window follow failures on macOS caused by `sleep infinity`.

- Buffer names containing separators now retain their exact identity through preview, paste, and deletion.
- Configuration reloads restore obsolete bindings and disabled notification monitors, preserving later user overrides.
- Leaving search restores the full object list.
