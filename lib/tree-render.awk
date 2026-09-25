# State is read once; the remaining input is a batched tmux metadata snapshot.
BEGIN { FS="\037"; client=ENVIRON["TMUX_CANOPY_RENDER_CLIENT"]; home=ENVIRON["TMUX_CANOPY_RENDER_HOME"] }
FILENAME == ARGV[1] {
    split($0, state, "\t")
    if (state[1] == "MOVE" && move == "") move=state[2]
    else if (state[1] == "LINK" && link == "") link=state[2]
    else if (state[1] == "DELETE" && now-state[3] <= 5) del=state[2]
    else if (state[1] ~ /^[SW]:/) collapsed[state[1]]=1
    next
}
$1 == "D" {
    icons=($2 == "" ? "unicode" : $2); notices=($3 == "" ? "none" : $3)
    theme=($4 == "" ? "ansi" : $4); density=($5 == "" ? "normal" : $5)
    custom_s=$6; custom_w=$7; custom_p=$8
    current_p=$9; current_w=$10; current_s=$11; width=$12; host=$13
}
$1 == "C" && $2 == client { current_s=$3; current_w=$4; current_p=$5 }
$1 == "S" { sessions[++ns]=$2; sname[$2]=$3; attached[$2]=$4 }
$1 == "W" {
    s=$2; w=$3; key=s SUBSEP w
    if (seen_w[key]++) next
    windows[s,++nw[s]]=w; wi[key]=$4; wn[key]=$5; links[w]=$6; sync[w]=$7
    wa[w]=$8+0; wb[w]=$9+0; wz[w]=$10+0
    sa[s]+=wa[w]; sb[s]+=wb[w]; sz[s]+=wz[w]
}
$1 == "P" {
    p=$2; if (seen_p[p]++) next
    pw[p]=$3; pi[p]=$4; command[p]=$5; title[p]=$6; path[p]=$7; dead[p]=$8
    sidebar[p]=$9; slot[p]=$10; pa[p]=$11+0; pb[p]=$12+0; pz[p]=$13+0; target[p]=$14; target_session[p]=$15
    if (sidebar[p] != 1 && slot[p] != 1) {
        panes[$3,++np[$3]]=p
        if (np[$3] == 1) shared_path[$3]=path[p]
        else if (shared_path[$3] != path[p]) shared_path[$3]=""
        if ($16 == 1) last_content[$3]=p
    }
}
function row(token, value, identity, terminator) {
    terminator=(nul ? sprintf("%c",0) : "\n")
    if (stable) printf "%s\t%s\t%s%s", token, value, identity, terminator
    else printf "%s\t%s%s", token, value, terminator
}
function mark(value, color) {
    color=(value == "●" ? green : value == "⇢" || value == "⇉" ? accent : attention)
    return value == " " ? value : color value reset
}
function notice(a,b,z, value) {
    if (notices == "none") return ""
    value=""
    if (a>0) value=value " !" a
    if (b>0) value=value " B" b
    if (z>0) value=value " …" z
    return value == "" ? "" : attention " [" substr(value,2) "]" reset
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
    if (value ~ /^(nvim|vim|vi)$/) return icon_blue
    if (value ~ /^(node|python|python3)$/) return icon_yellow
    if (value ~ /^(npm|npx|git|lazygit|oc)$/) return icon_red
    if (value ~ /^(kubectl|k9s)$/) return icon_blue
    if (value ~ /^(ssh|codex|top|htop|btop)$/) return icon_cyan
    if (value ~ /^(pi|opencode)$/) return icon_purple
    if (value == "claude") return icon_yellow
    return icon_neutral
}
function appicon(value, n, parts) {
    if (icons != "nerdfont") return pane_icon
    n=split(value,parts,"/"); value=parts[n]
    if (value == "nvim") return ""
    if (value ~ /^(vim|vi)$/) return ""
    if (value ~ /^(bash|zsh|fish|sh)$/) return ""
    if (value ~ /^(node|npm|npx)$/) return ""
    if (value ~ /^(python|python3)$/) return ""
    if (value ~ /^(git|lazygit)$/) return "󰊢"
    if (value == "ssh") return "󰢹"
    if (value ~ /^(kubectl|oc|k9s)$/) return "󱃾"
    if (value ~ /^(claude|codex|pi|opencode)$/) return "󰚩"
    if (value ~ /^(top|htop|btop)$/) return "󰍛"
    return pane_icon
}
END {
    if (ns == 0) exit
    if (theme != "mono") {
        reset="\033[0m"; bold="\033[1m"; dim="\033[2m"
        # Neutral text and guides, with distinct application and active-location colors.
        icon_blue="\033[94m"; icon_yellow="\033[93m"; icon_red="\033[91m"
        icon_cyan="\033[96m"; icon_purple="\033[95m"; icon_neutral="\033[39m"
        green="\033[1;32m"
        accent="\033[1;36m"; attention="\033[1;33m"; path_color=dim
    }
    session_icon=(icons == "nerdfont" ? "󰆍" : icons == "ascii" ? "S" : "◈")
    window_icon=(icons == "nerdfont" ? "󰖯" : icons == "ascii" ? "W" : "▣")
    pane_icon=(icons == "nerdfont" ? "" : icons == "ascii" ? ">" : "▹")
    if (custom_s != "") session_icon=custom_s
    if (custom_w != "") window_icon=custom_w
    if (custom_p != "") pane_icon=custom_p
    branch_mid=(icons == "ascii" ? "|-" : "├─"); branch_end=(icons == "ascii" ? "`-" : "└─")
    stem_mid=(icons == "ascii" ? "|  " : "│  ")
    if (sidebar[current_p] == 1) {
        last=last_content[pw[current_p]]
        if (last != "") { current_p=last; current_w=pw[last] }
        else if (target[current_p] != "" && pw[target[current_p]] != "" && sidebar[target[current_p]] != 1 && slot[target[current_p]] != 1) {
            if (target_session[current_p] != "") current_s=target_session[current_p]
            current_p=target[current_p]; current_w=pw[current_p]
        }
    }
    move_p=substr(move,3); move_w=(move ~ /^P:/ ? pw[move_p] : "")
    if (header) {
        mode=(move != "" ? "MOVE" : link != "" ? "LINK" : del != "" ? "DELETE" : "")
        mode_color=(del != "" && move == "" && link == "" ? attention : accent)
        # Reserve fzf's pointer gutter and keep operation warnings visible.
        available=width-2; reserved=(mode != "" ? length(mode)+1 : 0)
        tabs="[1 Tree]  2 Proc  3 Buff"
        if (length(tabs)+reserved>available) tabs="[1 T]  2 P  3 B"
        padding=available-length(tabs)-length(mode); if (padding<1) padding=1
        styled_tabs=tabs; sub(/\]/,"]" reset dim,styled_tabs)
        row("H:",accent styled_tabs reset (mode != "" ? sprintf("%*s",padding,"") mode_color mode reset : ""),"H:tree")
    }
    for (si=1;si<=ns;si++) {
        s=sessions[si]; st="S:" s
        sm=(st == del ? "✕" : s == current_s ? "●" : " ")
        meta=nw[s] "w"; if (attached[s]>0) meta=meta " · " attached[s] "c"
        row(st,(collapsed[st] ? "▸" : "▾") " " mark(sm) " " dim session_icon reset bold " " sname[s] " " dim "[" meta "]" reset notice(sa[s],sb[s],sz[s]),st)
        if (collapsed[st]) continue
        for (wpos=1;wpos<=nw[s];wpos++) {
            w=windows[s,wpos]; key=s SUBSEP w; wt="W:" w ":" s
            branch=(wpos == nw[s] ? branch_end : branch_mid); stem=(wpos == nw[s] ? "   " : stem_mid)
            wm=(wt == del ? "✕" : wt == link ? "⇉" : wt == move || w == move_w ? "⇢" : w == current_w && s == current_s ? "●" : notices != "none" && (wa[w] || wb[w] || wz[w]) ? "!" : " ")
            meta=(np[w]>1 ? " " np[w] "p" : "")
            if (links[w]>=2) meta=meta " linked:" links[w]
            if (sync[w]=="on") meta=meta " SYNC"
            grouped=(nul && density == "normal" && np[w]>1 && shared_path[w] != "" && !collapsed[wt])
            window_text=dim branch reset " " mark(wm) " " dim window_icon reset " " (collapsed[wt] ? "▸" : "▾") " " wi[key] ":" wn[key] dim meta reset notice(wa[w],wb[w],wz[w])
            if (grouped) {
                continuation=dim stem stem_mid sprintf("%*s",3+length(window_icon),"")
                window_text=window_text "\n" continuation shortpath(shared_path[w],width-12-length(window_icon)) reset
            }
            row(wt,window_text,wt)
            if (collapsed[wt]) continue
            for (ppos=1;ppos<=np[w];ppos++) {
                p=panes[w,ppos]; pt="P:" p
                pm=(pt == del ? "✕" : pt == move ? "⇢" : p == current_p && s == current_s ? "●" : dead[p]==1 ? "×" : " ")
                details=""
                if (density != "compact") {
                    useful=useful_title(p)
                    if (density == "detailed") details=" " pi[p] " " useful
                    else if (useful != "") details=" " useful
                }
                icon=appicon(command[p])
                prefix=dim stem (ppos == np[w] ? branch_end : branch_mid) reset " " mark(pm) " " appcolor(command[p]) icon reset
                if (nul && density != "compact") {
                    # Grouped panes use one line; other panes use two. Both
                    # retain one action token and occurrence-aware identity.
                    primary=prefix " " command[p] notice(pa[p],pb[p],pz[p]) dim details reset
                    continuation=dim stem (ppos == np[w] ? "   " : stem_mid) reset sprintf("%*s",3+length(icon),"")
                    secondary=continuation path_color (path[p] != "" ? shortpath(path[p],width-12-length(icon)) : "(directory unavailable)") reset
                    row(pt,primary (grouped ? "" : "\n" secondary),pt ":" s)
                } else {
                    # Compact mode and legacy newline consumers stay one-line.
                    row(pt,prefix sprintf(" %-8s ",command[p]) path_color shortpath(path[p]) reset dim details reset notice(pa[p],pb[p],pz[p]),pt ":" s)
                }
            }
        }
    }
}
