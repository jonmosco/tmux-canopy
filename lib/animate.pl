#!/usr/bin/env perl
# Animate WORKING / wrk status words in NUL-delimited fzf rows.
use strict;
use warnings;

my $frame = shift // 0;
$frame = 0 unless $frame =~ /^\d+$/;
$/ = "\0";

while (defined(my $row = <STDIN>)) {
    chop $row if substr($row, -1) eq "\0";
    my @fields = split(/\t/, $row, 3);
    if (@fields >= 2) {
        $fields[1] =~ s/(WORKING|wrk)/animate_word($1, $frame)/ge;
        $row = join("\t", @fields);
    }
    print $row, "\0";
}

sub animate_word {
    my ($word, $frame) = @_;
    my $length = length $word;
    my $band = $length <= 3 ? 1 : 2;
    my $positions = $length - $band + 1;
    my $cycle = 2 * ($positions - 1);
    my $phase = $frame % $cycle;
    my $start = $phase < $positions ? $phase : $cycle - $phase;
    my $out = '';
    for my $i (0 .. $length - 1) {
        my $char = substr($word, $i, 1);
        $out .= ($i >= $start && $i < $start + $band)
            ? "\e[7m${char}\e[27m"
            : $char;
    }
    return $out;
}
