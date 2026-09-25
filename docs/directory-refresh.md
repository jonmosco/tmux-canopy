# Directory refresh investigation

Status: investigated, not implemented. No prompt changes, timer, polling loop,
control-mode client, or additional persistent helper has been installed.

## Findings on tmux 3.7c

An isolated `tmux -f /dev/null` server with an attached PTY and a clean
`bash --noprofile --norc` shell was used. Automatic window renaming and application
window renaming were disabled; activity monitoring was enabled. The probe used
private fixture directories, not the user's live shell or prompt.

| Operation | Observed metadata | Observed relevant hook |
| --- | --- | --- |
| `cd` from fixture directory A to B | `pane_current_path` becomes B; session/window/pane IDs remain identical | None among the registered focus, mode, window-name and activity hooks |
| Emit OSC 7 `file://localhost/reported-path` | `pane_path` changes; `pane_current_path` remains B | No `pane-title-changed` |
| Emit OSC 2 `reported-title` | `pane_title` changes | `pane-title-changed` fires |

`set-hook` rejected `pane-current-path-changed` and `pane-path-changed` as unknown
hooks. It accepted `pane-title-changed` on this build, even though the installed
manual's hook/control-notification lists do not enumerate it. Any optional use
must therefore check support rather than assume it from those lists.

The renderer already reads `pane_current_path`. There is no need to replace it
with parsed prompt text, titles, an environment snapshot, or OSC 7 data. The
missing part is a reliable signal to request a new snapshot. The current
active-location worker deduplicates on session/window/pane identity; a directory
change alone leaves that identity unchanged. Simply calling that worker again
is insufficient while its unchanged-location shortcut applies.

The existing Ghostty Bash integration can publish both cwd titles and OSC 7.
However, the Bash panes inspected on this workstation currently have static host
titles. A title hook alone would not reliably cover this setup. Enabling or
rewiring shell integration is a separate prompt-workflow change, not something
this hardening pass should silently do.

## Options considered

1. **Manual Ctrl-r (available now).** No integration or recurring work. Refreshes
   the directory and other metadata using the same fzf process and stable IDs.
2. **Optional prompt notification (recommended for review).** A small Bash hook
   compares `$PWD` with its previous value using builtins. Only a change sends a
   local, asynchronous tmux refresh request. This is a signal, not a replacement
   prompt or a source of directory text for the renderer.
3. **Optional native title hook.** Useful when an existing shell integration
   already changes titles. Re-read actual tmux metadata and skip unchanged
   directories; do not treat arbitrary application titles as paths. This is not
   a universal `cd` hook and should not require changing window names.
4. **Control-mode format subscription.** The documented
   `refresh-client -B name:%pane:#{pane_current_path}` mechanism reports changes
   at most once a second, but requires a control-mode client. It would add a
   persistent connection/reader and its lifecycle to the current design.
5. **Polling or output/activity-driven refresh.** Polling adds recurring work.
   Output is not a directory-change signal, and log/TUI output could cause
   excessive jobs and reloads. Neither approach is proposed as the default.

## Proposed opt-in prompt design — approval required

Before implementation, agree on these constraints:

- Append an idempotent hook without replacing `PS1`, kube-ps1, Bash Git Prompt,
  or existing prompt hooks. Handle string and array `PROMPT_COMMAND` values.
- Preserve the incoming exit status and the prompt's existing status-capture
  ordering. No remote fetches, Git commands, credential inspection, or extra
  subprocesses on this hook's unchanged-directory path.
- Send only a validated pane identity to a plugin-owned helper. Do not interpolate
  `$PWD`, titles, command text, or other shell data into tmux command strings.
  Resolve directory metadata from tmux when rendering.
- Ignore sidebar/slot panes and shut down cleanly when the dock or client goes
  away. Do not attach a watcher or replace a terminal/PTY.
- Add a distinct metadata-dirty reason to refresh scheduling. Do not defeat the
  focus deduplicator by fabricating a focus change or overwriting its location.
- Coalesce changes and refresh only applicable owner UIs. A global Tree may show
  a changed pane that is not that owner's active pane; linked occurrences and
  multiple owners must be considered explicitly.
- Keep the same fzf process, query, selected object, viewport and collapse state.
  Do not navigate, auto-expand branches, resize applications or change the
  active-location marker merely because metadata changed.
- Test coexistence with the current multiline prompt, Git exit-status handling,
  kube-ps1, nested shells, repeated sourcing, hostile directory names, rapid
  changes, closed docks, linked sessions and two independent owners.

A prompt notification occurs when control returns to the shell prompt. It does
not instantly observe the intermediate directory in `cd elsewhere && long-job`,
nor does it provide continuous foreground-command tracking. `pane_current_path`
also describes local pane process state, not necessarily a remote SSH shell's
working directory. Those are separate requirements and should not be hidden
behind a claim of universal real-time directory tracking.

## Recommendation

Keep Ctrl-r as the current explicit refresh. Review an opt-in, cwd-change-only
prompt notifier next, with a dedicated metadata-refresh path and the tests above.
Do not alter the existing prompt or introduce polling as part of diagnostics and
launcher hardening.
