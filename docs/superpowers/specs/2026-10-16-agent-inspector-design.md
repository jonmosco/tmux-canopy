# Agent inspector field card

Date: 2026-10-16  
Status: approved for planning

## Problem

The agent drawer recently became a structured **Agent inspector** (separate from Terminal preview), but tall drawers still feel empty, identity is scattered, and Git place is missing. Competing tools (Herdr, AIHerd, agenmux) treat the sidebar as an attention surface: who needs you, and where you are — not a transcript dump.

Users want an explicit, glanceable summary: directory, agent, git repo/branch, and agent state — without noise.

## Goals

1. Replace the spacer-heavy inspector with a **fixed field card**: same field order every time, clipped lines, no blank filler rows.
2. Surface **directory**, **agent**, **git repo/branch** (when Git context is on), and **explicit state**, plus one dim **trust** line.
3. Keep a **request/command block** only when present, **below** the identity card.
4. Shorten the shared preview drawer default so the card is not surrounded by empty space.
5. Make **tmux place** obvious by reusing the tree’s green `●` active-location language.

## Non-goals

- Mode-specific drawer heights (inspector vs Terminal preview keep one geometry on `i`).
- Putting terminal excerpts, agent TUI footers, or screen transcripts back into the inspector.
- Renaming Canopy’s lifecycle vocabulary to Herdr’s idle/working/blocked triad.
- New Git polling, `git status`, or changing repository state.
- Changing tree badges, `n` jump, `>` reply, or Terminal preview content.
- Focusing content panes while browsing the sidebar solely to “sync” location.

## Decisions

| Topic | Choice |
|-------|--------|
| Layout | Approach 1: fixed field card |
| Request placement | Below identity; only when request and/or command (or unverified hint) exists |
| Trust detail | One dim line under state (not full tool·source·age provenance) |
| Drawer height | Shared default `@tmux-canopy-preview-height` `35%` → `25%` |
| Git in inspector | Same opt-in as tree/pane preview: `@tmux-canopy-git-context 'branch'` |
| Place line | Dim `session:index window` (e.g. `acme-api:0 web`); prefix green `●` iff selected pane is this client’s active content target |
| Dropped from inspector | Pane title, session/window/pane id dump as primary metadata, multi-part provenance, long “unavailable” essays, blank section padding |

## Content model

Order is fixed. Lines clip; they never wrap. No blank spacer rows except a single blank line before the request block when that block is shown.

| Order | Field | When shown | Rendering |
|-------|--------|------------|-----------|
| 1 | State · Agent | Always | Left: explicit state (`Needs input`, `Working`, `Ready`, `Turn ended`, `Interrupted`, `Session ended`, `Detected`, `Stale report`, `Unknown`, `No agent`, …). Right: agent name when width allows; else `State · Agent`. Attention color for needs-input / interrupted; cyan for working; dim for detected / stale / unknown. |
| 2 | Trust | When an agent is present | One dim line: verified reports use `lifecycle hook · 12s` (OpenCode: `plugin · 12s`); process-only uses `snapshot only`. Age is seconds since the last accepted report. |
| 3 | Directory | Always | Home-shortened path (`~/…`). |
| 4 | Git | When git-context is `branch` and a root exists | `reponame ⎇ branch` (ASCII: `[git:branch]`). Repo = basename of git root. Detached HEAD: `detached@…`. |
| 5 | Place | Always for a resolvable pane | `● session:index window` when this pane is the client’s active content target; otherwise the same text without the dot. Same meaning as the tree legend. |
| 6 | Request block | Only when verified request/command exist, or an unverified screen hint matched | Optional blank line, then request text, then amber `│ command` when present. Unverified hints use an explicit label on this block (e.g. `Possible input requested (unverified):`); that label is not duplicated on the trust line. |

### Short-drawer priority

If `FZF_PREVIEW_LINES` cannot fit the full card, drop from the bottom of the identity fields first, but **never** drop state/agent ahead of directory/git/place, and **never** drop a present request/command ahead of git or place:

1. Keep state/agent  
2. Keep trust when an agent is present  
3. Keep request/command when present  
4. Then directory, git, place (drop place, then git, then directory if still short)

### Modes and chrome

- Frame titles remain **Agent inspector** / **Terminal preview**.
- `i` selects mode and opens the drawer; `p` only toggles visibility.
- Both modes share drawer geometry (after the new 25% default).
- Agent awareness off (`A`) still forces terminal mode/label; restoring agents restores the inspector choice.

## Architecture

### Touch points

| Path | Change |
|------|--------|
| `scripts/agent-preview` | Build the field card; call `git-lib.sh` when gated; resolve active-place vs selection; remove spacer/rich padding and dropped fields |
| `scripts/ui-options.sh` / plugin defaults | Default preview height `25%` |
| `scripts/help` (and legend if it describes the drawer) | Match the new fields and height |
| `README.md`, `docs/reference.md`, `CHANGELOG.md` (`## Unreleased`) | Document the card, place `●`, git line, and 25% default |
| `docs/assets/inspector-runtime-captures.html` / visual study notes | Update when captures are regenerated |
| `tests/preview.py`, `tests/codex_panel.py` (and harnesses as needed) | Assert order, git, `●`, no blank padding, request gating, default height |

### Git

Reuse `scripts/git-lib.sh`:

- Gate on `@tmux-canopy-git-context == branch` and `command -v git`.
- `canopy_git_root` then `canopy_git_branch`; no status, no polling.
- One lookup per preview invocation for that pane’s directory (preview already runs per selection; do not add a per-row loop).

### Active place

Compare the previewed pane id to the **same client content target** that drives the tree’s green `●` (not “pane under keyboard focus while the sidebar owns the client”). If the target is unavailable, omit the dot and still show `session:window` when metadata is present.

## Error / empty states

| Situation | Card behavior |
|-----------|----------------|
| No supported agent | State `No agent`, agent `Terminal`, no trust line, directory + place (+ git if on); no request inference |
| Process-only agent | State `Detected`, trust `snapshot only`; optional unverified request hint only |
| Stale / unknown report | Explicit state word; trust shows age/source briefly; no invented request |
| Needs-input without details | State remains explicit; omit empty request lines rather than long essays |
| Not a git work tree | Omit git line entirely |
| Git context off | Omit git line entirely |
| Pane gone / sidebar pane | Existing short messages; no fake card |

## Testing

- Field order for needs-input with command, working with no request, detected, and no-agent.
- Git line appears only when the option is `branch` and a root exists; repo basename + branch (and detached form).
- `●` present only when the selected pane is the client’s active content target; absent when browsing elsewhere.
- No blank filler rows when the drawer is tall; at most one blank before a present request block.
- Default preview height is `25%`.
- Unverified screen hints remain labeled; verified hooks do not run screen inference.
- Existing frame/mode/`i`/`p` behavior unchanged except height default and card content.

## Success criteria

- In one glance: agent, state, directory, git (if enabled), and whether this pane is *here* (`●`).
- When blocked: the ask sits under that card without displacing it.
- Drawer feels shorter by default; Terminal preview still usable via crop + user-raised height.
- No new daemons, polls, or runtime dependencies.
