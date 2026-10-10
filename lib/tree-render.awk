# State is read once; the remaining input is a batched tmux metadata snapshot.
BEGIN { FS="\037"; client=ENVIRON["TMUX_CANOPY_RENDER_CLIENT"]; home=ENVIRON["TMUX_CANOPY_RENDER_HOME"] }
FILENAME == ARGV[1] {
    split($0, state, "\t")
    if (state[1] == "MOVE" && move == "") move=state[2]
    else if (state[1] == "LINK" && link == "") link=state[2]
    else if (state[1] == "DELETE" && now-state[3] <= 5) del=state[2]
    else if (state[1] == "FILTER") { filter_set=1; filter=state[2] }
    else if (state[1] == "FOOTER") footer_hidden=(state[2] == "off")
    else if (state[1] == "FILTER_WINDOW") { window_set=1; window_filter=state[2] }
    else if (state[1] == "FILTER_TITLE") { title_set=1; title_filter=state[2] }
    else if (state[1] ~ /^([SW]:|DIR:)/) collapsed[state[1]]=1
    next
}
$1 == "D" {
    icons=($2 == "" ? "unicode" : $2); notices=($3 == "" ? "none" : $3)
    theme=($4 == "" ? "ansi" : $4); density=($5 == "" ? "normal" : $5)
    custom_s=$6; custom_w=$7; custom_p=$8
    nicons=split("nvim vim shell node python git ssh kubectl claude codex gemini pi omp opencode agent antigravity make top crush copilot grok hermes",icon_keys," ")
    for (i=1;i<=nicons;i++) icon_override[icon_keys[i]]=$(17+i)
    appearance=($40 == "lazygit" || $40 == "pills" || $40 == "places" || $40 == "quiet" ? $40 : "classic")
    # Standalone/legacy snapshots still end with agents at field 41.
    agents_enabled=($42 == "on" || (NF == 41 && $41 == "on"))
    if (!agents_enabled) agent_view=0
    current_p=$9; current_w=$10; current_s=$11; width=$12; host=$13; compact_single=($14 == "on" || density == "minimal"); quiet_compact=($14 != "off")
    if (!filter_set) filter=$15
    if (!window_set) window_filter=$16
    if (!title_set) title_filter=$17
}
$1 == "C" && $2 == client { current_s=$3; current_w=$4; current_p=$5 }
$1 == "S" { sessions[++ns]=$2; sname[$2]=$3; attached[$2]=$4 }
$1 == "W" {
    s=$2; w=$3; key=s SUBSEP w
    if (seen_w[key]++) next
    windows[s,++nw[s]]=w; wi[key]=$4; wn[key]=$5; links[w]=$6; sync[w]=$7
    wa[w]=$8+0; wb[w]=$9+0; wz[w]=$10+0; w_zoomed[w]=$11+0
    sa[s]+=wa[w]; sb[s]+=wb[w]; sz[s]+=wz[w]
    if (wa[w] || wb[w] || wz[w]) unread_windows[s]++
}
$1 == "P" {
    p=$2; if (seen_p[p]++) next
    pw[p]=$3; pi[p]=$4; command[p]=$5; title[p]=$6; path[p]=$7; dead[p]=$8
    sidebar[p]=$9; slot[p]=$10; pa[p]=$11+0; pb[p]=$12+0; pz[p]=$13+0; target[p]=$14; target_session[p]=$15
    pane_pid[p]=$17; report_source[p]=$18; report_session[p]=$19; report_pid[p]=$20; report_status[p]=$21; report_updated[p]=$22
    subagent_list[p]=$25; pane_zoomed[p]=($26+0 == 1)
    if (sidebar[p] != 1 && slot[p] != 1) {
        panes[$3,++np[$3]]=p
        if (pa[p] || pb[p] || pz[p]) unread_panes[$3]++
        if (np[$3] == 1) shared_path[$3]=path[p]
        else if (shared_path[$3] != path[p]) shared_path[$3]=""
        if ($16 == 1) last_content[$3]=p
    }
}
$1 == "A" { agent_kind[$2]=$3 }
$1 == "G" { git_branch[$2]=$3 }
$1 == "V" { verified[$2]=1 }
agent_view && $0 ~ /^[[:space:]]*[0-9]+[[:space:]]+[0-9]+[[:space:]]+/ {
    process_line=$0; sub(/^[[:space:]]+/,"",process_line)
    split(process_line,process_field,/[[:space:]]+/)
    pid=process_field[1]; parent[pid]=process_field[2]
    name=process_field[3]; sub(/^.*\//,"",name); sub(/\.exe$/,"",name)
    process_name[pid]=name
    if (name=="codex" || name=="opencode" || name=="gemini" || name=="pi" || name=="omp" || name=="agy" || name=="crush" || name=="copilot" || name=="grok" || name=="hermes") agent_process[pid]=name
    else if (name=="antigravity") agent_process[pid]="agy"
    else if (name=="claude" || name=="claude-code") agent_process[pid]="claude"
    else if (name=="agent") agent_process[pid]="cursor-agent"
    next
}
# Shells, launchers, runtimes, and sandbox wrappers an agent may run under and
# still belong to its pane. Any other process in between (an editor such as nvim, or lazygit)
# owns the agent itself, so the pane is not reported as that agent.
function agent_carrier(name) {
    sub(/^-/,"",name)
    return name ~ /^(sh|bash|zsh|fish|dash|ksh|mksh|tcsh|csh|nu|xonsh|elvish|pwsh|login|su|sudo|doas|env|nice|nohup|time|timeout|script|stdbuf|caffeinate|direnv|mise|asdf|nix|nix-shell|devbox|node|nodejs|bun|deno|npx|npm|pnpm|yarn|tsx|ts-node|python[0-9.]*|uv|uvx|pipx|poetry|ruby|bundle|cargo|make|just|bwrap|firejail|sandbox-exec|nono|fence|landrun|nsjail|minijail0|unshare)$/ ||
        canonical_agent(name) != ""
}
function find_agents( pid,current,depth,p,root) {
    for (p in pane_pid) {
        root=pane_pid[p]
        if (sidebar[p]!=1 && slot[p]!=1 && root ~ /^[1-9][0-9]*$/) owner[root]=p
    }
    for (pid in agent_process) {
        current=pid
        for (depth=0;depth<128 && current>0;depth++) {
            # The agent itself, the pane's root, and everything between must
            # be carriers; a foreground app on the way disqualifies it.
            if (current != pid && (current in process_name) && !agent_carrier(process_name[current])) break
            if (current in owner) {
                p=owner[current]
                if (!(p in best_agent) || depth<best_agent[p]) {
                    best_agent[p]=depth; agent_kind[p]=agent_process[pid]; agent_process_id[p]=pid
                }
                break
            }
            if (seen_ancestor[pid,current]++) break
            current=parent[current]
        }
    }
}
# Build visibility before folding. Counts and compact eligibility still use the
# full content inventory; text constraints are literal, case-insensitive substrings.
function prepare_filter( si,s,wpos,w,key,ppos,p,keep,alert,first,label,window_needle,title_needle) {
    if (filter != "session" && filter != "unread") filter="all"
    window_needle=tolower(window_filter); title_needle=tolower(title_filter)
    filtered=(!switcher && (agent_view || filter != "all" || window_filter != "" || title_filter != ""))
    for (si=1;si<=ns;si++) {
        s=sessions[si]
        for (wpos=1;wpos<=nw[s];wpos++) {
            w=windows[s,wpos]; key=s SUBSEP w
            if (!agent_view && filtered && filter == "session" && s != filter_session) continue
            if (!agent_view && filtered && window_filter != "" && !index(tolower(wn[key]),window_needle)) continue
            first=""
            if (!(w in counted)) {
                counted[w]=1
                for (ppos=1;ppos<=np[w];ppos++) {
                    p=panes[w,ppos]
                    keep=(agent_view ? agent_kind[p] != "" : !filtered ||
                        ((title_filter == "" || index(tolower(title[p]),title_needle)) &&
                        (filter != "unread" || (notices != "none" && (pa[p] || pb[p] || pz[p])))))
                    if (!keep) continue
                    visible_p[p]=1; shown_p[w]++
                    if (first == "") first=p
                    if (pa[p] || pb[p] || pz[p]) shown_unread[w]++
                    vwa[w]+=pa[p]; vwb[w]+=pb[p]; vwz[w]+=pz[p]
                    # Agent lifecycle state is aggregated separately from unread
                    # terminal notifications, grouped into the same three tiers
                    # the per-pane badge already colors: needs-input (including
                    # interrupted), working, and finished. "unknown" is not
                    # actionable and is left out of the rollup entirely.
                    label=agent_label(p)
                    load_subagents(p)
                    if (label=="approval" || label=="interrupted" || sub_need[p]) { w_need[w]++; w_agent_shown[w]++ }
                    else if (label=="working" || sub_work[p]) { w_work[w]++; w_agent_shown[w]++ }
                    else if (label=="ready" || label=="turn ended" || label=="session ended") { w_done[w]++; w_agent_shown[w]++ }
                }
                first_p[w]=first
                # Consecutive panes with one directory share one visible path.
                first=""; previous=""
                for (ppos=1;ppos<=np[w];ppos++) {
                    p=panes[w,ppos]
                    if (!visible_p[p]) continue
                    if (path[p] != "" && path[p] == previous) {
                        group_count[first]++
                        group_member[p]=1
                    } else {
                        first=p; group_count[p]=1; previous=path[p]
                    }
                }
                # Retain a window-only alert when its original reporting pane
                # has gone away, but do not invent a pane matching a title rule.
                if (!agent_view && (!filtered || (!unread_panes[w] && title_filter == ""))) {
                    vwa[w]=wa[w]; vwb[w]=wb[w]; vwz[w]=wz[w]
                }
            }
            alert=(notices != "none" && (vwa[w] || vwb[w] || vwz[w]))
            if (agent_view && !shown_p[w]) continue
            if (!agent_view && filtered && !shown_p[w] && !(filter == "unread" && title_filter == "" && alert)) continue
            visible_w[key]=1; shown_w[s]++; total_visible++
            if (agent_view) shown_agents_s[s]+=shown_p[w]
            if (first_w[s] == "") first_w[s]=w
            vsa[s]+=vwa[w]; vsb[s]+=vwb[w]; vsz[s]+=vwz[w]
            s_need[s]+=w_need[w]; s_work[s]+=w_work[w]; s_done[s]+=w_done[w]
            if (alert) shown_unread_w[s]++
        }
        visible_s[s]=(!filtered || shown_w[s]>0)
    }
}
function resolve_focus(token, kind,s,w,p,parts) {
    if (!filtered) { printf "%s\t\n",token; return }
    split(token,parts,":"); kind=parts[1]
    if (kind == "S") {
        s=parts[2]
        if (!visible_s[s]) return
        w=(s == current_s && visible_w[s,current_w] ? current_w : first_w[s])
    } else if (kind == "W") {
        w=parts[2]; s=parts[3]
        if (!visible_w[s,w]) return
    } else return
    p=(s == current_s && pw[current_p] == w && visible_p[current_p] ? current_p : first_p[w])
    if (p != "") printf "P:%s\t%s\n",p,s
    else printf "W:%s:%s\t\n",w,s
}
function row(token, value, identity) {
    if (token != "H:" && token != "F:") {
        row_count++
        if (identity == ("P:" current_p ":" current_s) || (token ~ /^W:/ && w == current_w && s == current_s && p == current_p)) {
            focus_target = row_count
        } else if (!focus_target && (identity == ("W:" current_w ":" current_s))) {
            focus_window_target = row_count
        } else if (!focus_target && !focus_window_target && (identity == ("S:" current_s))) {
            focus_session_target = row_count
        }
    }
    if (stable) printf "%s\t%s\t%s", token, value, identity
    else printf "%s\t%s", token, value
    # BSD awk cannot retain NUL in strings; emit it directly.
    if (nul) printf "%c", 0
    else printf "\n"
}
function mark(value, color) {
    color=(value == "●" ? green : value == "⇢" || value == "⇉" ? accent : attention)
    return value == " " ? value : color value reset
}
# Lazygit pane rows should not reserve a blank column for an inactive marker
# or a missing shell icon. That gap is what pushes the name off the guide.
function lazy_prefix(stem, branch, pm, color, icon,    prefix) {
    prefix=dim stem branch reset
    if (pm != " " && pm != "●") prefix=prefix mark(pm)
    if (icon != "" && icon != " ") prefix=prefix " " color icon reset
    return prefix
}
# Keep an ordinary collapsed count at the edge, leaving a spare cell for fzf's
# gutter/scrollbar and wide terminal glyphs. Skip it if the name needs the room.
# Terminal cells, not characters: CJK, Hangul, fullwidth forms, and emoji take
# two. Each character is taken with match(), whose length is in bytes on macOS
# awk and in characters on gawk, so substr() agrees with it on both. The ranges
# compare as bytes because tree-source runs this with LC_COLLATE=C.
function text_width(value,    c,cells) {
    if (value !~ /[^ -~]/) return length(value)
    while (match(value, /^./)) {
        c=substr(value, 1, RLENGTH); value=substr(value, RLENGTH+1)
        cells+=((c >= "\342\272\200" && c < "\355\236\260") || (c >= "\357\274\200" && c < "\357\275\241") ||
                (c >= "\357\277\240" && c < "\357\277\247") || (c >= "\360\237\200\200" && c < "\360\237\274\200") ||
                (c >= "\360\240\200\200" && c < "\361\200\200\200")) ? 2 : 1
    }
    return cells
}
function edge_count(value,count,budget, plain,padding) {
    if (count == "") return value
    plain=value
    gsub(/\033\[[0-9;]*m/,"",plain)
    padding=budget-text_width(plain)-length(count)
    if (padding<2) return value
    style=dim
    if (count == "working" || count == "▷" || count == "+") style=accent
    else if (count == "waiting" || count == "interrupted" || count == "!" || count == "●") style=attention
    return value sprintf("%*s",padding,"") style count reset
}
function unread_glyph(a, b, z) {
    if (notices == "none" || !(a || b || z)) return ""
    return b ? bell_badge : a ? activity_badge : silence_badge
}
# Git labels are optional and never displace the active pointer or existing
# status text. An omitted narrow label remains available in the pane preview.
function git_line(value,p,budget,    plain,label) {
    if (git_branch[p] == "") return value
    label=(icons == "ascii" ? " [git:" git_branch[p] "]" : " ⎇ " git_branch[p])
    plain=value; gsub(/\033\[[0-9;]*m/,"",plain)
    if (budget > 0 && text_width(plain)+text_width(label)>budget) return value
    return value dim label reset
}
function quiet_git_row(value,p,budget,    suffix,plain,plain_suffix) {
    suffix=git_line("",p,0)
    if (suffix == "") return value
    plain=value; gsub(/\033\[[0-9;]*m/,"",plain)
    plain_suffix=suffix; gsub(/\033\[[0-9;]*m/,"",plain_suffix)
    if (text_width(plain)+text_width(plain_suffix)+2>budget) return value
    return edge_colored(value,suffix,budget)
}
# Compact status is independent of tmux's unread notice and of fzf selection.
# A live subagent request outranks its parent's working state, as in rollups.
function quiet_pane_edge(p,    label,glyph,style,notice_mark,signal) {
    label=agent_label(p)
    load_subagents(p)
    if (sub_need[p]) label="approval"
    else if (sub_work[p] && label != "approval" && label != "interrupted") label="working"
    if (label != "" && label != "stale") {
        glyph=quiet_mark(label)
        style=(glyph == "!" ? attention : glyph == "▷" || glyph == "+" ? accent : dim)
        if (glyph != "") signal=style glyph reset
    } else if (agent_view && agent_kind[p] != "") signal=dim (icons == "ascii" ? "o" : "○") reset
    notice_mark=unread_glyph(pa[p],pb[p],pz[p])
    # Plain output is the commonest notice and the least urgent: it stays dim so
    # bells, silence, and agents waiting on you keep the amber.
    if (notice_mark != "") signal=signal (signal == "" ? "" : " ") (pb[p] || pz[p] ? attention : dim) notice_mark reset
    return signal
}
# Keep right-edge attention visible even if a long command would otherwise
# push it beyond fzf's viewport. Clip by terminal cells without splitting a
# UTF-8 character or a source color sequence.
function quiet_clip(value,budget,    result,c,cells,step) {
    while (value != "" && cells<budget) {
        if (match(value,/^\033\[[0-9;]*m/)) {
            result=result substr(value,1,RLENGTH); value=substr(value,RLENGTH+1)
            continue
        }
        match(value,/^./); step=RLENGTH
        # Some awk builds match a UTF-8 byte; others match a code point.
        c=substr(value,1,step)
        if (step == 1 && c >= "\360" && c < "\370") step=4
        else if (step == 1 && c >= "\340" && c < "\360") step=3
        else if (step == 1 && c >= "\300" && c < "\340") step=2
        c=substr(value,1,step); value=substr(value,step+1)
        if (cells+text_width(c)>budget) break
        result=result c; cells+=text_width(c)
    }
    return result reset
}
function quiet_pane_line(prefix,name,tail,edge,budget,    plain,signal,detail,room) {
    plain=prefix name tail; gsub(/\033\[[0-9;]*m/,"",plain)
    signal=edge; gsub(/\033\[[0-9;]*m/,"",signal)
    if (edge == "" || text_width(plain)+text_width(signal)+2<=budget)
        return edge_colored(prefix name tail,edge,budget)
    plain=prefix; gsub(/\033\[[0-9;]*m/,"",plain)
    detail=tail; gsub(/\033\[[0-9;]*m/,"",detail)
    room=budget-text_width(plain)-text_width(signal)-2
    if (room < 1) return edge_colored(prefix,edge,budget)
    if (text_width(detail)>=room) { detail=""; tail="" }
    return edge_colored(prefix quiet_clip(name,room-text_width(detail)) tail,edge,budget)
}
function status_mark(status,    style) {
    if (status == "") return ""
    style=(status == "!" || status == "waiting" || status == "interrupted" ? attention : status == "working" || status == "▷" || status == "+" ? accent : dim)
    return " " style status reset
}
function pane_edge(unread, here,    arrow) {
    arrow=(here ? green "▶" reset : "")
    if (unread == "" && arrow == "") return ""
    if (unread != "" && arrow != "") return attention unread reset " " arrow
    if (arrow != "") return arrow
    return attention unread reset
}
function edge_colored(value, suffix, budget,    plain,suffix_plain,padding) {
    if (suffix == "") return value
    plain=value; gsub(/\033\[[0-9;]*m/,"",plain)
    suffix_plain=suffix; gsub(/\033\[[0-9;]*m/,"",suffix_plain)
    padding=budget-text_width(plain)-text_width(suffix_plain)
    if (padding<2) return value " " suffix
    return value sprintf("%*s",padding,"") suffix
}
# One badge per visible target. Counts describe unread descendants, not events
# or provider totals; multiple providers on one target never inflate the count.
function notice(a,b,z,count, glyph) {
    if (notices == "none" || !(a || b || z)) return ""
    glyph=(b ? bell_badge : a ? activity_badge : silence_badge)
    return " " attention glyph (count>1 ? count : "") reset
}
# Rolled-up agent lifecycle state for a collapsed session/window: how many
# descendant panes need input, are working, or have finished. This is
# separate from unread terminal notifications and never affects their
# clear-on-focus behavior. Needs-input outranks working outranks finished,
# matching the three color tiers the per-pane badge already uses.
function agent_summary(need,work,done, glyph,color,count) {
    if (need>0) { glyph=agent_need_badge; color=attention; count=need }
    else if (work>0) { glyph=agent_work_badge; color=accent; count=work }
    else if (done>0) { glyph=agent_done_badge; color=dim; count=done }
    else return ""
    return " " color glyph (count>1 ? count : "") reset
}
# Count each detected pane once, even when its window is linked into several
# sessions. A subagent can raise its parent pane's priority, but is not a
# separate focus target. Unknown includes process-only and stale reports.
function overview_add(glyph,count,color, space) {
    if (!count) return
    space=(overview_plain == "" ? "" : " ")
    overview_plain=overview_plain space glyph count
    overview_color=overview_color space color glyph count reset
}
# The Tree view's footer: every agent pane on the server, whatever the tree's
# filters and folds, counted like the Agents header. sidebar-source moves this
# record into fzf's footer; nothing is emitted when no agent is running.
function agent_footer( si,s,wpos,w,ppos,p,label,need,work,settled,unknown,total,seen,hint) {
    for (si=1;si<=ns;si++) {
        s=sessions[si]
        for (wpos=1;wpos<=nw[s];wpos++) {
            w=windows[s,wpos]
            for (ppos=1;ppos<=np[w];ppos++) {
                p=panes[w,ppos]
                if ((p in seen) || dead[p] == 1 || canonical_agent(command[p]) == "") continue
                seen[p]=1; total++
                label=agent_label(p)
                load_subagents(p)
                if (label == "approval" || label == "interrupted" || sub_need[p]) need++
                else if (label == "working" || sub_work[p]) work++
                else if (label == "ready" || label == "turn ended" || label == "session ended") settled++
                else unknown++
            }
        }
    }
    if (appearance == "quiet") {
        quiet_total=total; quiet_need=need; quiet_work=work; quiet_settled=settled; quiet_unknown=unknown
        return
    }
    if (!total) return
    # The footer has room the header lacks: "◆ 1  ▷ 2" reads more easily than
    # "◆1 ▷2". Fall back to the header's compact form when it would not fit.
    footer_plain=""; footer_color=""
    footer_add(icons == "ascii" ? "!" : agent_need_badge,need,attention)
    footer_add(agent_work_badge,work,accent)
    footer_add(agent_done_badge,settled,dim)
    footer_add(icons == "ascii" ? "o" : "○",unknown,dim)
    if (text_width("Agents  " footer_plain) > width-4) {
        overview_plain=""; overview_color=""
        overview_add(icons == "ascii" ? "!" : agent_need_badge,need,attention)
        overview_add(agent_work_badge,work,accent)
        overview_add(agent_done_badge,settled,dim)
        overview_add(icons == "ascii" ? "o" : "○",unknown,dim)
        footer_plain=overview_plain; footer_color=overview_color
    }
    # The jump hint appears only when it fits beside the counts.
    hint=(need && text_width("Agents  " footer_plain "   n jumps to input") <= width-4 ? dim "   n jumps to input" reset : "")
    row("F:", dim "Agents" reset "  " footer_color hint, "F:")
}
# A quiet header presents the current view and its filter, then a count of
# agents in each state if it fits, or the most urgent state with the total.
# In-flight MOVE/LINK/DELETE takes that count's place.
function quiet_header(    title,scope,joiner,summary,summary_color,style,plain,text,available,full_plain,full_color) {
    title=(agent_view ? "Agents" : "Tree")
    joiner=(icons == "ascii" ? " - " : " · ")
    scope=(agent_view ? "All" : filter_label)
    summary=""; summary_color=""; style=dim
    if (agent_view) {
        agent_overview()
        summary=overview_short_plain
        summary_color=overview_short_color
        full_plain=overview_plain; full_color=overview_color
    } else if (agents_enabled) {
        agent_footer()
        if (quiet_total) {
            overview_plain=""; overview_color=""
            overview_add(icons == "ascii" ? "!" : agent_need_badge,quiet_need,attention)
            overview_add(agent_work_badge,quiet_work,accent)
            overview_add(agent_done_badge,quiet_settled,dim)
            overview_add(icons == "ascii" ? "o" : "○",quiet_unknown,dim)
            full_plain=overview_plain; full_color=overview_color
            if (quiet_need) { summary=(icons == "ascii" ? "!" : "◆") quiet_need "/" quiet_total; style=attention }
            else if (quiet_work) { summary=agent_work_badge quiet_work "/" quiet_total; style=accent }
            else if (quiet_settled) { summary=agent_done_badge quiet_settled "/" quiet_total; style=dim }
            else summary=(icons == "ascii" ? "o" : "○") quiet_total
        }
    }
    if (summary != "" && summary_color == "") summary_color=style summary reset
    available=width-3
    # Every state at a glance ("◆1 ▷1 ○1") when it fits beside the title and
    # filter; otherwise the most urgent state with the total ("◆1/3").
    if (full_plain != "" && text_width(title joiner scope)+text_width(full_plain)+2 <= available) {
        summary=full_plain; summary_color=full_color
    }
    if (mode != "") { summary=mode; summary_color=mode_color mode reset }
    plain=title joiner scope
    if (text_width(plain)+text_width(summary)+2>available) {
        if (scope != "All") scope=substr(scope,1,1)
        plain=title joiner scope
    }
    if (text_width(plain)+text_width(summary)+2>available) { scope=""; plain=title }
    text=accent title reset (scope == "" ? "" : dim joiner scope reset)
    if (summary != "" && text_width(plain)+text_width(summary)+2<=available)
        text=edge_colored(text,summary_color,available)
    row("H:",text,"H:tree")
}
function quiet_footer(    text) {
    text=(agents_enabled ? "1 Tree   4 Agents   n Next" : "1 Tree   2 Proc   3 Buff")
    if (text_width(text)>width-4) text=(agents_enabled ? "1 Tree   4 Agents" : "1 Tree   2 Proc")
    if (text_width(text)>width-4) text="1 Tree"
    row("F:",dim text reset,"F:")
}
function footer_add(glyph,count,color, space) {
    if (!count) return
    space=(footer_plain == "" ? "" : "  ")
    footer_plain=footer_plain space glyph " " count
    footer_color=footer_color space color glyph reset " " count
}
# Without agent mode, the Tree view's footer summarizes the workspace instead:
# sessions, windows, and content panes, each counted once (linked windows,
# sidebars, and reserve panes excluded). A tree filter shows visible/total.
function workspace_footer( si,s,wpos,w,ppos,p,sessions_n,windows_n,panes_n,sessions_v,windows_v,panes_v,seen_w,seen_p,full,short,text) {
    for (si=1;si<=ns;si++) {
        s=sessions[si]
        sessions_n++
        if (visible_s[s]) sessions_v++
        for (wpos=1;wpos<=nw[s];wpos++) {
            w=windows[s,wpos]
            if (!np[w]) continue
            if (!(w in seen_w)) { seen_w[w]=0; windows_n++ }
            if (visible_w[s SUBSEP w] && !seen_w[w]) { seen_w[w]=1; windows_v++ }
            for (ppos=1;ppos<=np[w];ppos++) {
                p=panes[w,ppos]
                if (p in seen_p) continue
                seen_p[p]=1; panes_n++
                if (visible_p[p]) panes_v++
            }
        }
    }
    if (!sessions_n) return
    full=footer_count(session_icon, sessions_v, sessions_n, "session") "  " \
        footer_count(window_icon, windows_v, windows_n, "window") "  " \
        footer_count(pane_icon, panes_v, panes_n, "pane")
    short=footer_count(session_icon, sessions_v, sessions_n, "") "  " \
        footer_count(window_icon, windows_v, windows_n, "") "  " \
        footer_count(pane_icon, panes_v, panes_n, "")
    text=(text_width(full) <= width-4 ? full : short)
    row("F:", dim text reset, "F:")
}
# "◈ 3 sessions", or "◈ 1/3 sessions" while a tree filter hides some.
function footer_count(icon, shown, total, noun,    count) {
    count=(filtered && shown != total ? shown "/" total : total)
    return icon " " count (noun == "" ? "" : " " noun (total == 1 ? "" : "s"))
}
function agent_overview( p,label,need,work,settled,unknown,total,glyph,color,count) {
    overview_plain=""; overview_color=""
    for (p in agent_kind) {
        if (!visible_p[p]) continue
        total++
        label=agent_label(p)
        load_subagents(p)
        if (label == "approval" || label == "interrupted" || sub_need[p]) need++
        else if (label == "working" || sub_work[p]) work++
        else if (label == "ready" || label == "turn ended" || label == "session ended") settled++
        else unknown++
    }
    if (!total) {
        overview_plain="0 agents"; overview_color=dim overview_plain reset
        overview_short_plain="0"; overview_short_color=dim overview_short_plain reset
        return
    }
    overview_add(icons == "ascii" ? "!" : agent_need_badge,need,attention)
    overview_add(agent_work_badge,work,accent)
    overview_add(agent_done_badge,settled,dim)
    overview_add(icons == "ascii" ? "o" : "○",unknown,dim)
    if (need) { glyph=(icons == "ascii" ? "!" : agent_need_badge); color=attention; count=need }
    else if (work) { glyph=agent_work_badge; color=accent; count=work }
    else if (settled) { glyph=agent_done_badge; color=dim; count=settled }
    else { glyph=(icons == "ascii" ? "o" : "○"); color=dim; count=unknown }
    overview_short_plain=glyph count "/" total
    overview_short_color=color glyph count reset dim "/" total reset
}
# How long since the current report, for the row's right-aligned edge_count.
# Independent of agent_badge()'s own text so it never competes for the same
# inline width budget; edge_count already omits it gracefully when tight.
function agent_duration_text(p, age) {
    if (report_updated[p] !~ /^[0-9]+$/) return ""
    age=now-report_updated[p]
    if (age<0) return ""
    if (age<60) return "<1m"
    if (age<3600) return int(age/60) "m"
    if (age<86400) return int(age/3600) "h" (int(age/60)%60) "m"
    return int(age/86400) "d"
}
# Hook state is displayed only while a matching agent process still belongs to
# this live pane. Expired reports clear the row state; unsupported agents show none.
function agent_label(p, age,status,kind) {
    if (!agents_enabled) return ""
    if (p in agent_labels) return agent_labels[p]
    agent_labels[p]=""
    kind=(agent_view ? agent_kind[p] : canonical_agent(command[p]))
    if (dead[p] == 1 || kind == "" || report_source[p] != kind "-hook" ||
        report_session[p] == "" || pane_pid[p] == "" || report_pid[p] != pane_pid[p] ||
        report_updated[p] !~ /^[0-9]+$/ || length(report_updated[p])>12 || !verified[p]) return ""
    age=now-report_updated[p]
    if (age<0 || age>900) return agent_labels[p]="stale"
    status=report_status[p]
    if (status=="working") return agent_labels[p]="working"
    if (status=="needs-input") return agent_labels[p]="approval"
    if (status=="ready") return agent_labels[p]="ready"
    if (status=="turn-ended") return agent_labels[p]="turn ended"
    if (status=="interrupted") return agent_labels[p]="interrupted"
    if (status=="session-ended") return agent_labels[p]="session ended"
    return agent_labels[p]="unknown"
}
function canonical_agent(value) {
    sub(/^.*\//,"",value)
    sub(/\.exe$/,"",value)
    if (value == "claude-code") return "claude"
    if (value == "agent") return "cursor-agent"
    if (value == "antigravity") return "agy"
    if (value == "codex" || value == "claude" || value == "opencode" || value == "gemini" || value == "pi" || value == "omp" || value == "agy" || value == "cursor-agent" || value == "crush" || value == "copilot" || value == "grok" || value == "hermes") return value
    return ""
}
function agent_name(kind) {
    if (kind == "codex") return "Codex"
    if (kind == "claude") return "Claude Code"
    if (kind == "opencode") return "OpenCode"
    if (kind == "gemini") return "Gemini CLI"
    if (kind == "pi") return "Pi"
    if (kind == "omp") return "Oh My Pi"
    if (kind == "agy") return "Antigravity"
    if (kind == "cursor-agent") return "cursor-agent"
    if (kind == "crush") return "Crush"
    if (kind == "hermes") return "Hermes"
    if (kind == "copilot") return "Copilot CLI"
    if (kind == "grok") return "Grok Build"
    return kind
}
# The displayed status word, shared with title_detail()'s width budgeting so
# the two never disagree about how much space the badge actually takes.
function agent_status_word(label, narrow) {
    if (narrow) {
        if (label=="working") return "wrk"
        if (label=="approval") return "req"
        if (label=="ready") return "rdy"
        if (label=="turn ended" || label=="session ended") return "end"
        if (label=="interrupted") return "int"
        return "?"
    }
    if (label=="working") return "WORKING"
    if (label=="approval") return "NEEDS INPUT"
    if (label=="ready") return "READY"
    if (label=="turn ended") return "TURN ENDED"
    if (label=="session ended") return "SESSION ENDED"
    if (label=="interrupted") return "INTERRUPTED"
    return "UNKNOWN"
}
# Child lines need multi-line rows and are left out of compact density; a
# pane row there carries a count instead.
function subagent_lines_shown() { return nul && density != "compact" }
function subagent_count(p,    n) {
    if (!agents_enabled || subagent_lines_shown()) return ""
    n=load_subagents(p)
    return n ? " " dim "+" n reset : ""
}
# Claude Code and Codex subagents reported on their parent pane as id,type,status,updated,tool
# entries. They are shown, and counted, only while the parent's report is.
function load_subagents(p, n,i,items,parts,age,state) {
    if (!agents_enabled) return 0
    if (p in sub_count) return sub_count[p]
    sub_count[p]=0; sub_need[p]=0; sub_work[p]=0
    if (subagent_list[p] == "" || agent_label(p) == "") return 0
    n=split(subagent_list[p],items,";")
    for (i=1;i<=n;i++) {
        if (split(items[i],parts,",") != 5 || parts[4] !~ /^[0-9]+$/ || parts[3] == "done") continue
        age=now-parts[4]
        state=(age<0 || age>900 ? "unknown" : parts[3])
        sub_count[p]++
        sub_type[p,sub_count[p]]=parts[2]; sub_state[p,sub_count[p]]=state
        sub_age[p,sub_count[p]]=age
        if (state == "needs-input") sub_need[p]++
        else if (state == "working") sub_work[p]++
    }
    return sub_count[p]
}
function subagent_word(state, narrow) {
    if (state == "working") return narrow ? "wrk" : "WORKING"
    if (state == "needs-input") return narrow ? "req" : "NEEDS INPUT"
    return narrow ? "?" : "UNKNOWN"
}
# One continuation line per subagent, drawn as children of the pane row.
# A subagent line speaks the same status language as its parent row: words
# in classic and pills, the quiet glyphs (▷ working, ! needs input) in places,
# and lazygit's edge glyph alone.
function subagent_lines(p, continuation, n,i,state,style,text,lines,elapsed,glyph,status) {
    if (!agents_enabled || !subagent_lines_shown()) return ""
    n=load_subagents(p)
    lines=""
    for (i=1;i<=n;i++) {
        state=sub_state[p,i]
        style=(state == "working" ? bold accent : state == "needs-input" ? bold attention : dim)
        elapsed=sub_age[p,i]
        elapsed=(elapsed<0 ? "" : elapsed<60 ? "<1m" : elapsed<3600 ? int(elapsed/60) "m" : int(elapsed/3600) "h")
        glyph=quiet_mark(state == "working" ? "working" : state == "needs-input" ? "approval" : "")
        if (appearance == "lazygit" || appearance == "quiet" || state == "unknown") status=""
        else if (appearance == "places") status=(glyph == "" ? "" : " " style glyph reset)
        else status=" " style subagent_word(state,width<36) reset
        text=continuation dim (i == n ? branch_end : branch_mid) reset " " sub_type[p,i] status
        lines=lines "\n" edge_count(text, appearance == "lazygit" || appearance == "quiet" ? glyph : elapsed, width-3)
    }
    return lines
}
# The status word itself carries the color (no bracket tag): bold for the two
# actionable tiers (needs-input, working), plain dim for unknown so
# it recedes instead of competing for attention. Origin stays a small dim
# suffix since ·plugin? still meaningfully flags an unconfirmed association.
function quiet_mark(label) {
    if (label == "working") return icons == "ascii" ? "+" : "▷"
    if (label == "approval" || label == "interrupted") return "!"
    if (label == "ready" || label == "turn ended" || label == "session ended") return icons == "ascii" ? "d" : "✓"
    return ""
}
function hook_glyph(p,    label,status,glyph,style) {
    label=agent_label(p)
    if (label == "") return ""
    status=report_status[p]
    if (label == "stale") {
        if (status == "working") label="working"
        else if (status == "needs-input") label="approval"
        else if (status == "interrupted") label="interrupted"
        else if (status == "ready") label="ready"
        else if (status == "turn-ended") label="turn ended"
        else if (status == "session-ended") label="session ended"
        else return ""
        style=dim
    } else style=""
    glyph=quiet_mark(label)
    if (glyph == "") return ""
    if (style == "") style=(glyph == "!" ? attention : glyph == "▷" || glyph == "+" ? accent : dim)
    return " " style glyph reset
}
function pill_word(p, label) {
    label=agent_label(p)
    if (label=="working") return "working"
    if (label=="approval") return "waiting"
    if (label=="interrupted") return "interrupted"
    if (label=="ready") return "ready"
    if (label=="turn ended" || label=="session ended") return "ended"
    if (agent_view && agent_kind[p] != "") return "idle"
    return ""
}
function place_name(value,    n,parts) {
    if (value == "" || value == "(no directory)") return "(no directory)"
    if (value == home) return "home"
    n=split(value, parts, "/")
    return parts[n] == "" ? value : parts[n]
}
# Every scalar and scratch array is local: the caller's loop variables
# (w, p, key, ...) must survive this call.
# quiet has no folder rows, so a directory and its branch become a detail on
# the highest row whose panes all share them: the session heading, else each
# window, else each pane. Nothing mixed claims one directory or branch.
function quiet_home_place(s,    wpos,w,ppos,p) {
    quiet_place[s]=""; quiet_place_pane[s]=""
    for (wpos=1; wpos<=nw[s]; wpos++) {
        w=windows[s,wpos]
        if (!visible_w[s SUBSEP w]) continue
        for (ppos=1; ppos<=np[w]; ppos++) {
            p=panes[w,ppos]
            if (!visible_p[p]) continue
            if (quiet_place_pane[s] == "") { quiet_place[s]=path[p]; quiet_place_pane[s]=p }
            else if (path[p] != quiet_place[s]) { quiet_place[s]=""; quiet_place_pane[s]=""; return }
        }
    }
}
# The directory every visible pane of a window shares, or "" when they differ.
function shared_place(w,    ppos,p,place) {
    place=""
    for (ppos=1; ppos<=np[w]; ppos++) {
        p=panes[w,ppos]
        if (!visible_p[p]) continue
        if (place == "") place=path[p]
        else if (path[p] != place) return ""
    }
    return place
}
# The right-hand edge: pane p's directory and branch, then the row's marks.
# On a narrow row the detail gives way in steps (a shortened branch, then the
# directory alone, then nothing), never the name or a mark.
function quiet_edge(value, p, edge, budget,    plain,room,name,branch,opening,closing,detail) {
    if (p == "" || path[p] == "") return edge
    plain=value edge; gsub(/\033\[[0-9;]*m/,"",plain)
    room=budget-text_width(plain)-2-(edge == "" ? 0 : 2)
    # @tmux-canopy-directory off leaves only the branch, which needs git context.
    name=(details_directory == "off" ? "" : place_name(path[p])); branch=git_branch[p]
    if (name == "" && branch == "") return edge
    opening=(icons == "ascii" ? " [git:" : " ⎇ "); closing=(icons == "ascii" ? "]" : "")
    # Without a directory the branch leads: "⎇ main", not " ⎇ main".
    if (name == "") sub(/^ /, "", opening)
    if (branch != "" && text_width(name opening branch closing) <= room) detail=name opening branch closing
    else if (branch != "" && room-text_width(name opening closing)-1 >= 4)
        detail=name opening substr(branch, 1, room-text_width(name opening closing)-1) "…" closing
    else if (name != "" && text_width(name) <= room) detail=name
    else return edge
    return dim detail reset (edge == "" ? "" : "  " edge)
}
# A quiet session heading carries its own separator: a dim rule from the name
# to the right edge (or to its detail), so sessions stand apart without a blank
# line that a selection would cover.
function quiet_rule_row(value, suffix, budget,    plain,suffix_plain,room,rule) {
    plain=value; gsub(/\033\[[0-9;]*m/,"",plain)
    suffix_plain=suffix; gsub(/\033\[[0-9;]*m/,"",suffix_plain)
    room=budget-text_width(plain)-text_width(suffix_plain)-(suffix == "" ? 1 : 2)
    if (room < 2) return edge_colored(value, suffix, budget)
    rule=sprintf("%*s", room, ""); gsub(/ /, (icons == "ascii" ? "-" : "─"), rule)
    return value " " dim rule reset (suffix == "" ? "" : " " suffix)
}
# A shell at its prompt is scaffolding next to what is running. It recedes
# unless it is where you are or has something to report.
function idle_shell(p, s) {
    return command[p] ~ /^-?(sh|bash|zsh|fish|dash|ksh|mksh|tcsh|csh|nu|xonsh|elvish|pwsh)$/ &&
        !(p == current_p && s == current_s) && !pa[p] && !pb[p] && !pz[p]
}
function places_panes(s,    wpos,w,key,ppos,p,place,id,idx,n,i,cnt,pn,parts,bases,label,dir_last,dir_branch,dir_stem,dir_key,dir_open,folder,folder_color,folder_line,wc,win_ids,win_names,win_first,win_last,windex,wlast,win_stem,wt,wm,name_disp,pt,cmd,icon,pm,cmd_disp,line,pane_last,continuation,prefix,edge,current_place,stem_blank,pane_indent) {
    n=0
    # A finished branch leaves a blank stem as wide as an open one, so the last
    # folder's and window's children line up with their siblings'.
    stem_blank=sprintf("%*s", text_width(stem_mid), "")
    # quiet draws no guides, so a pane hangs from its window instead: its
    # location mark sits under the window's icon, and its icon under the
    # window's label. Every pane keeps an icon slot, blank or not, so pane
    # names line up with each other and start right of their window's name.
    pane_indent=sprintf("%*s", text_width(branch_mid " " fold_open) - text_width(stem_mid), "")
    current_place=path[current_p]; if (current_place == "") current_place="(no directory)"
    # quiet follows tmux's own order: one group, so each window appears once,
    # in index order, whatever directories its panes are in.
    if (appearance == "quiet") current_place="(tmux order)"
    for (wpos=1; wpos<=nw[s]; wpos++) {
        w=windows[s,wpos]; key=s SUBSEP w
        if (!visible_w[key]) continue
        for (ppos=1; ppos<=np[w]; ppos++) {
            p=panes[w,ppos]
            if (!visible_p[p]) continue
            place=(appearance == "quiet" ? "(tmux order)" : path[p]); if (place == "") place="(no directory)"
            id=s SUBSEP place
            if (!(id in place_seen)) { place_seen[id]=1; place_order[s, ++n]=place; place_count[id]=0 }
            idx=++place_count[id]
            place_pane[id, idx]=p
            place_wid[id, idx]=w
            place_wname[id, idx]=wn[key]
        }
    }
    for (i=1; i<=n; i++) bases[place_name(place_order[s, i])]++
    for (i=1; i<=n; i++) {
        place=place_order[s, i]; id=s SUBSEP place; cnt=place_count[id]
        label=place_name(place)
        if (bases[label] > 1 && place != home && place != "(no directory)") {
            pn=split(place, parts, "/")
            if (pn >= 2 && parts[pn-1] != "") label=parts[pn-1] "/" label
        }
        dir_last=(i == n)
        dir_branch=(dir_last ? branch_end : branch_mid)
        dir_stem=(appearance == "quiet" ? "" : dir_last ? stem_blank : stem_mid)
        dir_key="DIR:" place_pane[id, 1]
        dir_open=!(dir_key in collapsed)
        if (icons == "nerdfont") folder=(dir_open ? "󰝰" : "󰉋")
        else if (icons == "unicode") folder=(dir_open ? "📂" : "📁")
        else if (icons == "ascii") folder="/"
        else folder=(dir_open ? "📂" : "📁")
        folder_color=(theme == "mono" ? "" : "\033[38;5;74m")
        folder_line=dim dir_branch reset " " (dir_open ? fold_open : fold_closed) folder_color folder reset " " label
        if (appearance == "quiet") {
            if (!dir_open && s == current_s && visible_p[current_p] && place == current_place)
                folder_line=edge_colored(folder_line,green (icons == "ascii" ? ">" : "▶") reset,width-3)
            else folder_line=quiet_git_row(folder_line,place_pane[id,1],width-3)
        } else folder_line=git_line(folder_line,place_pane[id,1],width-5)
        if (appearance == "quiet") dir_open=1
        else {
            row(dir_key, folder_line, dir_key ":" s)
            if (!dir_open) continue
        }
        wc=0
        for (idx=1; idx<=cnt; idx++) {
            w=place_wid[id, idx]
            if (wc == 0 || win_ids[wc] != w) { win_ids[++wc]=w; win_names[wc]=place_wname[id, idx]; win_first[wc]=idx }
            win_last[wc]=idx
        }
        for (windex=1; windex<=wc; windex++) {
            w=win_ids[windex]; wlast=(windex == wc)
            win_stem=dir_stem (wlast ? stem_blank : stem_mid)
            wt="W:" w ":" s
            wm=(wt == del ? "✕" : wt == link ? "⇉" : wt == move || w == move_w ? "⇢" : " ")
            name_disp=(unnamed_w[s SUBSEP w] ? dim win_names[windex] reset : win_names[windex])
            if (appearance == "quiet" && quiet_compact && !agent_view && np[w] == 1 && win_first[windex] == win_last[windex]) {
                # A window holding one pane is one row with the window's identity:
                # the pane's icon stands in for the window's, its location mark
                # takes the fold's place, and its command shows only when the
                # window is named something else.
                p=place_pane[id, win_first[windex]]; pt="P:" p
                cmd=command[p]; icon=appicon(cmd)
                if (idle_shell(p, s)) name_disp=dim win_names[windex] reset
                pm=(wm != " " ? wm : pt == del ? "✕" : pt == move ? "⇢" : p == current_p && s == current_s ? "●" : dead[p] == 1 ? "×" : " ")
                prefix=dim dir_stem (wlast ? branch_end : branch_mid) reset " " (pm == "●" ? green (icons == "ascii" ? ">" : "●") reset : pm == " " ? " " : mark(pm)) " "
                prefix=prefix (icon != "" && icon != " " ? appcolor(cmd) icon reset : dim window_icon reset) " " dim wi[s SUBSEP w] ":" reset
                cmd_disp=(cmd == "" || cmd == win_names[windex] ? "" : dim " · " cmd reset)
                line=(w == current_w && s == current_s ? bold : "") name_disp reset
                line=quiet_pane_line(prefix, line, cmd_disp (w_zoomed[w] ? " " dim "[Z]" reset : "") subagent_count(p),
                    quiet_edge(prefix line cmd_disp, path[p] != quiet_place[s] ? p : "", quiet_pane_edge(p), width-3), width-3)
                continuation=prefix; gsub(/\033\[[0-9;]*m/,"",continuation)
                row(wt, line subagent_lines(p, sprintf("%*s", text_width(continuation), "")), wt)
                continue
            }
            line=dim dir_stem (wlast ? branch_end : branch_mid) reset " " (collapsed[wt] ? fold_closed : fold_open) (wm != " " ? mark(wm) " " : "") dim window_icon " " wi[s SUBSEP w] ":" reset (w == current_w && s == current_s ? bold : "") name_disp reset (w_zoomed[w] ? " [Z]" : "")
            if (collapsed[wt]) {
                line=line notice(vwa[w],vwb[w],vwz[w],shown_unread[w]) agent_summary(w_need[w],w_work[w],w_done[w]) dim " [" shown_p[w] "p]" reset
                if (w == current_w && s == current_s && visible_p[current_p] && place == current_place)
                    line=edge_colored(line,green (icons == "ascii" ? ">" : "▶") reset,width-3)
            } else if (appearance == "quiet" && shared_place(w) != "" && shared_place(w) != quiet_place[s])
                line=edge_colored(line, quiet_edge(line, place_pane[id, win_first[windex]], "", width-3), width-3)
            row(wt, line, wt)
            if (collapsed[wt]) continue
            for (idx=win_first[windex]; idx<=win_last[windex]; idx++) {
                p=place_pane[id, idx]; pt="P:" p
                cmd=command[p]; icon=appicon(cmd)
                pm=(pt == del ? "✕" : pt == move ? "⇢" : p == current_p && s == current_s ? "●" : dead[p] == 1 ? "×" : " ")
                cmd_disp=(unnamed_cmd[p] || (appearance == "quiet" && idle_shell(p, s)) ? dim cmd reset : cmd)
                pane_last=(idx == win_last[windex])
                if (appearance == "quiet") {
                    # A left-hand location dot leaves the right edge for agent
                    # attention and terminal notices; fzf still owns selection.
                    prefix=dim win_stem reset pane_indent (pm == "●" ? green (icons == "ascii" ? ">" : "●") reset : pm == " " ? " " : mark(pm)) " "
                    if (icon != "" && icon != " ") prefix=prefix appcolor(cmd) icon reset
                    prefix=prefix sprintf("%*s", 2 - text_width(icon == " " ? "" : icon), "") " "
                    line=quiet_pane_line(prefix dim pi[p] ":" reset,cmd_disp,(pane_zoomed[p] ? " " dim "[Z]" reset : "") subagent_count(p),
                        quiet_edge(prefix pi[p] ":" cmd_disp, shared_place(w) == "" && path[p] != quiet_place[s] ? p : "", quiet_pane_edge(p), width-3), width-3)
                    edge=""
                } else {
                    line=lazy_prefix(win_stem, pane_last ? branch_end : branch_mid, pm, appcolor(cmd), icon) " " dim pi[p] ":" reset cmd_disp (pane_zoomed[p] ? " " dim "[Z]" reset : "") hook_glyph(p) subagent_count(p)
                    edge=pane_edge(unread_glyph(pa[p],pb[p],pz[p]), pm == "●")
                }
                # Subagents hang beneath the pane, their branches aligned with
                # its command (lazy_prefix draws no icon cell for a blank icon).
                if (appearance == "quiet") {
                    continuation=prefix; gsub(/\033\[[0-9;]*m/,"",continuation)
                    continuation=sprintf("%*s", text_width(continuation)+length(pi[p])+1, "")
                }
                else continuation=dim win_stem (pane_last ? stem_blank : stem_mid) reset sprintf("%*s", (icon == "" || icon == " " ? 0 : 1+text_width(icon))+length(pi[p])+1, "")
                row(pt, (appearance == "quiet" ? line : edge_colored(line, edge, width-3)) subagent_lines(p, continuation), pt ":" s)
            }
        }
    }
}
function pills_session(s, st,    wpos,w,key,wt,ppos,p,pt,shown,name,icon,mark,line,note,cmd_disp) {
    note=(collapsed[st] ? nw[s] "w" : "")
    row(st, edge_count(dim (collapsed[st] ? fold_closed : "") sname[s] reset, note, width-2), st)
    if (collapsed[st]) return
    for (wpos=1;wpos<=nw[s];wpos++) {
        w=windows[s,wpos]; key=s SUBSEP w; wt="W:" w ":" s
        if (!visible_w[key]) continue
        shown=0
        for (ppos=1;ppos<=np[w];ppos++) if (visible_p[panes[w,ppos]]) shown++
        if (shown>1 || collapsed[wt]) {
            row(wt, edge_count("  " dim wn[key] (w_zoomed[w] ? " [Z]" : "") reset, collapsed[wt] ? shown "p" : "", width-2), wt)
            if (collapsed[wt]) continue
        }
        for (ppos=1;ppos<=np[w];ppos++) {
            p=panes[w,ppos]; pt="P:" p
            if (!visible_p[p]) continue
            name=(agent_view && agent_kind[p] != "" ? agent_name(agent_kind[p]) : command[p])
            cmd_disp=(unnamed_cmd[p] ? dim name reset : name)
            icon=appicon(agent_view && agent_kind[p] != "" ? agent_kind[p] : command[p])
            mark=(p == current_p && s == current_s ? green "●" reset : dead[p]==1 ? dim "×" reset : " ")
            line=mark " " appcolor(agent_view && agent_kind[p] != "" ? agent_kind[p] : command[p]) icon reset " " cmd_disp (pane_zoomed[p] ? " " dim "[Z]" reset : "") subagent_count(p)
            note=pill_word(p)
            if (note == "" && (pa[p] || pb[p] || pz[p])) note="●"
            row(pt, edge_count(git_line(line,p,width-6), note, width-2) subagent_lines(p, sprintf("%*s", 2+text_width(icon), "")), pt ":" s)
        }
    }
}
function agent_badge(p, label,style,origin,word) {
    if (!agents_enabled || appearance == "pills" || appearance == "lazygit") return ""
    label=agent_label(p)
    if (label=="stale") return agent_view ? " " dim "[process]" reset : ""
    if (label=="") return agent_view && agent_kind[p] != "" ? " " dim "[process]" reset : ""
    style=(label=="working" ? accent : label=="approval" || label=="interrupted" ? attention : dim)
    word=agent_status_word(label,width<36)
    origin=(report_source[p] == "opencode-hook" ? "plugin?" : "hook")
    return " " (style==dim ? "" : bold) style word reset dim " ·" origin reset
}
function shortpath(value, budget, n, parts, shortened) {
    if (value == home) value="~"
    else if (index(value,home "/") == 1) value="~" substr(value,length(home)+1)
    if (density == "detailed" || value == "~" || index(value,"/") == 0) return value
    n=split(value,parts,"/")
    if (n==2 && parts[1]=="~") return value
    if (density == "compact") return "…/" parts[n]
    shortened="…/" parts[n-1] "/" parts[n]
    # Prefer useful parent context, but do not crowd out the directory basename.
    # fzf does the final ANSI/Unicode cell clipping; never byte-slice a path.
    if (budget>0 && length(shortened)>budget) return "…/" parts[n]
    return shortened
}

# Show the shortest directory suffix that distinguishes paths in this window.
# At wide widths include the parent for context. Full paths remain in previews.
# The shortest path suffix that no other pane in the window shares. It is
# compared against every sibling, so it is computed once per pane and window
# even though callers ask with different budgets.
function path_suffix(p,w,    value,parts,n,depth,candidate,q,other,matches,otherparts,othern) {
    if ((p,w) in suffix_memo) return suffix_memo[p,w]
    value=path[p]
    n=split(value,parts,"/")
    depth=(width>=72 ? 2 : 1)
    if (depth>n) depth=n
    while (1) {
        candidate=parts[n-depth+1]
        for (q=n-depth+2;q<=n;q++) candidate=candidate "/" parts[q]
        matches=0
        for (q=1;q<=np[w];q++) {
            other=path[panes[w,q]]
            if (other == value || other == "") continue
            othern=split(other,otherparts,"/")
            if (othern>=depth && substr(other,length(other)-length(candidate)+1)==candidate &&
                (othern==depth || substr(other,length(other)-length(candidate),1)=="/")) { matches=1; break }
        }
        if (!matches || depth>=n) break
        depth++
    }
    suffix_depth[p,w]=depth
    return suffix_memo[p,w]=candidate
}
function pathlabel(p,w,budget,    value,parts,n,depth,candidate,need) {
    value=path[p]
    if (value == "") return "(directory unavailable)"
    if (density == "detailed" || density == "compact") return shortpath(value,budget)
    if (value == home) return appearance == "lazygit" ? "home" : "~"
    n=split(value,parts,"/")
    candidate=path_suffix(p,w)
    depth=suffix_depth[p,w]
    need=(depth<n ? "…/" : "") candidate
    if (budget>0 && length(need)>budget && depth>1) return "…/" parts[n]
    if (appearance == "lazygit") return tidy_path(value, candidate)
    return need
}
# A directory is its own name. No tilde and no ellipsis, so it does not look relative.
function tidy_path(value, candidate) {
    if (candidate == "") return "home"
    return candidate
}
function title_detail(p,    value,limit,label) {
    if (density == "compact" || width<38) return ""
    value=useful_title(p)
    if (density == "detailed") return " " pi[p] (value != "" ? " " value : "")
    if (value == "") return ""
    limit=width-25-length(command[p])
    if (pane_zoomed[p]) limit-=4
    label=agent_label(p)
    if (label!="" && label!="stale") limit-=length(agent_status_word(label,width<36))+3
    if (density == "normal" && width<56 && width>=32)
        limit-=length(pathlabel(p,pw[p],width-16))+3
    if (limit<8) return ""
    if (length(value)>limit) value=substr(value,1,limit-1) "…"
    return " " value
}
function useful_title(p, value) {
    value=title[p]
    if (value == host || index(value,host ".") == 1 || value == command[p]) return ""
    return value
}
# Standard terminal palette, independent of glyph theme. Green remains the
# active-location indicator; application colors do not imply activity/state.
# Icons and colors depend only on the command and settings fixed before
# rendering, and are asked for several times per pane.
function appcolor(value) {
    if (!(value in appcolor_memo)) appcolor_memo[value]=appcolor_lookup(value)
    return appcolor_memo[value]
}
function appcolor_lookup(value, n, parts) {
    if (theme == "mono") return ""
    n=split(value,parts,"/"); value=parts[n]
    sub(/\.exe$/,"",value)
    if (value ~ /^(nvim|vim|vi)$/) return icon_blue
    if (value ~ /^(node|python|python3)$/) return icon_yellow
    if (value ~ /^(npm|npx|git|lazygit|oc|hunk)$/) return icon_red
    if (value ~ /^(kubectl|k9s)$/) return icon_blue
    if (value ~ /^(ssh|codex|top|htop|btop|agy)$/) return icon_cyan
    if (value == "pi" || value == "crush") return icon_purple
    if (value == "omp" || value == "hermes") return icon_yellow
    if (value == "opencode" || value == "agent" || value == "cursor-agent" || value == "copilot" || value == "grok") return icon_neutral
    if (value ~ /^(claude|claude-code)$/) return icon_yellow
    if (value == "gemini") return icon_blue
    return icon_neutral
}
function app_key(value) {
    if (value == "nvim") return "nvim"
    if (value ~ /^(vim|vi)$/) return "vim"
    if (value ~ /^(bash|zsh|fish|sh)$/) return "shell"
    if (value ~ /^(node|npm|npx)$/) return "node"
    if (value ~ /^(python|python3)$/) return "python"
    if (value ~ /^(git|lazygit|hunk)$/) return "git"
    if (value == "ssh") return "ssh"
    if (value ~ /^(kubectl|oc|k9s)$/) return "kubectl"
    if (value ~ /^(claude|claude-code)$/) return "claude"
    if (value == "codex") return "codex"
    if (value == "gemini") return "gemini"
    if (value == "pi") return "pi"
    if (value == "omp") return "omp"
    if (value == "opencode") return "opencode"
    if (value == "agent" || value == "cursor-agent") return "agent"
    if (value ~ /^(agy|antigravity)$/) return "antigravity"
    if (value ~ /^(make|cmake|ninja)$/) return "make"
    if (value ~ /^(top|htop|btop)$/) return "top"
    if (value == "crush") return "crush"
    if (value == "hermes") return "hermes"
    if (value == "copilot") return "copilot"
    if (value == "grok") return "grok"
    return ""
}
function appicon(value) {
    if (!(value in appicon_memo)) appicon_memo[value]=appicon_lookup(value)
    return appicon_memo[value]
}
function appicon_lookup(value, n, parts,key,override) {
    n=split(value,parts,"/"); value=parts[n]
    sub(/\.exe$/,"",value)
    key=app_key(value)
    override=(key == "" ? "" : icon_override[key])
    if (override != "") return override == "none" ? " " : override
    if (icons == "ascii") return pane_icon
    if (icons == "unicode") {
        if (value ~ /^(nvim|vim|vi)$/) return "✎"
        if (value ~ /^(node|npm|npx)$/) return "◆"
        if (value ~ /^(python|python3)$/) return "◉"
        if (value ~ /^(git|lazygit|hunk)$/) return "◇"
        if (value == "ssh") return "⇄"
        if (value ~ /^(kubectl|oc|k9s)$/) return "✣"
        if (value ~ /^(claude|claude-code)$/) return "✳"
        if (value == "codex") return "❋"
        if (value == "gemini") return "✧"
        if (value == "pi" || value == "omp") return "π"
        if (value == "opencode") return "▦"
        if (value == "agent" || value == "cursor-agent") return "▸"
        if (value ~ /^(agy|antigravity)$/) return "◎"
        if (value == "crush") return "❖"
        if (value == "hermes") return "⚕"
        if (value == "copilot") return "⊚"
        if (value == "grok") return "⨯"
        if (value ~ /^(make|cmake|ninja)$/) return "✱"
        if (value ~ /^(top|htop|btop)$/) return "▥"
        return custom_p != "" ? pane_icon : " "
    }
    if (value == "nvim") return ""
    if (value ~ /^(vim|vi)$/) return ""
    if (value ~ /^(bash|zsh|fish|sh)$/) return " "
    if (value ~ /^(node|npm|npx)$/) return ""
    if (value ~ /^(python|python3)$/) return ""
    if (value ~ /^(git|lazygit|hunk)$/) return "󰊢"
    if (value == "ssh") return "󰢹"
    if (value ~ /^(kubectl|oc|k9s)$/) return "󱃾"
    if (value ~ /^(claude|claude-code)$/) return ""
    if (value == "codex") return ""
    if (value == "gemini") return "󰫢"
    if (value == "pi" || value == "omp") return "π"
    if (value == "opencode") return ""
    if (value == "agent" || value == "cursor-agent") return ""
    if (value ~ /^(agy|antigravity)$/) return "󰀘"
    if (value == "crush") return "❖"
    # Nerd Fonts has no Hermes mark; the plain Unicode staff renders in any font.
    if (value == "hermes") return "⚕"
    if (value == "copilot") return ""
    if (value == "grok") return "⨯"
    if (value ~ /^(make|cmake|ninja)$/) return ""
    if (value ~ /^(top|htop|btop)$/) return "󰍛"
    return custom_p != "" ? pane_icon : " "
}
END {
    if (ns == 0) exit
    for (w in np) {
        if (w_zoomed[w] && np[w] == 1) pane_zoomed[panes[w, 1]] = 1
    }
    if (agent_view) find_agents()
    if (theme != "mono") {
        reset="\033[0m"; bold="\033[1m"; dim="\033[2m"
        # Neutral text and guides, with distinct application and active-location colors.
        icon_blue="\033[94m"; icon_yellow="\033[93m"; icon_red="\033[91m"
        icon_cyan="\033[96m"; icon_purple="\033[95m"; icon_neutral="\033[39m"
        icon_white="\033[97m"
        green="\033[1;32m"
        accent="\033[1;36m"; attention="\033[1;33m"; path_color=dim
        # tmux's own green (its logo, about #1BB91F) for quiet session glyphs.
        tmux_green="\033[38;5;34m"; tmux_green_dim="\033[2;38;5;34m"
    }
    session_icon=(icons == "nerdfont" ? "" : icons == "ascii" ? "S" : "◈")
    window_icon=(icons == "nerdfont" ? "󰖯" : icons == "ascii" ? "W" : "▣")
    pane_icon=(icons == "nerdfont" ? "" : icons == "ascii" ? ">" : "▹")
    activity_badge=(icons == "ascii" ? "*" : "●")
    bell_badge=(icons == "nerdfont" ? "" : icons == "ascii" ? "B" : "🔔")
    silence_badge=(icons == "ascii" ? "~" : "◷")
    agent_need_badge=(icons == "ascii" ? "!" : "◆")
    agent_work_badge=(icons == "ascii" ? "+" : "▷")
    agent_done_badge=(icons == "ascii" ? "d" : "✓")
    if (custom_s != "") session_icon=custom_s
    if (custom_w != "") window_icon=custom_w
    if (custom_p != "") pane_icon=custom_p
    if (appearance == "pills") {
        branch_mid="  "; branch_end="  "; stem_mid="  "
        fold_open=(icons == "ascii" ? "> " : "▾ ")
        fold_closed=(icons == "ascii" ? "> " : "▸ ")
        show_session_glyph=0; show_window_glyph=0
    } else if (appearance == "quiet") {
        branch_mid="  "; branch_end="  "; stem_mid="  "
        fold_open=(icons == "ascii" ? "v " : "▾ ")
        fold_closed=(icons == "ascii" ? "> " : "▸ ")
    } else if ((appearance == "lazygit" || appearance == "places") && icons != "ascii") {
        branch_mid="├─"; branch_end="╰─"; stem_mid="│  "
        fold_open="▼ "; fold_closed="▶ "
    } else if (appearance == "lazygit" || appearance == "places") {
        branch_mid="|-"; branch_end="`-"; stem_mid="|  "
        fold_open="v "; fold_closed="> "
    } else {
        branch_mid=(icons == "ascii" ? "|-" : "├─"); branch_end=(icons == "ascii" ? "`-" : "└─")
        stem_mid=(icons == "ascii" ? "|  " : "│  ")
        fold_open="▾ "; fold_closed="▸ "
    }
    if (appearance == "lazygit" && theme != "mono") {
        fold_open=accent fold_open reset; fold_closed=accent fold_closed reset
    }
    show_session_glyph=(appearance == "lazygit" || appearance == "places" || appearance == "quiet" || custom_s != "")
    show_window_glyph=(appearance == "lazygit" ? custom_w != "" : custom_w != "")
    filter_session=current_s
    if (sidebar[current_p] == 1) {
        last=last_content[pw[current_p]]
        if (last != "") { current_p=last; current_w=pw[last] }
        else if (target[current_p] != "" && pw[target[current_p]] != "" && sidebar[target[current_p]] != 1 && slot[target[current_p]] != 1) {
            if (target_session[current_p] != "") current_s=target_session[current_p]
            current_p=target[current_p]; current_w=pw[current_p]
        }
    }
    if (ENVIRON["TMUX_CANOPY_POPUP"] == "1" && ENVIRON["TMUX_CANOPY_TARGET"] != "") {
        pop_target = ENVIRON["TMUX_CANOPY_TARGET"]
        if (pop_target in pw) {
            current_p = pop_target
            current_w = pw[pop_target]
            for (si = 1; si <= ns; si++) {
                s_candidate = sessions[si]
                for (wpos = 1; wpos <= nw[s_candidate]; wpos++) {
                    if (windows[s_candidate, wpos] == current_w) {
                        current_s = s_candidate
                        break
                    }
                }
            }
        }
    }
    for (si=1; si<=ns; si++) {
        s=sessions[si]
        if (sname[s] ~ /^['"[:space:]]*$/) sname[s]=s
        for (wpos=1; wpos<=nw[s]; wpos++) {
            w=windows[s,wpos]; key=s SUBSEP w
            for (ppos=1; ppos<=np[w]; ppos++) {
                p=panes[w,ppos]
                if (command[p] ~ /^['"[:space:]]*$/) {
                    ut=useful_title(p)
                    if (ut !~ /^['"[:space:]]*$/) command[p]=ut
                    else { command[p]="unnamed"; unnamed_cmd[p]=1 }
                }
            }
            if (wn[key] ~ /^['"[:space:]]*$/) {
                p=panes[w,1]
                cmd=(p != "" ? (agent_view && agent_kind[p] != "" ? agent_name(agent_kind[p]) : command[p]) : "")
                if (cmd != "" && cmd !~ /^['"[:space:]]*$/ && cmd != "unnamed") wn[key]=cmd
                else { wn[key]="unnamed"; unnamed_w[key]=1 }
            }
        }
    }
    prepare_filter()
    if (ENVIRON["TMUX_CANOPY_FILTER_TARGET"] != "") {
        resolve_focus(ENVIRON["TMUX_CANOPY_FILTER_TARGET"])
        exit
    }
    # Unfiltered, like the switcher: a pane needing input must never be
    # hidden by an active Tree filter. Caller forces agent_view so detection
    # includes agents running under a wrapper shell, not just the foreground
    # command. One entry per linked-session occurrence, natural tree order.
    if (ENVIRON["TMUX_CANOPY_NEEDS_INPUT"] != "") {
        for (si=1;si<=ns;si++) {
            s=sessions[si]
            for (wpos=1;wpos<=nw[s];wpos++) {
                w=windows[s,wpos]
                for (ppos=1;ppos<=np[w];ppos++) {
                    p=panes[w,ppos]
                    label=agent_label(p)
                    if (label=="approval" || label=="interrupted" || (load_subagents(p) && sub_need[p])) printf "P:%s\t%s\n",p,s
                }
            }
        }
        exit
    }
    move_p=substr(move,3); move_w=(move ~ /^P:/ ? pw[move_p] : "")
    if (header && !switcher) {
        mode=(move != "" ? "MOVE" : link != "" ? "LINK" : del != "" ? "DELETE" : "")
        mode_color=(del != "" && move == "" && link == "" ? attention : accent)
        mode_gap=(mode == "" ? 0 : 1)
        # Reserve fzf's pointer gutter and keep operation warnings visible.
        available=width-2
        filter_label=(filter == "session" ? "Session" : filter == "unread" ? "Unread" : "All")
        filter_sep=(icons == "ascii" ? " | " : appearance == "lazygit" || appearance == "places" ? " ─ " : " · ")
        if (window_filter != "") filter_label=filter_label "+W"
        if (title_filter != "") filter_label=filter_label "+T"
        reserved=text_width(filter_sep filter_label)+(mode != "" ? length(mode)+1 : 0)
        box_pad=(appearance == "lazygit" || appearance == "places" ? 3 : 0)
        if (appearance == "quiet") {
            quiet_header()
            if (!agent_view && !footer_hidden) quiet_footer()
        } else {
        if (appearance == "pills") {
            place=(agent_view ? "agents" : (current_s in sname ? sname[current_s] : ""))
            if (place == "" && ns > 0) place=sname[sessions[1]]
            hints=(filter != "all" || window_filter != "" || title_filter != "" ? filter_label : "")
            header_text=(agent_view ? accent : dim) place reset
            if (hints != "" && text_width(place)+text_width(hints)+2 <= available)
                header_text=header_text sprintf("%*s", available-text_width(place)-text_width(hints), "") dim hints reset
            if (mode != "") header_text=header_text " " mode_color mode reset
            row("H:",header_text,"H:tree")
        } else if (agent_view) {
            agent_overview()
            tabs="Tree [Agents] Proc Buff"
            if (text_width(tabs)+text_width(overview_plain)+length(mode)+mode_gap+1+box_pad>available-2) {
                overview_plain=overview_short_plain; overview_color=overview_short_color
            }
            if (text_width(tabs)+text_width(overview_plain)+length(mode)+mode_gap+1+box_pad>available-2) tabs="T [Agents] P B"
            if (text_width(tabs)+text_width(overview_plain)+length(mode)+mode_gap+1+box_pad>available-2) tabs="T [A] P B"
            if (text_width(tabs)+text_width(overview_plain)+length(mode)+mode_gap+1+box_pad>available-2) tabs="[A]"
        } else if (appearance == "lazygit" || appearance == "places") {
            tabs=(agents_enabled ? "Tree Agents Proc Buff" : "Tree Proc Buff")
            if (text_width(tabs)+reserved+box_pad>available-2) tabs=(agents_enabled ? "Tree A P B" : "Tree P B")
            if (text_width(tabs)+reserved+box_pad>available-2) tabs=(agents_enabled ? "T A P B" : "T P B")
            if (text_width(tabs)+reserved+box_pad>available-2) sub(/^(Session|Unread|All)/,substr(filter_label,1,1),filter_label)
            if (text_width(tabs)+text_width(filter_sep filter_label)+box_pad+(mode != "" ? length(mode)+1 : 0)>available-2) tabs="Tree"
            tabs=tabs filter_sep filter_label
        } else {
            tabs=(agents_enabled ? "[Tree] Agents Proc Buff" : "[Tree] Proc Buff")
            # Leave room for fzf's right edge and an active operation label.
            if (text_width(tabs)+reserved>available-2) tabs=(agents_enabled ? "[Tree] A P B" : "[Tree] P B")
            if (text_width(tabs)+reserved>available-2) tabs=(agents_enabled ? "[T] A P B" : "[T] P B")
            if (text_width(tabs)+reserved>available-2) sub(/^(Session|Unread|All)/,substr(filter_label,1,1),filter_label)
            if (text_width(tabs)+text_width(filter_sep filter_label)+(mode != "" ? length(mode)+1 : 0)>available-2) tabs="[T]"
            tabs=tabs filter_sep filter_label
        }
        if (appearance != "pills") {
        padding=available-text_width(tabs)-length(mode)-box_pad-(agent_view ? text_width(overview_plain)+1 : 0); if (padding<1) padding=1
        if ((appearance == "lazygit" || appearance == "places") && !agent_view) {
            styled_tabs=tabs
            if (match(styled_tabs, /^(Tree|T|Proc|P|Buff|B|Agents|A)/)) {
                active=substr(styled_tabs, RSTART, RLENGTH)
                rest=substr(styled_tabs, RSTART+RLENGTH)
                styled_tabs=accent active reset dim rest
            } else styled_tabs=dim styled_tabs
            header_text=accent "╭─ " reset styled_tabs reset
        } else {
            styled_tabs=tabs; sub(/\[/,reset accent "[",styled_tabs); sub(/\]/,"]" reset dim,styled_tabs); styled_tabs=dim styled_tabs
            header_text=styled_tabs reset
        }
        row("H:",header_text (agent_view ? " " overview_color : "") (mode != "" ? sprintf("%*s",padding,"") mode_color mode reset : ""),"H:tree")
        }
        if (!agent_view && !footer_hidden) {
            if (agents_enabled) agent_footer()
            else workspace_footer()
        }
        }
    }
    # A separate flat inventory ignores presentation folds without editing state.
    # Every linked occurrence retains its session, including pane targets.
    if (switcher) {
        for (si=1;si<=ns;si++) {
            s=sessions[si]; st="S:" s
            row(st,"Session  " sname[s],st)
            for (wpos=1;wpos<=nw[s];wpos++) {
                w=windows[s,wpos]; key=s SUBSEP w; wt="W:" w ":" s
                context=sname[s] ":" wi[key] ":" wn[key]
                row(wt,"Window   " context (w_zoomed[w] ? " [Z]" : ""),wt)
                for (ppos=1;ppos<=np[w];ppos++) {
                    p=panes[w,ppos]; pt="P:" p
                    row(pt,git_line("Pane     " context "." pi[p] "  " appcolor(command[p]) appicon(command[p]) reset " " command[p] (pane_zoomed[p] ? " [Z]" : "") " " useful_title(p) "  " path[p] (dead[p] == 1 ? " [exited]" : ""),p,0),pt ":" s)
                }
            }
        }
        exit
    }
    if (agent_view && !total_visible) row("V:agents-empty","No supported agent processes detected","V:agents-empty")
    else if (filtered && !total_visible) row("V:empty","No matches · F filters","V:empty")
    for (si=1;si<=ns;si++) {
        s=sessions[si]; st="S:" s
        if (!visible_s[s]) continue
        sm=(st == del ? "✕" : s == current_s && (collapsed[st] || !visible_w[s,current_w]) ? "●" : " ")
        meta=(agent_view ? " [" shown_agents_s[s] " agent" (shown_agents_s[s]==1 ? "" : "s") "]" : filtered ? " [" shown_w[s] "/" nw[s] "w]" : collapsed[st] ? " [" nw[s] "w]" : "")
        if (appearance == "pills") {
            pills_session(s, st)
            continue
        }
        session_glyph=(show_session_glyph ? dim session_icon reset " " : "")
        session_style=(sname[s] ~ /^[0-9]+$/ || sname[s] ~ /^session-[0-9]+$/ ? dim (s == current_s ? bold : "") : (s == current_s ? bold : ""))
        if (appearance == "quiet") {
            # Without guides, sessions are the headings: bold, each followed by a
            # dim rule, behind a glyph in tmux green. The session you are in has
            # a full green glyph and an accent-coloured name, so its heading says
            # where you are even when folded; the others' glyphs are dimmed.
            current_heading=(s == current_s)
            session_glyph=(show_session_glyph ? (current_heading ? bold tmux_green : tmux_green_dim) session_icon reset " " : "")
            session_style=(current_heading ? accent : bold) (sname[s] ~ /^[0-9]+$/ || sname[s] ~ /^session-[0-9]+$/ ? dim : "")
        }
        if (appearance == "quiet") quiet_home_place(s)
        session_body=(collapsed[st] ? fold_closed : fold_open) (sm != " " && sm != "●" ? mark(sm) " " : "") session_glyph session_style sname[s] reset (collapsed[st] ? notice(vsa[s],vsb[s],vsz[s],shown_unread_w[s]) agent_summary(s_need[s],s_work[s],s_done[s]) : "") dim meta reset
        session_mark=(sm == "●" ? green (appearance == "quiet" && icons == "ascii" ? ">" : "▶") reset : "")
        # A session named after its directory gains nothing from the directory
        # alone; a branch still adds something.
        if (appearance == "quiet" && !(place_name(quiet_place[s]) == sname[s] && git_branch[quiet_place_pane[s]] == ""))
            session_mark=quiet_edge(session_body, quiet_place_pane[s], session_mark, width-3)
        row(st,(appearance == "quiet" ? quiet_rule_row(session_body, session_mark, width-3) : edge_colored(session_body, session_mark, width-3)),st)
        if (collapsed[st]) continue
        if (appearance == "places" || appearance == "quiet") { places_panes(s); continue }
        visible_wpos=0
        for (wpos=1;wpos<=nw[s];wpos++) {
            w=windows[s,wpos]; key=s SUBSEP w; wt="W:" w ":" s
            if (!visible_w[key]) continue
            visible_wpos++
            branch=(visible_wpos == shown_w[s] ? branch_end : branch_mid); stem=(visible_wpos == shown_w[s] ? "   " : stem_mid)
            wm=(wt == del ? "✕" : wt == link ? "⇉" : wt == move || w == move_w ? "⇢" : \
                s == current_s && w == current_w && (collapsed[wt] || !visible_p[current_p]) ? "●" : " ")
            meta=(agent_view ? " [" shown_p[w] " agent" (shown_p[w]==1 ? "" : "s") "]" : filtered && collapsed[wt] ? " [" shown_p[w] "/" np[w] "p]" : "")
            collapsed_count=(!agent_view && !filtered && collapsed[wt] && np[w]>1 ? np[w] "p" : "")
            if (links[w]>=2) meta=meta " linked:" links[w]
            if (sync[w]=="on") meta=meta " SYNC"
            if (w_zoomed[w]) meta=meta " [Z]"
            window_glyph=(show_window_glyph ? dim window_icon reset " " : "")
            window_style=(w == current_w && s == current_s ? bold : "")
            if (!agent_view && compact_single && np[w] == 1 && shown_p[w] == 1) {
                p=panes[w,1]; pt="P:" p
                if (pt == del) wm="✕"
                else if (wm == " " && dead[p] == 1) wm="×"
                badge=(pa[p] || pb[p] || pz[p] ? notice(pa[p],pb[p],pz[p]) : notice(vwa[w],vwb[w],vwz[w]))
                # Retain the window identity/actions when switching presentation.
                # Its active content target is necessarily this sole pane.
                compact_path=(density == "minimal" || width<56 ? "" : " " pathlabel(p,w,width-24))
                if (p == current_p && s == current_s && wm == " ") wm="●"
                compact_label=agent_label(p)
                compact_duration=(appearance == "pills" ? pill_word(p) : appearance == "lazygit" ? quiet_mark(compact_label) : compact_label != "" && compact_label != "stale" ? agent_duration_text(p) : "")
                w_name=(unnamed_w[key] ? dim wn[key] reset : wn[key])
                cmd_disp=(unnamed_cmd[p] ? dim command[p] reset : command[p])
                row(wt,edge_colored(git_line(dim branch reset " " (wm != " " ? mark(wm) " " : "") window_glyph window_style (appearance == "pills" || appearance == "lazygit" ? w_name : wi[key] ":" w_name) reset "  " appcolor(command[p]) appicon(command[p]) reset " " cmd_disp agent_badge(p) status_mark(compact_duration) dim meta compact_path reset,p,width-7),pane_edge(unread_glyph(pa[p]||vwa[w], pb[p]||vwb[w], pz[p]||vwz[w]), p == current_p && s == current_s),width-3),wt)
                continue
            }
            grouped=(nul && density == "normal" && width>=56 && shown_p[w]>1 &&
                group_count[first_p[w]] == shown_p[w] && path[first_p[w]] != "" && !collapsed[wt])
            w_name=(unnamed_w[key] ? dim wn[key] reset : wn[key])
            window_text=dim branch reset " " (collapsed[wt] ? fold_closed : fold_open) (wm != " " && wm != "●" ? mark(wm) " " : "") window_glyph window_style (appearance == "pills" || appearance == "lazygit" ? w_name : wi[key] ":" w_name) reset (collapsed[wt] || !shown_unread[w] ? notice(vwa[w],vwb[w],vwz[w],shown_unread[w]) : "") (appearance == "lazygit" ? "" : (collapsed[wt] || !w_agent_shown[w] ? agent_summary(w_need[w],w_work[w],w_done[w]) : "")) dim meta reset
            window_edge=(appearance == "lazygit" && collapsed[wt] ? (w_need[w] > 0 ? "!" : w_work[w] > 0 ? quiet_mark("working") : collapsed_count) : collapsed_count)
            window_text=edge_colored(edge_count(window_text,window_edge,width-3), wm == "●" ? green (appearance == "quiet" && icons == "ascii" ? ">" : "▶") reset : "", width-3)
            if (grouped) {
                continuation=dim stem stem_mid "   "
                window_text=window_text "\n" continuation git_line(pathlabel(panes[w,1],w,width-12),panes[w,1],width-12-text_width(continuation)) reset
            }
            row(wt,window_text,wt)
            if (collapsed[wt]) continue
            visible_ppos=0
            for (ppos=1;ppos<=np[w];ppos++) {
                p=panes[w,ppos]; pt="P:" p
                if (!visible_p[p]) continue
                visible_ppos++
                pm=(pt == del ? "✕" : pt == move ? "⇢" : p == current_p && s == current_s ? "●" : dead[p]==1 ? "×" : " ")
                details=title_detail(p)
                compact_label=agent_label(p)
                duration=(appearance == "pills" ? pill_word(p) : appearance == "lazygit" ? quiet_mark(compact_label) : compact_label != "" && compact_label != "stale" ? agent_duration_text(p) : "")
                display_command=(agent_view ? agent_name(agent_kind[p]) : command[p])
                cmd_disp=(unnamed_cmd[p] ? dim display_command reset : display_command)
                icon=appicon(agent_view ? agent_kind[p] : command[p])
                zoom_badge=(pane_zoomed[p] ? " " dim "[Z]" reset : "")
                if (appearance == "lazygit")
                    prefix=lazy_prefix(stem, visible_ppos == shown_p[w] ? branch_end : branch_mid, pm, appcolor(agent_view ? agent_kind[p] : command[p]), icon)
                else prefix=dim stem (visible_ppos == shown_p[w] ? branch_end : branch_mid) reset " " (pm == "●" ? " " : mark(pm)) " " appcolor(agent_view ? agent_kind[p] : command[p]) icon reset
                show_path=(density == "detailed" || density == "compact" || (density == "normal" && width>=32))
                pane_path=(show_path && !grouped && !(density == "normal" && group_member[p]) ? pathlabel(p,w,width-12-text_width(icon)) : "")
                if (nul && density != "compact") {
                    inline_path=(density == "normal" && width<56 && pane_path != "" ? " " path_color pane_path reset : "")
                    # Prefer the directory line when present; never repeat a
                    # label already attached to the shared window directory.
                    primary_git=(grouped || (show_path && pane_path != "" && (density == "detailed" || width>=56)) ? "" : p)
                    primary=edge_colored(git_line(prefix " " cmd_disp zoom_badge agent_badge(p) status_mark(duration) dim details reset inline_path,primary_git,width-7),pane_edge(unread_glyph(pa[p],pb[p],pz[p]), pm == "●"),width-3)
                    continuation=dim stem (visible_ppos == shown_p[w] ? "   " : stem_mid) reset sprintf("%*s",3+text_width(icon),"")
                    secondary=git_line(continuation path_color pane_path reset,p,width-5)
                    row(pt,primary (show_path && pane_path != "" && (density == "detailed" || width>=56) ? "\n" secondary : "") subagent_lines(p,continuation),pt ":" s)
                } else {
                    # Legacy newline consumers stay one line per object.
                    path_text=(show_path && pane_path != "" ? " " path_color pane_path reset : "")
                    row(pt,edge_colored(git_line(prefix " " cmd_disp zoom_badge agent_badge(p) status_mark(duration) path_text dim details reset,p,width-7),pane_edge(unread_glyph(pa[p],pb[p],pz[p]), pm == "●"),width-3),pt ":" s)
                }
            }
        }
    }
    best_focus = (focus_target ? focus_target : (focus_window_target ? focus_window_target : focus_session_target))
    state_file = ENVIRON["TMUX_CANOPY_STATE"]
    if (state_file != "" && state_file != "/dev/null" && best_focus > 0) {
        pos_file = state_file ".pos"
        print best_focus > pos_file
        close(pos_file)
    }
}
