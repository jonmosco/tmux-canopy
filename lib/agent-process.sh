#!/usr/bin/env bash
# Process identity and ancestry helpers. Linux uses /proc without spawning ps.
canopy_ps_loaded=0
declare -gA CANOPY_PPID CANOPY_LSTART CANOPY_COMM CANOPY_KIND CANOPY_AGENT_KIND
# PIDs with a CANOPY_KIND or CANOPY_AGENT_KIND entry, so pane lookups skip the rest of the table.
declare -ga CANOPY_KIND_PIDS=() CANOPY_AGENT_PIDS=()
# Helpers also leave their result here so callers can avoid a $(...) subshell,
# which would discard the snapshot cache along with the fork.
CANOPY_REPLY=''
# Standalone Claude Code builds report their version (dots or underscores,
# e.g. 2.1.201 or 2_1_201) as kernel comm / pane_current_command.
canopy_is_claude_version() {
  [[ ${1:-} == [0-9]* && $1 =~ ^([0-9]+\.[0-9]+\.[0-9]+|[0-9]+_[0-9]+_[0-9]+)([-+][0-9A-Za-z._-]+)?$ ]]
}
# Non-Linux (no /proc) fallback: read the whole process table in one ps call
# and cache it for the lifetime of this process, instead of spawning ps per
# ancestor per pane. Safe to call repeatedly; only the first call forks ps.
canopy_ps_status=0
canopy_load_ps_snapshot() {
  ((canopy_ps_loaded)) && return "$canopy_ps_status"
  canopy_ps_loaded=1
  local pid ppid w1 w2 w3 w4 w5 argv0 rest raw
  local -a rest_args
  # args= exposes argv0 for Node CLIs whose comm is a thread name (e.g. MainThread).
  raw="$(ps -eo pid=,ppid=,lstart=,args= 2>/dev/null)"
  canopy_ps_status=$?
  while IFS=' ' read -r pid ppid w1 w2 w3 w4 w5 argv0 rest; do
    [[ $pid =~ ^[1-9][0-9]*$ ]] || continue
    CANOPY_PPID[$pid]=$ppid
    CANOPY_LSTART[$pid]="$w1 $w2 $w3 $w4 $w5"
    argv0=${argv0##*/}
    CANOPY_COMM[$pid]=${argv0%.exe}
    if canopy_agent_kind_from_name "${CANOPY_COMM[$pid]}" >/dev/null; then
      CANOPY_AGENT_KIND[$pid]=$CANOPY_REPLY
      CANOPY_AGENT_PIDS+=("$pid")
    fi
    case "${CANOPY_COMM[$pid]}" in
      node|nodejs|bun|pi|omp|hermes|hermes-agent|python|Python|python[0-9]|python[0-9].*) ;;
      *) continue ;;
    esac
    read -ra rest_args <<< "$rest"
    canopy_hosted_agent "${CANOPY_COMM[$pid]}" "${rest_args[@]}" >/dev/null || continue
    CANOPY_KIND[$pid]=$CANOPY_REPLY
    CANOPY_KIND_PIDS+=("$pid")
    if [[ -z "${CANOPY_AGENT_KIND[$pid]:-}" ]]; then
      CANOPY_AGENT_KIND[$pid]=$CANOPY_REPLY
      CANOPY_AGENT_PIDS+=("$pid")
    fi
  done <<< "$raw"
  return "$canopy_ps_status"
}
# Hermes runs as Python: its installer shim's -c launcher imports hermes_cli
# (ps splits that source into words, so any word counts), and its TUI is
# `python -m tui_gateway`. Any other Python process stays python.
canopy_hermes_args() {
  local token base module=0
  for token in "$@"; do
    [[ $token == *hermes_cli* ]] && return 0
  done
  for token in "$@"; do
    if ((module)); then
      [[ ${token%%.*} == tui_gateway ]]
      return
    fi
    [[ $token == -m ]] && { module=1; continue; }
    [[ $token == -* ]] && continue
    # The first operand is the script; anything after it is its arguments.
    base=${token##*/}
    base=${base%.exe}
    [[ $base == hermes || $base == hermes-agent ]]
    return
  done
  return 1
}
# Node/Bun-hosted CLIs (Pi, Oh My Pi, Gemini CLI, npm Claude/Codex/Copilot,
# etc.) identify from their first script operand; any other Node process stays node.
canopy_hosted_agent() {
  local host=${1:-} token base norm skip_next=0
  CANOPY_REPLY=''
  shift || true
  host=${host##*/}
  host=${host%.exe}
  case "$host" in
    pi|omp) CANOPY_REPLY=$host; printf '%s' "$host"; return 0 ;;
    hermes|hermes-agent) CANOPY_REPLY=hermes; printf 'hermes'; return 0 ;;
    node|nodejs|bun) ;;
    python|Python|python[0-9]|python[0-9].*)
      canopy_hermes_args "$@" || return 1
      CANOPY_REPLY=hermes; printf 'hermes'; return 0 ;;
    *) return 1 ;;
  esac
  while (($#)); do
    token=$1
    shift
    if ((skip_next)); then
      skip_next=0
      continue
    fi
    case "$token" in
      -r|--require|--import|--loader|--experimental-loader|-C|--conditions)
        skip_next=1; continue ;;
      -e|--eval|-p|--print|--eval=*|--print=*)
        return 1 ;;
      -*)
        continue ;;
    esac
    base=${token##*/}
    base=${base%.exe}
    case "$base" in
      pi|omp|codex|gemini|opencode|copilot|grok|cursor-agent|crush)
        CANOPY_REPLY=$base ;;
      claude|claude-code)
        CANOPY_REPLY=claude ;;
      agy|antigravity)
        CANOPY_REPLY=agy ;;
      *)
        norm="/${token#/}"
        norm=${norm//\\//}
        case "$norm" in
          */pi-coding-agent/*) CANOPY_REPLY=pi ;;
          */oh-my-pi/*) CANOPY_REPLY=omp ;;
          */@anthropic-ai/claude-code/*) CANOPY_REPLY=claude ;;
          */@google/gemini-cli/*|*/gemini-cli/*) CANOPY_REPLY=gemini ;;
          */@openai/codex/*) CANOPY_REPLY=codex ;;
          */cursor-agent/*) CANOPY_REPLY=cursor-agent ;;
          */@github/copilot/*) CANOPY_REPLY=copilot ;;
          */opencode-ai/*|*/node_modules/opencode/*) CANOPY_REPLY=opencode ;;
          *) return 1 ;;
        esac
        ;;
    esac
    if [[ $CANOPY_REPLY == codex && ( ${1:-} == app-server || ${2:-} == app-server ) ]]; then
      CANOPY_REPLY=''
      return 1
    fi
    printf '%s' "$CANOPY_REPLY"
    return 0
  done
  return 1
}
# Closest pi/omp descendant of a pane root, if Node is only hosting that CLI.
canopy_pane_agent() {
  local root=$1 pid current depth=0 best=129 found='' kind name
  CANOPY_REPLY=''
  [[ $root =~ ^[1-9][0-9]*$ ]] || return 1
  canopy_load_ps_snapshot || return 1
  for pid in "${CANOPY_KIND_PIDS[@]}"; do
    kind=${CANOPY_KIND[$pid]:-}
    [[ -n $kind ]] || continue
    current=$pid
    depth=0
    while ((depth < 128)); do
      if [[ $current != "$pid" ]]; then
        name=${CANOPY_KIND[$current]:-${CANOPY_COMM[$current]:-}}
        canopy_agent_carrier "$name" "$kind" || { depth=128; break; }
      fi
      [[ $current == "$root" ]] && break
      current=${CANOPY_PPID[$current]:-}
      [[ $current =~ ^[1-9][0-9]*$ ]] || { depth=128; break; }
      depth=$((depth + 1))
    done
    if [[ $current == "$root" && $depth -lt $best ]]; then
      best=$depth
      found=$kind
    fi
  done
  CANOPY_REPLY=$found
  [[ -n $found ]] && printf '%s' "$found"
}
# Emits "pid ppid comm" lines from the cached snapshot, for callers that only
# need a full-process-table scan (loads the snapshot on demand). The lines are
# also left in CANOPY_REPLY for callers that must keep the cache.
canopy_ps_snapshot_lines() {
  canopy_load_ps_snapshot || return 1
  local pid
  CANOPY_REPLY=''
  for pid in "${!CANOPY_PPID[@]}"; do
    # A hosted agent (Pi under node, Hermes under python) is listed as itself.
    CANOPY_REPLY+="$pid ${CANOPY_PPID[$pid]} ${CANOPY_KIND[$pid]:-${CANOPY_COMM[$pid]}}"$'\n'
  done
  printf '%s' "$CANOPY_REPLY"
}
canopy_proc_stat() {
  local line fields
  [[ $1 =~ ^[1-9][0-9]*$ && -r /proc/$1/stat ]] || return 1
  IFS= read -r line < "/proc/$1/stat" 2>/dev/null || return 1
  line=${line##*) }
  read -ra fields <<< "$line"
  [[ ${fields[1]:-} =~ ^[0-9]+$ && ${fields[19]:-} =~ ^[0-9]+$ ]] || return 1
  CANOPY_PARENT=${fields[1]}
  CANOPY_BIRTH=${fields[19]}
}
# Prefer argv0 basename from cmdline so Node-based CLIs still match.
canopy_process_name() {
  local pid=$1 proc_root=${CANOPY_PROC_ROOT:-/proc} argv0 name arg
  local -a args=()
  CANOPY_REPLY=''
  [[ $pid =~ ^[1-9][0-9]*$ ]] || return 1
  if [[ -r "$proc_root/$pid/cmdline" ]]; then
    while IFS= read -r -d '' arg || [[ -n $arg ]]; do
      args+=("$arg")
    done < "$proc_root/$pid/cmdline"
    if ((${#args[@]})); then
      if canopy_hosted_agent "${args[@]}" >/dev/null; then
        printf '%s\n' "$CANOPY_REPLY"
        return 0
      fi
      argv0=${args[0]##*/}
      name=${argv0%.exe}
      if [[ -n $name ]]; then
        if [[ $name == codex && ( ${args[1]:-} == app-server || ${args[2]:-} == app-server ) ]]; then
          name=codex-app-server
        fi
        canopy_is_claude_version "$name" && name=claude
        CANOPY_REPLY=$name
        printf '%s\n' "$name"
        return 0
      fi
    fi
  fi
  [[ -r "$proc_root/$pid/comm" ]] || return 1
  IFS= read -r name < "$proc_root/$pid/comm" 2>/dev/null || return 1
  name=${name%.exe}
  canopy_is_claude_version "$name" && name=claude
  CANOPY_REPLY=$name
  printf '%s\n' "$name"
}
canopy_process_identity() {
  local root=$1 pid=$2 birth=$3 kind=${4:-codex} current=$2 depth=0 name
  [[ $root =~ ^[1-9][0-9]*$ && $pid =~ ^[1-9][0-9]*$ ]] || return 1
  if [[ -d /proc/self ]]; then
    canopy_process_name "$pid" >/dev/null || return 1
    name=$CANOPY_REPLY
    canopy_agent_name_matches "$name" "$kind" || return 1
    canopy_proc_stat "$pid" || return 1
    [[ $CANOPY_BIRTH == "$birth" ]] || return 1
    while ((depth++ < 128)); do
      if [[ $current != "$pid" ]]; then
        canopy_process_name "$current" >/dev/null || return 1
        name=$CANOPY_REPLY
        canopy_agent_carrier "$name" "$kind" || return 1
      fi
      [[ $current == "$root" ]] && return 0
      canopy_proc_stat "$current" || return 1
      current=$CANOPY_PARENT
      [[ $current =~ ^[1-9][0-9]*$ ]] || return 1
    done
    return 1
  fi
  # Non-Linux fallback: require the same PID, start time and pane ancestry,
  # using a single cached process-table snapshot instead of a ps call per
  # ancestor (see canopy_load_ps_snapshot above).
  canopy_load_ps_snapshot
  # A hosted agent's own name is its host's (node, python); its kind is not.
  canopy_agent_name_matches "${CANOPY_KIND[$pid]:-${CANOPY_COMM[$pid]:-}}" "$kind" || return 1
  # ps pads single-digit days ("Oct  1"); the snapshot keeps single spaces.
  local -a birth_fields
  read -ra birth_fields <<< "$birth"
  [[ "${CANOPY_LSTART[$pid]:-}" == "${birth_fields[*]}" ]] || return 1
  current=$pid
  while ((depth++ < 128)); do
    if [[ $current != "$pid" ]]; then
      name=${CANOPY_KIND[$current]:-${CANOPY_COMM[$current]:-}}
      canopy_agent_carrier "$name" "$kind" || return 1
    fi
    [[ $current == "$root" ]] && return 0
    current=${CANOPY_PPID[$current]:-}
    [[ $current =~ ^[1-9][0-9]*$ ]] || return 1
  done
  return 1
}
canopy_agent_name_matches() {
  local target=${1%.exe}
  case "$2:$target" in
    codex:codex|claude:claude|claude:claude-code|opencode:opencode|gemini:gemini|pi:pi|omp:omp|agy:agy|agy:antigravity|cursor-agent:agent|cursor-agent:cursor-agent|copilot:copilot|grok:grok|hermes:hermes|hermes:hermes-agent) return 0 ;;
    claude:*) canopy_is_claude_version "$target" && return 0; return 1 ;;
    *) return 1 ;;
  esac
}
# Map a process basename to Canopy's agent kind (CANOPY_REPLY).
canopy_agent_kind_from_name() {
  local name=${1##*/}
  name=${name%.exe}
  CANOPY_REPLY=''
  case "$name" in
    codex) CANOPY_REPLY=codex ;;
    claude|claude-code) CANOPY_REPLY=claude ;;
    opencode|gemini|pi|omp|agy|crush|copilot|grok) CANOPY_REPLY=$name ;;
    hermes|hermes-agent) CANOPY_REPLY=hermes ;;
    antigravity) CANOPY_REPLY=agy ;;
    agent|cursor-agent) CANOPY_REPLY=cursor-agent ;;
    *)
      if canopy_is_claude_version "$name"; then
        CANOPY_REPLY=claude
      else
        return 1
      fi
      ;;
  esac
  printf '%s' "$CANOPY_REPLY"
}
# Display label for a kind (CANOPY_REPLY).
canopy_agent_label() {
  CANOPY_REPLY=''
  case "$1" in
    codex) CANOPY_REPLY='Codex' ;;
    claude) CANOPY_REPLY='Claude Code' ;;
    opencode) CANOPY_REPLY='OpenCode' ;;
    gemini) CANOPY_REPLY='Gemini CLI' ;;
    pi) CANOPY_REPLY='Pi' ;;
    omp) CANOPY_REPLY='Oh My Pi' ;;
    agy) CANOPY_REPLY='Antigravity' ;;
    cursor-agent) CANOPY_REPLY='cursor-agent' ;;
    crush) CANOPY_REPLY='Crush' ;;
    copilot) CANOPY_REPLY='Copilot CLI' ;;
    grok) CANOPY_REPLY='Grok Build' ;;
    hermes) CANOPY_REPLY='Hermes' ;;
    *) CANOPY_REPLY=$1 ;;
  esac
  printf '%s' "$CANOPY_REPLY"
}
# Shells, runtimes, and wrappers an agent may sit under and still belong to the pane.
canopy_agent_carrier() {
  local name=${1#-} kind=${2:-}
  name=${name##*/}
  name=${name%.exe}
  if [[ -n $kind ]]; then
    canopy_agent_name_matches "$name" "$kind" && return 0
  else
    case "$name" in
      codex|claude|claude-code|opencode|gemini|pi|omp|agy|antigravity|agent|cursor-agent|crush|copilot|grok|hermes|hermes-agent) return 0 ;;
    esac
    canopy_is_claude_version "$name" && return 0
  fi
  case "$name" in
    sh|bash|zsh|fish|dash|ksh|mksh|tcsh|csh|nu|xonsh|elvish|pwsh|login|su|sudo|doas|env|nice|nohup|time|timeout|script|stdbuf|caffeinate|direnv|mise|asdf|nix|nix-shell|devbox|node|nodejs|bun|deno|npx|npm|pnpm|yarn|tsx|ts-node|uv|uvx|pipx|poetry|ruby|bundle|cargo|make|just|bwrap|firejail|sandbox-exec|nono|fence|landrun|nsjail|minijail0|unshare|codex-app-server) return 0 ;;
    python|Python|python[0-9]*) return 0 ;;
    *) return 1 ;;
  esac
}
# Linux /proc fast path: walk only the pane root's own carrier descendants
# breadth-first via /proc/<pid>/task/*/children instead of spawning ps.
canopy_proc_resolve_pane_agent() {
  local root=$1 proc_root=${CANOPY_PROC_ROOT:-/proc} name cur tid_file children child depth=0
  local -a queue=() next_queue=()
  local -A seen=()
  CANOPY_REPLY=''
  [[ $root =~ ^[1-9][0-9]*$ ]] || return 1
  [[ -d "$proc_root/$root" ]] || return 1
  [[ -r "$proc_root/$root/task/$root/children" ]] || return 2
  canopy_process_name "$root" >/dev/null || return 1
  name=$CANOPY_REPLY
  if canopy_agent_kind_from_name "$name" >/dev/null; then
    printf '%s' "$CANOPY_REPLY"
    return 0
  fi
  canopy_agent_carrier "$name" '' || return 1
  queue=("$root")
  seen[$root]=1
  while ((${#queue[@]} && ++depth < 128)); do
    next_queue=()
    for cur in "${queue[@]}"; do
      for tid_file in "$proc_root/$cur/task/"*/children; do
        [[ -r "$tid_file" ]] || continue
        IFS= read -r children < "$tid_file" 2>/dev/null || continue
        for child in $children; do
          [[ $child =~ ^[1-9][0-9]*$ && -z "${seen[$child]:-}" ]] || continue
          seen[$child]=1
          canopy_process_name "$child" >/dev/null || continue
          name=$CANOPY_REPLY
          if canopy_agent_kind_from_name "$name" >/dev/null; then
            printf '%s' "$CANOPY_REPLY"
            return 0
          fi
          canopy_agent_carrier "$name" '' && next_queue+=("$child")
        done
      done
    done
    queue=("${next_queue[@]}")
  done
  CANOPY_REPLY=''
  return 1
}
# Resolve the agent kind for a pane: foreground command, hosted runtime, or
# closest matching descendant under only carrier processes (CANOPY_REPLY).
canopy_resolve_pane_agent() {
  local root=$1 base=${2##*/} pid current depth best=129 found='' kind name
  base=${base%.exe}
  CANOPY_REPLY=''
  if canopy_agent_kind_from_name "$base" >/dev/null; then
    return 0
  fi
  [[ $root =~ ^[1-9][0-9]*$ ]] || return 1
  if ((!canopy_ps_loaded)) && [[ -n "${CANOPY_PROC_ROOT:-}" || -d /proc/self ]] && ! declare -F ps >/dev/null; then
    canopy_proc_resolve_pane_agent "$root"
    case $? in
      0) return 0 ;;
      1) return 1 ;;
    esac
  fi
  if [[ "$base" =~ ^(node|nodejs|bun|python[0-9.]*|Python)$ ]]; then
    canopy_pane_agent "$root" >/dev/null && return 0
  fi
  canopy_load_ps_snapshot || return 1
  for pid in "${CANOPY_AGENT_PIDS[@]}"; do
    kind=${CANOPY_AGENT_KIND[$pid]:-}
    [[ -n $kind ]] || continue
    current=$pid
    for ((depth=0; depth<128; depth++)); do
      if [[ $current != "$pid" ]]; then
        name=${CANOPY_KIND[$current]:-${CANOPY_COMM[$current]:-}}
        canopy_agent_carrier "$name" "$kind" || break
      fi
      if [[ $current == "$root" ]]; then
        if ((depth < best)); then
          best=$depth
          found=$kind
        fi
        break
      fi
      current=${CANOPY_PPID[$current]:-}
      [[ $current =~ ^[1-9][0-9]*$ ]] || break
    done
  done
  CANOPY_REPLY=$found
  [[ -n $found ]] && printf '%s' "$found"
}
