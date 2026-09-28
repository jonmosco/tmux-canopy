# Lazygit appearance, create-refresh, and WORKING animation

Date: 2026-09-28  
Status: approved for planning

## Problem

Canopy’s sidebar works well but looks dated next to modern terminal TUIs (lazygit, yazi). Pane creation does not refresh the tree until the user selects another pane, so new rows appear late. Optional WORKING status motion is already sketched on the roadmap but not specified for this workstream.

## Goals

1. Opt-in **lazygit** appearance preset; keep today’s look as **classic** (default).
2. Reload the tree when a pane is **created**, not only after a later focus change.
3. Follow-up: opt-in **WORKING** status highlight animation without a permanent daemon.
4. Light focus-path cleanup only where it supports create/focus remaining a single paint.

## Non-goals

- Full megafile splits (`tree-action`, `tree-render.awk`) or shared hook-core refactor.
- Broad Agents inventory / `/proc` rewrite.
- Changing slot vs move window transitions (`@tmux-canopy-transition`).
- Making lazygit the default appearance.

## Decisions

| Topic | Choice |
|-------|--------|
| Visual direction | Lazygit chrome (box header, rounded branches, structural glyphs) |
| Delivery | Appearance preset `classic` \| `lazygit` (Approach 2) |
| Transitions (user-facing) | Snappy create/focus refresh now; WORKING motion as follow-up |
| Perf/cleanup depth | Create-refresh + light double-rebuild cleanup; not a full audit |
| Default appearance | `classic` |

## Section 1 — Appearance preset

### Option

```tmux
set -g @tmux-canopy-appearance 'classic'   # default
set -g @tmux-canopy-appearance 'lazygit'
```

Place before the Canopy `run-shell` / TPM plugin line. After changing: reload tmux config, then **close and reopen** the sidebar (same as density/position). Ctrl-r alone does not restyle a running fzf process.

### Behavior

**classic** — current tree: ▸/▾ folds, `├─`/`└─`/`│` guides, header `[Tree] Proc Buff · All`, session/window glyphs only when customized, app icons from `@tmux-canopy-icon-theme`.

**lazygit** — box-style header (`╭─ Tree Proc Buff ─ All ╮`), rounded end branches (`╰─`), cyan-leaning fold chevrons, session/window/pane structural glyphs when icon theme is `nerdfont` (unicode stand-ins `◈`/`▣`/`▹` otherwise). Active `●`, unread, and agent badges keep the same meaning.

`@tmux-canopy-icon-theme` (`auto`/`unicode`/`ascii`/`nerdfont`) still controls app glyphs and ASCII fallbacks. Appearance only changes chrome and which structural glyphs are shown by default.

### Implementation sketch

- Normalize and store `@tmux_canopy_appearance` in `tmux-canopy.tmux`.
- Pass appearance on the existing `D` record from `scripts/tree-source` into `lib/tree-render.awk`.
- Adjust fzf pointer/prompt/scrollbar chrome in `scripts/ui-options.sh` when appearance is `lazygit`.
- Non-tree headers (`scripts/view-header`) follow the same preset for tab chrome consistency.

## Section 2 — Structural refresh on create

### Problem evidence

Focus hooks today: `after-select-pane`, `after-select-window`, `after-new-window`, `client-session-changed` (`tmux-canopy.tmux`). Renames/kills call `cleanup refresh` → `C-r`. There is **no** `after-split-window` path, so native (and sometimes raced) splits leave the tree stale until a later select-pane refresh.

### Behavior

1. On `after-split-window`, trigger an owner-aware tree reload (same family as `refresh_sidebars` / rename refresh) so the new pane row appears immediately.
2. Canopy `s`/`v`/`t`/`S` create actions keep post-action `reload-sync`; ensure the reload runs after the pane exists and is not defeated by a focus race.
3. Light cleanup: where focus already schedules `C-o` then `C-r`, collapse to one rebuild when a reload is required, so create/focus stays one paint.

### Reload vs reopen

Hook install needs a **plugin/config reload** once. An already-open sidebar picks up the new hook without closing. Appearance still requires close/reopen.

## Section 3 — WORKING animation (follow-up)

- Option: `@tmux-canopy-animate on` (default off).
- When a visible row shows WORKING, a short-lived worker redraws only that status word with a moving highlight (~5–8 fps) from a cached snapshot (~2–3ms), not a full source reload (~60ms).
- Worker starts only when a working row is drawn; exits when none remain, the sidebar is hidden, or its pane closes.
- `mono` and animate-off stay static; all existing tests remain static unless an animate-specific suite is added.
- Ship after appearance + create-refresh are stable; may be a separate PR/plan step.

## Section 4 — Testing and docs

- Appearance: classic vs lazygit × unicode/nerdfont/ascii (extend `tests/icons.py` and a rendering case for header/guides).
- Create refresh: assert a split makes the new pane row visible without selecting another pane first.
- Animate (later): static when off/mono; worker lifecycle when on.
- Docs: README defaults and `docs/reference.md` for appearance, create-refresh, and later animate.
- Ignore brainstorm artifacts: `.superpowers/` in `.gitignore`.

## Rollout order

1. Appearance preset + docs/tests (classic default).
2. `after-split-window` create-refresh + light double-rebuild cleanup + tests.
3. Opt-in WORKING animator (follow-up).

## Success criteria

- Users can enable lazygit chrome without losing classic.
- Creating a pane updates the sidebar immediately after plugin reload.
- No permanent animation daemon; animate remains opt-in and inert when off.
