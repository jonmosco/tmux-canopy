#!/usr/bin/env bash
# Shared by the preflight parser and the real UI. Paths are expanded by a
# known POSIX shell from environment data, never embedded in fzf bind syntax.
# shellcheck disable=SC2016 # These variables expand in fzf's action shell.
sidebar_ui_options() {
  local pane="${1:-${TMUX_PANE:-}}" preview_mode preview_height selection_style pane_height preview_window fzf_colors theme selection_background
  local inspector_mode agents_enabled agents_format preview_label=' Terminal preview '
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
  # fzf pauses its screen when a command keeps it waiting over a second, and
  # resuming leaves mouse tracking off and the tty echoing what Canopy sends
  # the sidebar (^T, ^R). Popups, menus and prompts wait on the user, so they
  # run detached; a prompt that changes the tree refreshes it when it closes.
  local detach='</dev/null >/dev/null 2>&1 &'
  local refresh='tmux send-keys -t "$TMUX_PANE" C-r'
  local pane_flag=()
  [[ -n "$pane" ]] && pane_flag=(-t "$pane")
  agents_format="$(canopy_agents_format "${TMUX_CANOPY_CLIENT:-}")"
  IFS='|' read -r preview_mode preview_height selection_style pane_height selection_background theme appearance inspector_mode agents_enabled < <(
    tmux display-message -p "${pane_flag[@]}" \
      "#{@tmux-canopy-preview}|#{@tmux-canopy-preview-height}|#{@tmux-canopy-selection-style}|#{pane_height}|#{@tmux-canopy-selection-background}|#{@tmux-canopy-theme}|#{@tmux_canopy_appearance}|#{@tmux_canopy_preview_mode}|$agents_format" 2>/dev/null || true
  )
  if [[ "$agents_enabled" == on ]] && canopy_preview_is_inspector "$inspector_mode"; then
    preview_label=' Agent inspector '
  fi
  : "${preview_mode:=off}"
  : "${preview_height:=25%}"
  : "${selection_style:=subtle}"
  [[ "$pane_height" =~ ^[1-9][0-9]*$ ]] || pane_height=30
  preview_window="down,${preview_height},nowrap,noinfo,border-sharp,+0"
  if [[ "${TMUX_CANOPY_POPUP:-0}" == 1 ]]; then
    popup_cols=80
    read -r _rows popup_cols < <(stty size </dev/tty 2>/dev/null || echo "24 80")
    if [[ "$popup_cols" =~ ^[1-9][0-9]*$ ]] && ((popup_cols >= 100)); then
      preview_window="right,45%,nowrap,noinfo,border-sharp,+0"
    fi
  fi
  if [[ "$preview_mode" == off || ( "$preview_mode" == auto && "$pane_height" =~ ^[0-9]+$ && "$pane_height" -lt 28 ) ]]; then
    preview_window+=',hidden'
  fi
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
    *)
      fzf_colors+=",bg+:$selection_background,fg+:-1:regular"
      ;;
  esac
  [[ "$theme" != mono ]] || fzf_colors='bw'
  : "${appearance:=classic}"
  # Current-line arrow is drawn at the row edge. Leave the left pointer blank.
  pointer=' '; prompt='search › '; marker='●'; scrollbar='│'
  local activate_suffix='' jump_agent_bind="n:execute-silent($jump_agent_cmd)"
  local search_unbind='F,f,g,h,H,A,i,j,k,l,L,m,c,r,x,u,U,w,a,p,P,1,2,3,4,[,],s,v,t,S,N,n,z,b,>,?'
  # The footer sidebar-source stored for this load, or a search hint while
  # searching, so a refresh during a search keeps the hint.
  local footer_read='[ -n "$TMUX_CANOPY_STATE" ] || exit 0; f=; if [ -e "$TMUX_CANOPY_STATE.search" ]; then f="Esc clear   Enter focus"; elif [ -r "$TMUX_CANOPY_STATE.footer" ]; then IFS= read -r f < "$TMUX_CANOPY_STATE.footer"; fi'
  local footer_cmd="$footer_read"'; printf "change-footer:%s" "$f"'
  # Footer text is generated actions; the header may contain a user path, so
  # emit it last with fzf's literal, rest-of-action delimiter.
  local load_cmd="$footer_read"'; h=; [ ! -r "$TMUX_CANOPY_STATE.header" ] || IFS= read -r h < "$TMUX_CANOPY_STATE.header"; printf "change-footer(%s)+change-header:%s" "$f" "$h"'
  local esc_cmd='execute-silent(rm -f "$TMUX_CANOPY_STATE.search")+disable-search+clear-query+hide-input+search()+rebind('"$search_unbind"')'"+transform($footer_cmd)"
  if [[ "${TMUX_CANOPY_POPUP:-0}" == 1 ]]; then
    activate_suffix='+accept'
    jump_agent_bind="n:execute-silent($jump_agent_cmd)+accept"
    search_unbind+=',q'
    esc_cmd="transform($action_cmd esc-action)"
  fi
  # shellcheck disable=SC2034 # Output array consumed by sidebar/preflight.
  SIDEBAR_FZF_ARGS=(
    --ansi --read0 --multi-line --no-wrap --no-hscroll --gap=0 --highlight-line
    --with-shell='/bin/sh -c'
    --color="$fzf_colors" --delimiter=$'\t' --with-nth=2 --nth=1..
    --no-sort --track --id-nth=3 --disabled --layout=reverse --border=none
    --gutter=' ' --scrollbar="$scrollbar"
    --footer-border=line --no-input --info=hidden --no-separator --prompt="$prompt" --pointer="$pointer" --marker="$marker" --header=' '
    --preview="$preview_cmd {1}" --preview-window="$preview_window"
    --preview-label="$preview_label" --preview-label-pos=2
    --bind='j:down,k:up'
    # The mouse wheel scrolls the view and leaves the selection where it is;
    # by default each wheel event would move the selection one row. A
    # one-line scroll-off keeps the wheel from dragging the selection until it
    # reaches the edge, while j/k still show a row of context there. When the
    # list cannot scroll, fzf moves the selection instead.
    --bind='scroll-up:offset-up,scroll-down:offset-down' --scroll-off=1
    --bind="ctrl-g:execute-silent($switcher_cmd $detach)"
    --bind="ctrl-o:bg-transform($jump_cmd)"
    --bind="F:execute-silent($filter_cmd $detach)"
    --bind="ctrl-f:execute-silent($filter_cmd $detach)"
    # Explicit header text avoids reload-sync's stale input-header state and
    # the full-list redraws caused by toggling the input-header line count.
    --bind="load:+transform{[ -n \"\$TMUX_CANOPY_STATE\" ] && touch \"\$TMUX_CANOPY_STATE.ready\"; $load_cmd}"
    --bind="/:execute-silent([ -z \"\$TMUX_CANOPY_STATE\" ] || touch \"\$TMUX_CANOPY_STATE.search\")+show-input+enable-search+clear-query+unbind($search_unbind)+transform($footer_cmd)"
    --bind="esc:$esc_cmd"
    # Help owns a separate popup terminal; keep the current sidebar painted.
    --bind="?:execute-silent($help_cmd --context {1} $detach)"
    --bind="g:execute-silent($help_cmd --legend $detach)"
    # View changes must work even when the current view has no selectable row.
    --bind="1:execute-silent(rm -f \"\$TMUX_CANOPY_STATE.search\"; $action_cmd view-tree)+reload-sync($source_cmd --stable)"
    --bind="2:execute-silent(rm -f \"\$TMUX_CANOPY_STATE.search\"; $action_cmd view-processes)+reload-sync($source_cmd --stable)"
    --bind="3:execute-silent(rm -f \"\$TMUX_CANOPY_STATE.search\"; $action_cmd view-buffers)+reload-sync($source_cmd --stable)"
    --bind="4:execute-silent(rm -f \"\$TMUX_CANOPY_STATE.search\"; $action_cmd view-agents)+reload-sync($source_cmd --stable)"
    --bind="A:execute-silent($action_cmd toggle-agents)+transform($mode_cmd --label)+reload-sync($source_cmd --stable)+refresh-preview"
    --bind="f:execute-silent($action_cmd toggle-footer)+reload-sync($source_cmd --stable)"
    --bind="$jump_agent_bind"
    --bind="i:transform($mode_cmd --fzf)"
    --bind="a:execute-silent($action_cmd actions {1} $detach)"
    --bind='p:toggle-preview'
    --bind="P:execute-silent($popup_cmd {1} $detach)"
    --bind="enter:execute-silent(rm -f \"\$TMUX_CANOPY_STATE.search\"; $action_cmd activate {1} {3})$activate_suffix"
    --bind="double-click:execute-silent(rm -f \"\$TMUX_CANOPY_STATE.search\"; $action_cmd activate {1} {3})$activate_suffix"
    --bind="m:execute-silent($action_cmd move-toggle {1})+reload-sync($source_cmd --stable)"
    --bind="c:execute-silent($action_cmd move-cancel {1})+reload-sync($source_cmd --stable)"
    --bind="r:execute-silent(($action_cmd rename {1}; $refresh) $detach)"
    --bind=">:execute-silent($action_cmd send {1} $detach)"
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
    --bind="N:execute-silent(($action_cmd create-session-prompt {1}; $refresh) $detach)"
    --bind="z:execute-silent($action_cmd zoom {1})+reload-sync($source_cmd --stable)"
    --bind="b:execute-silent($action_cmd break-window {1})+reload-sync($source_cmd --stable)"
    --bind="ctrl-r:reload-sync($source_cmd --stable)+refresh-preview"
    --bind='ctrl-j:down,ctrl-k:up'
    --bind="ctrl-t:reload-sync($animate_cmd)"
    --bind='ctrl-q:abort'
  )
  if [[ "${TMUX_CANOPY_POPUP:-0}" == 1 ]]; then
    SIDEBAR_FZF_ARGS+=(
      --bind='q:abort'
      --bind="load:transform{[ -n \"\$TMUX_CANOPY_STATE\" ] && touch \"\$TMUX_CANOPY_STATE.ready\"; $load_cmd}"
      --bind="result-final:transform($action_cmd popup-focus)+unbind(result-final)"
    )
  else
    # vim-tmux-navigator forwards these keys to fzf instead of moving panes.
    # Ctrl-h is also Backspace in many terminals; search keeps text editing.
    SIDEBAR_FZF_ARGS+=(
      --bind="ctrl-h:transform(if [ -e \"\$TMUX_CANOPY_STATE.search\" ]; then printf backward-delete-char; else printf '%s' 'execute-silent(tmux select-pane -t \"\$TMUX_PANE\" -L)'; fi)"
      --bind='ctrl-l:execute-silent(tmux select-pane -t "$TMUX_PANE" -R)'
    )
  fi
}
