# Scale a saved native layout while preserving pane order and split topology.
# Input: saved layout, then the current layout. Refuse a changed pane inventory.
#
# Two input formats. tmux 3.7c and older emit the checksummed v1 string
# ("abcd,80x24,0,0{...}"); tmux 3.8 emits v2 JSON ({"V":2,"L":{...}}) from
# #{window_layout} and offers no way to ask for v1 outside control mode. Both
# are read here, and both carry the same pane identity: v1's trailing leaf
# number and v2's "I" are each the pane id (layout-custom.c writes wp->id for
# both). Output stays v1, which tmux 3.8 still accepts on select-layout.
BEGIN { for (i=0;i<128;i++) ord[sprintf("%c",i)]=i }
function number(    value) {
    if (!match(substr(text,pos),/^[0-9]+/)) { bad=1; return 0 }
    value=substr(text,pos,RLENGTH)+0; pos+=RLENGTH; return value
}
function take(character) {
    if (substr(text,pos++,1)!=character) bad=1
}
function parse(    n,c,k) {
    n=++nodes
    w[n]=number(); take("x"); h[n]=number(); take(",")
    if (w[n]<1 || h[n]<1) bad=1
    number(); take(","); number()
    c=substr(text,pos++,1)
    if (c==",") {
        id[n]=number(); leaves=leaves id[n] "|"; mw[n]=2; mh[n]=1
    } else if (c=="{" || c=="[") {
        axis[n]=c
        do {
            k=++count[n]; child[n,k]=parse()
            if (bad) return n
            c=substr(text,pos++,1)
        } while (c==",")
        if (c!=(axis[n]=="{" ? "}" : "]")) bad=1
        for (k=1;k<=count[n];k++) {
            c=child[n,k]
            if (axis[n]=="{") {
                mw[n]+=mw[c]+(k>1); if (mh[c]>mh[n]) mh[n]=mh[c]
            } else {
                mh[n]+=mh[c]+(k>1); if (mw[c]>mw[n]) mw[n]=mw[c]
            }
        }
    } else bad=1
    return n
}
# --- v2 JSON ---------------------------------------------------------------
# tmux generates this itself, so only what layout_append_v2 can write is
# accepted: no escapes inside strings and no nested structures beyond "c".
function json_skip() {
    while (substr(text,pos,1) ~ /^[ \t\r\n]$/) pos++
}
function json_take(literal,    n) {
    json_skip(); n=length(literal)
    if (substr(text,pos,n)!=literal) { bad=1; return 0 }
    pos+=n; return 1
}
# x and y are written with %d, so a negative offset must still be consumed.
function json_number(    value) {
    json_skip()
    if (!match(substr(text,pos),/^-?[0-9]+/)) { bad=1; return 0 }
    value=substr(text,pos,RLENGTH)+0; pos+=RLENGTH; return value
}
function json_string(    start,value) {
    json_skip()
    if (substr(text,pos,1)!="\"") { bad=1; return "" }
    pos++; start=pos
    while (pos<=length(text) && substr(text,pos,1)!="\"") pos++
    if (pos>length(text)) { bad=1; return "" }
    value=substr(text,start,pos-start); pos++
    return value
}
# Consume a key this script does not use ("a", "i", "l", "x", "y").
function json_discard(    c) {
    json_skip(); c=substr(text,pos,1)
    if (c=="\"") { json_string(); return }
    if (c=="t") { json_take("true"); return }
    if (c=="f") { json_take("false"); return }
    if (c=="n") { json_take("null"); return }
    if (c ~ /^[-0-9]$/) { json_number(); return }
    bad=1
}
function parse_json(    n,key,type,k,c) {
    n=++nodes
    if (!json_take("{")) return n
    for (;;) {
        key=json_string(); if (bad) return n
        if (!json_take(":")) return n
        if (key=="t") type=json_string()
        else if (key=="w") w[n]=json_number()
        else if (key=="h") h[n]=json_number()
        else if (key=="I") id[n]=substr(json_string(),2)+0
        else if (key=="z") { json_number(); floating=1 }
        else if (key=="c") {
            if (!json_take("[")) return n
            for (;;) {
                k=++count[n]; child[n,k]=parse_json()
                if (bad) return n
                json_skip(); c=substr(text,pos++,1)
                if (c=="]") break
                if (c!=",") { bad=1; return n }
            }
        } else json_discard()
        if (bad) return n
        json_skip(); c=substr(text,pos++,1)
        if (c=="}") break
        if (c!=",") { bad=1; return n }
    }
    if (w[n]<1 || h[n]<1) bad=1
    if (type=="p") {
        if (count[n] || id[n]=="") { bad=1; return n }
        leaves=leaves id[n] "|"; mw[n]=2; mh[n]=1
    } else if (type=="h" || type=="v") {
        if (!count[n]) { bad=1; return n }
        axis[n]=(type=="h" ? "{" : "[")
        for (k=1;k<=count[n];k++) {
            c=child[n,k]
            if (axis[n]=="{") {
                mw[n]+=mw[c]+(k>1); if (mh[c]>mh[n]) mh[n]=mh[c]
            } else {
                mh[n]+=mh[c]+(k>1); if (mw[c]>mw[n]) mw[n]=mw[c]
            }
        }
    } else bad=1
    return n
}
# {"V":2,"L":{cell}} - read in whatever order the keys arrive.
function parse_json_document(    root,key,c) {
    if (!json_take("{")) return 0
    for (;;) {
        key=json_string(); if (bad) return 0
        if (!json_take(":")) return 0
        if (key=="L") root=parse_json()
        else json_discard()
        if (bad) return 0
        json_skip(); c=substr(text,pos++,1)
        if (c=="}") break
        if (c!=",") { bad=1; return 0 }
    }
    if (!root) bad=1
    return root
}
function read_layout(value,    root) {
    pos=1; leaves=""; text=value
    if (substr(value,1,1)=="{") {
        root=parse_json_document()
    } else if (value ~ /^[0-9a-f]+,[0-9x,{}\[\]]+$/) {
        text=substr(value,index(value,",")+1)
        root=parse()
    } else { bad=1; return 0 }
    if (pos!=length(text)+1) bad=1
    return root
}
function emit(n,width,height,x,y,    out,k,c,horizontal,available,weight,reserve,size,minsize,oldsize) {
    if (width<mw[n] || height<mh[n]) { bad=1; return "" }
    out=width "x" height "," x "," y
    if (!count[n]) return out "," id[n]
    horizontal=(axis[n]=="{")
    available=(horizontal ? width : height)-count[n]+1
    weight=0; reserve=0
    for (k=1;k<=count[n];k++) {
        c=child[n,k]
        if (c==dock_node) { available-=dock_width; continue }
        weight+=(horizontal ? w[c] : h[c]); reserve+=(horizontal ? mw[c] : mh[c])
    }
    out=out axis[n]
    for (k=1;k<=count[n];k++) {
        c=child[n,k]; minsize=(horizontal ? mw[c] : mh[c]); oldsize=(horizontal ? w[c] : h[c])
        if (c==dock_node) {
            size=dock_width
        } else {
            reserve-=minsize
            size=int(available*oldsize/weight)
            if (size<minsize) size=minsize
            if (size>available-reserve) size=available-reserve
            available-=size; weight-=oldsize
        }
        out=out (k>1 ? "," : "") emit(c,horizontal ? size : width,horizontal ? height : size,x,y)
        if (horizontal) x+=size+1; else y+=size+1
    }
    return out (horizontal ? "}" : "]")
}
NR==1 { original=read_layout($0); original_ids=leaves }
NR==2 { current=read_layout($0); current_ids=leaves }
END {
    if (NR!=2 || bad || original_ids!=current_ids) exit 1
    # v1 cannot express a floating pane, and tmux drops floaters when it dumps
    # v1 itself, so scaling would silently retile one. Leave the window alone.
    if (floating) exit 1
    # Nothing to scale when the window kept its size. The caller used to decide
    # this by slicing the layout string, which only worked for v1.
    if (w[original]==w[current] && h[original]==h[current]) exit 1
    if (dock!="") {
        # Full-height edge docks keep their chosen width; distribute the rest
        # among content branches using their saved proportions.
        for (i=1;i<=count[original];i++) {
            n=child[original,i]
            if (!count[n] && id[n]==substr(dock,2)) {
                if (axis[original]!="{" || (i!=1 && i!=count[original]) || dock_width<2) exit 1
                dock_node=n; mw[original]+=dock_width-mw[n]; mw[n]=dock_width
            }
        }
        if (!dock_node) exit 1
    }
    value=emit(original,w[current],h[current],0,0)
    if (bad) exit 1
    checksum=0
    for (i=1;i<=length(value);i++) checksum=(int(checksum/2)+(checksum%2)*32768+ord[substr(value,i,1)])%65536
    printf "%04x,%s\n",checksum,value
}
