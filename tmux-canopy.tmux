#!/usr/bin/env bash

CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$CURRENT_DIR/scripts/notification-lib.sh"
# shellcheck disable=SC1091
source "$CURRENT_DIR/scripts/lib.sh"
# shellcheck disable=SC1091
source "$CURRENT_DIR/scripts/config-lib.sh"

# Arguments here are internal tmux format templates or validated plugin options.
# The installation path is literal data, protected from shell and tmux parsing.
plugin_command() {
  local script="$1"; shift
  printf '%s %s' "$(tmux_shell "$CURRENT_DIR/scripts/$script")" "$(shell_join "$@")"
}
plugin_job() {
  local flag="$1"; shift
  printf 'run-shell %s %s' "$flag" "$(tmux_quote "$(plugin_command "$@")")"
}

# Read every setting, Canopy's ownership records, and the options it may own
# in two tmux calls (see canopy_load_state); unset settings read as empty.
settings=(key width scope smooth-navigation last-window-key transition notifications notification-target
  silence-seconds icon-theme appearance animate resize-mode width-presets mode popup-threshold popup-width popup-height)
canopy_load_state "${settings[@]/#/@tmux-canopy-}" \
  window:window-status-activity-style window:window-status-bell-style \
  session:activity-action session:bell-action session:silence-action \
  window:monitor-activity window:monitor-bell window:monitor-silence
setting() { printf -v "$1" '%s' "${CANOPY_STATE["@tmux-canopy-$2"]:-}"; }
setting sidebar_key key; setting sidebar_width width; setting sidebar_scope scope
setting smooth_navigation smooth-navigation; setting last_window_key last-window-key
setting sidebar_transition transition; setting notification_sources notifications
setting notification_target notification-target; setting silence_seconds silence-seconds
setting icon_theme icon-theme; setting appearance appearance; setting animate animate
setting resize_mode resize-mode; setting width_presets width-presets
setting sidebar_mode mode; setting popup_threshold popup-threshold
setting popup_width popup-width; setting popup_height popup-height

: "${sidebar_key:=T}"
: "${sidebar_width:=42}"
: "${sidebar_scope:=global}"
: "${smooth_navigation:=on}"
: "${last_window_key:=Tab}"
: "${sidebar_transition:=slot}"
: "${notification_sources:=activity,bell}"
: "${notification_target:=sidebar}"
: "${silence_seconds:=30}"
: "${icon_theme:=auto}"
: "${appearance:=default}"
: "${animate:=on}"
: "${resize_mode:=live}"
: "${width_presets:=30,42,48}"
: "${sidebar_mode:=sidebar}"
: "${popup_threshold:=100}"
: "${popup_width:=85%}"
: "${popup_height:=80%}"

if [[ "$sidebar_mode" != 'popup' && "$sidebar_mode" != 'auto' && "$sidebar_mode" != 'sidebar' ]]; then
  sidebar_mode=sidebar
fi
if [[ ! "$popup_threshold" =~ ^[1-9][0-9]*$ ]]; then
  popup_threshold=100
fi
if [[ ! "$popup_width" =~ ^[1-9][0-9]*%?$ ]]; then
  popup_width='85%'
fi
if [[ ! "$popup_height" =~ ^[1-9][0-9]*%?$ ]]; then
  popup_height='80%'
fi

if [[ ! "$sidebar_width" =~ ^[1-9][0-9]*%?$ ]]; then
  sidebar_width=42
fi
if [[ "$sidebar_scope" != 'window' && "$sidebar_scope" != 'global' ]]; then
  sidebar_scope=global
fi
if [[ "$sidebar_transition" != 'move' && "$sidebar_transition" != 'slot' ]]; then
  sidebar_transition=slot
fi
if [[ ! "$silence_seconds" =~ ^[1-9][0-9]*$ ]]; then
  silence_seconds=30
fi
if [[ "$notification_target" != 'sidebar' && "$notification_target" != 'status' && "$notification_target" != 'both' ]]; then
  notification_target=sidebar
fi

if [[ "$resize_mode" != 'staged' && "$resize_mode" != 'preset' && "$resize_mode" != 'live' ]]; then
  resize_mode=live
fi

if [[ "$icon_theme" == 'auto' ]]; then
  # tmux cannot inspect the font selected by each attached terminal client.
  # A Nerd Font installed on the server is not evidence that its glyphs render.
  icon_theme=unicode
fi
if [[ "$icon_theme" != 'nerdfont' && "$icon_theme" != 'unicode' && "$icon_theme" != 'ascii' ]]; then
  icon_theme=unicode
fi
case "$appearance" in
  default|'') appearance=places ;;
  ascii) appearance=places; icon_theme=ascii ;;
  classic) appearance=classic ;; # Preserve explicitly configured older setups.
  *) appearance=places ;;
esac
if [[ "$animate" != 'on' && "$animate" != 'off' ]]; then
  animate=on
fi

sidebar_notification_sources="$notification_sources"
if [[ "$notification_target" == 'status' ]]; then
  sidebar_notification_sources=none
fi

canopy_queue set-option -gq @tmux_canopy_notifications "$sidebar_notification_sources"
canopy_queue set-option -gq @tmux_canopy_notification_target "$notification_target"
canopy_queue set-option -gq @tmux_canopy_icon_theme "$icon_theme"
canopy_queue set-option -gq @tmux_canopy_appearance "$appearance"
canopy_queue set-option -gq @tmux_canopy_animate "$animate"
canopy_queue set-option -gq @tmux_canopy_resize_mode "$resize_mode"
canopy_queue set-option -gq @tmux_canopy_width_presets "$width_presets"
canopy_queue set-option -gq @tmux_canopy_mode "$sidebar_mode"
canopy_queue set-option -gq @tmux_canopy_popup_threshold "$popup_threshold"
canopy_queue set-option -gq @tmux_canopy_popup_width "$popup_width"
canopy_queue set-option -gq @tmux_canopy_popup_height "$popup_height"

for alert_source in activity bell; do
  style=''
  if [[ "$notification_sources" != none && "$notification_target" == sidebar ]]; then style=default; fi
  canopy_owned_option window "window-status-${alert_source}-style" "$style"
done
for alert_source in activity bell silence; do
  action_value=''
  if [[ "$notification_target" != sidebar && ( ",$notification_sources," == *,"$alert_source",* || ",$notification_sources," == *,all,* ) ]]; then
    action_value=other
  fi
  canopy_owned_option session "$alert_source-action" "$action_value"
done

for provider in activity bell silence; do
  monitor_value=''
  if [[ ",$notification_sources," == *,"$provider",* || ",$notification_sources," == *,all,* ]]; then
    monitor_value=on
    [[ "$provider" != silence ]] || monitor_value="$silence_seconds"
  fi
  canopy_owned_option window "monitor-$provider" "$monitor_value"
done

canopy_bind prefix "$sidebar_key" run-shell \
  "$(plugin_command toggle '#{client_tty}' '#{pane_id}' "$sidebar_width" "$sidebar_scope" "$sidebar_key" "$last_window_key" "$sidebar_transition")"

# Native next-layout includes every pane, which would shuffle the dock too.
canopy_bind prefix Space run-shell \
  "$(plugin_command content-layout '#{pane_id}' next '#{client_tty}')"

if [[ "$smooth_navigation" != 'off' ]]; then
  canopy_bind prefix n run-shell \
    "$(plugin_command navigate '#{client_tty}' next "$sidebar_width" "$sidebar_scope" "$sidebar_transition")"
  canopy_bind prefix p run-shell \
    "$(plugin_command navigate '#{client_tty}' previous "$sidebar_width" "$sidebar_scope" "$sidebar_transition")"
  for window_index in {0..9}; do
    canopy_bind prefix "$window_index" run-shell \
      "$(plugin_command navigate '#{client_tty}' "index:$window_index" "$sidebar_width" "$sidebar_scope" "$sidebar_transition")"
  done
  if [[ "$last_window_key" != 'off' ]]; then
    canopy_bind prefix "$last_window_key" run-shell \
      "$(plugin_command navigate '#{client_tty}' last "$sidebar_width" "$sidebar_scope" "$sidebar_transition")"
  fi
fi

# Dedicated array indexes avoid replacing hooks owned by the user's
# configuration or other plugins. Reloading removes stale hooks when modes
# change.
canopy_queue set-hook -gu 'after-select-window[9001]'
canopy_queue set-hook -gu 'after-new-window[9001]'
canopy_queue set-hook -gu 'client-session-changed[9001]'
canopy_queue set-hook -gu 'after-resize-pane[9001]'
canopy_queue set-hook -gu 'alert-activity[9002]'
canopy_queue set-hook -gu 'alert-bell[9002]'
canopy_queue set-hook -gu 'alert-silence[9002]'
canopy_queue set-hook -gu 'after-select-window[9002]'
canopy_queue set-hook -gu 'after-select-pane[9002]'
canopy_queue set-hook -gu 'client-session-changed[9002]'
canopy_queue set-hook -gu 'after-kill-pane[9003]'
canopy_queue set-hook -gu 'after-split-window[9003]'
canopy_queue set-hook -gu 'client-detached[9003]'
canopy_queue set-hook -gu 'client-resized[9003]'
canopy_queue set-hook -gu 'after-resize-window[9003]'
canopy_queue set-hook -gu 'after-rename-session[9003]'
canopy_queue set-hook -gu 'after-rename-window[9003]'
canopy_queue set-hook -gu 'window-layout-changed[9005]'
canopy_queue set-hook -gu 'window-unlinked[9005]'
canopy_queue set-hook -gu 'after-resize-pane[9006]'
canopy_queue set-hook -gu 'window-layout-changed[9007]'
for focus_hook in after-select-pane after-select-window after-new-window client-session-changed; do
  canopy_queue set-hook -gu "${focus_hook}[9004]"
done

if [[ "$sidebar_scope" == 'global' ]]; then
  # Detached new-window resolves to the unchanged live client, hence a no-op.
  for hook in after-select-window after-new-window client-session-changed; do
    canopy_queue set-hook -g "${hook}[9001]" "$(plugin_job '' follow '#{client_tty}' '#{pane_id}' "$sidebar_width" "$sidebar_transition")"
  done
fi

# Resize hooks fire for every pane on the server. Test the resized pane inside
# tmux so ordinary content resizes start no shell at all.
sidebar_pane_event="#{==:#{@tmux_canopy},1}"
if [[ "$sidebar_transition" == 'slot' && "$resize_mode" == 'live' ]]; then
  canopy_queue set-hook -g 'after-resize-pane[9001]' \
    "if-shell -F $(tmux_quote "$sidebar_pane_event") $(tmux_quote "$(plugin_job -b sync-width '#{pane_id}' '#{pane_width}')")"
fi

# A staged drag leaves the physical border in place, so subsequent events
# arrive over panes as well as borders. A temporary key table handles those
# events without replacing the user's normal pane-selection/copy bindings.
resize_table=tmux-canopy-resize
for event in MouseDrag1Pane MouseDrag1Border MouseDrag1Status; do
  canopy_queue bind-key -T "$resize_table" "$event" \
    if-shell -F '#{==:#{@tmux_canopy_drag_native},1}' \
    "resize-pane -M ; switch-client -T $resize_table" "switch-client -T $resize_table"
done
# mouse_x is pane-relative and empty on a border. Convert valid release
# coordinates to window columns before passing them to the resize helper.
release_x='#{?#{!=:#{mouse_x},},#{e|+:#{mouse_x},#{pane_left}},}'
for event in MouseDragEnd1Pane MouseDragEnd1Border MouseDragEnd1Status MouseUp1Pane MouseUp1Border MouseUp1Status; do
  canopy_queue bind-key -T "$resize_table" "$event" run-shell \
    "$(plugin_command mouse-resize end '#{@tmux_canopy_staged_sidebar}' '#{window_id}' "$release_x" "$resize_mode")"
done
# tmux can classify motion outside the original pane as an unnamed mouse
# event. Keep waiting for release; ordinary keyboard input cancels the drag.
canopy_queue bind-key -T "$resize_table" Any if-shell -F '#{mouse_pane}' \
  "switch-client -T $resize_table" "$(plugin_job '' mouse-resize clear)"
canopy_bind root MouseDown1Border \
  if-shell -F '1' \
    "$(plugin_job '' mouse-resize start '#{mouse_pane}' '#{window_id}' '#{mouse_x}' "$resize_mode") ; if-shell -F '#{==:#{@tmux_canopy_drag_native},1}' 'select-pane -M' ; if-shell -F '#{@tmux_canopy_staged_sidebar}' 'switch-client -T $resize_table' 'select-pane -M'" \
    ''
canopy_bind root MouseDrag1Border \
  if-shell -F '#{@tmux_canopy_staged_sidebar}' '' 'resize-pane -M'
canopy_bind root MouseDragEnd1Border \
  if-shell -F '#{@tmux_canopy_staged_sidebar}' \
    "$(plugin_job '' mouse-resize end '#{@tmux_canopy_staged_sidebar}' '#{window_id}' '#{mouse_x}' "$resize_mode")" \
    ''

# Native exits do not run after-kill-pane. Layout notifications cover exits,
# kills and moving the last content pane out. Gate in tmux: ordinary resizing
# and windows with live OR retained-dead content start no lifecycle worker.
# Hook default context can be the foreground window, even for a background
# exit. Resolve hook_window through native loops; vanished windows simply do
# not match. Only the matching window evaluates its pane inventory.
empty_event="#{S:#{W:#{?#{==:#{window_id},#{hook_window}},#{?$(sidebar_empty_window_condition),1,},}}}"
canopy_queue set-hook -g 'window-layout-changed[9005]' \
  "if-shell -F $(tmux_quote "$empty_event") $(tmux_quote "$(plugin_job -b reap-empty)")"
canopy_queue set-hook -g 'window-unlinked[9005]' "$(plugin_job -b reap-empty)"
balance_event="#{S:#{W:#{?#{==:#{window_id},#{hook_window}},#{?#{==:#{P:#{?#{||:#{==:#{@tmux_canopy},1},#{==:#{@tmux_canopy_slot},1}},,1}},1},1,},}}}"
canopy_queue set-hook -g 'window-layout-changed[9007]' \
  "if-shell -F $(tmux_quote "$balance_event") $(tmux_quote "$(plugin_job -b balance-window '#{hook_window}')")"
canopy_queue set-hook -g 'after-kill-pane[9003]' "$(plugin_job -b cleanup refresh)"
# Native and Canopy splits must repaint the tree immediately; waiting for a
# later select-pane leaves the new pane missing until focus moves again.
# Run synchronously so a slot split still sees the navigation transition guard
# and skips the reload (background -b can outlive the guard).
# With no sidebar anywhere on the server there is nothing to repaint, so the
# synchronous job is skipped inside tmux.
any_sidebar_event="#{S:#{W:#{P:#{?#{==:#{@tmux_canopy},1},1,}}}}"
canopy_queue set-hook -g 'after-split-window[9003]' \
  "if-shell -F $(tmux_quote "$any_sidebar_event") $(tmux_quote "$(plugin_job '' cleanup split)")"
# client_tty may already resolve to a surviving client after a detach.
canopy_queue set-hook -g 'client-detached[9003]' "$(plugin_job -b cleanup client '#{hook_client}')"
for hook in client-resized after-resize-window; do
  canopy_queue set-hook -g "${hook}[9003]" "$(plugin_job -b responsive-width)"
done
# Right-edge marks are padded to the sidebar width at render time. One reload
# after the width settles, not a tree rebuild on every column of a drag.
canopy_queue set-hook -gu 'after-resize-pane[9006]'
canopy_queue set-hook -g 'after-resize-pane[9006]' \
  "if-shell -F $(tmux_quote "$sidebar_pane_event") $(tmux_quote "$(plugin_job -b edge-refresh '#{pane_id}')")"
for hook in after-rename-session after-rename-window; do
  canopy_queue set-hook -g "${hook}[9003]" "$(plugin_job -b cleanup refresh)"
done
# tmux 3.8+ monitors pane command changes. The refresh script no-ops unless
# a sidebar client currently has agent mode on.
tmux set-hook -Bgu '@tmux_canopy_command:%*:#{pane_current_command}' 2>/dev/null || true
tmux set-hook -B -g '@tmux_canopy_command:%*:#{pane_current_command}' \
  "$(plugin_job -b agent-refresh)" 2>/dev/null || true
# Mouse and keyboard changes use the same debounced, state-preserving refresh.
for focus_hook in after-select-pane after-select-window after-new-window client-session-changed; do
  canopy_queue set-hook -g "${focus_hook}[9004]" \
    "$(plugin_job -b refresh-sidebar '#{pane_id}' '#{client_tty}' "$focus_hook" '#{mouse_pane}')"
done

if [[ "$notification_sources" != 'none' && "$notification_target" != 'status' ]]; then
  for source in activity bell silence; do
    canopy_queue set-hook -g "alert-${source}[9002]" "$(plugin_job -b notify set '#{window_id}' '#{pane_id}' "$source")"
  done
  clear_request="$(notification_clear_command "$CURRENT_DIR/scripts/notify" '#{client_tty}' '#{window_id}')"
  for hook in after-select-window after-select-pane client-session-changed; do
    canopy_queue set-hook -g "${hook}[9002]" "$clear_request"
  done
fi

# The legacy compatibility entrypoint is also a *.tmux file. TPM executes
# both; this marker lets that entrypoint avoid a duplicate load.
canopy_queue set-option -gq @tmux_canopy_loaded_path "$CURRENT_DIR"
# Write everything queued above, record new bindings, restore unused ones.
canopy_load_finish
