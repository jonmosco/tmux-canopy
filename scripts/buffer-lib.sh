#!/usr/bin/env bash
# Versioned hex identities are safe in tmux, fzf fields, and shell arguments.
# Keep decoding legacy B: rows so an already-open UI can upgrade on refresh.
buffer_token() {
  local name="$1" byte i LC_ALL=C
  printf 'B2:'
  for ((i=0; i<${#name}; i++)); do
    printf -v byte '%02x' "'${name:i:1}"
    printf '%s' "$byte"
  done
}

buffer_decode_token() {
  local token="$1" hex byte i LC_ALL=C
  BUFFER_NAME=''
  case "$token" in
    B:*) BUFFER_NAME="${token#B:}" ;;
    B2:*)
      hex="${token#B2:}"
      [[ "$hex" =~ ^([[:xdigit:]]{2})+$ ]] || return 1
      for ((i=0; i<${#hex}; i+=2)); do
        [[ "${hex:i:2}" != 00 ]] || return 1
        printf -v byte '%b' "\\x${hex:i:2}"
        BUFFER_NAME+="$byte"
      done
      ;;
    *) return 1 ;;
  esac
  [[ -n "$BUFFER_NAME" && "$BUFFER_NAME" != *[[:cntrl:]]* ]]
}
