# State is read once; the remaining input is a batched tmux metadata snapshot.
BEGIN { FS="\037"; client=ENVIRON["TMUX_CANOPY_RENDER_CLIENT"]; home=ENVIRON["TMUX_CANOPY_RENDER_HOME"] }
FILENAME == ARGV[1] {
    split($0, state, "\t")
    if (state[1] == "MOVE" && move == "") move=state[2]
    else if (state[1] == "LINK" && link == "") link=state[2]
    else if (state[1] == "DELETE" && now-state[3] <= 5) del=state[2]
    else if (state[1] == "FILTER") { filter_set=1; filter=state[2] }
    else if (state[1] == "FILTER_WINDOW") { window_set=1; window_filter=state[2] }
    else if (state[1] == "FILTER_TITLE") { title_set=1; title_filter=state[2] }
    else if (state[1] ~ /^[SW]:/) collapsed[state[1]]=1
    next
}
$1 == "D" {
    icons=($2 == "" ? "unicode" : $2); notices=($3 == "" ? "none" : $3)
    theme=($4 == "" ? "ansi" : $4); density=($5 == "" ? "normal" : $5)
    custom_s=$6; custom_w=$7; custom_p=$8
    nicons=split("nvim vim shell node python git ssh kubectl claude codex gemini pi omp opencode antigravity make top",icon_keys," ")
    for (i=1;i<=nicons;i++) icon_override[icon_keys[i]]=$(17+i)
    appearance=($35 == "lazygit" ? "lazygit" : "classic")
    agents_enabled=($36 == "on")
    if (!agents_enabled) agent_view=0
    current_p=$9; current_w=$10; current_s=$11; width=$12; host=$13; compact_single=($14 == "on" || density == "minimal")
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
    wa[w]=$8+0; wb[w]=$9+0; wz[w]=$10+0
    sa[s]+=wa[w]; sb[s]+=wb[w]; sz[s]+=wz[w]
    if (wa[w] || wb[w] || wz[w]) unread_windows[s]++
}
$1 == "P" {
    p=$2; if (seen_p[p]++) next
    pw[p]=$3; pi[p]=$4; command[p]=$5; title[p]=$6; path[p]=$7; dead[p]=$8
    sidebar[p]=$9; slot[p]=$10; pa[p]=$11+0; pb[p]=$12+0; pz[p]=$13+0; target[p]=$14; target_session[p]=$15
    pane_pid[p]=$17; report_source[p]=$18; report_session[p]=$19; report_pid[p]=$20; report_status[p]=$21; report_updated[p]=$22
    subagent_list[p]=$25
    if (sidebar[p] != 1 && slot[p] != 1) {
        panes[$3,++np[$3]]=p
        if (pa[p] || pb[p] || pz[p]) unread_panes[$3]++
        if (np[$3] == 1) shared_path[$3]=path[p]
        else if (shared_path[$3] != path[p]) shared_path[$3]=""
        if ($16 == 1) last_content[$3]=p
    }
}
$1 == "A" { agent_kind[$2]=$3 }
$1 == "V" { verified[$2]=1 }
agent_view && $0 ~ /^[[:space:]]*[0-9]+[[:space:]]+[0-9]+[[:space:]]+/ {
    process_line=$0; sub(/^[[:space:]]+/,"",process_line)
    split(process_line,process_field,/[[:space:]]+/)
    pid=process_field[1]; parent[pid]=process_field[2]
    name=process_field[3]; sub(/^.*\//,"",name); sub(/\.exe$/,"",name)
    if (name=="codex" || name=="opencode" || name=="gemini" || name=="pi" || name=="omp" || name=="agy") agent_process[pid]=name
    else if (name=="claude" || name=="claude-code") agent_process[pid]="claude"
    next
}
function find_agents( pid,current,depth,p,root) {
    for (p in pane_pid) {
        root=pane_pid[p]
        if (sidebar[p]!=1 && slot[p]!=1 && root ~ /^[1-9][0-9]*$/) owner[root]=p
    }
    for (pid in agent_process) {
        current=pid
        for (depth=0;depth<128 && current>0;depth++) {
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
function prepare_filter( si,s,wpos,w,key,ppos,p,keep,alert,first,label) {
    if (filter != "session" && filter != "unread") filter="all"
    filtered=(!switcher && (agent_view || filter != "all" || window_filter != "" || title_filter != ""))
    for (si=1;si<=ns;si++) {
        s=sessions[si]
        for (wpos=1;wpos<=nw[s];wpos++) {
            w=windows[s,wpos]; key=s SUBSEP w
            if (!agent_view && filtered && filter == "session" && s != filter_session) continue
            if (!agent_view && filtered && window_filter != "" && !index(tolower(wn[key]),tolower(window_filter))) continue
            first=""
            if (!(w in counted)) {
                counted[w]=1
                for (ppos=1;ppos<=np[w];ppos++) {
                    p=panes[w,ppos]
                    keep=(agent_view ? agent_kind[p] != "" : !filtered ||
                        ((title_filter == "" || index(tolower(title[p]),tolower(title_filter))) &&
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
# Keep an ordinary collapsed count at the edge, leaving a spare cell for fzf's
# gutter/scrollbar and wide terminal glyphs. Skip it if the name needs the room.
# Display columns, not bytes: macOS awk's length() counts UTF-8 bytes, but its
# regex engine (like gawk's) matches whole characters.
function text_width(value) { return gsub(/./,"",value) }
function edge_count(value,count,budget, plain,padding) {
    if (count == "") return value
    plain=value
    gsub(/\033\[[0-9;]*m/,"",plain)
    padding=budget-text_width(plain)-length(count)
    if (padding<2) return value
    return value sprintf("%*s",padding,"") dim count reset
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
# this live pane. Expired reports say unknown; unsupported agents show no state.
function agent_label(p, age,status,kind) {
    if (!agents_enabled) return ""
    if (p in agent_labels) return agent_labels[p]
    agent_labels[p]=""
    kind=(agent_view ? agent_kind[p] : canonical_agent(command[p]))
    if (dead[p] == 1 || kind == "" || report_source[p] != kind "-hook" ||
        report_session[p] == "" || pane_pid[p] == "" || report_pid[p] != pane_pid[p] ||
        report_updated[p] !~ /^[0-9]+$/ || length(report_updated[p])>12 || !verified[p]) return ""
    age=now-report_updated[p]
    if (age<0 || age>900) return agent_labels[p]="unknown"
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
    if (value == "codex" || value == "claude" || value == "opencode" || value == "gemini" || value == "pi" || value == "omp" || value == "agy") return value
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
function subagent_lines(p, continuation, n,i,state,style,text,lines,elapsed) {
    if (!agents_enabled) return ""
    n=load_subagents(p)
    lines=""
    for (i=1;i<=n;i++) {
        state=sub_state[p,i]
        style=(state == "working" ? bold accent : state == "needs-input" ? bold attention : dim)
        elapsed=sub_age[p,i]
        elapsed=(elapsed<0 ? "" : elapsed<60 ? "<1m" : elapsed<3600 ? int(elapsed/60) "m" : int(elapsed/3600) "h")
        text=continuation dim (i == n ? branch_end : branch_mid) reset " " sub_type[p,i] " " style subagent_word(state,width<36) reset
        lines=lines "\n" edge_count(text,elapsed,width-3)
    }
    return lines
}
# The status word itself carries the color (no bracket tag): bold for the two
# actionable tiers (needs-input, working), plain dim for unknown so
# it recedes instead of competing for attention. Origin stays a small dim
# suffix since ·plugin? still meaningfully flags an unconfirmed association.
function agent_badge(p, label,style,origin,word) {
    if (!agents_enabled) return ""
    label=agent_label(p)
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
function pathlabel(p,w,budget,    value,parts,n,depth,candidate,q,other,matches,need,otherparts,othern) {
    value=path[p]
    if (value == "") return "(directory unavailable)"
    if (density == "detailed" || density == "compact") return shortpath(value,budget)
    if (value == home) return "~"
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
    need=(depth<n ? "…/" : "") candidate
    if (budget>0 && length(need)>budget && depth>1) return "…/" parts[n]
    return need
}
function title_detail(p,    value,limit,label) {
    if (density == "compact" || width<38) return ""
    value=useful_title(p)
    if (density == "detailed") return " " pi[p] (value != "" ? " " value : "")
    if (value == "") return ""
    limit=width-25-length(command[p])
    label=agent_label(p)
    if (label!="") limit-=length(agent_status_word(label,width<36))+3
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
function appcolor(value, n, parts) {
    if (theme == "mono") return ""
    n=split(value,parts,"/"); value=parts[n]
    sub(/\.exe$/,"",value)
    if (value ~ /^(nvim|vim|vi)$/) return icon_blue
    if (value ~ /^(node|python|python3)$/) return icon_yellow
    if (value ~ /^(npm|npx|git|lazygit|oc|hunk)$/) return icon_red
    if (value ~ /^(kubectl|k9s)$/) return icon_blue
    if (value ~ /^(ssh|codex|top|htop|btop|agy)$/) return icon_cyan
    if (value ~ /^(pi|omp|opencode)$/) return icon_purple
    if (value ~ /^(claude|claude-code)$/) return icon_yellow
    if (value == "gemini") return icon_white
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
    if (value ~ /^(agy|antigravity)$/) return "antigravity"
    if (value ~ /^(make|cmake|ninja)$/) return "make"
    if (value ~ /^(top|htop|btop)$/) return "top"
    return ""
}
function appicon(value, n, parts,key,override) {
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
        if (value ~ /^(claude|claude-code)$/) return "✦"
        if (value == "codex") return "◈"
        if (value == "gemini") return "✧"
        if (value ~ /^(pi|omp|opencode)$/) return "◎"
        if (value ~ /^(agy|antigravity)$/) return "○"
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
    if (value ~ /^(claude|claude-code)$/) return "◇"
    if (value == "codex") return "◈"
    if (value == "gemini") return "󰊭"
    if (value ~ /^(pi|omp|opencode)$/) return "󰚩"
    if (value ~ /^(agy|antigravity)$/) return "󰀘"
    if (value ~ /^(make|cmake|ninja)$/) return ""
    if (value ~ /^(top|htop|btop)$/) return "󰍛"
    return custom_p != "" ? pane_icon : " "
}
END {
    if (ns == 0) exit
    if (agent_view) find_agents()
    if (theme != "mono") {
        reset="\033[0m"; bold="\033[1m"; dim="\033[2m"
        # Neutral text and guides, with distinct application and active-location colors.
        icon_blue="\033[94m"; icon_yellow="\033[93m"; icon_red="\033[91m"
        icon_cyan="\033[96m"; icon_purple="\033[95m"; icon_neutral="\033[39m"
        icon_white="\033[97m"
        green="\033[1;32m"
        accent="\033[1;36m"; attention="\033[1;33m"; path_color=dim
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
    if (appearance == "lazygit" && icons != "ascii") {
        branch_mid="├─"; branch_end="╰─"; stem_mid="│  "
        fold_open="▼ "; fold_closed="▶ "
    } else if (appearance == "lazygit") {
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
    show_session_glyph=(appearance == "lazygit" || custom_s != "")
    show_window_glyph=(appearance == "lazygit" || custom_w != "")
    filter_session=current_s
    if (sidebar[current_p] == 1) {
        last=last_content[pw[current_p]]
        if (last != "") { current_p=last; current_w=pw[last] }
        else if (target[current_p] != "" && pw[target[current_p]] != "" && sidebar[target[current_p]] != 1 && slot[target[current_p]] != 1) {
            if (target_session[current_p] != "") current_s=target_session[current_p]
            current_p=target[current_p]; current_w=pw[current_p]
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
        filter_sep=(icons == "ascii" ? " | " : appearance == "lazygit" ? " ─ " : " · ")
        if (window_filter != "") filter_label=filter_label "+W"
        if (title_filter != "") filter_label=filter_label "+T"
        reserved=text_width(filter_sep filter_label)+(mode != "" ? length(mode)+1 : 0)
        box_pad=(appearance == "lazygit" ? 3 : 0)
        if (agent_view) {
            agent_overview()
            tabs="Tree Proc Buff [Agents]"
            if (text_width(tabs)+text_width(overview_plain)+length(mode)+mode_gap+1+box_pad>available-2) {
                overview_plain=overview_short_plain; overview_color=overview_short_color
            }
            if (text_width(tabs)+text_width(overview_plain)+length(mode)+mode_gap+1+box_pad>available-2) tabs="T P B [Agents]"
            if (text_width(tabs)+text_width(overview_plain)+length(mode)+mode_gap+1+box_pad>available-2) tabs="T P B [A]"
            if (text_width(tabs)+text_width(overview_plain)+length(mode)+mode_gap+1+box_pad>available-2) tabs="[A]"
        } else if (appearance == "lazygit") {
            tabs=(agents_enabled ? "Tree Proc Buff Agents" : "Tree Proc Buff")
            if (text_width(tabs)+reserved+box_pad>available-2) tabs=(agents_enabled ? "Tree P B A" : "Tree P B")
            if (text_width(tabs)+reserved+box_pad>available-2) tabs=(agents_enabled ? "T P B A" : "T P B")
            if (text_width(tabs)+reserved+box_pad>available-2) sub(/^(Session|Unread|All)/,substr(filter_label,1,1),filter_label)
            if (text_width(tabs)+text_width(filter_sep filter_label)+box_pad+(mode != "" ? length(mode)+1 : 0)>available-2) tabs="Tree"
            tabs=tabs filter_sep filter_label
        } else {
            tabs=(agents_enabled ? "[Tree] Proc Buff Agents" : "[Tree] Proc Buff")
            # Leave room for fzf's right edge and an active operation label.
            if (text_width(tabs)+reserved>available-2) tabs=(agents_enabled ? "[Tree] P B A" : "[Tree] P B")
            if (text_width(tabs)+reserved>available-2) tabs=(agents_enabled ? "[T] P B A" : "[T] P B")
            if (text_width(tabs)+reserved>available-2) sub(/^(Session|Unread|All)/,substr(filter_label,1,1),filter_label)
            if (text_width(tabs)+text_width(filter_sep filter_label)+(mode != "" ? length(mode)+1 : 0)>available-2) tabs="[T]"
            tabs=tabs filter_sep filter_label
        }
        padding=available-text_width(tabs)-length(mode)-box_pad-(agent_view ? text_width(overview_plain)+1 : 0); if (padding<1) padding=1
        if (appearance == "lazygit" && !agent_view) {
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
    # A separate flat inventory ignores presentation folds without editing state.
    # Every linked occurrence retains its session, including pane targets.
    if (switcher) {
        for (si=1;si<=ns;si++) {
            s=sessions[si]; st="S:" s
            row(st,"Session  " sname[s],st)
            for (wpos=1;wpos<=nw[s];wpos++) {
                w=windows[s,wpos]; key=s SUBSEP w; wt="W:" w ":" s
                context=sname[s] ":" wi[key] ":" wn[key]
                row(wt,"Window   " context,wt)
                for (ppos=1;ppos<=np[w];ppos++) {
                    p=panes[w,ppos]; pt="P:" p
                    row(pt,"Pane     " context "." pi[p] "  " appcolor(command[p]) appicon(command[p]) reset " " command[p] " " useful_title(p) "  " path[p] (dead[p] == 1 ? " [exited]" : ""),pt ":" s)
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
        session_glyph=(show_session_glyph ? dim session_icon reset " " : "")
        session_style=(s == current_s ? bold : "")
        row(st,(collapsed[st] ? fold_closed : fold_open) (sm != " " ? mark(sm) " " : "") session_glyph session_style sname[s] reset (collapsed[st] ? notice(vsa[s],vsb[s],vsz[s],shown_unread_w[s]) agent_summary(s_need[s],s_work[s],s_done[s]) : "") dim meta reset,st)
        if (collapsed[st]) continue
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
                compact_duration=(agent_label(p) != "" ? agent_duration_text(p) : "")
                row(wt,edge_count(dim branch reset " " (wm != " " ? mark(wm) " " : "") window_glyph window_style wi[key] ":" wn[key] reset "  " appcolor(command[p]) appicon(command[p]) reset " " command[p] agent_badge(p) badge dim meta compact_path reset,compact_duration,width-3),wt)
                continue
            }
            grouped=(nul && density == "normal" && width>=56 && shown_p[w]>1 &&
                group_count[first_p[w]] == shown_p[w] && path[first_p[w]] != "" && !collapsed[wt])
            window_text=dim branch reset " " (collapsed[wt] ? fold_closed : fold_open) (wm != " " ? mark(wm) " " : "") window_glyph window_style wi[key] ":" wn[key] reset (collapsed[wt] || !shown_unread[w] ? notice(vwa[w],vwb[w],vwz[w],shown_unread[w]) : "") (collapsed[wt] || !w_agent_shown[w] ? agent_summary(w_need[w],w_work[w],w_done[w]) : "") dim meta reset
            window_text=edge_count(window_text,collapsed_count,width-3)
            if (grouped) {
                continuation=dim stem stem_mid "   "
                window_text=window_text "\n" continuation pathlabel(panes[w,1],w,width-12) reset
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
                duration=(agent_label(p) != "" ? agent_duration_text(p) : "")
                display_command=(agent_view ? agent_name(agent_kind[p]) : command[p])
                icon=appicon(agent_view ? agent_kind[p] : command[p])
                prefix=dim stem (visible_ppos == shown_p[w] ? branch_end : branch_mid) reset " " mark(pm) " " appcolor(agent_view ? agent_kind[p] : command[p]) icon reset
                show_path=(density == "detailed" || density == "compact" || (density == "normal" && width>=32))
                pane_path=(show_path && !grouped && !(density == "normal" && group_member[p]) ? pathlabel(p,w,width-12-text_width(icon)) : "")
                if (nul && density != "compact") {
                    inline_path=(density == "normal" && width<56 && pane_path != "" ? " " path_color pane_path reset : "")
                    primary=edge_count(prefix " " display_command agent_badge(p) notice(pa[p],pb[p],pz[p]) dim details reset inline_path,duration,width-3)
                    continuation=dim stem (visible_ppos == shown_p[w] ? "   " : stem_mid) reset sprintf("%*s",3+text_width(icon),"")
                    secondary=continuation path_color pane_path reset
                    row(pt,primary (show_path && pane_path != "" && (density == "detailed" || width>=56) ? "\n" secondary : "") subagent_lines(p,continuation),pt ":" s)
                } else {
                    # Legacy newline consumers stay one line per object.
                    path_text=(show_path && pane_path != "" ? " " path_color pane_path reset : "")
                    row(pt,edge_count(prefix " " display_command agent_badge(p) notice(pa[p],pb[p],pz[p]) path_text dim details reset,duration,width-3),pt ":" s)
                }
            }
        }
    }
}
