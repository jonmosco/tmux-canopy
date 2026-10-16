# Agent inspector field card Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the spacer-heavy agent inspector with a fixed field card (state, trust, directory, git, place with `●`, request below) and shorten the shared preview drawer default to 25%.

**Architecture:** Rewrite `scripts/agent-preview` rendering; reuse `git-lib.sh` and the sidebar’s `@tmux_canopy_target` for the green place marker; update defaults, docs, and existing preview/panel tests.

**Tech Stack:** Bash, awk, tmux options, fzf preview, Python test suites on private tmux servers.

## Global Constraints

- No daemon, no Git polling, no `git status`; git only when `@tmux-canopy-git-context` is `branch`.
- Inspector stays structured (no terminal excerpt); Terminal preview remains on `i`.
- One shared preview height for both modes; default `25%`.
- Bash 4.4+ for scripts; keep ShellCheck clean.
- Display order: state/agent → trust → directory → git → place → optional blank → request → command.
- Short-drawer keep order when space is tight: state/agent → request/command (if present) → trust → directory → git → place.

---

### Task 1: Failing tests for the field card

**Files:**
- Modify: `tests/codex_panel.py`
- Modify: `tests/harnesses.py`
- Modify: `tests/preview.py` (height default if asserted)

**Interfaces:**
- Consumes: `scripts/agent-preview` stdout lines
- Produces: assertions for field order, git line, `●` place, no blank padding, no title/pane-id dump

- [ ] **Step 1: Update panel/harness expectations** for no title/`%pane` dump; directory + place; trust one-liner; tall drawers have no empty filler; short drawers keep request over trust; git when option on.
- [ ] **Step 2: Run** `python3 tests/codex_panel.py` and `python3 tests/harnesses.py` — expect failures on old layout.
- [ ] **Step 3: Commit** test expectations with the implementation in Task 2 (single commit preferred for this repo’s style unless tests land first cleanly).

### Task 2: Implement `agent-preview` field card + 25% default

**Files:**
- Modify: `scripts/agent-preview`
- Modify: `scripts/ui-options.sh` (default `25%`)
- Modify: plugin/docs defaults wherever `35%` is documented for preview height

**Interfaces:**
- Reads `@tmux_canopy_target` from `TMUX_PANE` (sidebar) for `●`
- Calls `canopy_git_root` / `canopy_git_branch` when gated
- Emits ANSI styles as today (mono/ascii respected)

- [ ] **Step 1: Implement card emission** with budget-aware keep order above.
- [ ] **Step 2: Change default preview height** to `25%` in `ui-options.sh` and docs.
- [ ] **Step 3: Run** `python3 tests/codex_panel.py`, `python3 tests/harnesses.py`, `python3 tests/preview.py`, and any git-adjacent coverage needed.
- [ ] **Step 4: Update** README, `docs/reference.md`, `scripts/help`, `CHANGELOG.md` Unreleased.

### Task 3: Spec/plan docs committed with the feature

**Files:**
- `docs/superpowers/specs/2026-10-16-agent-inspector-design.md`
- `docs/superpowers/plans/2026-10-16-agent-inspector.md`

- [ ] **Step 1: Commit** implementation + docs together when the user asked for commits, or leave uncommitted if only code was requested; prefer one commit: `make agent inspector a fixed field card`.
