#!/usr/bin/env bash
# Resolve sidebar colors from tmux styles (ansi), built-in named presets, or
# the fixed ANSI palette, plus per-role @tmux-canopy-color-* overrides.
# Results land in CANOPY_THEME, CANOPY_THEME_LIGHT, and CANOPY_COLOR_*
# variables. CANOPY_REPLY is used for single-value helpers. Prefer freezing
# once at sidebar open so Ctrl-r does not re-sample.

# Extract fg= or bg= from a tmux style string. default / empty → CANOPY_REPLY="".
canopy_style_attr() {
  local style="${1:-}" attr="${2:-fg}" rest pair key value
  CANOPY_REPLY=
  [[ -n "$style" && "$style" != default ]] || return 0
  rest=$style
  while [[ -n "$rest" ]]; do
    pair=${rest%%,*}
    if [[ "$rest" == *,* ]]; then rest=${rest#*,}; else rest=; fi
    pair=${pair#"${pair%%[![:space:]]*}"}
    pair=${pair%"${pair##*[![:space:]]}"}
    [[ "$pair" == *=* ]] || continue
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
  local value="${1:-}" lower
  CANOPY_REPLY=
  value=${value#"${value%%[![:space:]]*}"}
  value=${value%"${value##*[![:space:]]}"}
  [[ -n "$value" ]] || return 0
  if [[ "$value" =~ ^#[[:xdigit:]]{6}$ ]]; then
    CANOPY_REPLY=$value
    return 0
  fi
  lower=${value,,}
  if [[ "$lower" =~ ^colou?r([0-9]{1,3})$ ]]; then
    value=${BASH_REMATCH[1]}
  fi
  if [[ "$value" =~ ^([0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])$ ]]; then
    CANOPY_REPLY=$value
    return 0
  fi
  case "$lower" in
    black) CANOPY_REPLY=0 ;;
    red) CANOPY_REPLY=1 ;;
    green) CANOPY_REPLY=2 ;;
    yellow) CANOPY_REPLY=3 ;;
    blue) CANOPY_REPLY=4 ;;
    magenta) CANOPY_REPLY=5 ;;
    cyan) CANOPY_REPLY=6 ;;
    white) CANOPY_REPLY=7 ;;
    brightblack) CANOPY_REPLY=8 ;;
    brightred) CANOPY_REPLY=9 ;;
    brightgreen) CANOPY_REPLY=10 ;;
    brightyellow) CANOPY_REPLY=11 ;;
    brightblue) CANOPY_REPLY=12 ;;
    brightmagenta) CANOPY_REPLY=13 ;;
    brightcyan) CANOPY_REPLY=14 ;;
    brightwhite) CANOPY_REPLY=15 ;;
    *) CANOPY_REPLY= ;;
  esac
}

# Map a color token to an ANSI SGR sequence (bold for the classic 8 named colors).
canopy_color_to_ansi() {
  local value="${1:-}" r g b
  CANOPY_REPLY=
  value=${value#"${value%%[![:space:]]*}"}
  value=${value%"${value##*[![:space:]]}"}
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
  if [[ "${value,,}" =~ ^colou?r([0-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-5])$ ]]; then
    printf -v CANOPY_REPLY '\033[38;5;%sm' "${BASH_REMATCH[1]}"
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
  CANOPY_THEME_LIGHT=0
  CANOPY_COLOR_FG_FZF='-1'
  CANOPY_COLOR_ACCENT_FZF=6
  CANOPY_COLOR_ACTIVE_FZF=2
  CANOPY_COLOR_ATTENTION_FZF=3
  CANOPY_COLOR_ERROR_FZF=1
  CANOPY_COLOR_MUTED_FZF=245
  CANOPY_COLOR_BORDER_FZF='-1'
  CANOPY_COLOR_SELECTION_BG=236
  CANOPY_COLOR_SELECTION_FG=
  CANOPY_COLOR_ACCENT_ANSI=$'\033[1;36m'
  CANOPY_COLOR_ACTIVE_ANSI=$'\033[1;32m'
  CANOPY_COLOR_ATTENTION_ANSI=$'\033[1;33m'
  CANOPY_COLOR_ERROR_ANSI=$'\033[1;31m'
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

# Perceived brightness, 0–1000, for #rrggbb, 0–255, or named ANSI colors.
canopy_color_luma() {
  local token="${1:-}" n idx ri gi bi r g b gray
  CANOPY_REPLY=
  [[ -n "$token" && "$token" != -1 ]] || return 0
  canopy_color_to_fzf "$token"
  token=$CANOPY_REPLY
  [[ -n "$token" ]] || return 0
  if [[ "$token" == \#* ]]; then
    canopy_hex_luma "$token"
    return 0
  fi
  n=$((10#$token))
  if (( n >= 232 )); then
    gray=$(( 8 + 10 * (n - 232) ))
    CANOPY_REPLY=$(( gray * 1000 / 255 ))
  elif (( n >= 16 )); then
    idx=$(( n - 16 ))
    ri=$(( idx / 36 ))
    gi=$(( (idx / 6) % 6 ))
    bi=$(( idx % 6 ))
    r=$(( ri ? 55 + 40 * ri : 0 ))
    g=$(( gi ? 55 + 40 * gi : 0 ))
    b=$(( bi ? 55 + 40 * bi : 0 ))
    CANOPY_REPLY=$(( (299 * r + 587 * g + 114 * b) / 255 ))
  else
    case "$n" in
      0)  CANOPY_REPLY=0 ;;
      1)  CANOPY_REPLY=240 ;;
      2)  CANOPY_REPLY=470 ;;
      3)  CANOPY_REPLY=710 ;;
      4)  CANOPY_REPLY=180 ;;
      5)  CANOPY_REPLY=330 ;;
      6)  CANOPY_REPLY=560 ;;
      7)  CANOPY_REPLY=750 ;;
      8)  CANOPY_REPLY=330 ;;
      9)  CANOPY_REPLY=410 ;;
      10) CANOPY_REPLY=710 ;;
      11) CANOPY_REPLY=890 ;;
      12) CANOPY_REPLY=390 ;;
      13) CANOPY_REPLY=520 ;;
      14) CANOPY_REPLY=780 ;;
      15) CANOPY_REPLY=1000 ;;
    esac
  fi
}

# Pick a contrasting foreground token for solid accent selection bars.
canopy_solid_fg() {
  local accent="${1:-6}" luma=560
  canopy_color_luma "$accent"
  [[ -z "$CANOPY_REPLY" ]] || luma=$CANOPY_REPLY
  if [[ "$accent" == \#* ]]; then
    if (( luma < 450 )); then CANOPY_REPLY='#ffffff'; else CANOPY_REPLY='#000000'; fi
  elif [[ "$accent" =~ ^[0-9]+$ ]] && (( 10#$accent >= 16 || ${CANOPY_THEME_LIGHT:-0} == 1 )); then
    if (( luma < 450 )); then CANOPY_REPLY=231; else CANOPY_REPLY=16; fi
  else
    if (( luma < 450 )); then CANOPY_REPLY=15; else CANOPY_REPLY=0; fi
  fi
}

# True when two 0–1000 luma values can be told apart as foreground and background.
canopy_luma_contrast_ok() {
  local hi=$1 lo=$2
  (( hi < lo )) && { hi=$2; lo=$1; }
  # 1.8 rejects a foreground that is the background (Dracula mode fg #282a36
  # on status bg #282a36) and keeps pastel accents such as Nord green; a 280
  # luma gap keeps warm amber/ochre accents on high-luma light backgrounds.
  (( (hi + 50) * 10 / (lo + 50) >= 18 || hi - lo >= 280 ))
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
    if [[ "$attr" == fg && "${CANOPY_FG_CONTRAST:-1}" == 1 && -n "${CANOPY_BG_LUMA:-}" ]] && \
       { [[ "$token" == \#* ]] || (( 10#$token >= 16 )); }; then
      canopy_color_luma "$token"
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
# hides the row. Lift it enough to see.
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

# Symmetric adjustment for light themes: an inherited near-white status
# background disappears on a matching light terminal unless shaded slightly.
canopy_darken_light_hex() {
  local hex="${1#\#}" channel out i
  CANOPY_REPLY=$1
  [[ "$hex" =~ ^[[:xdigit:]]{6}$ ]] || return 0
  out='#'
  for ((i = 0; i < 6; i += 2)); do
    channel=$((16#${hex:i:2} - 32))
    (( channel < 0 )) && channel=0
    printf -v channel '%02x' "$channel"
    out+=$channel
  done
  CANOPY_REPLY=$out
}

# Set one semantic role from a raw color token. Leaves the role unchanged when
# the token is empty or invalid.
canopy_set_role_color() {
  local role="$1" raw="${2:-}" fzf_val ansi_val
  canopy_color_to_fzf "$raw"
  fzf_val=$CANOPY_REPLY
  [[ -n "$fzf_val" ]] || return 1
  case "$role" in
    accent)
      CANOPY_COLOR_ACCENT_FZF=$fzf_val
      canopy_color_to_ansi "$raw"; ansi_val=$CANOPY_REPLY
      [[ -n "$ansi_val" ]] && CANOPY_COLOR_ACCENT_ANSI=$ansi_val
      ;;
    active)
      CANOPY_COLOR_ACTIVE_FZF=$fzf_val
      canopy_color_to_ansi "$raw"; ansi_val=$CANOPY_REPLY
      [[ -n "$ansi_val" ]] && CANOPY_COLOR_ACTIVE_ANSI=$ansi_val
      ;;
    attention)
      CANOPY_COLOR_ATTENTION_FZF=$fzf_val
      canopy_color_to_ansi "$raw"; ansi_val=$CANOPY_REPLY
      [[ -n "$ansi_val" ]] && CANOPY_COLOR_ATTENTION_ANSI=$ansi_val
      ;;
    error)
      CANOPY_COLOR_ERROR_FZF=$fzf_val
      canopy_color_to_ansi "$raw"; ansi_val=$CANOPY_REPLY
      [[ -n "$ansi_val" ]] && CANOPY_COLOR_ERROR_ANSI=$ansi_val
      ;;
    muted)
      CANOPY_COLOR_MUTED_FZF=$fzf_val
      canopy_color_to_ansi "$raw"; ansi_val=$CANOPY_REPLY
      [[ -n "$ansi_val" ]] && CANOPY_COLOR_MUTED_ANSI=$ansi_val
      ;;
    border)
      CANOPY_COLOR_BORDER_FZF=$fzf_val
      ;;
    fg)
      CANOPY_COLOR_FG_FZF=$fzf_val
      ;;
    selection-bg)
      CANOPY_COLOR_SELECTION_BG=$fzf_val
      ;;
    selection-fg)
      CANOPY_COLOR_SELECTION_FG=$fzf_val
      ;;
    *) return 1 ;;
  esac
  return 0
}

canopy_apply_palette() {
  CANOPY_THEME_LIGHT=$1
  canopy_set_role_color accent "$2"
  canopy_set_role_color active "$3"
  canopy_set_role_color attention "$4"
  canopy_set_role_color error "$5"
  canopy_set_role_color muted "$6"
  canopy_set_role_color selection-bg "$7"
  canopy_set_role_color border "$8"
}

# Normalize a theme name into CANOPY_REPLY. Returns 0 when recognized, 1 (with
# CANOPY_REPLY=ansi) when empty or unknown.
canopy_theme_normalize() {
  local name="${1:-}"
  name=${name#"${name%%[![:space:]]*}"}
  name=${name%"${name##*[![:space:]]}"}
  name=${name,,}
  name=${name//_/-}
  case "$name" in
    catppuccin) name=catppuccin-mocha ;;
    gruvbox) name=gruvbox-dark ;;
    tokyo-night-light) name=tokyo-night-day ;;
  esac
  case "$name" in
    ansi|fixed|mono|\
    catppuccin-mocha|catppuccin-macchiato|catppuccin-frappe|catppuccin-latte|\
    tokyo-night|tokyo-night-storm|tokyo-night-day|\
    dracula|nord|gruvbox-dark|gruvbox-light|\
    github-dark|github-light|\
    rose-pine|rose-pine-moon|rose-pine-dawn|\
    kanagawa|everforest|one-dark|\
    solarized-dark|solarized-light)
      CANOPY_REPLY=$name
      return 0
      ;;
  esac
  CANOPY_REPLY=ansi
  return 1
}

canopy_theme_preset() {
  local preset="$1"
  canopy_theme_fixed
  CANOPY_THEME=$preset
  case "$preset" in
    catppuccin-mocha)     canopy_apply_palette 0 '#89b4fa' '#a6e3a1' '#f9e2af' '#f38ba8' '#a6adc8' '#313244' '#45475a' ;;
    catppuccin-macchiato) canopy_apply_palette 0 '#8aadf4' '#a6da95' '#eed49f' '#ed8796' '#a5adcb' '#363a4f' '#494d64' ;;
    catppuccin-frappe)    canopy_apply_palette 0 '#8caaee' '#a6d189' '#e5c890' '#e78284' '#a5adce' '#414559' '#51576d' ;;
    catppuccin-latte)     canopy_apply_palette 1 '#1e66f5' '#40a02b' '#df8e1d' '#d20f39' '#5c5f77' '#ccd0da' '#bcc0cc' ;;
    tokyo-night)          canopy_apply_palette 0 '#7aa2f7' '#9ece6a' '#e0af68' '#f7768e' '#9aa5ce' '#292e42' '#3b4261' ;;
    tokyo-night-storm)    canopy_apply_palette 0 '#7aa2f7' '#9ece6a' '#e0af68' '#f7768e' '#9aa5ce' '#2f3549' '#3b4261' ;;
    tokyo-night-day)      canopy_apply_palette 1 '#2e7de9' '#587539' '#8c6c3e' '#f52a65' '#6172b0' '#c4c8da' '#a8aecb' ;;
    dracula)              canopy_apply_palette 0 '#bd93f9' '#50fa7b' '#ffb86c' '#ff5555' '#9ea8c7' '#44475a' '#6272a4' ;;
    nord)                 canopy_apply_palette 0 '#88c0d0' '#a3be8c' '#ebcb8b' '#bf616a' '#9aa5b8' '#434c5e' '#4c566a' ;;
    gruvbox-dark)         canopy_apply_palette 0 '#83a598' '#b8bb26' '#fabd2f' '#fb4934' '#a89984' '#3c3836' '#504945' ;;
    gruvbox-light)        canopy_apply_palette 1 '#076678' '#79740e' '#b57614' '#9d0006' '#665c54' '#ebdbb2' '#d5c4a1' ;;
    github-dark)          canopy_apply_palette 0 '#58a6ff' '#3fb950' '#d29922' '#f85149' '#8b949e' '#30363d' '#30363d' ;;
    github-light)         canopy_apply_palette 1 '#0969da' '#1a7f37' '#9a6700' '#cf222e' '#57606a' '#dde3ea' '#d0d7de' ;;
    rose-pine)            canopy_apply_palette 0 '#c4a7e7' '#9ccfd8' '#f6c177' '#eb6f92' '#908caa' '#403d52' '#403d52' ;;
    rose-pine-moon)       canopy_apply_palette 0 '#c4a7e7' '#9ccfd8' '#f6c177' '#eb6f92' '#908caa' '#44415a' '#56526e' ;;
    rose-pine-dawn)       canopy_apply_palette 1 '#286983' '#56949f' '#ea9d34' '#b4637a' '#797593' '#dfdad9' '#cecacd' ;;
    kanagawa)             canopy_apply_palette 0 '#7e9cd8' '#98bb6c' '#e6c384' '#e46876' '#9cabca' '#363646' '#54546d' ;;
    everforest)           canopy_apply_palette 0 '#7fbbb3' '#a7c080' '#dbbc7f' '#e67e80' '#9da9a0' '#3d484d' '#4f585e' ;;
    one-dark)             canopy_apply_palette 0 '#61afef' '#98c379' '#e5c07b' '#e06c75' '#848b98' '#3e4451' '#4b5263' ;;
    solarized-dark)       canopy_apply_palette 0 '#268bd2' '#859900' '#b58900' '#dc322f' '#93a1a1' '#0f4250' '#586e75' ;;
    solarized-light)      canopy_apply_palette 1 '#268bd2' '#859900' '#b58900' '#dc322f' '#586e75' '#e6dfca' '#93a1a1' ;;
    *) return 1 ;;
  esac
}

canopy_theme_resolve() {
  local raw_theme='' theme status_style='' active_border='' pane_border=''
  local message_style='' message_cmd='' selection_background='' selection_luma
  local opt_name opt_val bg_token
  local ov_accent='' ov_active='' ov_attention='' ov_error='' ov_muted=''
  local ov_border='' ov_sel_bg='' ov_sel_fg='' ov_fg=''

  if [[ "${CANOPY_THEME_FROZEN:-0}" == 1 && -n "${CANOPY_COLOR_ACCENT_FZF:-}" ]]; then
    return 0
  fi

  # One batched tmux call collects every tmux style and Canopy theme option.
  while IFS=' ' read -r opt_name opt_val; do
    if [[ "$opt_val" == \"*\" && ${#opt_val} -ge 2 ]]; then
      opt_val=${opt_val:1:${#opt_val}-2}
      opt_val=${opt_val//\\\"/\"}
      opt_val=${opt_val//\\\\/\\}
    fi
    case "$opt_name" in
      status-style) status_style=$opt_val ;;
      pane-active-border-style) active_border=$opt_val ;;
      pane-border-style) pane_border=$opt_val ;;
      message-style) message_style=$opt_val ;;
      message-command-style) message_cmd=$opt_val ;;
      @tmux-canopy-theme) raw_theme=$opt_val ;;
      @tmux-canopy-selection-background) selection_background=$opt_val ;;
      @tmux-canopy-color-accent) ov_accent=$opt_val ;;
      @tmux-canopy-color-active) ov_active=$opt_val ;;
      @tmux-canopy-color-attention) ov_attention=$opt_val ;;
      @tmux-canopy-color-error) ov_error=$opt_val ;;
      @tmux-canopy-color-muted) ov_muted=$opt_val ;;
      @tmux-canopy-color-border) ov_border=$opt_val ;;
      @tmux-canopy-color-selection-bg) ov_sel_bg=$opt_val ;;
      @tmux-canopy-color-selection-fg) ov_sel_fg=$opt_val ;;
      @tmux-canopy-color-fg) ov_fg=$opt_val ;;
    esac
  done < <(
    tmux show-options -g status-style \; \
      show-options -g pane-active-border-style \; \
      show-options -g pane-border-style \; \
      show-options -g message-style \; \
      show-options -g message-command-style \; \
      show-options -gq @tmux-canopy-theme \; \
      show-options -gq @tmux-canopy-selection-background \; \
      show-options -gq @tmux-canopy-color-accent \; \
      show-options -gq @tmux-canopy-color-active \; \
      show-options -gq @tmux-canopy-color-attention \; \
      show-options -gq @tmux-canopy-color-error \; \
      show-options -gq @tmux-canopy-color-muted \; \
      show-options -gq @tmux-canopy-color-border \; \
      show-options -gq @tmux-canopy-color-selection-bg \; \
      show-options -gq @tmux-canopy-color-selection-fg \; \
      show-options -gq @tmux-canopy-color-fg 2>/dev/null || true
  )

  canopy_theme_normalize "$raw_theme" || true
  theme=$CANOPY_REPLY

  if [[ "$theme" == mono ]]; then
    canopy_theme_fixed
    CANOPY_THEME=mono
    return 0
  fi

  if [[ "$theme" == fixed ]]; then
    canopy_theme_fixed
    return 0
  fi

  if [[ "$theme" != ansi ]]; then
    canopy_theme_preset "$theme"
  else
    # ansi: inherit with per-slot fallbacks to the fixed palette.
    canopy_theme_fixed
    CANOPY_THEME=ansi

    # Status background is the best hint of a dark or light terminal when it is
    # a real theme background (hex or 256-color >= 16, not stock tmux bg=green).
    # mode-style is not an accent: its fg contrasts with the highlight itself.
    CANOPY_BG_LUMA=
    CANOPY_FG_CONTRAST=0 canopy_first_style_color bg "$status_style"
    bg_token=$CANOPY_REPLY
    if [[ "$bg_token" == \#* ]] || \
       { [[ "$bg_token" =~ ^[0-9]+$ ]] && (( 10#$bg_token >= 16 )); }; then
      canopy_color_luma "$bg_token"
      CANOPY_BG_LUMA=$CANOPY_REPLY
    fi
    if [[ -n "$CANOPY_BG_LUMA" ]]; then
      if (( CANOPY_BG_LUMA < 450 )); then
        CANOPY_THEME_LIGHT=0
        CANOPY_COLOR_MUTED_FZF='#e6e6e6'
        CANOPY_COLOR_MUTED_ANSI=$'\033[38;2;230;230;230m'
      else
        CANOPY_THEME_LIGHT=1
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

    # Stock tmux uses bg=green; inheriting that makes selection neon. Prefer
    # truecolor / 256-color status backgrounds from real themes only, and lift
    # very dark or shade very light inherited backgrounds so selection shows.
    if [[ "$bg_token" == \#* ]]; then
      CANOPY_COLOR_SELECTION_BG=$bg_token
      if [[ -n "$CANOPY_BG_LUMA" ]]; then
        if (( CANOPY_BG_LUMA < 180 )); then
          canopy_lift_dark_hex "$CANOPY_COLOR_SELECTION_BG"
          CANOPY_COLOR_SELECTION_BG=$CANOPY_REPLY
        elif (( CANOPY_BG_LUMA > 820 )); then
          canopy_darken_light_hex "$CANOPY_COLOR_SELECTION_BG"
          CANOPY_COLOR_SELECTION_BG=$CANOPY_REPLY
        fi
      fi
    elif [[ "$bg_token" =~ ^[0-9]+$ ]] && (( 10#$bg_token >= 16 )); then
      CANOPY_COLOR_SELECTION_BG=$bg_token
      if [[ -n "$CANOPY_BG_LUMA" ]]; then
        if (( CANOPY_BG_LUMA < 180 )); then
          CANOPY_COLOR_SELECTION_BG=237
        elif (( CANOPY_BG_LUMA > 820 )); then
          CANOPY_COLOR_SELECTION_BG=252
        fi
      fi
    fi

    # A border is a line. It may be close to the background and still be the
    # right color; the contrast filter is for text.
    CANOPY_FG_CONTRAST=0 canopy_first_style_color fg "$pane_border"
    if [[ -n "$CANOPY_REPLY" ]]; then
      CANOPY_COLOR_BORDER_FZF=$CANOPY_REPLY
    fi
  fi

  # Explicit per-role user overrides layer on top of ansi and named presets,
  # and are never altered by inherited selection-background luma adjustments.
  canopy_set_role_color accent "$ov_accent" || true
  canopy_set_role_color active "$ov_active" || true
  canopy_set_role_color attention "$ov_attention" || true
  canopy_set_role_color error "$ov_error" || true
  canopy_set_role_color muted "$ov_muted" || true
  canopy_set_role_color border "$ov_border" || true
  canopy_set_role_color fg "$ov_fg" || true
  canopy_set_role_color selection-fg "$ov_sel_fg" || true
  if canopy_set_role_color selection-bg "$ov_sel_bg" || \
     canopy_set_role_color selection-bg "$selection_background"; then
    CANOPY_SELECTION_EXPLICIT=1
  fi
  if [[ -n "$ov_sel_bg" || -n "$selection_background" ]] && (( CANOPY_SELECTION_EXPLICIT == 1 )); then
    canopy_color_luma "$CANOPY_COLOR_SELECTION_BG"
    selection_luma=$CANOPY_REPLY
    # If ansi had no status bg hint, let a bright explicit selection bar inform
    # light-mode contrast when muted was not explicitly overridden.
    if [[ "$theme" == ansi && -z "${CANOPY_BG_LUMA:-}" && -n "$selection_luma" && "$selection_luma" -ge 700 ]]; then
      CANOPY_THEME_LIGHT=1
      if [[ -z "$ov_muted" ]]; then
        CANOPY_COLOR_MUTED_FZF='#3a3a3a'
        CANOPY_COLOR_MUTED_ANSI=$'\033[38;2;58;58;58m'
      fi
    fi
  fi
}

# Export resolved colors for child processes (fzf reloads, awk).
canopy_theme_export() {
  export CANOPY_THEME CANOPY_THEME_LIGHT \
    CANOPY_COLOR_FG_FZF \
    CANOPY_COLOR_ACCENT_FZF CANOPY_COLOR_ACTIVE_FZF \
    CANOPY_COLOR_ATTENTION_FZF CANOPY_COLOR_ERROR_FZF \
    CANOPY_COLOR_MUTED_FZF CANOPY_COLOR_BORDER_FZF \
    CANOPY_COLOR_SELECTION_BG CANOPY_COLOR_SELECTION_FG \
    CANOPY_COLOR_ACCENT_ANSI CANOPY_COLOR_ACTIVE_ANSI \
    CANOPY_COLOR_ATTENTION_ANSI CANOPY_COLOR_ERROR_ANSI \
    CANOPY_COLOR_MUTED_ANSI \
    CANOPY_SELECTION_EXPLICIT
}

canopy_theme_freeze() {
  canopy_theme_resolve
  canopy_theme_export
  export CANOPY_THEME_FROZEN=1
}
