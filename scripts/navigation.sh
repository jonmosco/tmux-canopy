#!/usr/bin/env bash
# Shared navigation engine. Callers source lib.sh first.
# shellcheck disable=SC1091
source "$SCRIPT_DIR/notification-lib.sh"

# One read transaction supplies target/client context and pane relationships.
# No titles or paths are collected: only stable IDs and navigation metadata.
sidebar_navigation_snapshot() {
  local kind a b c d e f g h i j k l index current_index='' last_window='' chosen='' wrap=''
  local -A relative_windows=()
  local -a query=() prefix=()
  if [[ "$nav_spec" == :* ]]; then
    # display-message -c chooses the message recipient, NOT the session used
    # by a relative -t. Resolve against this client's window inventory instead.
    query=(list-windows -a -F 'W|#{session_id}|#{window_id}|#{window_index}|#{window_last_flag}')
  else
    query=(display-message -p -t "$nav_spec" "T|#{session_id}|#{window_id}|#{pane_id}|#{$nav_guard}")
  fi
  if [[ "${1:-}" == locked ]]; then
    prefix=(wait-for -L "$nav_lock" ';' set-option -gq "$nav_guard" 1 ';')
  fi
  nav_target='' nav_session='' nav_current='' nav_current_session='' nav_current_window=''
  nav_position=left nav_sidebar='' nav_slot='' nav_slot_width='' nav_first='' nav_active='' nav_last='' nav_guarded=''
  nav_windows=() nav_sidebars=() nav_slots=() nav_widths=() nav_targets=() nav_actives=() nav_totals=() nav_lasts=() nav_heights=()
  while IFS='|' read -r kind a b c d e f g h i j k l; do
    case "$kind" in
      G)
        nav_requested="${a:-$nav_width}"; nav_minimum="${b:-24}"; nav_maximum="${c:-0}"; nav_min_content="${d:-40}"
        if [[ "$nav_requested" =~ ^[1-9][0-9]*$ && "$e" =~ ^([1-9][0-9]*|[1-9][0-9]?%)$ ]]; then nav_requested="$e"; fi
        ;;
      T) nav_session="$a"; nav_window="$b"; nav_target="$c"; nav_guarded="$d" ;;
      C)
        if [[ "$a" == "$nav_client" ]]; then
          nav_current_session="$b"; nav_current_window="$c"; nav_current="$d"; nav_guarded="$e"
        fi
        ;;
      W)
        if [[ "$a" == "$nav_current_session" ]]; then
          relative_windows["$c"]="$b"
          [[ "$b" == "$nav_current_window" ]] && current_index="$c"
          [[ "$d" == 1 ]] && last_window="$b"
        fi
        ;;
      P)
        nav_windows["$a"]="$b"; nav_actives["$a"]="$c"; nav_lasts["$a"]="$j"
        nav_sidebars["$a"]="$d"; nav_slots["$a"]="$e"
        nav_widths["$a"]="$g"; nav_targets["$a"]="$h"; nav_totals["$a"]="$i"; nav_heights["$a"]="$l"
        if [[ "$d" == 1 && ( ( -n "$nav_client" && "$f" == "$nav_client" ) || ( -z "$nav_client" && "$a" == "$nav_hint" ) ) ]]; then
          nav_sidebar="$a"
          [[ "$k" != right ]] || nav_position=right
        fi
        ;;
    esac
  done < <(tmux "${prefix[@]}" list-clients -F "C|#{client_tty}|#{session_id}|#{window_id}|#{pane_id}|#{$nav_guard}" \; \
    list-panes -a -F 'P|#{pane_id}|#{window_id}|#{pane_active}|#{@tmux_canopy}|#{@tmux_canopy_slot}|#{@tmux_canopy_client}|#{pane_width}|#{@tmux_canopy_target}|#{window_width}|#{pane_last}|#{@tmux_canopy_position}|#{window_height}' \; \
    display-message -p 'G|#{@tmux-canopy-width}|#{@tmux-canopy-min-width}|#{@tmux-canopy-max-width}|#{@tmux-canopy-min-content-width}|#{@tmux_canopy_runtime_width}' \; \
    "${query[@]}" 2>/dev/null)

  # A hook's expanded pane may be stale, especially across sessions. Never
  # move toward it when the owning client's live destination is available.
  if [[ "$nav_mode" == follow && -n "$nav_current" ]]; then
    nav_target="$nav_current"; nav_window="$nav_current_window"; nav_session="$nav_current_session"
  fi
  if [[ "$nav_spec" == :* ]]; then
    [[ -n "$nav_current" && -n "$current_index" ]] || return 1
    nav_session="$nav_current_session"
    case "$nav_spec" in
      ':!') nav_window="$last_window" ;;
      :[0-9]) nav_window="${relative_windows[${nav_spec#:}]:-}" ;;
      ':+'|':-')
        for index in "${!relative_windows[@]}"; do
          if [[ "$nav_spec" == ':+' ]]; then
            if [[ -z "$wrap" ]] || ((index < wrap)); then wrap="$index"; fi
            if ((index > current_index)) && { [[ -z "$chosen" ]] || ((index < chosen)); }; then chosen="$index"; fi
          else
            if [[ -z "$wrap" ]] || ((index > wrap)); then wrap="$index"; fi
            if ((index < current_index)) && { [[ -z "$chosen" ]] || ((index > chosen)); }; then chosen="$index"; fi
          fi
        done
        nav_window="${relative_windows[${chosen:-$wrap}]:-}"
        ;;
    esac
    [[ -n "$nav_window" ]] || return 1
  else
    [[ -n "$nav_target" && -n "${nav_windows[$nav_target]:-}" ]] || return 1
    nav_window="${nav_windows[$nav_target]}"
  fi
  for a in "${!nav_windows[@]}"; do
    [[ "${nav_windows[$a]}" == "$nav_window" ]] || continue
    if [[ "${nav_slots[$a]}" == 1 ]]; then
      nav_slot="$a"; nav_slot_width="${nav_widths[$a]}"
    elif [[ "${nav_sidebars[$a]}" != 1 ]]; then
      # Numeric stable IDs give a deterministic fallback independent of hash order.
      if [[ -z "$nav_first" ]] || (( ${a#%} < ${nav_first#%} )); then nav_first="$a"; fi
      [[ "${nav_actives[$a]}" == 1 ]] && nav_active="$a"
      [[ "${nav_lasts[$a]}" == 1 ]] && nav_last="$a"
    fi
  done
  nav_target="${nav_target:-${nav_active:-${nav_last:-$nav_first}}}"
  [[ -n "$nav_target" ]] || return 1
  if [[ "${nav_sidebars[$nav_target]}" == 1 || "${nav_slots[$nav_target]}" == 1 ]]; then
    nav_target="${nav_active:-${nav_last:-$nav_first}}"
  fi
  [[ -n "$nav_target" && -n "$nav_session" ]]
}

# mode=select focuses the destination; mode=follow only relocates the sidebar.
# A subshell scopes the transition cleanup trap, including interruption/error paths.
sidebar_navigate() (
  local nav_client="${1:-}" nav_spec="${2:-}" nav_width="${3:-42}"
  local nav_scope="${4:-window}" nav_transition="${5:-move}" nav_mode="${6:-select}" nav_hint="${7:-}"
  local nav_key nav_guard nav_lock nav_locked=0 nav_notice_window=''
  local nav_target nav_session nav_window nav_current nav_current_session nav_current_window
  local nav_position nav_sidebar nav_slot nav_slot_width nav_first nav_active nav_last nav_guarded
  local nav_requested nav_minimum nav_maximum nav_min_content nav_source_width nav_saved_layout
  local SIDEBAR_WIDTH_FORMAT SIDEBAR_WIDTH_FITS_FORMAT
  local -A nav_windows=() nav_sidebars=() nav_slots=() nav_widths=() nav_targets=() nav_actives=() nav_totals=() nav_lasts=() nav_heights=()
  local -a commands=() placement=()
  [[ -n "$nav_spec" ]] || exit 0
  nav_key="$(sidebar_client_key "$nav_client")"
  nav_guard="@tmux_canopy_transition_$nav_key"
  nav_lock="tmux-canopy-follow-$nav_key"

  sidebar_navigation_snapshot || exit 0
  [[ "$nav_mode" == follow && "$nav_guarded" == 1 ]] && exit 0
  [[ "$nav_mode" == follow && -z "$nav_sidebar" ]] && exit 0

  # Common case: no layout or session/window transition. Do not invoke
  # switch-client/select-window merely to focus a pane (or reselect it).
  if [[ "$nav_guarded" != 1 ]] && \
     [[ ( "$nav_current_window" == "$nav_window" && "$nav_current_session" == "$nav_session" ) || "$nav_mode" == follow ]] && \
     [[ "$nav_scope" != global || -z "$nav_sidebar" || "${nav_windows[$nav_sidebar]}" == "$nav_window" ]]; then
    if [[ -n "$nav_sidebar" ]]; then
      nav_source_width="$(clamp_sidebar_width_for_total "${nav_totals[$nav_sidebar]}" "$nav_requested" "$nav_minimum" "$nav_maximum" "$nav_min_content")" || nav_source_width=''
      if [[ -n "$nav_source_width" && "${nav_widths[$nav_sidebar]}" != "$nav_source_width" ]]; then
        commands+=(resize-pane -t "$nav_sidebar" -x "$nav_source_width" ';')
      fi
    fi
    if [[ -n "$nav_sidebar" && "${nav_targets[$nav_sidebar]}" != "$nav_target" ]]; then
      commands+=(set-option -p -t "$nav_sidebar" @tmux_canopy_target "$nav_target" ';')
    fi
    if [[ "$nav_mode" == select && "$nav_current" != "$nav_target" ]]; then
      commands+=(select-pane -t "$nav_target" ';')
    fi
    if ((${#commands[@]})); then tmux "${commands[@]}"; fi
    exit 0
  fi

  # Serialize structural navigation across all entry points. Nested follow
  # hooks see the guard above and return before waiting on this lock.
  # shellcheck disable=SC2317,SC2329 # Invoked by the EXIT trap in this subshell.
  navigation_cleanup() {
    if ((nav_locked)); then
      local -a finish=(set-option -gu "$nav_guard" ';')
      if [[ -n "$nav_notice_window" ]]; then
        finish+=(set-option -wu -t "$nav_notice_window" @tmux_canopy_notice_suppress ';'
          if-shell -F 1 "$(notification_clear_command "$SCRIPT_DIR/notify" "$nav_client" "$nav_notice_window")" ';')
      fi
      finish+=(wait-for -U "$nav_lock")
      if [[ "$nav_mode" == select && -n "$nav_sidebar" && -n "$nav_current" ]]; then
        # Selection hooks can run while guarded. Schedule one final owner-only
        # marker update after the transaction, not an intermediate layout. The
        # transition already serialized and completed under this lock, so the
        # destination is provably settled; "settled" skips the general
        # stability debounce instead of paying its ~75ms+ minimum latency.
        finish+=(';' run-shell -b "$(tmux_shell "$SCRIPT_DIR/refresh-sidebar" "$nav_target" "$nav_client" settled)")
      fi
      tmux "${finish[@]}" 2>/dev/null || tmux wait-for -U "$nav_lock" 2>/dev/null || true
    fi
  }
  trap navigation_cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  nav_locked=1
  # Refresh after acquiring the lock; another transition may have completed
  # while this request waited. Slot/client decisions must use this snapshot.
  sidebar_navigation_snapshot locked || exit 0

  if [[ "$nav_mode" == select && -n "$nav_current" ]]; then
    nav_notice_window="$nav_window"
    commands+=(set-option -wq -t "$nav_window" @tmux_canopy_notice_suppress 1 ';')
    if [[ "$nav_current_window" != "$nav_window" || "$nav_current_session" != "$nav_session" ]]; then
      # Freeze relative next/last/index resolution before changing the client.
      nav_spec="$nav_session:.$nav_target"
      if [[ -n "${nav_totals[$nav_target]:-}" && "${nav_totals[$nav_target]}" == "${nav_totals[$nav_current]:-}" && \
            -n "${nav_heights[$nav_target]:-}" && "${nav_heights[$nav_target]}" == "${nav_heights[$nav_current]:-}" ]]; then
        # Fast path: the hidden destination window already matches client dimensions.
        # Defer window selection to the final batch after swap-pane below so the sidebar
        # is already in the destination window when it becomes visible, eliminating the
        # empty-slot flash.
        :
      else
        # Automatic tmux sizing is deferred past the selection command queue.
        # Let it settle before measuring/resizing the destination slot. On warm
        # switches the existing slot preserves content geometry during this step.
        # Native shrinking subtracts columns instead of retaining proportions and
        # can crush an application pane to one column in a stale, large window.
        nav_saved_layout="$(tmux display-message -p -t "$nav_target" '#{window_layout}' 2>/dev/null || true)"
        if [[ "$nav_current_session" != "$nav_session" ]]; then
          commands+=(switch-client -c "$nav_client" -t "$nav_session:$nav_window" ';')
        else
          commands+=(select-window -t "$nav_session:$nav_window" ';')
        fi
        tmux "${commands[@]}" || exit 0
        commands=()
        "$SCRIPT_DIR/restore-window-layout" "$nav_target" "$nav_saved_layout" "$nav_slot" \
          "$nav_requested" "$nav_minimum" "$nav_maximum" "$nav_min_content"
        sidebar_navigation_snapshot || exit 0
      fi
    fi
  fi
  if [[ "$nav_scope" == global && -n "$nav_sidebar" && "${nav_windows[$nav_sidebar]}" != "$nav_window" ]]; then
    # A pane's measured width may have been crushed by automatic window sizing.
    # Preserve the chosen width, clamped independently for each destination.
    nav_width="$(clamp_sidebar_width_for_total "${nav_totals[$nav_target]}" "$nav_requested" "$nav_minimum" "$nav_maximum" "$nav_min_content")" || nav_width=''
    if [[ -z "$nav_width" ]]; then
      # Leave the dock parked when this destination cannot accommodate it.
      nav_sidebar=''
    else
      nav_source_width="$(clamp_sidebar_width_for_total "${nav_totals[$nav_sidebar]}" "$nav_requested" "$nav_minimum" "$nav_maximum" "$nav_min_content")" || nav_source_width=''
      if [[ -n "$nav_source_width" && "${nav_widths[$nav_sidebar]}" != "$nav_source_width" ]]; then
        commands+=(resize-pane -t "$nav_sidebar" -x "$nav_source_width" ';')
      fi
    fi
  fi
  if [[ "$nav_scope" == global && -n "$nav_sidebar" && "${nav_windows[$nav_sidebar]}" != "$nav_window" ]]; then
    if [[ "$nav_transition" == slot ]]; then
      if [[ -z "$nav_slot" ]]; then
        nav_slot="$(ensure_slot_for_window "$nav_window" "$nav_target" "$nav_width" '' "$nav_position")" || exit 1
        [[ -n "$nav_slot" ]] || exit 1
      elif [[ "$nav_slot_width" != "$nav_width" ]]; then
        commands+=(resize-pane -t "$nav_slot" -x "$nav_width" ';')
      fi
      commands+=(swap-pane -d -s "$nav_sidebar" -t "$nav_slot" ';')
    else
      placement=(-b)
      [[ "$nav_position" != right ]] || placement=()
      commands+=(join-pane -d -h "${placement[@]}" -f -l "$nav_width" -s "$nav_sidebar" -t "$nav_target" ';')
    fi
  fi
  if [[ -n "$nav_sidebar" && "${nav_targets[$nav_sidebar]}" != "$nav_target" ]]; then
    commands+=(set-option -p -t "$nav_sidebar" @tmux_canopy_target "$nav_target" ';')
  fi
  if [[ "$nav_mode" == select ]]; then
    if [[ -n "$nav_current" && "$nav_current_session" != "$nav_session" ]]; then
      commands+=(switch-client -c "$nav_client" -t "$nav_session:$nav_window" ';')
    fi
    if [[ "$nav_current_window" != "$nav_window" || "$nav_current_session" != "$nav_session" ]]; then
      commands+=(select-window -t "$nav_session:$nav_window" ';')
    fi
    [[ "$nav_current" == "$nav_target" ]] || commands+=(select-pane -t "$nav_target" ';')
  fi
  if [[ -n "$nav_sidebar" ]]; then
    # Revalidate live geometry before releasing the navigation guard. Native
    # -C expansion is required: resize-pane's -x does not expand formats itself.
    sidebar_width_expression "$nav_requested" "$nav_minimum" "$nav_maximum" "$nav_min_content"
    commands+=(if-shell -F -t "$nav_sidebar" "#{&&:$SIDEBAR_WIDTH_FITS_FORMAT,#{!=:#{pane_width},$SIDEBAR_WIDTH_FORMAT}}"
      "run-shell -C -t '$nav_sidebar' 'resize-pane -t $nav_sidebar -x $SIDEBAR_WIDTH_FORMAT'" ';')
  fi
  if ((${#commands[@]})); then tmux "${commands[@]}"; fi
)
