# Cursor Agent (`cursor-agent`) lifecycle adapter

Date: 2026-09-28  
Status: approved for planning

## Problem

Canopy agent awareness detects Codex, Claude Code, OpenCode, Gemini CLI, Antigravity, Pi, and Oh My Pi, but not the Cursor Agent CLI. Panes whose process is `agent` never appear in the Agents view and have no installable lifecycle hooks, even though Cursor exposes `~/.cursor/hooks.json` events the CLI can fire.

## Goals

1. Detect the live process named **`agent`** as Canopy kind **`cursor-agent`**.
2. Install an observational adapter via `canopy integration install cursor-agent` into `~/.cursor/hooks.json`.
3. Report lifecycle state (`READY` / `WORKING` / `TURN ENDED` / `SESSION ENDED`) with a `·hook` origin when events fire.
4. Show subagent child lines from `subagentStart` / `subagentStop` when Cursor supplies usable identities.
5. In the Agents view, label the kind **`cursor-agent`** for clarity; Tree keeps the real command `agent`.

## Non-goals

- `NEEDS INPUT` / approval state from hooks (Cursor has no `PermissionRequest`; drawer keeps unverified screen hints).
- Registering shell/tool permission hooks (`beforeShellExecution`, `preToolUse`, `beforeMCPExecution`, etc.).
- Project-level `.cursor/hooks.json` management (user-global only, same pattern as other adapters).
- IDE Agent Chat panes that are not a tmux `agent` process (no `TMUX_PANE` / process match → no-op).
- Renaming the Cursor binary or inventing a wrapper command.

## Decisions

| Topic | Choice |
|-------|--------|
| Approach | Extend shared `agent-hook` path (not a separate `cursor-hook.py`) |
| Kind / install ID | `cursor-agent` |
| Process basename | `agent` |
| Agents view label | `cursor-agent` |
| Tree view label | raw command `agent` |
| Config path | `~/.cursor/hooks.json` |
| Needs-input (v1) | omitted |
| Subagents (v1) | included |

## Architecture

- **Detection:** `lib/agent_kinds.py`, `lib/agent-process.sh`, `lib/agent-process.py`, and `lib/tree-render.awk` map process name `agent` → kind `cursor-agent`.
- **Reporter:** `scripts/agent-hook cursor-agent` → `lib/agent-hook.py` (shared with Claude/Gemini/Pi/etc.).
- **Installer:** `canopy` gains kind `cursor-agent` with executable check `which agent`, Cursor-flat JSON merge/remove, template `docs/cursor-agent-hooks.example.json`.
- **Binding:** accept reports only when `TMUX_PANE` is a live non-sidebar pane whose process tree contains `agent`, with the same pane/process identity checks as other adapters.
- **Display:** `agent_name("cursor-agent")` returns `cursor-agent` for Agents view rows; icons treat command `agent` like other agent apps.

## Event mapping

| Cursor hook event | Canopy state / effect |
|-------------------|------------------------|
| `sessionStart` | `ready` |
| `beforeSubmitPrompt` | `working` |
| `stop` | `turn-ended` |
| `sessionEnd` | `session-ended` |
| `subagentStart` | add/update subagent child (`WORKING`) |
| `subagentStop` | remove matching subagent child |

Session identity: prefer `conversation_id`, fall back to `session_id`.  
Subagent identity: `subagent_id` when present; type from `subagent_type` (mapped into existing child `agent_type` field).

Event name source: Cursor’s `hook_event_name` (camelCase), same field Claude/Gemini use with different spellings.

**Not installed:** permission-shaped tool/shell hooks; any path that returns deny/ask for user actions.

**CLI caveat:** Cursor Agent CLI hook coverage is still partial and version-dependent. Missing events leave the pane as `[process]` until a supported lifecycle event arrives. Hooks load at process start — restart `agent` after install.

## Installer & config shape

Cursor hooks use a flatter schema than Claude/Codex:

```json
{
  "version": 1,
  "hooks": {
    "sessionStart": [
      { "command": "/absolute/path/to/tmux-canopy/scripts/agent-hook cursor-agent", "timeout": 3 }
    ]
  }
}
```

- Merge/remove only Canopy-owned commands ending in `/scripts/agent-hook` with argv kind `cursor-agent`.
- Preserve unrelated user/plugin hooks.
- Set `loop_limit: null` on `stop` and `subagentStop` entries so Canopy never participates in follow-up loops.
- Status states: `installed` / `partial` / `outdated path` / `absent`, parallel to other JSON adapters but with Cursor’s list-of-command-objects shape.
- Doctor self-test: representative event (e.g. `beforeSubmitPrompt`) → expected `working`.

## Safety

Adapters remain observational:

- Always exit 0.
- Do not register `beforeShellExecution`, `preToolUse`, or similar permission gates.
- For most events, stdout is `{}`.
- **Exception:** Cursor treats `subagentStart` as a permission hook; invalid/missing schema can block Task subagents. For that event only, print fail-open `{"permission":"allow"}` so observation does not stall the agent. Never print `deny` or `ask`.
- `subagentStop` / `stop` must not emit `followup_message`.

## Subagent stop matching

Cursor’s published `subagentStop` schema emphasizes `subagent_type` and may omit `subagent_id`. Matching rules:

1. Prefer `subagent_id` when present (including common-schema extras if Cursor sends them).
2. Else if exactly one live child has that `subagent_type`, remove it.
3. Else no-op (do not guess among multiples).

## Testing

- Unit/harness coverage in `tests/agent_reporting.py` (and related) for Cursor event names and `conversation_id` / `subagent_id` / `subagent_type`.
- Integration merge/remove/status for `~/.cursor/hooks.json` flat schema.
- Icon/process detection for command `agent` → kind `cursor-agent`.
- Agents view display name `cursor-agent`; Tree still shows `agent`.
- Self-test path in `canopy doctor` for the new reporter.

## Docs

- README agent list + install examples include `cursor-agent`.
- `docs/reference.md` supported kinds, contract `agent` enum, and adapter notes.
- `CHANGELOG.md` entry for the new adapter.
- Example hooks file under `docs/cursor-agent-hooks.example.json`.

## Out of scope follow-ups

- Best-effort `NEEDS INPUT` if Cursor later exposes a stable approval hook.
- Project-scoped hook install.
- Richer subagent attribution if Cursor documents `subagent_id` on stop consistently.
