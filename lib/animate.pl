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
        # The quiet working mark is one cell, so it pulses instead of sweeping.
        $fields[1] =~ s/\xe2\x96\xb7/animate_mark($frame)/ge;
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

sub animate_mark {
    my ($frame) = @_;
    my @styles = ("\e[36m", "\e[1;36m", "\e[1;96m", "\e[7;36m");
    return $styles[$frame % 4] . "\xe2\x96\xb7\e[0m";
}
