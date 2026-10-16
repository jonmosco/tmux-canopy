# Theme inheritance (soft palette)

Date: 2026-10-16  
Status: approved for implementation

## Problem

Canopy’s sidebar uses fixed ANSI accents (cyan pointer, green active dot, yellow
attention, gray selection). Users with Catppuccin, Nord, or other tmux themes
see a sidebar that does not match their status line and borders.

## Goals

1. Make `@tmux-canopy-theme 'ansi'` (default) inherit fzf chrome and tree
   semantic accents from tmux styles when those styles have real colors.
2. Keep today’s hard-coded palette available as `@tmux-canopy-theme 'fixed'`.
3. Leave `mono` unchanged.
4. Sample once when the sidebar opens; close/reopen to pick up theme changes.

## Non-goals (this pass)

- Live restyle of fzf `--color` without reopen
- Independent Canopy palette tables for every UI slot
- Recoloring application icons
- Lazygit chrome / layout changes

## Decisions

| Topic | Choice |
|---|---|
| Scope | fzf chrome + semantic accents (active / attention / accent) |
| Default | `ansi` inherits; escape hatch is `fixed` |
| Sample timing | Sidebar open only (`CANOPY_THEME_FROZEN`) |
| Option surface | Extend `@tmux-canopy-theme`: `ansi` \| `fixed` \| `mono` |

## Color map

| Role | tmux source (first usable color) | Consumers |
|---|---|---|
| Accent | `mode-style` → `pane-active-border-style` → `status-style` fg | fzf pointer/prompt/hl; tree accent; Processes/Buffers header |
| Active | `pane-active-border-style` fg | tree green `●` / `▶` |
| Attention | `message-style` → `message-command-style` fg | tree `!` / needs-input / warnings |
| Selection bg | `status-style` bg | subtle `bg+` unless `@tmux-canopy-selection-background` is set |
| Border | `pane-border-style` fg | fzf border / scrollbar / preview label |

`default` / empty / unreadable → that slot keeps today’s fixed ANSI value.

### Precedence

`mono` → `fixed` → `ansi` (inherit with per-slot fallback) → explicit
`@tmux-canopy-selection-background` overrides selection bg on color themes.

## Architecture

- `scripts/theme-lib.sh`: parse style attributes; `canopy_theme_resolve` fills
  `CANOPY_COLOR_*_FZF` and `CANOPY_COLOR_*_ANSI` (and freezes when requested).
- `scripts/ui-options.sh`: build fzf `--color` from resolved FZF values.
- `scripts/sidebar`: resolve + freeze + export before starting fzf.
- `scripts/tree-source`: ensure colors are resolved for awk `ENVIRON` when not
  already frozen (CLI / tests).
- `lib/tree-render.awk`: when theme is not `mono`/`fixed`, prefer env ANSI for
  `green` / `accent` / `attention`.

## Tests

- Parser unit cases (named, colourN, #rrggbb, default, missing).
- Private tmux: distinct styles + `ansi` → fzf string and tree ANSI differ from
  fixed; `fixed` ignores styles; `mono` stays colorless; explicit selection bg
  wins.

## Docs

README, `docs/reference.md`, CHANGELOG, ROADMAP (tmux derive partially done).
