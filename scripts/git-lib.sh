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
