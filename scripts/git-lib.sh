#!/usr/bin/env bash
# Read-only Git context. Callers gate this on the opt-in setting and git being
# installed; results are returned in variables so a pane loop need not fork.
# shellcheck disable=SC2034 # Results are consumed by the sourcing scripts.
canopy_git_root() {
  local directory=$1
  CANOPY_GIT_ROOT=''
  [[ "$directory" == /* && -d "$directory" ]] || return 1
  while :; do
    if [[ -d "$directory/.git" || -f "$directory/.git" ]]; then
      CANOPY_GIT_ROOT=$directory
      return 0
    fi
    [[ "$directory" != / ]] || return 1
    directory=${directory%/*}
    [[ -n "$directory" ]] || directory=/
  done
}

canopy_git_branch() {
  local root=$1 branch
  CANOPY_GIT_BRANCH=''
  # An inherited GIT_DIR/GIT_WORK_TREE must not redirect the query to a
  # different repository than the pane's own working directory.
  branch="$(unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE; git -C "$root" symbolic-ref --quiet --short HEAD 2>/dev/null)" || {
    branch="$(unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE; git -C "$root" rev-parse --short HEAD 2>/dev/null)" || return 1
    branch="detached@$branch"
  }
  [[ -n "$branch" && "$branch" != *[$'\001'-$'\037'$'\177']* ]] || return 1
  CANOPY_GIT_BRANCH=$branch
}

canopy_git_dirty() {
  local root=$1 icons=${2:-unicode} budget=${3:-0} status_out diff_out line a d _path
  local count=0 added=0 deleted=0 sep=' · ' minus='−' short full
  CANOPY_GIT_DIRTY=''
  [[ "$icons" == ascii ]] && { sep=' | '; minus='-'; }
  status_out="$(unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE; git --no-optional-locks -C "$root" status --porcelain 2>/dev/null)" || return 1
  [[ -n "$status_out" ]] || return 1
  while IFS= read -r line; do
    [[ -n "$line" ]] && ((count++))
  done <<< "$status_out"
  ((count > 0)) || return 1
  diff_out="$(unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE; git --no-optional-locks -C "$root" diff --numstat HEAD 2>/dev/null)" ||
    diff_out="$(unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE; git --no-optional-locks -C "$root" diff --numstat 2>/dev/null; git --no-optional-locks -C "$root" diff --cached --numstat 2>/dev/null)" || diff_out=''
  while IFS=$'\t' read -r a d _path; do
    [[ "$a" =~ ^[0-9]+$ ]] && ((added += a))
    [[ "$d" =~ ^[0-9]+$ ]] && ((deleted += d))
  done <<< "$diff_out"
  short="${sep}${count} changed"
  if ((added > 0 || deleted > 0)); then
    full="${short} (+${added} ${minus}${deleted})"
  else
    full="$short"
  fi
  if ((budget <= 0 || ${#full} <= budget)); then
    CANOPY_GIT_DIRTY="$full"
  elif ((${#short} <= budget)); then
    CANOPY_GIT_DIRTY="$short"
  else
    return 1
  fi
}
