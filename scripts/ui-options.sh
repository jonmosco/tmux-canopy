#!/usr/bin/env bash
# Shared by the preflight parser and the real UI. Paths are expanded by a
# known POSIX shell from environment data, never embedded in fzf bind syntax.
# shellcheck disable=SC2016 # These variables expand in fzf's action shell.
sidebar_ui_options() {
  local pane="${1:-${TMUX_PANE:-}}" preview_mode preview_height selection_style pane_height preview_window fzf_colors
  local source_cmd='"$TMUX_CANOPY_ROOT/scripts/sidebar-source"'
  local action_cmd='"$TMUX_CANOPY_ROOT/scripts/sidebar-action"'
  local preview_cmd='"$TMUX_CANOPY_ROOT/scripts/sidebar-preview"'
  local help_cmd='"$TMUX_CANOPY_ROOT/scripts/help"'
  local popup_cmd='"$TMUX_CANOPY_ROOT/scripts/preview-popup"'
  preview_mode="$(tmux show-option -gqv @tmux-canopy-preview 2>/dev/null || true)"
  preview_height="$(tmux show-option -gqv @tmux-canopy-preview-height 2>/dev/null || true)"
  selection_style="$(tmux show-option -gqv @tmux-canopy-selection-style 2>/dev/null || true)"
  : "${preview_mode:=auto}"
  : "${preview_height:=35%}"
  : "${selection_style:=subtle}"
  pane_height="$(tmux display-message -p -t "$pane" '#{pane_height}' 2>/dev/null || printf '30')"
  preview_window="down,${preview_height},nowrap,border-top,+0"
  if [[ "$preview_mode" == off || ( "$preview_mode" == auto && "$pane_height" =~ ^[0-9]+$ && "$pane_height" -lt 28 ) ]]; then
    preview_window+=',hidden'
  fi
  case "$selection_style" in
    solid) fzf_colors='bg+:24,fg+:15,pointer:14,marker:10,hl:11,hl+:11' ;;
    reverse) fzf_colors='bg+:7,fg+:0,pointer:6,marker:2,hl:3,hl+:3' ;;
    pointer) fzf_colors='bg+:-1,fg+:-1,pointer:6,marker:2,hl:3,hl+:3' ;;
    *) fzf_colors='bg+:236,fg+:15,pointer:14,marker:10,hl:11,hl+:11' ;;
  esac
  # shellcheck disable=SC2034 # Output array consumed by sidebar/preflight.
  SIDEBAR_FZF_ARGS=(
    --ansi --read0 --multi-line --no-wrap --no-hscroll --gap=0 --highlight-line
    --with-shell='/bin/sh -c'
    --color="$fzf_colors" --delimiter=$'\t' --with-nth=2 --nth=1..
    --no-sort --track --id-nth=3 --disabled --layout=reverse --border=none
    --info=inline-right --prompt='tmux › ' --pointer='›' --marker='●' --header-lines=1
    --preview="$preview_cmd {1}" --preview-window="$preview_window"
    --preview-label=' Preview ' --preview-label-pos=2
    --bind='j:down,k:up'
    # Force header replacement after reload-sync (including error recovery).
    # Both actions run in one event, without an intermediate painted frame.
    --bind='load:+change-header-lines(0)+change-header-lines(1)'
    --bind='/:enable-search+clear-query+change-prompt(search › )+unbind(h,H,j,k,l,L,m,c,r,x,u,U,w,a,p,P,1,2,3,[,],s,v,t,S,?)'
    --bind='esc:disable-search+clear-query+change-prompt(tmux › )+rebind(h,H,j,k,l,L,m,c,r,x,u,U,w,a,p,P,1,2,3,[,],s,v,t,S,?)'
    # Help owns a separate popup terminal; keep the current sidebar painted.
    --bind="?:execute-silent($help_cmd)"
    # View changes must work even when the current view has no selectable row.
    --bind="1:execute-silent($action_cmd view-tree)+reload-sync($source_cmd --stable)"
    --bind="2:execute-silent($action_cmd view-processes)+reload-sync($source_cmd --stable)"
    --bind="3:execute-silent($action_cmd view-buffers)+reload-sync($source_cmd --stable)"
    --bind="a:execute-silent($action_cmd actions {1})"
    --bind='p:toggle-preview'
    --bind="P:execute-silent($popup_cmd {1})"
    --bind="enter:execute-silent($action_cmd activate {1} {3})"
    --bind="double-click:execute-silent($action_cmd activate {1} {3})"
    --bind="m:execute-silent($action_cmd move-toggle {1})+reload-sync($source_cmd --stable)"
    --bind="c:execute-silent($action_cmd move-cancel {1})+reload-sync($source_cmd --stable)"
    --bind="r:execute-silent($action_cmd rename {1})+reload-sync($source_cmd --stable)"
    --bind="x:execute-silent($action_cmd delete {1})+reload-sync($source_cmd --stable)"
    --bind="u:execute-silent($action_cmd notification-clear {1})+reload-sync($source_cmd --stable)"
    --bind="U:execute-silent($action_cmd notifications-clear-all {1})+reload-sync($source_cmd --stable)"
    --bind="[:execute-silent($action_cmd resize-previous {1})"
    --bind="]:execute-silent($action_cmd resize-next {1})"
    --bind="w:execute-silent($action_cmd resize-cycle {1})"
    --bind="h:execute-silent($action_cmd collapse {1} {3})+reload-sync($source_cmd --stable)"
    --bind="left:execute-silent($action_cmd collapse {1} {3})+reload-sync($source_cmd --stable)"
    --bind="l:execute-silent($action_cmd expand {1})+reload-sync($source_cmd --stable)"
    --bind="right:execute-silent($action_cmd expand {1})+reload-sync($source_cmd --stable)"
    --bind="H:execute-silent($action_cmd collapse-all)+reload-sync($source_cmd --stable)"
    --bind="L:execute-silent($action_cmd expand-all)+reload-sync($source_cmd --stable)"
    --bind="s:execute-silent($action_cmd split-horizontal {1})+reload-sync($source_cmd --stable)"
    --bind="v:execute-silent($action_cmd split-vertical {1})+reload-sync($source_cmd --stable)"
    --bind="t:execute-silent($action_cmd create-window {1})+reload-sync($source_cmd --stable)"
    --bind="S:execute-silent($action_cmd create-session {1})+reload-sync($source_cmd --stable)"
    --bind="ctrl-r:reload-sync($source_cmd --stable)"
    --bind='ctrl-q:abort'
  )
}
