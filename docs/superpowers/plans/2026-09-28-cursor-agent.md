# Cursor Agent (`cursor-agent`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect the Cursor Agent CLI process `agent` as Canopy kind `cursor-agent`, install observational hooks into `~/.cursor/hooks.json`, and report lifecycle + subagent state in the Agents view.

**Architecture:** Extend the shared `agent-hook` reporter (same path as Claude/Gemini). Map process basename `agent` → kind `cursor-agent`. Teach `canopy` a Cursor-flat hooks.json merge (list of `{command}` objects, not Claude nested matcher groups). Agents view label is `cursor-agent`; Tree keeps command `agent`. No needs-input in v1.

**Tech Stack:** Bash/tmux, Python 3 reporters, awk tree render, Cursor `~/.cursor/hooks.json` (schema version 1).

## Global Constraints

- Kind / install ID: `cursor-agent`; process basename: `agent`
- Config path: `~/.cursor/hooks.json` (user-global only)
- Observational only: exit 0; never register shell/tool permission hooks; never emit deny/ask
- `subagentStart` stdout exception: fail-open `{"permission":"allow"}`; all other events `{}`
- `stop` / `subagentStop` install entries set `loop_limit: null`
- No `NEEDS INPUT` from hooks in v1
- Status column width must fit `cursor-agent` (12 chars) — use `{kind:12}` in `canopy` status/live output
- Spec: `docs/superpowers/specs/2026-09-28-cursor-agent-design.md`

---

## File structure

| File | Responsibility |
|------|----------------|
| `lib/agent_kinds.py` | Map `agent` → `cursor-agent`; NAMES entry |
| `lib/agent-process.sh` | Process name match for `cursor-agent` |
| `lib/codex-hook.py` | `process_identity` names for `cursor-agent` → `{agent}` |
| `lib/tree-render.awk` | Detect `agent`, normalize kind, Agents-view label, icons |
| `lib/agent-hook.py` | Event mapping, session/subagent IDs, stdout, main allow-list |
| `lib/subagent_state.py` | Optional helpers for Cursor subagent id/type + type-fallback stop |
| `docs/cursor-agent-hooks.example.json` | Install template (flat Cursor schema) |
| `canopy` | Kind registration, config path, flat merge/remove/status, self-test, column width |
| `tests/agent_reporting.py` | Lifecycle + subagent semantics |
| `tests/setup.py` | Install/uninstall/status for flat hooks.json |
| `tests/icons.py` | Glyph/color for command `agent` |
| `tests/harnesses.py` | Optional live pane smoke for `cursor-agent` |
| `README.md`, `docs/reference.md`, `CHANGELOG.md` | User-facing docs |

---

### Task 1: Process detection + Agents view label + icons

**Files:**
- Modify: `lib/agent_kinds.py`
- Modify: `lib/agent-process.sh`
- Modify: `lib/codex-hook.py` (`process_identity` names map)
- Modify: `lib/tree-render.awk` (agent process scan, normalize, `agent_name`, icon matchers)
- Modify: `tests/icons.py`
- Test: `python3 tests/icons.py`

**Interfaces:**
- Consumes: existing `KINDS` / awk agent scan patterns
- Produces: process `agent` → kind `cursor-agent`; Agents view label `cursor-agent`; Tree still shows raw `agent`

- [ ] **Step 1: Extend `tests/icons.py` expectations for `agent`**

Add `agent` alongside other agent commands in the nerdfont/unicode tables (reuse a distinct glyph — prefer `◎` unicode / matching nerdfont robot-style glyph already used for `pi`/`opencode`, or the same yellow family as Claude if color-keyed — pick one and keep tests consistent). Include `agent` in the ansi theme key list if present.

- [ ] **Step 2: Run icons test to verify it fails**

Run: `python3 tests/icons.py`  
Expected: FAIL on missing `agent` glyph/color handling

- [ ] **Step 3: Implement detection + display**

`lib/agent_kinds.py`:
```python
KINDS = {
    'codex': 'codex',
    'claude': 'claude', 'claude-code': 'claude',
    'opencode': 'opencode',
    'gemini': 'gemini',
    'pi': 'pi', 'omp': 'omp',
    'agy': 'agy',
    'agent': 'cursor-agent',
}

NAMES = {
    'codex': 'Codex', 'claude': 'Claude Code', 'opencode': 'OpenCode',
    'gemini': 'Gemini CLI', 'pi': 'Pi', 'omp': 'Oh My Pi',
    'agy': 'Antigravity', 'cursor-agent': 'cursor-agent',
}
```

`lib/agent-process.sh` — add `cursor-agent:agent` to `canopy_agent_name_matches`.

`lib/codex-hook.py` — in `process_identity` names map add `"cursor-agent": {"agent"}`.

`lib/tree-render.awk`:
- In process scan: `else if (name=="agent") agent_process[pid]="cursor-agent"`
- In normalize: accept `cursor-agent`
- `agent_name`: `if (kind == "cursor-agent") return "cursor-agent"`
- Icon color/glyph branches: treat `agent` like other agents (same glyph choice as Step 1)
- Add `agent` to `nicons` / icon_keys split list if required for overrides

- [ ] **Step 4: Run icons test to verify it passes**

Run: `python3 tests/icons.py`  
Expected: `ok - command-aware icon colors...`

- [ ] **Step 5: Commit**

```bash
git add lib/agent_kinds.py lib/agent-process.sh lib/codex-hook.py lib/tree-render.awk tests/icons.py
git commit -m "Detect Cursor Agent CLI process as cursor-agent."
```

---

### Task 2: Reporter lifecycle + subagent mapping

**Files:**
- Modify: `lib/subagent_state.py` (Cursor id/type helpers + type-fallback stop)
- Modify: `lib/agent-hook.py`
- Modify: `tests/agent_reporting.py`
- Test: `python3 tests/agent_reporting.py`

**Interfaces:**
- Consumes: kind `cursor-agent`; Cursor stdin JSON with `hook_event_name`, `conversation_id` / `session_id`, `subagent_id`, `subagent_type`
- Produces: pane options `source=cursor-agent-hook`, statuses `ready|working|turn-ended|session-ended`, subagent child lines; `main()` accepts `cursor-agent` and prints `{"permission":"allow"}` only for `subagentStart`

- [ ] **Step 1: Write failing reporter tests**

Append to `tests/agent_reporting.py`:

```python
# Cursor Agent: conversation_id session key, camelCase events, no needs-input.
state = harness("cursor-agent")
send("cursor-agent", {"hook_event_name": "sessionStart", "conversation_id": "c1"})
check(state.get("status") == "ready" and state.get("session") == "c1", "cursor-agent sessionStart")
send("cursor-agent", {"hook_event_name": "beforeSubmitPrompt", "conversation_id": "c1"})
check(state.get("status") == "working", "cursor-agent beforeSubmitPrompt")
send("cursor-agent", {"hook_event_name": "subagentStart", "conversation_id": "c1",
                      "subagent_id": "s1", "subagent_type": "explore"})
check("s1," in state.get("subagents", "") and "explore" in state.get("subagents", ""),
      f"cursor-agent subagentStart: {state}")
send("cursor-agent", {"hook_event_name": "subagentStop", "conversation_id": "c1",
                      "subagent_id": "s1", "subagent_type": "explore"})
check("s1," not in state.get("subagents", ""), f"cursor-agent subagentStop by id: {state}")
send("cursor-agent", {"hook_event_name": "subagentStart", "conversation_id": "c1",
                      "subagent_id": "s2", "subagent_type": "shell"})
send("cursor-agent", {"hook_event_name": "subagentStop", "conversation_id": "c1",
                      "subagent_type": "shell"})  # id omitted — unique type fallback
check("s2," not in state.get("subagents", ""), f"cursor-agent subagentStop by type: {state}")
send("cursor-agent", {"hook_event_name": "stop", "conversation_id": "c1"})
check(state.get("status") == "turn-ended", "cursor-agent stop")
send("cursor-agent", {"hook_event_name": "sessionEnd", "conversation_id": "c1"})
check(state.get("status") == "session-ended" and not state.get("subagents"),
      "cursor-agent sessionEnd clears subagents")
send("cursor-agent", {"hook_event_name": "sessionStart", "conversation_id": "c2"})
send("cursor-agent", {"hook_event_name": "stop", "conversation_id": "c1"})
check(state.get("session") == "c2" and state.get("status") == "ready",
      "late cursor-agent event cannot overwrite new session")
# session_id fallback when conversation_id absent
state = harness("cursor-agent")
send("cursor-agent", {"hook_event_name": "sessionStart", "session_id": "legacy-1"})
check(state.get("session") == "legacy-1", "cursor-agent session_id fallback")
```

Also extend the contract allow-list test to accept `"cursor-agent"` if that assertion lists kinds explicitly.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 tests/agent_reporting.py`  
Expected: FAIL (unknown kind / no mapping)

- [ ] **Step 3: Implement reporter + subagent helpers**

In `lib/subagent_state.py`, add:

```python
def cursor_agent_id(event):
    value = event.get('subagent_id') or event.get('agent_id')
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value) else ''


def with_cursor_subagent_fields(event):
    """Copy Cursor field names into the Claude-shaped keys update_subagent expects."""
    out = dict(event)
    if not out.get('agent_type') and isinstance(out.get('subagent_type'), str):
        out['agent_type'] = out['subagent_type']
    return out


def resolve_cursor_stop_id(event, current_text):
    """Prefer subagent_id; else unique live child matching subagent_type."""
    direct = cursor_agent_id(event)
    if direct:
        return direct
    wanted = list_field(event.get('subagent_type'), 40)
    if not wanted:
        return ''
    matches = [entry[0] for entry in parse_subagents(current_text)
               if entry[2] != 'done' and entry[1] == wanted]
    return matches[0] if len(matches) == 1 else ''
```

In `lib/agent-hook.py`:

1. Import the new helpers.
2. `normalized`: for `kind == 'cursor-agent'`, read `hook_event_name` and map:
   - `sessionStart` → `ready`
   - `beforeSubmitPrompt` → `working`
   - `stop` → `turn-ended`
   - `sessionEnd` → `session-ended`
   - `subagentStart` → `subagent-start`
   - `subagentStop` → `subagent-stop`
3. Event name source: treat `cursor-agent` like `claude`/`gemini` for `hook_event_name`.
4. `session_id`: if kind is `cursor-agent`, `core.field(event.get('conversation_id') or event.get('session_id'), 128)`.
5. `subagent_id`: for `cursor-agent`, use `cursor_agent_id(event)`; on `subagentStop` with empty id, `resolve_cursor_stop_id(event, current['subagents'])` (call after `current` is loaded in `report`, or pass current into a small helper used from `report`).
6. Before `next_entries` for cursor-agent, pass `with_cursor_subagent_fields(event)`.
7. Session start tuple includes `'sessionStart'`.
8. Contract allow-list includes `'cursor-agent'`.
9. `main()` allow-list includes `'cursor-agent'`. After `report`, if `kind == 'cursor-agent'` and event `hook_event_name == 'subagentStart'`, `print('{"permission":"allow"}')`; else for cursor-agent print `{}` only when needed — simplest: always `print('{}')` except subagentStart prints allow. (Hooks that ignore stdout are fine with `{}`.)

Important: read stdin once; decide response from parsed `hook_event_name`. Never print `followup_message`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 tests/agent_reporting.py`  
Expected: exits 0 (existing prints + new checks)

- [ ] **Step 5: Commit**

```bash
git add lib/agent-hook.py lib/subagent_state.py tests/agent_reporting.py
git commit -m "Report Cursor Agent lifecycle and subagent hook events."
```

---

### Task 3: Installer template + flat `hooks.json` merge

**Files:**
- Create: `docs/cursor-agent-hooks.example.json`
- Modify: `canopy` (KINDS, EXECUTABLES, TEMPLATES, `config_path`, merge/remove/count/state/change, SELF_TEST_EVENTS, status width `{kind:12}`)
- Modify: `tests/setup.py`
- Test: `python3 tests/setup.py`

**Interfaces:**
- Consumes: template with flat Cursor hook entries
- Produces: `canopy integration install|uninstall|status cursor-agent` against `~/.cursor/hooks.json`

- [ ] **Step 1: Add example template**

Create `docs/cursor-agent-hooks.example.json`:

```json
{
  "version": 1,
  "hooks": {
    "sessionStart": [
      {"command": "/absolute/path/to/tmux-canopy/scripts/agent-hook cursor-agent", "timeout": 3}
    ],
    "beforeSubmitPrompt": [
      {"command": "/absolute/path/to/tmux-canopy/scripts/agent-hook cursor-agent", "timeout": 3}
    ],
    "stop": [
      {"command": "/absolute/path/to/tmux-canopy/scripts/agent-hook cursor-agent", "timeout": 3, "loop_limit": null}
    ],
    "sessionEnd": [
      {"command": "/absolute/path/to/tmux-canopy/scripts/agent-hook cursor-agent", "timeout": 3}
    ],
    "subagentStart": [
      {"command": "/absolute/path/to/tmux-canopy/scripts/agent-hook cursor-agent", "timeout": 3}
    ],
    "subagentStop": [
      {"command": "/absolute/path/to/tmux-canopy/scripts/agent-hook cursor-agent", "timeout": 3, "loop_limit": null}
    ]
  }
}
```

- [ ] **Step 2: Write failing setup coverage**

In `tests/setup.py`, extend install/uninstall/status lists to include `cursor-agent`. Seed `HOME/.cursor/hooks.json` with an unrelated hook entry to prove preservation. Assert installed commands contain `agent-hook cursor-agent`, `version == 1`, `loop_limit` is null on stop/subagentStop, and unrelated entries survive uninstall. Widen assertions from `{kind:9}` to `{kind:12}` for all kinds (or assert with startswith / regex) so `cursor-agent` fits.

Also assert status column still lines up for shorter kinds.

- [ ] **Step 3: Run setup test to verify failure**

Run: `python3 tests/setup.py`  
Expected: FAIL (unknown choice `cursor-agent` or missing path)

- [ ] **Step 4: Implement canopy installer support**

In `canopy`:

```python
KINDS = ("codex", "claude", "gemini", "agy", "pi", "omp", "opencode", "cursor-agent")
EXECUTABLES = {..., "cursor-agent": "agent"}
TEMPLATES = {..., "cursor-agent": "cursor-agent-hooks.example.json"}
```

`config_path`:
```python
if kind == "cursor-agent":
    return home / ".cursor" / "hooks.json"
```

`template("cursor-agent")` uses JSON replace like codex/claude (PLACEHOLDER → quoted ROOT).

Add Cursor-flat helpers (names illustrative — keep style consistent with file):

```python
def is_cursor_entry(item, kind):
    return isinstance(item, dict) and is_ours(item.get("command"), kind)

def count_cursor_hooks(data, kind):
    return sum(1 for groups in data.get("hooks", {}).values() if isinstance(groups, list)
               for item in groups if is_cursor_entry(item, kind))

def merge_cursor_hooks(data, kind):
    data.setdefault("version", 1)
    hooks = data.setdefault("hooks", {})
    for event, entries in template(kind)["hooks"].items():
        existing = hooks.setdefault(event, [])
        if not isinstance(existing, list):
            raise ValueError(f"{event}: expected a hook list")
        wanted = entries[0]
        found = False
        for item in existing:
            if is_cursor_entry(item, kind):
                item.clear(); item.update(wanted); found = True; break
        if not found:
            existing.append(dict(wanted))

def remove_cursor_hooks(data, kind):
    for event, groups in list(data.get("hooks", {}).items()):
        if not isinstance(groups, list):
            continue
        kept = [item for item in groups if not is_cursor_entry(item, kind)]
        if kept:
            data["hooks"][event] = kept
        else:
            del data["hooks"][event]
    if not data.get("hooks"):
        data.pop("hooks", None)
```

Wire `integration_state` / `change` for `cursor-agent` similarly to codex/claude but using the Cursor helpers (compare expected event commands for installed vs outdated path vs partial).

`SELF_TEST_EVENTS`:
```python
"cursor-agent": ({"hook_event_name": "beforeSubmitPrompt", "conversation_id": "self-test"}, "working"),
```

Widen `status` / `show_live_agents` / error prints from `{kind:9}` to `{kind:12}`.

- [ ] **Step 5: Run setup + doctor self-test path**

Run: `python3 tests/setup.py`  
Expected: all `ok - ...` lines

Run: `./canopy integration status cursor-agent` (may be absent) and ensure no crash.

Optionally run reporter self-test via importing or `./canopy doctor` if cheap enough in this environment.

- [ ] **Step 6: Commit**

```bash
git add docs/cursor-agent-hooks.example.json canopy tests/setup.py
git commit -m "Add cursor-agent integration install for Cursor hooks.json."
```

---

### Task 4: Docs + CHANGELOG

**Files:**
- Modify: `README.md`
- Modify: `docs/reference.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update user docs**

README: add Cursor Agent / `cursor-agent` to the agents list and install examples (`canopy integration install cursor-agent`).

reference.md:
- Supported process list includes Cursor Agent (`agent` → `cursor-agent`)
- Contract `agent` enum includes `cursor-agent`
- Adapter section: merge `docs/cursor-agent-hooks.example.json` into `~/.cursor/hooks.json`; note no needs-input; subagent fail-open allow; CLI hook coverage caveat; restart `agent` after install
- Icon table: document `agent` command if other agents are listed

CHANGELOG: under Unreleased/Added — Cursor Agent (`cursor-agent`) process detection and optional lifecycle adapter.

- [ ] **Step 2: Sanity grep**

Run: `rg -n "cursor-agent|Cursor Agent" README.md docs/reference.md CHANGELOG.md`  
Expected: hits in all three

- [ ] **Step 3: Commit**

```bash
git add README.md docs/reference.md CHANGELOG.md
git commit -m "Document cursor-agent adapter and detection."
```

---

### Task 5: Harness smoke (optional but recommended)

**Files:**
- Modify: `tests/harnesses.py` if extending the multi-agent harness is low-cost
- Test: `python3 tests/harnesses.py` (requires tmux)

- [ ] **Step 1: Add `agent` fixture pane named for cursor-agent**

Install a fixture binary named `agent` (copy existing agent fixture pattern). Fire `sessionStart` / `beforeSubmitPrompt` via `event('cursor-agent', pane, {...})`. Assert Agents/tree preview shows `WORKING` or `cursor-agent` label as appropriate for that harness’s assertions.

If harness runtime is heavy or flaky in CI, keep coverage in `agent_reporting.py` + `setup.py` and skip this task — note the skip in the commit message.

- [ ] **Step 2: Run harness**

Run: `python3 tests/harnesses.py`  
Expected: pass

- [ ] **Step 3: Commit if changes were made**

```bash
git add tests/harnesses.py
git commit -m "Exercise cursor-agent hooks in the multi-agent harness."
```

---

## Spec coverage check

| Spec requirement | Task |
|------------------|------|
| Detect process `agent` as `cursor-agent` | Task 1 |
| Agents view label `cursor-agent`; Tree raw `agent` | Task 1 |
| Icons for `agent` | Task 1 |
| Shared `agent-hook` reporter | Task 2 |
| Event map sessionStart/beforeSubmitPrompt/stop/sessionEnd | Task 2 |
| Subagents + type-fallback stop | Task 2 |
| Fail-open allow on subagentStart only | Task 2 |
| No needs-input | Task 2 (omitted mapping) |
| `~/.cursor/hooks.json` flat install | Task 3 |
| `loop_limit: null` on stop/subagentStop | Task 3 |
| doctor self-test | Task 3 |
| Docs/CHANGELOG | Task 4 |
| Optional live harness | Task 5 |

## Placeholder / consistency notes

- Kind string is always `cursor-agent` in installers/reporters; process match is always `agent`.
- Report source is `cursor-agent-hook` via existing `kind + '-hook'` pattern.
- Status format width `{kind:12}` updated wherever `{kind:9}` would truncate.
