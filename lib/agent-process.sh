#!/usr/bin/env bash
# Process identity and ancestry helpers. Linux uses /proc without spawning ps.
canopy_ps_loaded=0
declare -gA CANOPY_PPID CANOPY_LSTART CANOPY_COMM CANOPY_KIND
# PIDs with a CANOPY_KIND entry, so pane lookups skip the rest of the table.
declare -ga CANOPY_KIND_PIDS=()
# Helpers also leave their result here so callers can avoid a $(...) subshell,
# which would discard the snapshot cache along with the fork.
CANOPY_REPLY=''
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
    case "${CANOPY_COMM[$pid]}" in
      node|nodejs|pi|omp) ;;
      *) continue ;;
    esac
    read -ra rest_args <<< "$rest"
    canopy_hosted_agent "${CANOPY_COMM[$pid]}" "${rest_args[@]}" >/dev/null || continue
    CANOPY_KIND[$pid]=$CANOPY_REPLY
    CANOPY_KIND_PIDS+=("$pid")
  done <<< "$raw"
  return "$canopy_ps_status"
}
# Pi and Oh My Pi exec through Node. A node/nodejs argv0 is those agents only
# when a later argument is their launcher; every other Node process stays node.
canopy_hosted_agent() {
  local host=${1:-} token base
  CANOPY_REPLY=''
  shift || true
  host=${host##*/}
  host=${host%.exe}
  case "$host" in
    pi|omp) CANOPY_REPLY=$host; printf '%s' "$host"; return 0 ;;
    node|nodejs) ;;
    *) return 1 ;;
  esac
  for token in "$@"; do
    [[ $token == -* ]] && continue
    base=${token##*/}
    base=${base%.exe}
    case "$base" in
      pi|omp) CANOPY_REPLY=$base; printf '%s' "$base"; return 0 ;;
    esac
    case "$token" in
      *pi-coding-agent*) CANOPY_REPLY=pi; printf 'pi'; return 0 ;;
      *oh-my-pi*) CANOPY_REPLY=omp; printf 'omp'; return 0 ;;
    esac
  done
  return 1
}
# Closest pi/omp descendant of a pane root, if Node is only hosting that CLI.
canopy_pane_agent() {
  local root=$1 pid current depth=0 best=129 found='' kind
  CANOPY_REPLY=''
  [[ $root =~ ^[1-9][0-9]*$ ]] || return 1
  canopy_load_ps_snapshot || return 1
  for pid in "${CANOPY_KIND_PIDS[@]}"; do
    kind=${CANOPY_KIND[$pid]:-}
    [[ -n $kind ]] || continue
    current=$pid
    depth=0
    while ((depth < 128)); do
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
    CANOPY_REPLY+="$pid ${CANOPY_PPID[$pid]} ${CANOPY_COMM[$pid]}"$'\n'
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
  local pid=$1 argv0 name arg
  local -a args=()
  [[ $pid =~ ^[1-9][0-9]*$ ]] || return 1
  if [[ -r /proc/$pid/cmdline ]]; then
    while IFS= read -r -d '' arg; do
      args+=("$arg")
    done < "/proc/$pid/cmdline"
    if ((${#args[@]})); then
      name=$(canopy_hosted_agent "${args[@]}") && { printf '%s\n' "$name"; return 0; }
      argv0=${args[0]##*/}
      name=${argv0%.exe}
      if [[ -n $name ]]; then
        printf '%s\n' "$name"
        return 0
      fi
    fi
  fi
  [[ -r /proc/$pid/comm ]] || return 1
  IFS= read -r name < "/proc/$pid/comm" 2>/dev/null || return 1
  printf '%s\n' "${name%.exe}"
}
canopy_process_identity() {
  local root=$1 pid=$2 birth=$3 kind=${4:-codex} current=$2 depth=0 name
  [[ $root =~ ^[1-9][0-9]*$ && $pid =~ ^[1-9][0-9]*$ ]] || return 1
  if [[ -d /proc/self ]]; then
    name="$(canopy_process_name "$pid")" || return 1
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
  # ps pads single-digit days ("Oct  1"); the snapshot keeps single spaces.
  local -a birth_fields
  read -ra birth_fields <<< "$birth"
  [[ "${CANOPY_LSTART[$pid]:-}" == "${birth_fields[*]}" ]] || return 1
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
