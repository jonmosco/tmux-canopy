#!/usr/bin/env bash
# Shared by the preflight parser and the real UI. Paths are expanded by a
# known POSIX shell from environment data, never embedded in fzf bind syntax.
# shellcheck disable=SC2016 # These variables expand in fzf's action shell.
sidebar_ui_options() {
  local pane="${1:-${TMUX_PANE:-}}" preview_mode preview_height selection_style pane_height preview_window fzf_colors theme selection_background
  local source_cmd='"$TMUX_CANOPY_ROOT/scripts/sidebar-source"'
  local action_cmd='"$TMUX_CANOPY_ROOT/scripts/sidebar-action"'
  local preview_cmd='"$TMUX_CANOPY_ROOT/scripts/sidebar-preview"'
  local help_cmd='"$TMUX_CANOPY_ROOT/scripts/help"'
  local filter_cmd='"$TMUX_CANOPY_ROOT/scripts/tree-filter"'
  local switcher_cmd='"$TMUX_CANOPY_ROOT/scripts/quick-switch"'
  local jump_cmd='"$TMUX_CANOPY_ROOT/scripts/jump-current"'
  local jump_agent_cmd='"$TMUX_CANOPY_ROOT/scripts/jump-agent"'
  local popup_cmd='"$TMUX_CANOPY_ROOT/scripts/preview-popup"'
  local animate_cmd='"$TMUX_CANOPY_ROOT/scripts/animate-frame"'
  local mode_cmd='"$TMUX_CANOPY_ROOT/scripts/preview-mode"'
  preview_mode="$(tmux show-option -gqv @tmux-canopy-preview 2>/dev/null || true)"
  preview_height="$(tmux show-option -gqv @tmux-canopy-preview-height 2>/dev/null || true)"
  selection_style="$(tmux show-option -gqv @tmux-canopy-selection-style 2>/dev/null || true)"
  : "${preview_mode:=off}"
  : "${preview_height:=35%}"
  : "${selection_style:=subtle}"
  pane_height="$(tmux display-message -p -t "$pane" '#{pane_height}' 2>/dev/null || printf '30')"
  preview_window="down,${preview_height},nowrap,border-top,+0"
  if [[ "$preview_mode" == off || ( "$preview_mode" == auto && "$pane_height" =~ ^[0-9]+$ && "$pane_height" -lt 28 ) ]]; then
    preview_window+=',hidden'
  fi
  selection_background="$(tmux show-option -gqv @tmux-canopy-selection-background 2>/dev/null || true)"
  if [[ "$selection_background" =~ ^([0-9]|[1-9][0-9]{1,2})$ ]] && ((selection_background <= 255)); then
    :
  elif [[ ! "$selection_background" =~ ^#[[:xdigit:]]{6}$ ]]; then
    selection_background=236
  fi
  # Preserve source foreground colors, including application icons and notices.
  fzf_colors='fg:-1,bg:-1,bg+:-1,gutter:-1,header:-1,info:-1,query:-1,disabled:-1,preview-fg:-1,preview-bg:-1,border:-1:dim,label:-1:dim,scrollbar:-1:dim,preview-scrollbar:-1:dim,spinner:6,prompt:6,pointer:6:bold,marker:6,hl:6:bold,hl+:6:bold'
  case "$selection_style" in
    solid) fzf_colors+=',bg+:6,fg+:0,hl+:0:bold' ;;
    reverse) fzf_colors+=',fg+:-1:reverse,hl+:6:bold:reverse' ;;
    pointer) fzf_colors+=',fg+:-1:regular' ;;
    *) fzf_colors+=",bg+:$selection_background,fg+:-1:regular" ;;
  esac
  theme="$(tmux show-option -gqv @tmux-canopy-theme 2>/dev/null || true)"
  [[ "$theme" != mono ]] || fzf_colors='bw'
  appearance="$(tmux show-option -gqv @tmux_canopy_appearance 2>/dev/null || true)"
  : "${appearance:=classic}"
  # Current-line arrow is drawn at the row edge. Leave the left pointer blank.
  pointer=' '; prompt='search › '; marker='●'; scrollbar='│'
  # shellcheck disable=SC2034 # Output array consumed by sidebar/preflight.
  SIDEBAR_FZF_ARGS=(
    --ansi --read0 --multi-line --no-wrap --no-hscroll --gap=0 --highlight-line
    --with-shell='/bin/sh -c'
    --color="$fzf_colors" --delimiter=$'\t' --with-nth=2 --nth=1..
    --no-sort --track --id-nth=3 --disabled --layout=reverse --border=none
    --gutter=' ' --scrollbar="$scrollbar"
    --no-input --info=hidden --no-separator --prompt="$prompt" --pointer="$pointer" --marker="$marker" --header-lines=1
    --preview="$preview_cmd {1}" --preview-window="$preview_window"
    --preview-label=' Preview ' --preview-label-pos=2
    --bind='j:down,k:up'
    --bind="ctrl-g:execute-silent($switcher_cmd)"
    --bind="ctrl-o:transform($jump_cmd)"
    --bind="F:execute-silent($filter_cmd)"
    --bind="ctrl-f:execute-silent($filter_cmd)"
    # Force header replacement after reload-sync (including error recovery).
    # Both actions run in one event, without an intermediate painted frame.
    --bind='load:+execute-silent([ -z "$TMUX_CANOPY_STATE" ] || touch "$TMUX_CANOPY_STATE.ready")+change-header-lines(0)+change-header-lines(1)'
    --bind='/:execute-silent([ -z "$TMUX_CANOPY_STATE" ] || touch "$TMUX_CANOPY_STATE.search")+show-input+enable-search+clear-query+unbind(F,g,h,H,A,i,j,k,l,L,m,c,r,x,u,U,w,a,p,P,1,2,3,4,[,],s,v,t,S,N,n,z,b,?)'
    --bind='esc:execute-silent(rm -f "$TMUX_CANOPY_STATE.search")+disable-search+clear-query+hide-input+search()+rebind(F,g,h,H,A,i,j,k,l,L,m,c,r,x,u,U,w,a,p,P,1,2,3,4,[,],s,v,t,S,N,n,z,b,?)'
    # Help owns a separate popup terminal; keep the current sidebar painted.
    --bind="?:execute-silent($help_cmd)"
    --bind="g:execute-silent($help_cmd --legend)"
    # View changes must work even when the current view has no selectable row.
    --bind="1:execute-silent(rm -f \"\$TMUX_CANOPY_STATE.search\"; $action_cmd view-tree)+reload-sync($source_cmd --stable)"
    --bind="2:execute-silent(rm -f \"\$TMUX_CANOPY_STATE.search\"; $action_cmd view-processes)+reload-sync($source_cmd --stable)"
    --bind="3:execute-silent(rm -f \"\$TMUX_CANOPY_STATE.search\"; $action_cmd view-buffers)+reload-sync($source_cmd --stable)"
    --bind="4:execute-silent(rm -f \"\$TMUX_CANOPY_STATE.search\"; $action_cmd view-agents)+reload-sync($source_cmd --stable)"
    --bind="A:execute-silent($action_cmd toggle-agents)+reload-sync($source_cmd --stable)"
    --bind="n:execute-silent($jump_agent_cmd)"
    --bind="i:execute-silent($mode_cmd)+refresh-preview+show-preview"
    --bind="a:execute-silent($action_cmd actions {1})"
    --bind='p:toggle-preview'
    --bind="P:execute-silent($popup_cmd {1})"
    --bind="enter:execute-silent(rm -f \"\$TMUX_CANOPY_STATE.search\"; $action_cmd activate {1} {3})"
    --bind="double-click:execute-silent(rm -f \"\$TMUX_CANOPY_STATE.search\"; $action_cmd activate {1} {3})"
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
    --bind="N:execute-silent($action_cmd create-session-prompt {1})+reload-sync($source_cmd --stable)"
    --bind="z:execute-silent($action_cmd zoom {1})+reload-sync($source_cmd --stable)"
    --bind="b:execute-silent($action_cmd break-window {1})+reload-sync($source_cmd --stable)"
    --bind="ctrl-r:clear-screen+reload-sync($source_cmd --stable)"
    --bind='ctrl-l:clear-screen'
    --bind="ctrl-t:reload-sync($animate_cmd)"
    --bind='ctrl-q:abort'
  )
}
