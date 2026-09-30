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

# Import settings from the previous project name once per option. Explicit
# canopy options (including empty values) always take precedence.
while read -r legacy_option _legacy_value; do
  [[ "$legacy_option" == @tmux-tree-sidebar-* ]] || continue
  canopy_option="@tmux-canopy-${legacy_option#@tmux-tree-sidebar-}"
  if [[ -z "$(tmux show-option -gq "$canopy_option")" ]]; then
    tmux set-option -gq "$canopy_option" "$(tmux show-option -gqv "$legacy_option")"
  fi
done < <(tmux show-options -g)

sidebar_key="$(tmux show-option -gqv @tmux-canopy-key)"
sidebar_width="$(tmux show-option -gqv @tmux-canopy-width)"
sidebar_scope="$(tmux show-option -gqv @tmux-canopy-scope)"
smooth_navigation="$(tmux show-option -gqv @tmux-canopy-smooth-navigation)"
last_window_key="$(tmux show-option -gqv @tmux-canopy-last-window-key)"
sidebar_transition="$(tmux show-option -gqv @tmux-canopy-transition)"
notification_sources="$(tmux show-option -gqv @tmux-canopy-notifications)"
notification_target="$(tmux show-option -gqv @tmux-canopy-notification-target)"
silence_seconds="$(tmux show-option -gqv @tmux-canopy-silence-seconds)"
icon_theme="$(tmux show-option -gqv @tmux-canopy-icon-theme)"
appearance="$(tmux show-option -gqv @tmux-canopy-appearance)"
animate="$(tmux show-option -gqv @tmux-canopy-animate)"
resize_mode="$(tmux show-option -gqv @tmux-canopy-resize-mode)"
width_presets="$(tmux show-option -gqv @tmux-canopy-width-presets)"

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

tmux set-option -gq @tmux_canopy_notifications "$sidebar_notification_sources"
tmux set-option -gq @tmux_canopy_notification_target "$notification_target"
tmux set-option -gq @tmux_canopy_icon_theme "$icon_theme"
tmux set-option -gq @tmux_canopy_appearance "$appearance"
tmux set-option -gq @tmux_canopy_animate "$animate"
tmux set-option -gq @tmux_canopy_resize_mode "$resize_mode"
tmux set-option -gq @tmux_canopy_width_presets "$width_presets"

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
tmux set-hook -gu 'after-select-window[9001]' 2>/dev/null || true
tmux set-hook -gu 'after-new-window[9001]' 2>/dev/null || true
tmux set-hook -gu 'client-session-changed[9001]' 2>/dev/null || true
tmux set-hook -gu 'after-resize-pane[9001]' 2>/dev/null || true
tmux set-hook -gu 'alert-activity[9002]' 2>/dev/null || true
tmux set-hook -gu 'alert-bell[9002]' 2>/dev/null || true
tmux set-hook -gu 'alert-silence[9002]' 2>/dev/null || true
tmux set-hook -gu 'after-select-window[9002]' 2>/dev/null || true
tmux set-hook -gu 'after-select-pane[9002]' 2>/dev/null || true
tmux set-hook -gu 'client-session-changed[9002]' 2>/dev/null || true
tmux set-hook -gu 'after-kill-pane[9003]' 2>/dev/null || true
tmux set-hook -gu 'after-split-window[9003]' 2>/dev/null || true
tmux set-hook -gu 'client-detached[9003]' 2>/dev/null || true
tmux set-hook -gu 'client-resized[9003]' 2>/dev/null || true
tmux set-hook -gu 'after-resize-window[9003]' 2>/dev/null || true
tmux set-hook -gu 'after-rename-session[9003]' 2>/dev/null || true
tmux set-hook -gu 'after-rename-window[9003]' 2>/dev/null || true
tmux set-hook -gu 'window-layout-changed[9005]' 2>/dev/null || true
tmux set-hook -gu 'window-unlinked[9005]' 2>/dev/null || true
tmux set-hook -gu 'after-resize-pane[9006]' 2>/dev/null || true
tmux set-hook -gu 'window-layout-changed[9007]' 2>/dev/null || true
for focus_hook in after-select-pane after-select-window after-new-window client-session-changed; do
  tmux set-hook -gu "${focus_hook}[9004]" 2>/dev/null || true
done

if [[ "$sidebar_scope" == 'global' ]]; then
  # Detached new-window resolves to the unchanged live client, hence a no-op.
  for hook in after-select-window after-new-window client-session-changed; do
    tmux set-hook -g "${hook}[9001]" "$(plugin_job '' follow '#{client_tty}' '#{pane_id}' "$sidebar_width" "$sidebar_transition")"
  done
fi

if [[ "$sidebar_transition" == 'slot' && "$resize_mode" == 'live' ]]; then
  tmux set-hook -g 'after-resize-pane[9001]' \
    "$(plugin_job -b sync-width '#{pane_id}' '#{pane_width}')"
fi

# A staged drag leaves the physical border in place, so subsequent events
# arrive over panes as well as borders. A temporary key table handles those
# events without replacing the user's normal pane-selection/copy bindings.
resize_table=tmux-canopy-resize
for event in MouseDrag1Pane MouseDrag1Border MouseDrag1Status; do
  tmux bind-key -T "$resize_table" "$event" \
    if-shell -F '#{==:#{@tmux_canopy_drag_native},1}' \
    "resize-pane -M ; switch-client -T $resize_table" "switch-client -T $resize_table"
done
# mouse_x is pane-relative and empty on a border. Convert valid release
# coordinates to window columns before passing them to the resize helper.
release_x='#{?#{!=:#{mouse_x},},#{e|+:#{mouse_x},#{pane_left}},}'
for event in MouseDragEnd1Pane MouseDragEnd1Border MouseDragEnd1Status MouseUp1Pane MouseUp1Border MouseUp1Status; do
  tmux bind-key -T "$resize_table" "$event" run-shell \
    "$(plugin_command mouse-resize end '#{@tmux_canopy_staged_sidebar}' '#{window_id}' "$release_x" "$resize_mode")"
done
# tmux can classify motion outside the original pane as an unnamed mouse
# event. Keep waiting for release; ordinary keyboard input cancels the drag.
tmux bind-key -T "$resize_table" Any if-shell -F '#{mouse_pane}' \
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
tmux set-hook -g 'window-layout-changed[9005]' \
  "if-shell -F $(tmux_quote "$empty_event") $(tmux_quote "$(plugin_job -b reap-empty)")"
tmux set-hook -g 'window-unlinked[9005]' "$(plugin_job -b reap-empty)"
balance_event="#{S:#{W:#{?#{==:#{window_id},#{hook_window}},#{?#{==:#{P:#{?#{||:#{==:#{@tmux_canopy},1},#{==:#{@tmux_canopy_slot},1}},,1}},1},1,},}}}"
tmux set-hook -g 'window-layout-changed[9007]' \
  "if-shell -F $(tmux_quote "$balance_event") $(tmux_quote "$(plugin_job -b balance-window '#{hook_window}')")"
tmux set-hook -g 'after-kill-pane[9003]' "$(plugin_job -b cleanup refresh)"
# Native and Canopy splits must repaint the tree immediately; waiting for a
# later select-pane leaves the new pane missing until focus moves again.
# Run synchronously so a slot split still sees the navigation transition guard
# and skips the reload (background -b can outlive the guard).
tmux set-hook -g 'after-split-window[9003]' "$(plugin_job '' cleanup split)"
# client_tty may already resolve to a surviving client after a detach.
tmux set-hook -g 'client-detached[9003]' "$(plugin_job -b cleanup client '#{hook_client}')"
for hook in client-resized after-resize-window; do
  tmux set-hook -g "${hook}[9003]" "$(plugin_job -b responsive-width)"
done
# Right-edge marks are padded to the sidebar width at render time. One reload
# after the width settles, not a tree rebuild on every column of a drag.
tmux set-hook -gu 'after-resize-pane[9006]' 2>/dev/null || true
tmux set-hook -g 'after-resize-pane[9006]' "$(plugin_job -b edge-refresh '#{pane_id}')"
for hook in after-rename-session after-rename-window; do
  tmux set-hook -g "${hook}[9003]" "$(plugin_job -b cleanup refresh)"
done
# tmux 3.8+ monitors pane command changes. The refresh script no-ops unless
# a sidebar client currently has agent mode on.
tmux set-hook -Bgu '@tmux_canopy_command:%*:#{pane_current_command}' 2>/dev/null || true
tmux set-hook -B -g '@tmux_canopy_command:%*:#{pane_current_command}' \
  "$(plugin_job -b agent-refresh)" 2>/dev/null || true
# Mouse and keyboard changes use the same debounced, state-preserving refresh.
for focus_hook in after-select-pane after-select-window after-new-window client-session-changed; do
  tmux set-hook -g "${focus_hook}[9004]" \
    "$(plugin_job -b refresh-sidebar '#{pane_id}' '#{client_tty}' "$focus_hook")"
done

if [[ "$notification_sources" != 'none' && "$notification_target" != 'status' ]]; then
  for source in activity bell silence; do
    tmux set-hook -g "alert-${source}[9002]" "$(plugin_job -b notify set '#{window_id}' '#{pane_id}' "$source")"
  done
  clear_request="$(notification_clear_command "$CURRENT_DIR/scripts/notify" '#{client_tty}' '#{window_id}')"
  for hook in after-select-window after-select-pane client-session-changed; do
    tmux set-hook -g "${hook}[9002]" "$clear_request"
  done
fi

canopy_restore_unused_bindings
# The legacy compatibility entrypoint is also a *.tmux file. TPM executes
# both; this marker lets that entrypoint avoid a duplicate load.
tmux set-option -gq @tmux_canopy_loaded_path "$CURRENT_DIR"
