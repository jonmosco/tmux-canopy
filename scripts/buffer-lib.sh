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

# Cross-platform system clipboard detection. An explicit override always
# wins; otherwise cascade through the tool most likely correct for the
# current environment, mirroring tmux-yank's approach. Prints a shell
# command (run via /bin/sh -c with buffer bytes on stdin) or fails if no
# clipboard tool is available.
buffer_clipboard_command() {
  local override
  override="$(tmux show-option -gqv @tmux-canopy-copy-command 2>/dev/null || true)"
  if [[ -n "$override" ]]; then
    printf '%s\n' "$override"; return 0
  fi
  if command -v pbcopy >/dev/null 2>&1; then
    if command -v reattach-to-user-namespace >/dev/null 2>&1; then
      printf 'reattach-to-user-namespace pbcopy\n'
    else
      printf 'pbcopy\n'
    fi
    return 0
  fi
  if command -v clip.exe >/dev/null 2>&1; then
    printf 'clip.exe\n'; return 0
  fi
  if [[ -n "${WAYLAND_DISPLAY:-}" ]] && command -v wl-copy >/dev/null 2>&1; then
    printf 'wl-copy\n'; return 0
  fi
  if [[ -n "${DISPLAY:-}" ]]; then
    if command -v xsel >/dev/null 2>&1; then
      printf 'xsel -i -b\n'; return 0
    fi
    if command -v xclip >/dev/null 2>&1; then
      printf 'xclip -i -selection clipboard\n'; return 0
    fi
  fi
  if command -v putclip >/dev/null 2>&1; then
    printf 'putclip\n'; return 0
  fi
  return 1
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
