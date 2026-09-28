# Animate WORKING / wrk status words with a sliding reverse-video band.
# Records are NUL-delimited fzf rows: token, text, [identity]. Frame is 0-based.
BEGIN {
    RS = "\0"
    ORS = "\0"
    FS = OFS = "\t"
}
NF < 2 { printf "%s", $0 ORS; next }
$2 !~ /WORKING|wrk/ { printf "%s", $0 ORS; next }
{
    $2 = animate_status($2, frame + 0)
    printf "%s", $1
    for (i = 2; i <= NF; i++) printf "%s%s", OFS, $i
    printf "%s", ORS
}
function animate_status(text, frame,   out, word, wlen, band, start, i, ch, before, after, mid) {
    out = ""
    while (match(text, /WORKING|wrk/)) {
        word = substr(text, RSTART, RLENGTH)
        before = substr(text, 1, RSTART - 1)
        after = substr(text, RSTART + RLENGTH)
        wlen = length(word)
        band = (wlen <= 3 ? 1 : 2)
        start = frame % (wlen - band + 2)
        if (start > wlen - band) start = wlen - band
        mid = ""
        for (i = 1; i <= wlen; i++) {
            ch = substr(word, i, 1)
            if (i > start && i <= start + band) mid = mid "\033[7m" ch "\033[27m"
            else mid = mid ch
        }
        out = out before mid
        text = after
    }
    return out text
}
