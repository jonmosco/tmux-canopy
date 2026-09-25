# Changelog

## Unreleased

### Added

- Persistent client-owned sidebar with tree, process, and buffer views.
- Left/right placement, stable slots, live mouse resizing, and width presets.
- Responsive help, shared-directory grouping, colored application icons, and selection highlighting.
- Apache 2.0 license, public installation instructions, and automated release checks.

### Fixed

- Slot navigation uses native empty panes, fixing new-window follow failures on macOS caused by `sleep infinity`.

- Buffer names containing separators now retain their exact identity through preview, paste, and deletion.
- Configuration reloads restore obsolete bindings and disabled notification monitors, preserving later user overrides.
- Leaving search restores the full object list.
