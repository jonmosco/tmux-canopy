#!/usr/bin/env bash
# shellcheck disable=SC1091
source "${BASH_SOURCE[0]%/*}/launch-lib.sh"

sidebar_client_key() {
  printf '%s' "${1:-}" | cksum | awk '{ print $1 }'
}

sidebar_cache_option() {
  printf '@tmux_canopy_client_%s\n' "$(sidebar_client_key "${1:-}")"
}

sidebar_transition_option() {
  printf '@tmux_canopy_transition_%s\n' "$(sidebar_client_key "${1:-}")"
}

begin_sidebar_transition() {
  tmux set-option -gq "$(sidebar_transition_option "${1:-}")" 1
}

end_sidebar_transition() {
  tmux set-option -gu "$(sidebar_transition_option "${1:-}")" 2>/dev/null || true
}

sidebar_transition_active() {
  [[ "$(tmux show-option -gqv "$(sidebar_transition_option "${1:-}")" 2>/dev/null || true)" == '1' ]]
}

client_pane() {
  local client="${1:-}"
  [[ -n "$client" ]] || return 1
  tmux list-clients -F '#{client_tty}|#{pane_id}' 2>/dev/null |
    awk -F '|' -v client="$client" '$1 == client { print $2; exit }'
}

sidebar_rows() {
  tmux list-panes -a \
    -F $'#{pane_id}\t#{@tmux_canopy}\t#{@tmux_canopy_client}' \
    2>/dev/null
}

sidebar_for_client() {
  local client="${1:-}" cache_option cached pane
  cache_option="$(sidebar_cache_option "$client")"
  cached="$(tmux show-option -gqv "$cache_option" 2>/dev/null || true)"

  if [[ -n "$cached" ]] \
    && [[ "$(tmux show-option -pqv -t "$cached" @tmux_canopy 2>/dev/null || true)" == '1' ]] \
    && [[ "$(tmux show-option -pqv -t "$cached" @tmux_canopy_client 2>/dev/null || true)" == "$client" ]]; then
    printf '%s\n' "$cached"
    return 0
  fi

  pane="$(sidebar_rows |
    awk -F '\t' -v client="$client" '
      $2 == "1" && $3 == client { print $1; exit }
    ')"
  if [[ -n "$pane" ]]; then
    tmux set-option -gq "$cache_option" "$pane"
    printf '%s\n' "$pane"
  else
    tmux set-option -gu "$cache_option" 2>/dev/null || true
  fi
}

cache_sidebar_for_client() {
  tmux set-option -gq "$(sidebar_cache_option "${1:-}")" "${2:-}"
}

clear_sidebar_cache() {
  tmux set-option -gu "$(sidebar_cache_option "${1:-}")" 2>/dev/null || true
}

unowned_sidebar() {
  sidebar_rows |
    awk -F '\t' '$2 == "1" && $3 == "" { print $1; exit }'
}

pane_exists() {
  local pane_id="${1:-}"
  [[ -n "$pane_id" ]] || return 1
  tmux list-panes -a -F '#{pane_id}' 2>/dev/null | grep -Fqx -- "$pane_id"
}

is_sidebar_pane() {
  local pane_id="${1:-}"
  [[ -n "$pane_id" ]] || return 1
  [[ "$(tmux show-option -pqv -t "$pane_id" @tmux_canopy 2>/dev/null || true)" == '1' ]]
}

slot_for_window() {
  local window_id="${1:-}"
  [[ -n "$window_id" ]] || return 1
  tmux list-panes -t "$window_id" -F $'#{pane_id}\t#{@tmux_canopy_slot}' 2>/dev/null |
    awk -F '\t' '$2 == "1" { print $1; exit }'
}

ensure_slot_for_window() {
  local window_id="${1:-}" target_pane="${2:-}" width="${3:-42}"
  local slot_pane slot_width row position="${5:-left}"
  local -a placement=(-b)
  [[ "$position" != right ]] || placement=()
  # A caller holding the navigation lock may supply an already-read slot
  # record (including an empty record) to avoid querying the window twice.
  if (($# >= 4)); then
    row="$4"
  else
    row="$(tmux list-panes -t "$window_id" -f '#{==:#{@tmux_canopy_slot},1}' -F '#{pane_id}|#{pane_width}' 2>/dev/null)"
  fi
  IFS='|' read -r slot_pane slot_width <<< "$row"
  if [[ -n "$slot_pane" ]]; then
    if [[ "$width" =~ ^[1-9][0-9]*$ && "$slot_width" != "$width" ]]; then
      tmux resize-pane -t "$slot_pane" -x "$width" 2>/dev/null || true
    fi
    printf '%s\n' "$slot_pane"
    return 0
  fi
  [[ -n "$target_pane" ]] || return 1

  # Native empty panes need no placeholder process or shell startup. In
  # particular, macOS sleep rejects the GNU-style infinity argument.
  slot_pane="$(tmux split-window -d -h "${placement[@]}" -f -l "$width" -t "$target_pane" -P -F '#{pane_id}' '')"
  [[ -n "$slot_pane" ]] || return 1
  tmux set-option -p -t "$slot_pane" @tmux_canopy_slot 1 \; \
    set-option -p -t "$slot_pane" @tmux_canopy_position "$position" \; \
    set-option -p -t "$slot_pane" allow-set-title off \; \
    select-pane -t "$slot_pane" -T 'tmux-canopy-slot' 2>/dev/null || return 1
  printf '%s\n' "$slot_pane"
}

cleanup_sidebar_slots() {
  local slot_pane
  while IFS= read -r slot_pane; do
    [[ -n "$slot_pane" ]] && tmux kill-pane -t "$slot_pane" 2>/dev/null || true
  done < <(tmux list-panes -a -F $'#{pane_id}\t#{@tmux_canopy_slot}' 2>/dev/null |
    awk -F '\t' '$2 == "1" { print $1 }')
}

sync_sidebar_slots() {
  local requested="${1:-}" minimum="${2:-24}" maximum="${3:-0}" min_content="${4:-40}" slot_pane current total width
  [[ "$requested" =~ ^[1-9][0-9]*%?$ ]] || return 1
  while IFS='|' read -r slot_pane current total; do
    [[ -n "$slot_pane" ]] || continue
    width="$(clamp_sidebar_width_for_total "$total" "$requested" "$minimum" "$maximum" "$min_content")" || continue
    [[ "$current" == "$width" ]] && continue
    tmux resize-pane -t "$slot_pane" -x "$width" 2>/dev/null || true
  done < <(tmux list-panes -a -f '#{==:#{@tmux_canopy_slot},1}' \
    -F '#{pane_id}|#{pane_width}|#{window_width}' 2>/dev/null)
}

cleanup_slots_if_no_sidebars() {
  local excluding="${1:-}" remaining
  remaining="$(tmux list-panes -a -F $'#{pane_id}\t#{@tmux_canopy}' 2>/dev/null |
    awk -F '\t' -v excluding="$excluding" '$2 == "1" && $1 != excluding { count++ } END { print count + 0 }')"
  ((remaining == 0)) && cleanup_sidebar_slots
}

# Dead regular panes (remain-on-exit) still count as content. Only our internal
# dock/slot panes may be removed to finish a window's normal lifetime.
sidebar_empty_window_condition() {
  printf '%s' '#{&&:#{window_panes},#{==:#{P:#{?#{||:#{==:#{@tmux_canopy},1},#{==:#{@tmux_canopy_slot},1}},,1}},}}'
}

content_pane_for_window() {
  local window_id="${1:-}"
  [[ -n "$window_id" ]] || return 1
  tmux list-panes -t "$window_id" -F $'#{pane_id}\t#{@tmux_canopy}\t#{@tmux_canopy_slot}\t#{pane_active}\t#{pane_last}' 2>/dev/null |
    awk -F '\t' '
      $2 != "1" && $3 != "1" && $4 == "1" { print $1; found = 1; exit }
      $2 != "1" && $3 != "1" && $5 == "1" { last = $1 }
      $2 != "1" && $3 != "1" && first == "" { first = $1 }
      END { if (!found && first != "") print (last != "" ? last : first) }
    '
}

pane_window() {
  local pane_id="${1:-}"
  [[ -n "$pane_id" ]] || return 1
  tmux display-message -p -t "$pane_id" '#{window_id}' 2>/dev/null
}

clamp_sidebar_width() {
  local target_pane="${1:-}" requested="${2:-42}" minimum="${3:-24}" maximum="${4:-0}" min_content="${5:-40}"
  local total
  [[ -n "$target_pane" ]] || return 1
  total="$(tmux display-message -p -t "$target_pane" '#{window_width}' 2>/dev/null || true)"
  clamp_sidebar_width_for_total "$total" "$requested" "$minimum" "$maximum" "$min_content"
}

clamp_sidebar_width_for_total() {
  local total="${1:-}" requested="${2:-42}" minimum="${3:-24}" maximum="${4:-0}" min_content="${5:-40}"
  # A zero maximum leaves only the minimum-content constraint.
  local desired available
  [[ "$total" =~ ^[1-9][0-9]*$ ]] || return 1
  [[ "$minimum" =~ ^[1-9][0-9]*$ ]] || minimum=24
  [[ "$maximum" =~ ^(0|[1-9][0-9]*)$ ]] || maximum=0
  [[ "$min_content" =~ ^[1-9][0-9]*$ ]] || min_content=40
  ((maximum > 0 && maximum < minimum)) && maximum="$minimum"

  if [[ "$requested" =~ ^([1-9][0-9]?)%$ ]]; then
    desired=$((total * BASH_REMATCH[1] / 100))
  elif [[ "$requested" =~ ^[1-9][0-9]*$ ]]; then
    desired="$requested"
  else
    desired=42
  fi

  ((desired < minimum)) && desired="$minimum"
  ((maximum > 0 && desired > maximum)) && desired="$maximum"
  available=$((total - min_content - 1))
  ((available < minimum)) && return 1
  ((desired > available)) && desired="$available"
  printf '%s\n' "$desired"
}

# Native command-queue equivalent of clamp_sidebar_width_for_total. Evaluate
# against the destination *after* tmux's automatic window sizing, not a stale
# shell snapshot. Inputs are strictly numeric or percentage configuration.
sidebar_width_expression() {
  local requested="${1:-42}" minimum="${2:-24}" maximum="${3:-0}" min_content="${4:-40}" desired available
  [[ "$minimum" =~ ^[1-9][0-9]*$ ]] || minimum=24
  [[ "$maximum" =~ ^(0|[1-9][0-9]*)$ ]] || maximum=0
  [[ "$min_content" =~ ^[1-9][0-9]*$ ]] || min_content=40
  ((maximum == 0 || maximum >= minimum)) || maximum="$minimum"
  if [[ "$requested" =~ ^([1-9][0-9]?)%$ ]]; then
    desired="#{e|/:#{e|*:#{window_width},${BASH_REMATCH[1]}},100}"
  elif [[ "$requested" =~ ^[1-9][0-9]*$ ]]; then desired="$requested"
  else desired=42
  fi
  desired="#{?#{e|<:$desired,$minimum},$minimum,$desired}"
  if ((maximum > 0)); then desired="#{?#{e|>:$desired,$maximum},$maximum,$desired}"; fi
  available="#{e|-:#{window_width},$((min_content+1))}"
  # shellcheck disable=SC2034 # Output variables consumed by navigation.sh.
  SIDEBAR_WIDTH_FORMAT="#{?#{e|>:$desired,$available},$available,$desired}"
  # shellcheck disable=SC2034
  SIDEBAR_WIDTH_FITS_FORMAT="#{e|>=:#{window_width},$((minimum+min_content+1))}"
}

refresh_sidebars() {
  local pane
  while IFS= read -r pane; do
    [[ -n "$pane" ]] && tmux send-keys -t "$pane" C-r 2>/dev/null || true
  done < <(tmux list-panes -a -F $'#{pane_id}\t#{@tmux_canopy}' 2>/dev/null |
    awk -F '\t' '$2 == "1" { print $1 }')
}
