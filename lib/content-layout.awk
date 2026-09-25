# Emit one native tmux layout with a fixed full-height dock on the left.
# No temporary windows/panes: the server applies the finished layout once.
BEGIN { FS="|"; for (i=0;i<128;i++) ord[sprintf("%c",i)]=i }
$1 == "M" { width=$2+0; height=$3+0; main_w=$4; main_h=$5 }
$1 == "P" {
    if (first_pane == "") first_pane=$2
    if ($3 == 1 || $4 == 1) { dock=$2; dock_width=$5+0; docks++ }
    else panes[++count]=$2
}
function box(w,h,x,y) { return w "x" h "," x "," y }
function leaf(id,w,h,x,y) {
    if (w<2 || h<2) { bad=1; return "" }
    return box(w,h,x,y) "," substr(id,2)
}
function stripe(first,n,w,h,x,y,axis,   space,base,extra,i,size,out,part) {
    if (n==1) return leaf(panes[first],w,h,x,y)
    space=(axis=="h" ? w : h)-n+1
    base=int(space/n); extra=space%n
    if (base<2) { bad=1; return "" }
    out=box(w,h,x,y) (axis=="h" ? "{" : "[")
    for (i=0;i<n;i++) {
        size=base+(i<extra)
        part=(axis=="h" ? leaf(panes[first+i],size,h,x,y) : leaf(panes[first+i],w,size,x,y))
        out=out (i ? "," : "") part
        if (axis=="h") x+=size+1; else y+=size+1
    }
    return out (axis=="h" ? "}" : "]")
}
function main_size(value,total,   size) {
    size=(value ~ /%$/ ? int(total*value/100) : value+0)
    if (size<2) size=2
    if (size>total-3) size=total-3
    return size
}
function content(w,h,x,y,   axis,mirror,size,one,rest,cols,rows,r,n,first,rh,base,extra,out) {
    if (count==1) return leaf(panes[1],w,h,x,y)
    if (layout=="even-horizontal") return stripe(1,count,w,h,x,y,"h")
    if (layout=="even-vertical") return stripe(1,count,w,h,x,y,"v")
    if (layout ~ /^main-/) {
        axis=(layout ~ /main-vertical/ ? "h" : "v")
        mirror=(layout ~ /mirrored$/)
        size=main_size(axis=="h" ? main_w : main_h,axis=="h" ? w : h)
        if (axis=="h") {
            one=leaf(panes[1],size,h,x+(mirror ? w-size : 0),y)
            rest=stripe(2,count-1,w-size-1,h,x+(mirror ? 0 : size+1),y,"v")
        } else {
            one=leaf(panes[1],w,size,x,y+(mirror ? h-size : 0))
            rest=stripe(2,count-1,w,h-size-1,x,y+(mirror ? 0 : size+1),"h")
        }
        return box(w,h,x,y) (axis=="h" ? "{" : "[") (mirror ? rest "," one : one "," rest) (axis=="h" ? "}" : "]")
    }
    # Tiled: near-square grid, with a full-width final row when needed.
    cols=int(sqrt(count)+0.999)
    for (r=0;r<count;r++) {
        n=(cols+r-1)%count+1; rows=int((count+n-1)/n)
        if (w>=3*n-1 && h>=3*rows-1) { cols=n; break }
    }
    if (r==count) { bad=1; return "" }
    rows=int((count+cols-1)/cols)
    if (rows==1) return stripe(1,count,w,h,x,y,"h")
    base=int((h-rows+1)/rows); extra=(h-rows+1)%rows
    out=box(w,h,x,y) "["; first=1
    for (r=0;r<rows;r++) {
        n=(count-first+1<cols ? count-first+1 : cols); rh=base+(r<extra)
        out=out (r ? "," : "") stripe(first,n,w,rh,x,y,"h")
        first+=n; y+=rh+1
    }
    return out "]"
}
END {
    # select-layout assigns leaves in pane-index order, not by the saved IDs.
    # Refuse an already-reordered dock rather than assigning its cell to an app.
    if (docks!=1 || dock!=first_pane || count<1 || dock_width<2 || width-dock_width-1<2) exit 1
    right=content(width-dock_width-1,height,dock_width+1,0)
    left=leaf(dock,dock_width,height,0,0)
    if (bad) exit 1
    value=box(width,height,0,0) "{" left "," right "}"
    checksum=0
    for (i=1;i<=length(value);i++) checksum=(int(checksum/2)+(checksum%2)*32768+ord[substr(value,i,1)])%65536
    printf "%04x,%s\n", checksum,value
}
