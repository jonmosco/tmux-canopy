# macOS installation and lifecycle audit

Date: 2026-09-26. Result: installation checks pass; the complete release gate
does **not** pass on this machine.

Environment: macOS 15.7.3 (Apple Silicon), tmux 3.7c, fzf 0.74.3,
Bash 5.3.15, Python 3.14.7, system awk 20200816. Tested working tree based on
`c89a528`, including the local test changes described below.

All checks used private tmux servers and temporary fixtures. Agent installation
checks used temporary configuration directories. Existing user agent settings
and live tmux sessions were not modified by these tests.

## Installation and setup

- Real TPM scripts installed a fresh, disposable Git snapshot of the working
  tree, loaded both entrypoints safely, and passed `canopy doctor`.
- Installed Tree, Processes, Buffers and Agents providers returned NUL-framed
  records without a failure row.
- Repeated TPM installation and loading succeeded.
- Removing the plugin declaration and running TPM cleanup removed Canopy and
  retained TPM. This checks file removal, not automatic removal of live hooks.
- A separate manual clone and `run-shell` installation passed doctor.
- All six integration adapters passed install, status, idempotent reinstall,
  stale-path repair and uninstall checks, preserving unrelated settings.
- Dry-run, interactive setup cancellation, interactive all-agent setup, invalid
  JSON handling and protection of modified extension files passed.

The TPM test uses the existing local TPM checkout and a local Git source. It
does not cover GitHub download/authentication, fetching a published release,
pressing the physical prefix-I shortcut, or real agent CLI conversations.
Reported hook state tests use synthetic agent processes and events.

Reproduce the additional installation check with:

```sh
python3 tests/tpm_install.py "$HOME/.tmux/plugins/tpm"
python3 tests/setup.py
```

## Release suite

Every suite from `tests/run.sh` was attempted individually so an early failure
would not skip later suites. After correcting test portability assumptions,
17 of 25 suite invocations passed:

`integration`, `configuration`, `setup`, `buffers`, `navigation`, `focus`,
`icons`, `notifications`, `processes`, `help`, `preview`, `layout`,
`layout_scaling`, `directories`, `filters`, `widths`, and `widths --right`.

Eight invocations remain failing:

| Suite | Observed failure |
| --- | --- |
| rendering | Collapsed row length is 33 instead of 39 at a 42-column sidebar. macOS awk counts the UTF-8 glyph bytes in this padding calculation. |
| multiline | Continuation path does not align with the command column. |
| quick_switch | Test does not observe the popup fzf start marker after Ctrl-g. |
| launch | Diagnostics popup process is not observed in the quoted-path scenario. Earlier launch/recovery checks run before this assertion. |
| codex_panel | Expected Ready state from the synthetic Codex lifecycle hook is absent. |
| harnesses | Expected Approval requested state from the synthetic Claude hook is absent. |
| lifecycle | Final-session detachment records a resize signal in an unrelated application's fixture. |
| lifecycle --right | Same final-detachment assertion. |

The lifecycle suites stop at their first failing mode. Each remaining mode was
therefore run separately: global/slot, global/move and window/slot on both left
and right all reach the same final-detachment assertion. Earlier checks pass,
including last-pane closure, Ctrl-D, confirmed deletion, retaining the sidebar,
and native session fallback. The resize failure still needs a native control
comparison to distinguish a plugin regression from startup/signal timing in
the fixture. Popup and agent state failures also need further diagnosis; these
results do not establish their root causes.

## Test portability changes

- Count rows without macOS `wc -l` whitespace padding.
- Compare process basenames, since macOS `ps comm` returns executable paths.
- Use GNU `gsleep` for renamed agent fixtures on macOS; copying Apple's system
  `sleep` fails on protected metadata or produces an unusable renamed fixture.
- Add interactive setup and dry-run coverage and a reusable real-TPM test.

ShellCheck and diff whitespace checks pass. Per-suite logs from this run are
in `/tmp/canopy-macos-audit/` and are temporary. The full release gate remains
red; installation success alone is not evidence of complete macOS support.

## Quick-switch follow-up

The same third-popup timeout was subsequently reported by GitHub CI and
reproduced locally. The test now waits for the debounced focus refresh and
retries its read-only selection probe while fzf is busy. Popup opens and
navigation keystrokes remain single-shot, and the original focus, pending-state
and stale-target assertions are retained. Three consecutive local quick-switch
runs passed after this change. GitHub CI has not yet been rerun; the counts above
describe the original audit run.
