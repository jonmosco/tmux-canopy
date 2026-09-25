# Scale a saved native layout while preserving pane order and split topology.
# Input: saved layout, then the current layout. Refuse a changed pane inventory.
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
function read_layout(value,    root) {
    if (value !~ /^[0-9a-f]+,[0-9x,{}\[\]]+$/) { bad=1; return 0 }
    text=substr(value,index(value,",")+1); pos=1; leaves=""
    root=parse()
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
