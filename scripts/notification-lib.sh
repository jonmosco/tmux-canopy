#!/usr/bin/env bash
# Return a native tmux command. Empty/read windows never start a shell, and
# overlapping selection hooks share one window-scoped, expiring clear claim.
notification_clear_command() {
  local script="$1" client="$2" window="$3" notices eligible expired deadline job body target_args=''
  notices='#{||:#{==:#{@tmux_canopy_notice_activity},1},#{||:#{==:#{@tmux_canopy_notice_bell},1},#{==:#{@tmux_canopy_notice_silence},1}}}'
  expired='#{||:#{!:#{@tmux_canopy_notice_clear_pending}},#{<=:#{@tmux_canopy_notice_clear_pending},#{T:#{l:%s}}}}'
  eligible="#{&&:#{!=:#{@tmux_canopy_notifications},none},#{&&:$notices,#{&&:#{!=:#{@tmux_canopy_notice_suppress},1},$expired}}}"
  deadline='#{e|+:#{T:#{l:%s}},2}'
  job="run-shell -b $(tmux_quote "$(tmux_shell "$script") $(shell_join clear-client "$client" "$window" '#{@tmux_canopy_notice_clear_pending}')")"
  # -t is not a format argument. Hook registrations already inherit the
  # selected window's native target context; only concrete IDs may use -t.
  [[ "$window" == '#{window_id}' ]] || target_args="-t $(tmux_quote "$window")"
  body="set-option -wF $target_args @tmux_canopy_notice_clear_pending $(tmux_quote "$deadline") ; $job"
  printf 'if-shell -F %s %s %s' "$target_args" "$(tmux_quote "$eligible")" "$(tmux_quote "$body")"
}
