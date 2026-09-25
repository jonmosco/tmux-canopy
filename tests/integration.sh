#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOCKET="tmux-canopy-test-$$"
TMUX_TEST=(tmux -L "$SOCKET")

cleanup() {
  "${TMUX_TEST[@]}" kill-server 2>/dev/null || true
}
trap cleanup EXIT

fail() {
  printf 'not ok - %s\n' "$1" >&2
  exit 1
}

assert_eq() {
  local expected="$1" actual="$2" message="$3"
  [[ "$actual" == "$expected" ]] || fail "$message (expected '$expected', got '$actual')"
}

run_in_server() {
  local target="$1"
  shift
  "${TMUX_TEST[@]}" run-shell -t "$target" "$*"
}

sidebar_for_owner() {
  local owner="$1"
  "${TMUX_TEST[@]}" list-panes -a \
    -F $'#{pane_id}\t#{@tmux_canopy}\t#{@tmux_canopy_client}' |
    awk -F '\t' -v owner="$owner" '$2 == "1" && $3 == owner { print $1; exit }'
}

help_output="$(TMUX_CANOPY_HELP_TEST=1 "$PROJECT_DIR/scripts/help")"
grep -Fq 'Navigation' <<< "$help_output" || fail 'help includes navigation keys'
grep -Fq 'Create' <<< "$help_output" || fail 'help includes creation keys'
grep -Fq 'prefix + T' <<< "$help_output" || fail 'help includes the sidebar toggle'
printf 'ok - renders built-in quick help\n'

"${TMUX_TEST[@]}" -f /dev/null new-session -d -s test -x 160 -y 44
"${TMUX_TEST[@]}" set-option -g bell-action none
"${TMUX_TEST[@]}" set-option -g base-index 1
"${TMUX_TEST[@]}" set-window-option -g pane-base-index 1
"${TMUX_TEST[@]}" move-window -s test:0 -t test:1
# Existing installations retain settings; explicit Canopy options win.
"${TMUX_TEST[@]}" set-option -g @tmux-tree-sidebar-width 37
"${TMUX_TEST[@]}" set-option -g @tmux-tree-sidebar-preview off
"${TMUX_TEST[@]}" set-option -g @tmux-canopy-width 42
"${TMUX_TEST[@]}" set-option -g @tmux-canopy-scope global
"${TMUX_TEST[@]}" set-option -g @tmux-canopy-transition slot
"${TMUX_TEST[@]}" set-option -g @tmux-canopy-notifications none
run_in_server test:1 "'$PROJECT_DIR/tmux-tree-sidebar.tmux'"
assert_eq '42' "$("${TMUX_TEST[@]}" show-option -gqv @tmux-canopy-width)" 'Canopy setting takes precedence over legacy setting'
assert_eq 'off' "$("${TMUX_TEST[@]}" show-option -gqv @tmux-canopy-preview)" 'legacy launcher imports existing settings'
"${TMUX_TEST[@]}" set-option -gu @tmux-canopy-notifications
printf 'ok - legacy launcher migrates settings without overriding Canopy options\n'

"${TMUX_TEST[@]}" split-window -h -t test:1
"${TMUX_TEST[@]}" split-window -v -t test:1.1

target="$("${TMUX_TEST[@]}" list-panes -t test:1 -F '#{pane_id} #{pane_left}' | sort -nk2 | tail -1 | awk '{ print $1 }')"
run_in_server "$target" "'$PROJECT_DIR/scripts/toggle' 'client-a' '$target' 42 global"
sleep 0.5

sidebar="$(sidebar_for_owner client-a)"
[[ -n "$sidebar" ]] || fail 'toggle creates a client-owned sidebar'
client_cache_key="$(printf '%s' client-a | cksum | awk '{ print $1 }')"
assert_eq "$sidebar" "$("${TMUX_TEST[@]}" show-option -gqv "@tmux_canopy_client_$client_cache_key")" 'toggle caches the client-owned sidebar ID'
assert_eq '0' "$("${TMUX_TEST[@]}" display-message -p -t "$sidebar" '#{pane_left}')" 'sidebar is anchored at the far left'
assert_eq '42' "$("${TMUX_TEST[@]}" display-message -p -t "$sidebar" '#{pane_width}')" 'sidebar uses the configured width'
assert_eq '44' "$("${TMUX_TEST[@]}" display-message -p -t "$sidebar" '#{pane_height}')" 'sidebar spans the full window height'
printf 'ok - opens full-height at the far left\n'

source_window="$("${TMUX_TEST[@]}" display-message -p -t "$target" '#{window_id}')"
"${TMUX_TEST[@]}" set-option -gq @tmux_canopy_notifications 'activity,bell'
run_in_server "$target" "'$PROJECT_DIR/scripts/notify' set '$source_window' '$target' activity"
sleep 0.3
assert_eq '1' "$("${TMUX_TEST[@]}" show-option -wqv -t "$source_window" @tmux_canopy_notice_activity)" 'activity provider records a window notification'
notice_file="$(mktemp)"
run_in_server "$sidebar" "TMUX_CANOPY_STATE=/dev/null TMUX_CANOPY_CLIENT='' '$PROJECT_DIR/scripts/tree-source' > '$notice_file'"
grep -F "W:$source_window" "$notice_file" | grep -Fq '!1' || fail 'tree renders the window activity badge'
grep -F "S:\$0" "$notice_file" | grep -Fq '!1' || fail 'tree aggregates activity at the session level'
rm -f "$notice_file"
run_in_server "$target" "'$PROJECT_DIR/scripts/notify' clear-window '$source_window'"
sleep 0.3
[[ -z "$("${TMUX_TEST[@]}" show-option -wqv -t "$source_window" @tmux_canopy_notice_activity)" ]] || fail 'focusing a window clears its notification state'
printf 'ok - records, aggregates, renders, and clears provider notifications\n'

"${TMUX_TEST[@]}" set-option -g @tmux-canopy-notification-target status
run_in_server "$target" "'$PROJECT_DIR/tmux-canopy.tmux'"
assert_eq 'none' "$("${TMUX_TEST[@]}" show-option -gqv @tmux_canopy_notifications)" 'status target disables sidebar notification rendering'
assert_eq 'reverse' "$("${TMUX_TEST[@]}" show-window-option -gv window-status-activity-style)" 'status target restores the original activity style'
assert_eq 'other' "$("${TMUX_TEST[@]}" show-option -gv bell-action)" 'status target enables configured tmux alert actions'
if "${TMUX_TEST[@]}" show-hooks -g alert-activity 2>/dev/null | grep -Fq 'alert-activity[9002]'; then
  fail 'status target removes sidebar alert hooks'
fi
"${TMUX_TEST[@]}" set-option -g @tmux-canopy-notification-target sidebar
run_in_server "$target" "'$PROJECT_DIR/tmux-canopy.tmux'"
assert_eq 'activity,bell' "$("${TMUX_TEST[@]}" show-option -gqv @tmux_canopy_notifications)" 'sidebar target enables sidebar notification rendering'
assert_eq 'default' "$("${TMUX_TEST[@]}" show-window-option -gv window-status-activity-style)" 'sidebar target suppresses status-bar alert styling'
assert_eq 'none' "$("${TMUX_TEST[@]}" show-option -gv bell-action)" 'sidebar target restores the original tmux alert action'
"${TMUX_TEST[@]}" show-hooks -g alert-activity | grep -Fq 'alert-activity[9002]' || fail 'sidebar target installs alert hooks'
printf 'ok - makes sidebar and status-bar notification presentation mutually selectable\n'

"${TMUX_TEST[@]}" set-option -g @tmux-canopy-resize-mode live
run_in_server "$target" "'$PROJECT_DIR/tmux-canopy.tmux'"
"${TMUX_TEST[@]}" show-hooks -g after-resize-pane | grep -Fq 'after-resize-pane[9001]' || fail 'live resize mode retains the resize hook'
"${TMUX_TEST[@]}" set-option -g @tmux-canopy-resize-mode staged
run_in_server "$target" "'$PROJECT_DIR/tmux-canopy.tmux'"
if "${TMUX_TEST[@]}" show-hooks -g after-resize-pane 2>/dev/null | grep -Fq 'after-resize-pane[9001]'; then
  fail 'staged resize mode removes the per-column resize hook'
fi
printf 'ok - makes staged resizing avoid per-column hook processes\n'

"${TMUX_TEST[@]}" show-hooks -g after-new-window | grep -Fq 'after-new-window[9001]' || fail 'global scope follows ordinary newly created windows'
"${TMUX_TEST[@]}" show-hooks -g after-new-window | grep -Fq "scripts/follow" || fail 'new-window hook delegates to client-aware follow logic'
printf 'ok - follows the owning client into newly created windows\n'

"${TMUX_TEST[@]}" new-window -d -t test -n destination
destination="$("${TMUX_TEST[@]}" display-message -p -t test:destination '#{pane_id}')"
source_window="$("${TMUX_TEST[@]}" display-message -p -t "$sidebar" '#{window_id}')"
"${TMUX_TEST[@]}" set-option -gq "@tmux_canopy_transition_$client_cache_key" 1
run_in_server "$destination" "'$PROJECT_DIR/scripts/follow' 'client-a' '$destination' 42"
sleep 0.2
assert_eq "$source_window" "$("${TMUX_TEST[@]}" display-message -p -t "$sidebar" '#{window_id}')" 'fallback hook is suppressed during an atomic transition'
"${TMUX_TEST[@]}" set-option -gu "@tmux_canopy_transition_$client_cache_key"

run_in_server "$destination" "'$PROJECT_DIR/scripts/follow' 'client-a' '$destination' 42"
sleep 0.3

assert_eq "$sidebar" "$(sidebar_for_owner client-a)" 'global follow preserves the sidebar pane identity'
assert_eq "$("${TMUX_TEST[@]}" display-message -p -t "$destination" '#{window_id}')" "$("${TMUX_TEST[@]}" display-message -p -t "$sidebar" '#{window_id}')" 'global follow moves into the selected window'
assert_eq '0' "$("${TMUX_TEST[@]}" display-message -p -t "$sidebar" '#{pane_left}')" 'follow keeps the sidebar at the far left'
printf 'ok - moves one existing pane between windows\n'

slot_target="$("${TMUX_TEST[@]}" new-window -d -t test: -n slot-target -P -F '#{pane_id}')"
run_in_server "$slot_target" "'$PROJECT_DIR/scripts/follow' 'client-a' '$slot_target' 42 slot"
sleep 0.3
slot_content_width="$("${TMUX_TEST[@]}" display-message -p -t "$slot_target" '#{pane_width}')"
slot_placeholder="$("${TMUX_TEST[@]}" list-panes -t test:destination -F $'#{pane_id}\t#{@tmux_canopy_slot}' | awk -F '\t' '$2 == "1" { print $1; exit }')"
[[ -n "$slot_placeholder" ]] || fail 'slot transition leaves a placeholder in the source window'
run_in_server "$slot_placeholder" "'$PROJECT_DIR/scripts/follow' 'client-a' '$slot_placeholder' 42 slot"
sleep 0.3
assert_eq "$("${TMUX_TEST[@]}" display-message -p -t "$destination" '#{window_id}')" "$("${TMUX_TEST[@]}" display-message -p -t "$sidebar" '#{window_id}')" 'follow resolves stale slot hook targets to content windows'
assert_eq "$slot_content_width" "$("${TMUX_TEST[@]}" display-message -p -t "$slot_target" '#{pane_width}')" 'slot transition preserves inactive content width'
slot_placeholder="$("${TMUX_TEST[@]}" list-panes -t test:slot-target -F $'#{pane_id}\t#{@tmux_canopy_slot}' | awk -F '\t' '$2 == "1" { print $1; exit }')"
[[ -n "$slot_placeholder" ]] || fail 'slot placeholder follows back into the inactive window'
printf 'ok - slot transitions preserve content geometry\n'

"${TMUX_TEST[@]}" resize-pane -t "$sidebar" -x 47
run_in_server "$sidebar" "'$PROJECT_DIR/scripts/sync-width' '$sidebar' 47"
sleep 0.4
assert_eq '47' "$("${TMUX_TEST[@]}" display-message -p -t "$slot_placeholder" '#{pane_width}')" 'debounced resize synchronizes inactive slots'
assert_eq '47' "$("${TMUX_TEST[@]}" show-option -gqv @tmux_canopy_runtime_width)" 'resized width becomes the configured runtime width'
printf 'ok - synchronizes resized slot widths\n'

state_file="$(mktemp)"

destination_window="$("${TMUX_TEST[@]}" display-message -p -t "$destination" '#{window_id}')"
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' rename-apply 'W:$destination_window' 'renamed destination'"
assert_eq 'renamed destination' "$("${TMUX_TEST[@]}" display-message -p -t "$destination_window" '#{window_name}')" 'rename action preserves names containing spaces'
printf 'ok - renames native tmux objects without temporary layout panes\n'

other_notice_pane="$("${TMUX_TEST[@]}" display-message -p -t test:slot-target '#{pane_id}')"
other_notice_window="$("${TMUX_TEST[@]}" display-message -p -t "$other_notice_pane" '#{window_id}')"
run_in_server "$destination" "'$PROJECT_DIR/scripts/notify' set '$destination_window' '$destination' activity"
run_in_server "$other_notice_pane" "'$PROJECT_DIR/scripts/notify' set '$other_notice_window' '$other_notice_pane' bell"
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' notification-clear 'W:$destination_window'"
[[ -z "$("${TMUX_TEST[@]}" show-option -wqv -t "$destination_window" @tmux_canopy_notice_activity)" ]] || fail 'u clears the selected target notification'
assert_eq '1' "$("${TMUX_TEST[@]}" show-option -wqv -t "$other_notice_window" @tmux_canopy_notice_bell)" 'target clear leaves other notifications unread'
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' notifications-clear-all 'W:$destination_window'"
[[ -z "$("${TMUX_TEST[@]}" show-option -wqv -t "$other_notice_window" @tmux_canopy_notice_bell)" ]] || fail 'U clears every sidebar notification'
printf 'ok - clears selected and global notification state\n'

content_panes_before="$("${TMUX_TEST[@]}" list-panes -t "$destination_window" -F '#{@tmux_canopy}' | awk '$0 != "1" { count++ } END { print count + 0 }')"
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_CANOPY_WIDTH=42 TMUX_CANOPY_SCOPE=global TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' split-horizontal 'P:$destination'"
sleep 0.3
content_panes_after="$("${TMUX_TEST[@]}" list-panes -t "$destination_window" -F '#{@tmux_canopy}' | awk '$0 != "1" { count++ } END { print count + 0 }')"
assert_eq "$((content_panes_before + 1))" "$content_panes_after" 'split action creates a content pane'

window_count_before="$("${TMUX_TEST[@]}" list-windows -t test -F '#{window_id}' | wc -l)"
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_CANOPY_WIDTH=42 TMUX_CANOPY_SCOPE=global TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' create-window 'W:$destination_window'"
sleep 0.3
window_count_after="$("${TMUX_TEST[@]}" list-windows -t test -F '#{window_id}' | wc -l)"
assert_eq "$((window_count_before + 1))" "$window_count_after" 'window action creates a window in the selected session'

session_count_before="$("${TMUX_TEST[@]}" list-sessions -F '#{session_id}' | wc -l)"
target_after_window="$("${TMUX_TEST[@]}" show-option -pqv -t "$sidebar" @tmux_canopy_target)"
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_CANOPY_WIDTH=42 TMUX_CANOPY_SCOPE=global TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' create-session 'P:$target_after_window'"
sleep 0.3
session_count_after="$("${TMUX_TEST[@]}" list-sessions -F '#{session_id}' | wc -l)"
assert_eq "$((session_count_before + 1))" "$session_count_after" 'session action creates a session'
tmux_session_name="$("${TMUX_TEST[@]}" display-message -p -t "$sidebar" '#{session_name}')"
assert_eq 'session-1' "$tmux_session_name" 'new sessions receive the next automatic name'
printf 'ok - creates pane splits, windows, and sessions\n'

# Native window ordering and linked-window occurrences.
order_a="$("${TMUX_TEST[@]}" new-window -d -t test: -n order-a -P -F '#{pane_id}')"
order_b="$("${TMUX_TEST[@]}" new-window -d -t test: -n order-b -P -F '#{pane_id}')"
order_b_window="$("${TMUX_TEST[@]}" display-message -p -t "$order_b" '#{window_id}')"
order_a_index="$("${TMUX_TEST[@]}" display-message -p -t "$order_a" '#{window_index}')"
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' window-up 'W:$order_b_window:\$0'"
assert_eq "$order_a_index" "$("${TMUX_TEST[@]}" display-message -p -t "$order_b" '#{window_index}')" 'window-up swaps native window order'
destination_session_id="$("${TMUX_TEST[@]}" display-message -p -t session-1 '#{session_id}')"
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' link-toggle 'W:$order_b_window:\$0'"
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' activate 'S:$destination_session_id'"
"${TMUX_TEST[@]}" list-windows -t "$destination_session_id" -F '#{window_id}' | grep -Fqx "$order_b_window" || fail 'link action adds the window to the destination session'
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' unlink 'W:$order_b_window:$destination_session_id'"
if "${TMUX_TEST[@]}" list-windows -t "$destination_session_id" -F '#{window_id}' | grep -Fqx "$order_b_window"; then fail 'unlink removes only the selected session occurrence'; fi
"${TMUX_TEST[@]}" list-windows -t test -F '#{window_id}' | grep -Fqx "$order_b_window" || fail 'unlink preserves the source occurrence'
printf 'ok - reorders, links, and unlinks native windows\n'

# Pane operations and window-level controls.
pane_ops="$("${TMUX_TEST[@]}" new-window -d -t test: -n pane-ops -P -F '#{pane_id}')"
pane_ops_second="$("${TMUX_TEST[@]}" split-window -d -h -t "$pane_ops" -P -F '#{pane_id}')"
pane_ops_window="$("${TMUX_TEST[@]}" display-message -p -t "$pane_ops" '#{window_id}')"
first_index="$("${TMUX_TEST[@]}" display-message -p -t "$pane_ops" '#{pane_index}')"
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' pane-up 'P:$pane_ops_second'"
assert_eq "$first_index" "$("${TMUX_TEST[@]}" display-message -p -t "$pane_ops_second" '#{pane_index}')" 'pane-up swaps panes natively'
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' zoom 'P:$pane_ops_second'"
assert_eq '1' "$("${TMUX_TEST[@]}" display-message -p -t "$pane_ops_second" '#{window_zoomed_flag}')" 'zoom action zooms the selected pane'
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' zoom 'P:$pane_ops_second'"
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' layout 'W:$pane_ops_window:\$0' even-horizontal"
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' sync-confirm 'W:$pane_ops_window:\$0'"
assert_eq 'on' "$("${TMUX_TEST[@]}" show-window-option -v -t "$pane_ops_window" synchronize-panes)" 'sync confirmation enables synchronized panes'
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' sync-toggle 'W:$pane_ops_window:\$0'"
assert_eq 'off' "$("${TMUX_TEST[@]}" show-window-option -v -t "$pane_ops_window" synchronize-panes)" 'sync toggle disables broadcasting without confirmation'
printf 'ok - zooms, swaps, lays out, and synchronizes panes\n'

# Dead-pane respawn is permitted without exposing forced live-pane respawn.
"${TMUX_TEST[@]}" set-window-option -t "$pane_ops_window" remain-on-exit on
dead_pane="$("${TMUX_TEST[@]}" split-window -d -t "$pane_ops" -P -F '#{pane_id}' 'exit 0')"
sleep 0.2
assert_eq '1' "$("${TMUX_TEST[@]}" display-message -p -t "$dead_pane" '#{pane_dead}')" 'test pane exits and remains visible'
dead_pid="$("${TMUX_TEST[@]}" display-message -p -t "$dead_pane" '#{pane_pid}')"
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' respawn 'P:$dead_pane'"
sleep 0.2
new_dead_pid="$("${TMUX_TEST[@]}" display-message -p -t "$dead_pane" '#{pane_pid}')"
[[ "$new_dead_pid" != "$dead_pid" ]] || fail 'respawn starts a new process for a dead pane'
printf 'ok - safely respawns dead panes\n'

# Process and buffer views are dispatched through the same fzf process.
view_file="$(mktemp)"
printf 'VIEW\tprocesses\n' > "$state_file"
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='' '$PROJECT_DIR/scripts/sidebar-source' > '$view_file'"
grep -Fq 'H:' "$view_file" || fail 'process view has a dynamic source header'
grep -Fq "Q:$pane_ops" "$view_file" || fail 'process view attributes processes to tmux panes'
"${TMUX_TEST[@]}" set-buffer -b tree-test-buffer 'buffer payload'
printf 'VIEW\tbuffers\n' > "$state_file"
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='' '$PROJECT_DIR/scripts/sidebar-source' > '$view_file'"
grep -Fq 'B2:747265652d746573742d627566666572' "$view_file" || fail 'buffer view lists native tmux buffers'
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/sidebar-action' delete 'B:tree-test-buffer'"
if "${TMUX_TEST[@]}" list-buffers -F '#{buffer_name}' | grep -Fqx tree-test-buffer; then fail 'buffer delete action removes the native buffer'; fi
printf 'VIEW\ttree\n' > "$state_file"
rm -f "$view_file"
printf 'ok - exposes process and buffer views in the persistent sidebar\n'

delete_window_pane="$("${TMUX_TEST[@]}" new-window -d -t test: -n delete-test -P -F '#{pane_id}')"
delete_window_id="$("${TMUX_TEST[@]}" display-message -p -t "$delete_window_pane" '#{window_id}')"
delete_second_pane="$("${TMUX_TEST[@]}" split-window -d -t "$delete_window_pane" -P -F '#{pane_id}')"
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_CANOPY_SCOPE=global TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' delete 'P:$delete_second_pane'"
grep -Fq $'DELETE\tP:'"$delete_second_pane" "$state_file" || fail 'first x arms deletion without deleting'
"${TMUX_TEST[@]}" display-message -p -t "$delete_second_pane" '#{pane_id}' >/dev/null || fail 'first x preserves the target'
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_CANOPY_SCOPE=global TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' delete 'P:$delete_second_pane'"
if "${TMUX_TEST[@]}" list-panes -a -F '#{pane_id}' | grep -Fqx "$delete_second_pane"; then fail 'second x deletes the armed pane'; fi
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_CANOPY_SCOPE=global TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' delete 'W:$delete_window_id'"
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_CANOPY_SCOPE=global TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' delete 'W:$delete_window_id'"
if "${TMUX_TEST[@]}" list-windows -a -F '#{window_id}' | grep -Fqx "$delete_window_id"; then fail 'confirmed window deletion removes the window'; fi
printf 'ok - confirms destructive pane and window actions\n'

move_source_pane="$("${TMUX_TEST[@]}" new-window -d -t test: -n move-pane-source -P -F '#{pane_id}')"
move_destination_pane="$("${TMUX_TEST[@]}" new-window -d -t session-1: -n move-pane-target -P -F '#{pane_id}')"
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_CANOPY_WIDTH=42 TMUX_CANOPY_SCOPE=global TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' move-toggle 'P:$move_source_pane'"
# Query through the private server so tree-source sees its TMUX environment.
marker_file="$(mktemp)"
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='' '$PROJECT_DIR/scripts/tree-source' > '$marker_file'"
grep -F "P:$move_source_pane" "$marker_file" | grep -Fq '⇢' || fail 'move source is visibly marked in the tree'
rm -f "$marker_file"
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_CANOPY_WIDTH=42 TMUX_CANOPY_SCOPE=global TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' complete-move 'P:$move_source_pane' 'P:$move_destination_pane' right"
sleep 0.3
assert_eq "$("${TMUX_TEST[@]}" display-message -p -t "$move_destination_pane" '#{window_id}')" "$("${TMUX_TEST[@]}" display-message -p -t "$move_source_pane" '#{window_id}')" 'pane move places the source in the destination window'
! grep -q $'^MOVE\t' "$state_file" || fail 'successful pane move clears move mode'

move_window_pane="$("${TMUX_TEST[@]}" new-window -d -t test: -n move-window-source -P -F '#{pane_id}')"
move_window_id="$("${TMUX_TEST[@]}" display-message -p -t "$move_window_pane" '#{window_id}')"
destination_session_id="$("${TMUX_TEST[@]}" display-message -p -t session-1 '#{session_id}')"
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_CANOPY_WIDTH=42 TMUX_CANOPY_SCOPE=global TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' move-toggle 'W:$move_window_id'"
run_in_server "$sidebar" "TMUX_CANOPY_STATE='$state_file' TMUX_CANOPY_CLIENT='client-a' TMUX_CANOPY_WIDTH=42 TMUX_CANOPY_SCOPE=global TMUX_PANE='$sidebar' '$PROJECT_DIR/scripts/tree-action' activate 'S:$destination_session_id'"
sleep 0.3
assert_eq "$destination_session_id" "$("${TMUX_TEST[@]}" display-message -p -t "$move_window_id" '#{session_id}')" 'window move places the source in the destination session'
! grep -q $'^MOVE\t' "$state_file" || fail 'successful window move clears move mode'
printf 'ok - marks and moves panes and windows through the stateful tree\n'

rm -f "$state_file"

run_in_server "$destination" "'$PROJECT_DIR/scripts/toggle' 'client-b' '$destination' 36 global"
sleep 0.5
sidebar_b="$(sidebar_for_owner client-b)"
[[ -n "$sidebar_b" && "$sidebar_b" != "$sidebar" ]] || fail 'different clients own different sidebar panes'

run_in_server "$destination" "'$PROJECT_DIR/scripts/toggle' 'client-a' '$destination' 42 global"
sleep 0.3
[[ -z "$(sidebar_for_owner client-a)" ]] || fail 'toggle closes only the invoking client sidebar'
assert_eq "$sidebar_b" "$(sidebar_for_owner client-b)" 'closing one client sidebar leaves another client sidebar intact'
printf 'ok - ownership and toggling are client-scoped\n'

# Simulate an unexpected sidebar death and verify hook-independent maintenance.
sidebar_b_cache_key="$(printf '%s' client-b | cksum | awk '{ print $1 }')"
"${TMUX_TEST[@]}" kill-pane -t "$sidebar_b"
sleep 0.2
run_in_server "$destination" "'$PROJECT_DIR/scripts/cleanup' scan"
[[ -z "$("${TMUX_TEST[@]}" show-option -gqv "@tmux_canopy_client_$sidebar_b_cache_key")" ]] || fail 'cleanup removes a stale sidebar cache'
slot_count="$("${TMUX_TEST[@]}" list-panes -a -F '#{@tmux_canopy_slot}' | awk '$0 == "1" { count++ } END { print count + 0 }')"
assert_eq '0' "$slot_count" 'cleanup removes slots when no sidebar remains'
printf 'ok - cleans orphan caches and stable slots\n'

"${TMUX_TEST[@]}" set-option -g @tmux-canopy-min-width 24
"${TMUX_TEST[@]}" set-option -g @tmux-canopy-max-width 48
"${TMUX_TEST[@]}" set-option -g @tmux-canopy-min-content-width 40
width_target="$("${TMUX_TEST[@]}" new-window -d -t test: -n width-test -P -F '#{pane_id}')"
run_in_server "$width_target" "'$PROJECT_DIR/scripts/toggle' 'width-client' '$width_target' '50%' window"
sleep 0.3
width_sidebar="$(sidebar_for_owner width-client)"
assert_eq '48' "$("${TMUX_TEST[@]}" display-message -p -t "$width_sidebar" '#{pane_width}')" 'percentage width is clamped to the configured maximum'
"${TMUX_TEST[@]}" set-option -g @tmux-canopy-width-presets '30,42,48'
run_in_server "$width_sidebar" "'$PROJECT_DIR/scripts/resize' previous '$width_sidebar'"
assert_eq '42' "$("${TMUX_TEST[@]}" display-message -p -t "$width_sidebar" '#{pane_width}')" 'previous preset commits one resize'
run_in_server "$width_sidebar" "'$PROJECT_DIR/scripts/resize' next '$width_sidebar'"
assert_eq '48' "$("${TMUX_TEST[@]}" display-message -p -t "$width_sidebar" '#{pane_width}')" 'next preset commits one resize'
width_window="$("${TMUX_TEST[@]}" display-message -p -t "$width_sidebar" '#{window_id}')"
run_in_server "$width_sidebar" "'$PROJECT_DIR/scripts/mouse-resize' start '$width_sidebar' '$width_window' 48 staged"
assert_eq "$width_sidebar" "$("${TMUX_TEST[@]}" show-option -pqv -t "$width_sidebar" @tmux_canopy_staged_sidebar)" 'sidebar border drag is marked for staged resizing'
run_in_server "$width_sidebar" "'$PROJECT_DIR/scripts/mouse-resize' end '$width_sidebar' '$width_window' 35 staged"
assert_eq '35' "$("${TMUX_TEST[@]}" display-message -p -t "$width_sidebar" '#{pane_width}')" 'staged mouse release commits only the final width'
[[ -z "$("${TMUX_TEST[@]}" show-option -pqv -t "$width_sidebar" @tmux_canopy_staged_sidebar)" ]] || fail 'staged drag marker clears after commit'
"${TMUX_TEST[@]}" set-option -g @tmux-canopy-width '25%'
"${TMUX_TEST[@]}" resize-window -t "$width_sidebar" -x 100 -y 44
run_in_server "$width_sidebar" "'$PROJECT_DIR/scripts/responsive-width'"
sleep 0.3
assert_eq '25' "$("${TMUX_TEST[@]}" display-message -p -t "$width_sidebar" '#{pane_width}')" 'percentage width responds to terminal resizing'
run_in_server "$width_target" "'$PROJECT_DIR/scripts/toggle' 'width-client' '$width_target' '50%' window"
sleep 0.2
narrow_target="$("${TMUX_TEST[@]}" new-window -d -t test: -n narrow-test -P -F '#{pane_id}')"
"${TMUX_TEST[@]}" resize-window -t "$narrow_target" -x 60 -y 44
run_in_server "$narrow_target" "'$PROJECT_DIR/scripts/toggle' 'narrow-client' '$narrow_target' 42 window"
sleep 0.2
[[ -z "$(sidebar_for_owner narrow-client)" ]] || fail 'minimum content guard refuses a terminal that is too narrow'
printf 'ok - clamps percentage widths and refuses undersized windows\n'

zoom_target="$("${TMUX_TEST[@]}" new-window -d -t test: -n zoom-test -P -F '#{pane_id}')"
"${TMUX_TEST[@]}" split-window -d -t "$zoom_target"
"${TMUX_TEST[@]}" resize-pane -Z -t "$zoom_target"
"${TMUX_TEST[@]}" set-option -g @tmux-canopy-zoom-action refuse
run_in_server "$zoom_target" "'$PROJECT_DIR/scripts/toggle' 'zoom-client' '$zoom_target' 42 window"
sleep 0.2
[[ -z "$(sidebar_for_owner zoom-client)" ]] || fail 'zoom guard refuses to alter a zoomed layout'
assert_eq '1' "$("${TMUX_TEST[@]}" display-message -p -t "$zoom_target" '#{window_zoomed_flag}')" 'refused open preserves zoom'
"${TMUX_TEST[@]}" set-option -g @tmux-canopy-zoom-action unzoom
run_in_server "$zoom_target" "'$PROJECT_DIR/scripts/toggle' 'zoom-client' '$zoom_target' 42 window"
sleep 0.3
[[ -n "$(sidebar_for_owner zoom-client)" ]] || fail 'unzoom mode opens the sidebar'
assert_eq '0' "$("${TMUX_TEST[@]}" display-message -p -t "$zoom_target" '#{window_zoomed_flag}')" 'unzoom mode temporarily clears zoom'
run_in_server "$zoom_target" "'$PROJECT_DIR/scripts/toggle' 'zoom-client' '$zoom_target' 42 window"
sleep 0.2
assert_eq '1' "$("${TMUX_TEST[@]}" display-message -p -t "$zoom_target" '#{window_zoomed_flag}')" 'closing restores the original zoomed pane'
printf 'ok - guards zoomed layouts and optionally restores zoom on close\n'

# Position is chosen on open and retained across both navigation modes.
position_target="$("${TMUX_TEST[@]}" new-window -d -t test: -n position-test -P -F '#{pane_id}')"
position_other="$("${TMUX_TEST[@]}" new-window -d -t test: -n position-other -P -F '#{pane_id}')"
"${TMUX_TEST[@]}" set-option -g @tmux-canopy-width 42
"${TMUX_TEST[@]}" set-option -g @tmux-canopy-position invalid
run_in_server "$position_target" "'$PROJECT_DIR/scripts/toggle' 'position-client' '$position_target' 42 global"
position_sidebar="$(sidebar_for_owner position-client)"
assert_eq '0' "$("${TMUX_TEST[@]}" display-message -p -t "$position_sidebar" '#{pane_left}')" 'invalid position falls back to left'
run_in_server "$position_target" "'$PROJECT_DIR/scripts/toggle' 'position-client' '$position_target' 42 global"
for transition in slot move; do
  "${TMUX_TEST[@]}" set-option -g @tmux-canopy-position right
  run_in_server "$position_target" "'$PROJECT_DIR/scripts/toggle' 'position-client' '$position_target' 42 global T Tab '$transition'"
  position_sidebar="$(sidebar_for_owner position-client)"
  "${TMUX_TEST[@]}" set-option -g @tmux-canopy-position left
  for destination in "$position_other" "$position_target"; do
    run_in_server "$destination" "'$PROJECT_DIR/scripts/follow' 'position-client' '$destination' 42 '$transition'"
    assert_eq "$("${TMUX_TEST[@]}" display-message -p -t "$destination" '#{window_width}')" \
      "$("${TMUX_TEST[@]}" display-message -p -t "$position_sidebar" '#{e|+:#{pane_left},#{pane_width}}')" 'open right sidebar retains its side after a configuration change'
    assert_eq 'right' "$("${TMUX_TEST[@]}" show-option -pqv -t "$position_sidebar" @tmux_canopy_position)" 'position is retained on the sidebar'
  done
  run_in_server "$position_target" "'$PROJECT_DIR/scripts/toggle' 'position-client' '$position_target' 42 global T Tab '$transition'"
done
run_in_server "$position_target" "'$PROJECT_DIR/scripts/toggle' 'position-client' '$position_target' 42 global"
position_sidebar="$(sidebar_for_owner position-client)"
assert_eq '0' "$("${TMUX_TEST[@]}" display-message -p -t "$position_sidebar" '#{pane_left}')" 'reopening applies the new left position'
run_in_server "$position_target" "'$PROJECT_DIR/scripts/toggle' 'position-client' '$position_target' 42 global"
printf 'ok - left default/fallback, right slot/move placement, and close/reopen position changes\n'

printf 'all integration tests passed\n'
