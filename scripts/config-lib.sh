#!/usr/bin/env bash
# Remember only state Canopy owns. Native tmux parses saved binding commands;
# shell eval is never used. Later user changes take precedence during reload.
#
# Plugin load reads tmux state once (canopy_load_state), decides in the shell,
# and writes in one batch (canopy_queue/canopy_flush) instead of several tmux
# calls per binding and option. A failing command stops the rest of a batch,
# so only commands valid on every supported tmux version are queued.
declare -A CANOPY_WANTED_BINDINGS=()
declare -A CANOPY_KEYS=() CANOPY_STATE=() CANOPY_CURRENT=()
declare -a CANOPY_BATCH=() CANOPY_BOUND=()

CANOPY_KEY_FORMAT=$'#{key_table}\037#{key_string}\037bind-key #{?key_repeat,-r ,}-T #{q/a:key_table} -N #{q/a:key_note} #{q/a:key_string} #{key_command}'

canopy_binding() {
  local table="$1" key="$2" row_key command
  while IFS=$'\037' read -r row_key command; do
    [[ "$row_key" == "$key" ]] && { printf '%s' "$command"; return; }
  done < <(tmux list-keys -T "$table" -F $'#{key_string}\037bind-key #{?key_repeat,-r ,}-T #{q/a:key_table} -N #{q/a:key_note} #{q/a:key_string} #{key_command}' 2>/dev/null)
}

# tmux sends a whole command line to the server as one message (about 16 KiB
# at most, or "command too long"), so a batch is flushed before it gets near
# that; hook commands repeat the install path and add up quickly.
CANOPY_BATCH_BYTES=0
canopy_queue() {
  local argument size=0
  for argument in "$@"; do size=$((size + ${#argument} + 1)); done
  ((CANOPY_BATCH_BYTES + size < 8000)) || canopy_flush
  ((${#CANOPY_BATCH[@]} == 0)) || CANOPY_BATCH+=(';')
  CANOPY_BATCH+=("$@")
  CANOPY_BATCH_BYTES=$((CANOPY_BATCH_BYTES + size + 2))
}

canopy_flush() {
  ((${#CANOPY_BATCH[@]})) || return 0
  tmux "${CANOPY_BATCH[@]}"
  CANOPY_BATCH=()
  CANOPY_BATCH_BYTES=0
}

canopy_load_keys() {
  local table key command
  CANOPY_KEYS=()
  while IFS=$'\037' read -r table key command; do
    CANOPY_KEYS["$table"$'\037'"$key"]=$command
  done < <(tmux list-keys -F "$CANOPY_KEY_FORMAT" 2>/dev/null)
}

# Read Canopy's records (@tmux_canopy_binding_*, @tmux_canopy_owned_*) and the
# named settings into CANOPY_STATE, and the global values of the options Canopy
# may own into CANOPY_CURRENT, in two tmux calls. Arguments are setting names
# (@tmux-canopy-*) or owned options as scope:name (session or window).
# show-options -g quotes values when listing them, so it only supplies the
# names that exist; each value is then read raw with -v, one line per option.
# Unlike display-message, this works before tmux has created any session.
canopy_load_state() {
  local name _value line index=0 spec
  local -A wanted=()
  local -a names=() builtins=() query=()
  for spec in "$@"; do
    if [[ "$spec" == @* ]]; then wanted["$spec"]=1; else builtins+=("$spec"); fi
  done
  canopy_load_keys
  while read -r name _value; do
    [[ "$name" =~ ^@tmux_canopy_(binding|owned)_ || -n "${wanted["$name"]:-}" ]] && names+=("$name")
  done < <(tmux show-options -g 2>/dev/null)
  for name in "${names[@]}"; do
    ((${#query[@]} == 0)) || query+=(';')
    query+=(show-options -gqv "$name")
  done
  for spec in "${builtins[@]}"; do
    ((${#query[@]} == 0)) || query+=(';')
    if [[ "${spec%%:*}" == window ]]; then query+=(show-options -gwv "${spec#*:}")
    else query+=(show-options -gv "${spec#*:}")
    fi
  done
  CANOPY_STATE=() CANOPY_CURRENT=()
  ((${#query[@]})) || return 0
  while IFS= read -r line; do
    if ((index < ${#names[@]})); then CANOPY_STATE["${names[index]}"]=$line
    else CANOPY_CURRENT["${builtins[index - ${#names[@]}]}"]=$line
    fi
    ((index += 1))
  done < <(tmux "${query[@]}" 2>/dev/null)
}

canopy_bind() {
  local table="$1" key="$2" id base current installed
  shift 2
  # The binding id is cksum of "table\nkey"; canopy_client_key computes it in Bash.
  canopy_client_key "$table"$'\n'"$key"
  # shellcheck disable=SC2153 # CANOPY_KEY is set by canopy_client_key (launch-lib.sh).
  id=$CANOPY_KEY
  base="@tmux_canopy_binding_$id"
  CANOPY_WANTED_BINDINGS[$id]=1
  current=${CANOPY_KEYS["$table"$'\037'"$key"]:-}
  installed=${CANOPY_STATE["${base}_installed"]:-}
  if [[ -n "$installed" ]]; then
    [[ "$current" == "$installed" ]] || return 0
  else
    canopy_queue set-option -gq "${base}_prior" "$current"
    canopy_queue set-option -gq "${base}_table" "$table"
    canopy_queue set-option -gq "${base}_key" "$key"
  fi
  canopy_queue bind-key -T "$table" "$key" "$@"
  CANOPY_BOUND+=("$base"$'\037'"$table"$'\037'"$key")
}

canopy_restore_unused_bindings() {
  local name id base table key prior installed current field
  for name in "${!CANOPY_STATE[@]}"; do
    [[ "$name" =~ ^@tmux_canopy_binding_([0-9]+)_installed$ ]] || continue
    id="${BASH_REMATCH[1]}"
    [[ -z "${CANOPY_WANTED_BINDINGS[$id]:-}" ]] || continue
    base="@tmux_canopy_binding_$id"
    table=${CANOPY_STATE["${base}_table"]:-}
    key=${CANOPY_STATE["${base}_key"]:-}
    prior=${CANOPY_STATE["${base}_prior"]:-}
    installed=${CANOPY_STATE["${base}_installed"]:-}
    current=${CANOPY_KEYS["$table"$'\037'"$key"]:-}
    if [[ "$current" == "$installed" ]]; then
      # A saved binding is tmux command text; source-file parses it natively.
      if [[ -n "$prior" ]]; then printf '%s\n' "$prior" | tmux source-file -
      else canopy_queue unbind-key -T "$table" "$key"
      fi
    fi
    for field in prior table key installed; do canopy_queue set-option -gu "${base}_$field"; done
  done
}

# Write queued changes, then record each new binding exactly as tmux stored it,
# which later reloads compare against to detect user changes.
canopy_load_finish() {
  local entry base table key
  canopy_flush
  if ((${#CANOPY_BOUND[@]})); then
    canopy_load_keys
    for entry in "${CANOPY_BOUND[@]}"; do
      IFS=$'\037' read -r base table key <<< "$entry"
      canopy_queue set-option -gq "${base}_installed" "${CANOPY_KEYS["$table"$'\037'"$key"]:-}"
    done
  fi
  canopy_restore_unused_bindings
  canopy_flush
}

canopy_owned_option() {
  local scope="$1" option="$2" desired="$3" base current installed
  local -a setter=(set-option -g)
  [[ "$scope" != window ]] || setter=(set-window-option -g)
  base="@tmux_canopy_owned_${scope}_${option//-/_}"
  current=${CANOPY_CURRENT["$scope:$option"]:-}
  installed=${CANOPY_STATE["${base}_installed"]:-}
  if [[ -n "$installed" ]]; then
    if [[ -z "$desired" ]]; then
      if [[ "$current" == "$installed" ]]; then
        canopy_queue "${setter[@]}" "$option" "${CANOPY_STATE["${base}_prior"]:-}"
      fi
      canopy_queue set-option -gu "${base}_prior"
      canopy_queue set-option -gu "${base}_installed"
      return
    fi
    [[ "$current" == "$installed" ]] || return 0
  elif [[ -n "$desired" ]]; then
    canopy_queue set-option -gq "${base}_prior" "$current"
  else return 0
  fi
  canopy_queue "${setter[@]}" "$option" "$desired"
  canopy_queue set-option -gq "${base}_installed" "$desired"
}
