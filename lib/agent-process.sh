#!/usr/bin/env bash
# Process identity and ancestry helpers. Linux uses /proc without spawning ps.
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
  # Non-Linux fallback: require the same PID, start time and pane ancestry.
  local record parent cmd started
  record=$(ps -p "$pid" -o ppid= -o comm= 2>/dev/null) || return 1
  read -r parent cmd <<< "$record"
  parent=${parent//[[:space:]]/}
  canopy_agent_name_matches "${cmd##*/}" "$kind" || return 1
  started=$(ps -p "$pid" -o lstart= 2>/dev/null) || return 1
  [[ $started == "$birth" ]] || return 1
  current=$pid
  while ((depth++ < 128)); do
    [[ $current == "$root" ]] && return 0
    current=$(ps -p "$current" -o ppid= 2>/dev/null) || return 1
    current=${current//[[:space:]]/}
    [[ $current =~ ^[1-9][0-9]*$ ]] || return 1
  done
  return 1
}
canopy_agent_name_matches() {
  case "$2:$1" in
    codex:codex|claude:claude|claude:claude-code|opencode:opencode|gemini:gemini|pi:pi|omp:omp) return 0 ;;
    *) return 1 ;;
  esac
}
