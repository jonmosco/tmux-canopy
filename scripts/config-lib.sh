#!/usr/bin/env bash
# Remember only state Canopy owns. Native tmux parses saved binding commands;
# shell eval is never used. Later user changes take precedence during reload.
declare -A CANOPY_WANTED_BINDINGS=()

canopy_binding() {
  local table="$1" key="$2" row_key command
  while IFS=$'\037' read -r row_key command; do
    [[ "$row_key" == "$key" ]] && { printf '%s' "$command"; return; }
  done < <(tmux list-keys -T "$table" -F $'#{key_string}\037bind-key #{?key_repeat,-r ,}-T #{q/a:key_table} -N #{q/a:key_note} #{q/a:key_string} #{key_command}' 2>/dev/null)
}

canopy_bind() {
  local table="$1" key="$2" id base current installed
  shift 2
  read -r id _ < <(printf '%s\n%s' "$table" "$key" | cksum)
  base="@tmux_canopy_binding_$id"
  CANOPY_WANTED_BINDINGS[$id]=1
  current="$(canopy_binding "$table" "$key")"
  if [[ -n "$(tmux show-option -gq "${base}_installed")" ]]; then
    installed="$(tmux show-option -gqv "${base}_installed")"
    [[ "$current" == "$installed" ]] || return 0
  else
    tmux set-option -gq "${base}_prior" "$current"
    tmux set-option -gq "${base}_table" "$table"
    tmux set-option -gq "${base}_key" "$key"
  fi
  tmux bind-key -T "$table" "$key" "$@" || return
  tmux set-option -gq "${base}_installed" "$(canopy_binding "$table" "$key")"
}

canopy_restore_unused_bindings() {
  local option id base table key prior installed current field
  while read -r option _; do
    [[ "$option" =~ ^@tmux_canopy_binding_([0-9]+)_installed$ ]] || continue
    id="${BASH_REMATCH[1]}"
    [[ -z "${CANOPY_WANTED_BINDINGS[$id]:-}" ]] || continue
    base="@tmux_canopy_binding_$id"
    table="$(tmux show-option -gqv "${base}_table")"
    key="$(tmux show-option -gqv "${base}_key")"
    prior="$(tmux show-option -gqv "${base}_prior")"
    installed="$(tmux show-option -gqv "${base}_installed")"
    current="$(canopy_binding "$table" "$key")"
    if [[ "$current" == "$installed" ]]; then
      if [[ -n "$prior" ]]; then printf '%s\n' "$prior" | tmux source-file -
      else tmux unbind-key -T "$table" "$key"
      fi
    fi
    for field in prior table key installed; do tmux set-option -gu "${base}_$field"; done
  done < <(tmux show-options -g)
}

canopy_owned_option() {
  local scope="$1" option="$2" desired="$3" base current installed
  local -a query=(show-option -gv) setter=(set-option -g)
  if [[ "$scope" == window ]]; then query=(show-window-option -gv); setter=(set-window-option -g); fi
  base="@tmux_canopy_owned_${scope}_${option//-/_}"
  current="$(tmux "${query[@]}" "$option")"
  if [[ -n "$(tmux show-option -gq "${base}_installed")" ]]; then
    installed="$(tmux show-option -gqv "${base}_installed")"
    if [[ -z "$desired" ]]; then
      if [[ "$current" == "$installed" ]]; then
        tmux "${setter[@]}" "$option" "$(tmux show-option -gqv "${base}_prior")"
      fi
      tmux set-option -gu "${base}_prior"
      tmux set-option -gu "${base}_installed"
      return
    fi
    [[ "$current" == "$installed" ]] || return 0
  elif [[ -n "$desired" ]]; then
    tmux set-option -gq "${base}_prior" "$current"
  else return 0
  fi
  tmux "${setter[@]}" "$option" "$desired"
  tmux set-option -gq "${base}_installed" "$desired"
}
