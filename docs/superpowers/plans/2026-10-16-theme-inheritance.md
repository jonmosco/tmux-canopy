# Theme inheritance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** `@tmux-canopy-theme 'ansi'` inherits fzf chrome and tree semantic accents from tmux styles; `fixed` keeps today’s palette; sample on sidebar open only.

**Architecture:** `theme-lib.sh` samples and resolves colors; `ui-options.sh` / `tree-render.awk` / `view-header` consume them; sidebar freezes exports for the fzf process lifetime.

**Tech Stack:** Bash 4.4+, awk, fzf `--color`, private tmux in Python tests.

## File map

| File | Role |
|---|---|
| `scripts/theme-lib.sh` | Parse styles; resolve/freeze palette |
| `scripts/ui-options.sh` | fzf `--color` from resolved values |
| `scripts/sidebar` | Resolve + freeze + export at open |
| `scripts/tree-source` | Export ANSI env for awk when needed |
| `lib/tree-render.awk` | Prefer env for green/accent/attention |
| `scripts/view-header` | Accent from env when set |
| `tests/theme.py` | Parser + private-tmux suite |
| Docs | README, reference, CHANGELOG, ROADMAP |

## Tasks

### Task 1: Failing theme tests

Write `tests/theme.py` covering parser cases and private-tmux inherit/fixed/mono/selection override. Run → fail. Add suite to `tests/run.sh`.

### Task 2: `theme-lib.sh` + wire consumers

Implement resolve/parse; wire ui-options, sidebar, tree-source, awk, view-header. Run `tests/theme.py` → pass.

### Task 3: Docs + full suite

Update README/reference/CHANGELOG/ROADMAP. Run `bash tests/run.sh`.
