#!/usr/bin/env bash
# Process identity and ancestry helpers. Linux uses /proc without spawning ps.
canopy_ps_loaded=0
declare -gA CANOPY_PPID CANOPY_LSTART CANOPY_COMM
# Non-Linux (no /proc) fallback: read the whole process table in one ps call
# and cache it for the lifetime of this process, instead of spawning ps per
# ancestor per pane. Safe to call repeatedly; only the first call forks ps.
canopy_ps_status=0
canopy_load_ps_snapshot() {
  ((canopy_ps_loaded)) && return "$canopy_ps_status"
  canopy_ps_loaded=1
  local pid ppid w1 w2 w3 w4 w5 comm raw
  raw="$(ps -eo pid=,ppid=,lstart=,comm= 2>/dev/null)"
  canopy_ps_status=$?
  while IFS=' ' read -r pid ppid w1 w2 w3 w4 w5 comm; do
    [[ $pid =~ ^[1-9][0-9]*$ ]] || continue
    CANOPY_PPID[$pid]=$ppid
    CANOPY_LSTART[$pid]="$w1 $w2 $w3 $w4 $w5"
    comm=${comm##*/}
    CANOPY_COMM[$pid]=${comm%.exe}
  done <<< "$raw"
  return "$canopy_ps_status"
}
# Emits "pid ppid comm" lines from the cached snapshot, for callers that only
# need a full-process-table scan (loads the snapshot on demand).
canopy_ps_snapshot_lines() {
  canopy_load_ps_snapshot || return 1
  local pid
  for pid in "${!CANOPY_PPID[@]}"; do
    printf '%s %s %s\n' "$pid" "${CANOPY_PPID[$pid]}" "${CANOPY_COMM[$pid]}"
  done
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
canopy_process_identity() {
  local root=$1 pid=$2 birth=$3 kind=${4:-codex} current=$2 depth=0 name
  [[ $root =~ ^[1-9][0-9]*$ && $pid =~ ^[1-9][0-9]*$ ]] || return 1
  if [[ -d /proc/self ]]; then
    [[ -r /proc/$pid/comm ]] || return 1
    IFS= read -r name < "/proc/$pid/comm" 2>/dev/null || return 1
    canopy_agent_name_matches "$name" "$kind" || return 1
    canopy_proc_stat "$pid" || return 1
    [[ $CANOPY_BIRTH == "$birth" ]] || return 1
    while ((depth++ < 128)); do
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
  canopy_agent_name_matches "${CANOPY_COMM[$pid]:-}" "$kind" || return 1
  [[ "${CANOPY_LSTART[$pid]:-}" == "$birth" ]] || return 1
  current=$pid
  while ((depth++ < 128)); do
    [[ $current == "$root" ]] && return 0
    current=${CANOPY_PPID[$current]:-}
    [[ $current =~ ^[1-9][0-9]*$ ]] || return 1
  done
  return 1
}
canopy_agent_name_matches() {
  local target=${1%.exe}
  case "$2:$target" in
    codex:codex|claude:claude|claude:claude-code|opencode:opencode|gemini:gemini|pi:pi|omp:omp|agy:agy|agy:antigravity|cursor-agent:agent) return 0 ;;
    *) return 1 ;;
  esac
}
