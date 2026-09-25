# Work checkpoint

## Current requests

1. When the last content pane exits, let tmux close the window and choose its normal successor, keeping the existing sidebar open when possible.
2. **Newest request: entering and exiting Help must not change the sidebar's size or application layout.** This has been acknowledged but is not implemented yet.

Project: `/home/jmosco/dev/projects/tmux-canopy`.

Preserve all pre-existing staged, unstaged and untracked work. No commit/reset has been performed. No deliberate live plugin reload or sidebar restart has been performed during this work; on-disk helpers may nevertheless be used by existing processes.

## Earlier completed work

The preceding diagnostics/launch-hardening pass added preflight, owner-targeted fixed failure summaries, `scripts/doctor`, shared fzf options, ambient-fzf isolation, complete in-memory source staging, provider-error propagation, literal rename handling, and safe buffer menus. Its suites passed before the current lifecycle changes.

Directory-change refresh remains investigation only: `docs/directory-refresh.md`. No prompt changes or polling were added.

## Implemented in the current lifecycle pass

- New executable `scripts/reap-empty`:
  - Detects windows containing only sidebar/slot panes; retained dead regular panes count as content.
  - Serializes workers with a global lock and dock moves with the existing owner navigation lock/guard.
  - Parks an existing sidebar via a destination slot without selecting windows or altering window history.
  - Removes only internal leftover panes, letting native tmux window/session destruction choose the successor.
  - Follows the live owner's actual successor and restores content focus only for affected foreground windows.
  - Revalidates emptiness before mutations; never destroys a whole window containing newly created content.
  - Cleans background slot-only windows without stealing browsing focus.
  - Respects `detach-on-destroy`; with `on`, does not borrow geometry from unrelated sessions before detachment.
  - Retains existing width bounds. No safe destination means the internal dock can close rather than keep a zombie window alive.
- `scripts/lib.sh`:
  - Added `sidebar_empty_window_condition()`.
  - `content_pane_for_window()` now prefers the last regular pane when an internal pane is active.
- `scripts/navigation.sh`:
  - Added `pane_last` to the existing snapshot and uses it before the arbitrary first-pane fallback.
  - No extra snapshot tmux call on the ordinary navigation fast paths.
- `tmux-canopy.tmux`:
  - Sources `lib.sh` instead of directly sourcing `launch-lib.sh`.
  - Added `[9005]` hooks for `window-layout-changed` and `window-unlinked`.
  - Layout hook filters in tmux using nested session/window loops matching `hook_window`; only the matching window evaluates the empty-pane predicate.
  - Important: a layout hook's default window context can be the foreground window even when a background window changed. The initial simpler predicate missed background exits and was replaced.
  - Detach cleanup now uses `#{hook_client}` instead of `#{client_tty}`. The latter could resolve to a surviving client and close the wrong sidebar.
- `scripts/tree-action`: confirmed deletion of a last content pane now kills that pane and invokes the reaper rather than converting it into arbitrary first-window navigation. Existing last-window deletion refusal remains.
- `scripts/toggle`: publishes owner/target metadata before the sidebar marker, and checks for an empty window at startup to catch a last-content exit during opening.
- `scripts/launch-lib.sh`: requires the reaper helper and `sort` at preflight.
- README/help document native empty-window behavior and remaining limitations.

Explicit native `kill-window` / `kill-session` still deliberately kill all included panes; the new behavior concerns last-content removal. Explicit sidebar window deletion still uses its previous separate path.

## Tests and latest status

New `tests/lifecycle.py` covers:

- Real shell `exit` and real attached-terminal Ctrl-D.
- Native pane killing and confirmed sidebar last-pane deletion.
- Native last-window history rather than first-window selection.
- Same sidebar and fzf PIDs, full-height left placement, 42-column width.
- Warm multi-pane destination geometry and last-content-pane focus.
- Remaining panes and retained-dead panes.
- Background slot-only windows without focus theft.
- Linked-window closure and `detach-on-destroy=off` cross-session fallback.
- Unrelated client detach preserving the owner's dock.
- `detach-on-destroy=on` cleanup, including zero resize signals to an unrelated application.
- Profiles: slot/global, move/global, slot/window.

Lifecycle, launch, width, navigation, and integration suites have passed during this pass. Syntax/ShellCheck checks passed at intermediate stages.

**Latest full regression run is NOT green:**

- Integration and navigation passed.
- `tests/rendering.py` passed through linked-pane activation, then failed in the deleted-selection fallback test:
  - line 231: `chosen = selection()[1]`
  - line 66: selection waits for a probe file
  - line 61: `AssertionError: fzf selection probe`
- Remaining suites in that run did not execute because the loop stopped.
- Investigate this as a possible lifecycle/refresh interaction, not automatically a timing-only test failure.

Latest production edits after some earlier successful tests include filtering the reaper's initial `list-windows` query with the native empty predicate and the startup metadata/empty-window check in `toggle`.

Use:

```bash
export PYTHONDONTWRITEBYTECODE=1
for file in tmux-canopy.tmux scripts/* tests/*.sh; do bash -n "$file" || break; done
shellcheck tmux-canopy.tmux scripts/* tests/*.sh
tests/integration.sh
for suite in navigation rendering focus icons preview layout multiline widths launch lifecycle; do
  python3 "tests/$suite.py" || break
done
git diff --check
```

Also check new/untracked files for whitespace. A test-generated `tests/__pycache__/support.cpython-314.pyc` may need cleanup; do not remove unrelated work.

## New Help-size request: investigation started

- Current `scripts/ui-options.sh` binds Help with:
  ```bash
  --bind="?:execute($help_cmd)"
  ```
- `scripts/help` clears the terminal, prints the long help text in-pane, and waits for a key. It does not intentionally invoke pane resizing.
- No help code change has been made yet.
- Consider a client-targeted native Help popup so fzf remains in place and the application layout is not altered, but ensure the long help is readable/scrollable and preserve existing help test behavior. This is only a possible approach, not implemented or validated.
- Add a real PTY regression checking dock and application geometry before/during/after Help, retained fzf PID, query/selection, and preferably no application SIGWINCH.
- Do not assume visual terminal reflow proves a physical pane resize; reproduce and measure actual tmux geometry.

Most recent read-only live sidebar observation:

- Pane `%140`, window `@0`, owner `/dev/pts/0`.
- Sidebar Bash PID `1102337`.
- Dock width 42, window width 211.
- No live fzf PID was gathered in that inspection.

## Next steps

1. Address/reproduce the new Help-size request, measuring actual geometry.
2. Resolve the rendering deleted-selection regression introduced or exposed by the lifecycle changes.
3. Run the complete regression suite and syntax/lint/whitespace checks again.
4. Only once stable, reload the live plugin hooks without restarting the existing sidebar if possible; verify IDs/PIDs and geometry before/after. Consider one reaper pass for already stranded internal-only windows, but never destroy regular or retained-dead application panes.
5. Report accurately which changes are active live and whether any startup-binding change requires reopening the UI.

No prompt integration, directory polling, process-graph rewrite, or general multi-client geometry arbitration should be slipped into these fixes.
