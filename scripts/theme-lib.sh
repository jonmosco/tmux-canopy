#!/usr/bin/env bash
# Resolve sidebar colors from tmux styles (ansi) or the fixed ANSI palette.
# Results land in CANOPY_THEME and CANOPY_COLOR_* variables. CANOPY_REPLY is
# used for single-value helpers. Prefer freezing once at sidebar open so
# Ctrl-r does not re-sample.

# Extract fg= or bg= from a tmux style string. default / empty → CANOPY_REPLY="".
canopy_style_attr() {
  local style="${1:-}" attr="${2:-fg}" rest pair key value
  CANOPY_REPLY=
  [[ -n "$style" && "$style" != default ]] || return 0
  rest=$style
  while [[ -n "$rest" ]]; do
    pair=${rest%%,*}
    if [[ "$rest" == *,* ]]; then rest=${rest#*,}; else rest=; fi
    key=${pair%%=*}
    value=${pair#*=}
    [[ "$key" == "$attr" ]] || continue
    [[ -n "$value" && "$value" != default ]] || return 0
    # colourN → N for fzf/ansi converters.
    if [[ "$value" =~ ^[Cc]olou?r([0-9]{1,3})$ ]]; then
      CANOPY_REPLY=${BASH_REMATCH[1]}
    else
      CANOPY_REPLY=$value
    fi
    return 0
  done
}

# Map a color token to an fzf --color value (0-255, #rrggbb), or empty.
canopy_color_to_fzf() {
  local value="${1:-}"
  CANOPY_REPLY=
  [[ -n "$value" ]] || return 0
  if [[ "$value" =~ ^#[[:xdigit:]]{6}$ ]]; then
    CANOPY_REPLY=$value
    return 0
  fi
  if [[ "$value" =~ ^([0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])$ ]]; then
    CANOPY_REPLY=$value
    return 0
  fi
  case "${value,,}" in
    black|colour0|color0) CANOPY_REPLY=0 ;;
    red|colour1|color1) CANOPY_REPLY=1 ;;
    green|colour2|color2) CANOPY_REPLY=2 ;;
    yellow|colour3|color3) CANOPY_REPLY=3 ;;
    blue|colour4|color4) CANOPY_REPLY=4 ;;
    magenta|colour5|color5) CANOPY_REPLY=5 ;;
    cyan|colour6|color6) CANOPY_REPLY=6 ;;
    white|colour7|color7) CANOPY_REPLY=7 ;;
    brightblack|colour8|color8) CANOPY_REPLY=8 ;;
    brightred|colour9|color9) CANOPY_REPLY=9 ;;
    brightgreen|colour10|color10) CANOPY_REPLY=10 ;;
    brightyellow|colour11|color11) CANOPY_REPLY=11 ;;
    brightblue|colour12|color12) CANOPY_REPLY=12 ;;
    brightmagenta|colour13|color13) CANOPY_REPLY=13 ;;
    brightcyan|colour14|color14) CANOPY_REPLY=14 ;;
    brightwhite|colour15|color15) CANOPY_REPLY=15 ;;
    *) CANOPY_REPLY= ;;
  esac
}

# Map a color token to an ANSI SGR sequence (bold for the classic 8 colors).
canopy_color_to_ansi() {
  local value="${1:-}" r g b
  CANOPY_REPLY=
  [[ -n "$value" ]] || return 0
  if [[ "$value" =~ ^#([[:xdigit:]]{2})([[:xdigit:]]{2})([[:xdigit:]]{2})$ ]]; then
    r=$((16#${BASH_REMATCH[1]}))
    g=$((16#${BASH_REMATCH[2]}))
    b=$((16#${BASH_REMATCH[3]}))
    printf -v CANOPY_REPLY '\033[38;2;%d;%d;%dm' "$r" "$g" "$b"
    return 0
  fi
  if [[ "$value" =~ ^([0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])$ ]]; then
    printf -v CANOPY_REPLY '\033[38;5;%sm' "$value"
    return 0
  fi
  canopy_color_to_fzf "$value"
  [[ -n "$CANOPY_REPLY" ]] || return 0
  case "$CANOPY_REPLY" in
    0) CANOPY_REPLY=$'\033[1;30m' ;;
    1) CANOPY_REPLY=$'\033[1;31m' ;;
    2) CANOPY_REPLY=$'\033[1;32m' ;;
    3) CANOPY_REPLY=$'\033[1;33m' ;;
    4) CANOPY_REPLY=$'\033[1;34m' ;;
    5) CANOPY_REPLY=$'\033[1;35m' ;;
    6) CANOPY_REPLY=$'\033[1;36m' ;;
    7) CANOPY_REPLY=$'\033[1;37m' ;;
    *) printf -v CANOPY_REPLY '\033[38;5;%sm' "$CANOPY_REPLY" ;;
  esac
}

canopy_theme_fixed() {
  CANOPY_THEME=fixed
  CANOPY_COLOR_ACCENT_FZF=6
  CANOPY_COLOR_ACTIVE_FZF=2
  CANOPY_COLOR_ATTENTION_FZF=3
  CANOPY_COLOR_SELECTION_BG=236
  CANOPY_COLOR_BORDER_FZF='-1'
  CANOPY_COLOR_ACCENT_ANSI=$'\033[1;36m'
  CANOPY_COLOR_ACTIVE_ANSI=$'\033[1;32m'
  CANOPY_COLOR_ATTENTION_ANSI=$'\033[1;33m'
  CANOPY_COLOR_MUTED_FZF=245
  CANOPY_COLOR_MUTED_ANSI=$'\033[38;5;245m'
  CANOPY_SELECTION_EXPLICIT=0
}

# Perceived brightness, 0–1000. Empty when the token is not hex.
canopy_hex_luma() {
  local hex="${1#\#}" r g b
  CANOPY_REPLY=
  [[ "$hex" =~ ^[[:xdigit:]]{6}$ ]] || return 0
  r=$((16#${hex:0:2})) g=$((16#${hex:2:2})) b=$((16#${hex:4:2}))
  CANOPY_REPLY=$(( (299 * r + 587 * g + 114 * b) / 255 ))
}

# True when two 0–1000 luma values can be told apart as foreground and background.
canopy_luma_contrast_ok() {
  local hi=$1 lo=$2
  (( hi < lo )) && { hi=$2; lo=$1; }
  # 1.8 rejects a foreground that is the background (Dracula mode fg #282a36
  # on status bg #282a36) and keeps pastel accents such as Nord green.
  (( (hi + 50) * 10 / (lo + 50) >= 18 ))
}

# mode-style fg is the color of text on the mode highlight (often the theme's
# dark background). Drawn on the terminal itself it vanishes. Skip any
# foreground that does not contrast with the status background when we know it.
canopy_first_style_color() {
  local attr="$1" style token luma
  shift
  CANOPY_REPLY=
  for style in "$@"; do
    canopy_style_attr "$style" "$attr"
    token=$CANOPY_REPLY
    [[ -n "$token" ]] || continue
    canopy_color_to_fzf "$token"
    token=$CANOPY_REPLY
    [[ -n "$token" ]] || continue
    if [[ "$attr" == fg && "${CANOPY_FG_CONTRAST:-1}" == 1 && -n "${CANOPY_BG_LUMA:-}" && "$token" == \#* ]]; then
      canopy_hex_luma "$token"
      luma=$CANOPY_REPLY
      [[ -n "$luma" ]] || continue
      canopy_luma_contrast_ok "$luma" "$CANOPY_BG_LUMA" || continue
    fi
    CANOPY_REPLY=$token
    return 0
  done
  CANOPY_REPLY=
}

# A dark status background used as the selection bar matches the terminal and
# hides the row. Lift it enough to see. Light backgrounds stay put.
canopy_lift_dark_hex() {
  local hex="${1#\#}" channel out i
  CANOPY_REPLY=$1
  [[ "$hex" =~ ^[[:xdigit:]]{6}$ ]] || return 0
  out='#'
  for ((i = 0; i < 6; i += 2)); do
    channel=$((16#${hex:i:2} + 48))
    (( channel > 255 )) && channel=255
    printf -v channel '%02x' "$channel"
    out+=$channel
  done
  CANOPY_REPLY=$out
}

canopy_theme_resolve() {
  local theme status_style active_border pane_border message_style message_cmd
  local selection_background selection_luma

  if [[ "${CANOPY_THEME_FROZEN:-0}" == 1 && -n "${CANOPY_COLOR_ACCENT_FZF:-}" ]]; then
    return 0
  fi

  theme=$(tmux show-option -gqv @tmux-canopy-theme 2>/dev/null || true)
  case "$theme" in
    mono|fixed|ansi) ;;
    *) theme=ansi ;;
  esac
  CANOPY_THEME=$theme

  if [[ "$theme" == mono ]]; then
    canopy_theme_fixed
    CANOPY_THEME=mono
    return 0
  fi

  if [[ "$theme" == fixed ]]; then
    canopy_theme_fixed
    return 0
  fi

  # ansi: inherit with per-slot fallbacks to the fixed palette.
  canopy_theme_fixed
  CANOPY_THEME=ansi

  local -a styles=()
  mapfile -t styles < <(
    tmux show-options -gv status-style \; \
      show-options -gv pane-active-border-style \; \
      show-options -gv pane-border-style \; \
      show-options -gv mode-style \; \
      show-options -gv message-style \; \
      show-options -gv message-command-style \; \
      show-options -gqv @tmux-canopy-selection-background 2>/dev/null || true
  )
  status_style=${styles[0]:-}
  active_border=${styles[1]:-}
  pane_border=${styles[2]:-}
  message_style=${styles[4]:-}
  message_cmd=${styles[5]:-}
  selection_background=${styles[6]:-}

  # Status background is the best hint of a dark or light terminal. mode-style
  # is not an accent: its foreground is chosen to contrast with the highlight.
  CANOPY_BG_LUMA=
  canopy_style_attr "$status_style" bg
  if [[ "$CANOPY_REPLY" == \#* ]]; then
    canopy_hex_luma "$CANOPY_REPLY"
    CANOPY_BG_LUMA=$CANOPY_REPLY
  fi
  if [[ -n "$CANOPY_BG_LUMA" ]]; then
    if (( CANOPY_BG_LUMA < 450 )); then
      CANOPY_COLOR_MUTED_FZF='#e6e6e6'
      CANOPY_COLOR_MUTED_ANSI=$'\033[38;2;230;230;230m'
    else
      CANOPY_COLOR_MUTED_FZF='#3a3a3a'
      CANOPY_COLOR_MUTED_ANSI=$'\033[38;2;58;58;58m'
    fi
  fi

  canopy_first_style_color fg "$active_border" "$status_style" "$message_style"
  if [[ -n "$CANOPY_REPLY" ]]; then
    CANOPY_COLOR_ACCENT_FZF=$CANOPY_REPLY
    canopy_color_to_ansi "$CANOPY_REPLY"
    CANOPY_COLOR_ACCENT_ANSI=$CANOPY_REPLY
  fi

  canopy_first_style_color fg "$active_border"
  if [[ -n "$CANOPY_REPLY" ]]; then
    CANOPY_COLOR_ACTIVE_FZF=$CANOPY_REPLY
    canopy_color_to_ansi "$CANOPY_REPLY"
    CANOPY_COLOR_ACTIVE_ANSI=$CANOPY_REPLY
  fi

  canopy_first_style_color fg "$message_style" "$message_cmd"
  if [[ -n "$CANOPY_REPLY" ]]; then
    CANOPY_COLOR_ATTENTION_FZF=$CANOPY_REPLY
    canopy_color_to_ansi "$CANOPY_REPLY"
    CANOPY_COLOR_ATTENTION_ANSI=$CANOPY_REPLY
  fi

  CANOPY_SELECTION_EXPLICIT=0
  if [[ "$selection_background" =~ ^([0-9]|[1-9][0-9]{1,2})$ ]] && ((selection_background <= 255)); then
    CANOPY_COLOR_SELECTION_BG=$selection_background
    CANOPY_SELECTION_EXPLICIT=1
  elif [[ "$selection_background" =~ ^#[[:xdigit:]]{6}$ ]]; then
    CANOPY_COLOR_SELECTION_BG=$selection_background
    CANOPY_SELECTION_EXPLICIT=1
  else
    # Stock tmux uses bg=green; inheriting that makes selection neon. Prefer
    # truecolor / 256-color status backgrounds from real themes only.
    canopy_first_style_color bg "$status_style"
    if [[ "$CANOPY_REPLY" =~ ^#[[:xdigit:]]{6}$ ]] || \
       [[ "$CANOPY_REPLY" =~ ^([0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])$ && CANOPY_REPLY -ge 16 ]]; then
      CANOPY_COLOR_SELECTION_BG=$CANOPY_REPLY
    fi
  fi
  if [[ "$CANOPY_COLOR_SELECTION_BG" == \#* ]]; then
    canopy_hex_luma "$CANOPY_COLOR_SELECTION_BG"
    selection_luma=$CANOPY_REPLY
    if [[ -n "$selection_luma" ]] && (( selection_luma < 180 )); then
      canopy_lift_dark_hex "$CANOPY_COLOR_SELECTION_BG"
      CANOPY_COLOR_SELECTION_BG=$CANOPY_REPLY
    fi
  fi

  # A border is a line. It may be close to the background and still be the
  # right color; the contrast filter is for text.
  CANOPY_FG_CONTRAST=0 canopy_first_style_color fg "$pane_border"
  if [[ -n "$CANOPY_REPLY" ]]; then
    CANOPY_COLOR_BORDER_FZF=$CANOPY_REPLY
  fi
}

# Export resolved colors for child processes (fzf reloads, awk).
canopy_theme_export() {
  export CANOPY_THEME \
    CANOPY_COLOR_ACCENT_FZF CANOPY_COLOR_ACTIVE_FZF CANOPY_COLOR_ATTENTION_FZF \
    CANOPY_COLOR_SELECTION_BG CANOPY_COLOR_BORDER_FZF \
    CANOPY_COLOR_ACCENT_ANSI CANOPY_COLOR_ACTIVE_ANSI CANOPY_COLOR_ATTENTION_ANSI \
    CANOPY_COLOR_MUTED_FZF CANOPY_COLOR_MUTED_ANSI \
    CANOPY_SELECTION_EXPLICIT
}

canopy_theme_freeze() {
  canopy_theme_resolve
  canopy_theme_export
  export CANOPY_THEME_FROZEN=1
}
