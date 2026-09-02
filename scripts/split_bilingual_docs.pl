#!/usr/bin/perl
# Split bilingual (EN + ZH mixed) Markdown documents into two files per document:
#   <name>.md      -> English edition (keeps the original path)
#   <name>.zh.md   -> Chinese edition
#
# Recognized source conventions:
#   1. Inline pair on one line:   "English text / 中文文本"
#      The separator is exactly " / " (space slash space). A split point is valid
#      only when everything left of it is CJK-free and the first segment on the
#      right contains CJK. At most one such boundary can exist per text.
#   2. Label pair:                "- Status / 状态：content"
#      A short EN label, the separator, a short ZH label, a colon, then content
#      that may itself be an inline pair or language-neutral text.
#   3. Vertical pair:             an EN unit (paragraph, bullet, heading, ...)
#      followed by its ZH translation as a separate unit. Runs of EN units pair
#      item-by-item with a following run of ZH units of the same kind and length.
#   4. Language-neutral units (commands, code spans, table separators, fences)
#      are emitted unchanged to both editions.
#
# Backtick spans are masked before analysis when they contain no valid boundary,
# so commands and quoted commit subjects never break the detection. Spans that
# themselves carry a valid EN/ZH boundary (for example `PASS — ... / 通过 — ...`)
# stay unmasked and split normally.
#
# The Chinese edition additionally rewrites local Markdown links from X.md to
# X.zh.md (both the target and a purely path-like link text). Every edition is
# prefixed with a language switcher line.
#
# Usage:
#   perl scripts/split_bilingual_docs.pl --dry-run [root]
#   perl scripts/split_bilingual_docs.pl --write    [root]
#
# Idempotence note: *.zh.md files are never treated as sources, so re-running
# after editing a bilingual source regenerates its pair. This is the one-shot
# migration tool for execution 0028; new documents are authored directly in
# both languages.

use strict;
use warnings;
use utf8;
use open ':std', ':encoding(UTF-8)';
use File::Find;

my $mode = shift @ARGV // '';
my $root = shift @ARGV // '.';
$mode =~ /^--(dry-run|write)$/ or die "usage: $0 --dry-run|--write [root]\n";

my $CJK     = qr/[\x{4e00}-\x{9fff}]/;
my $SEP     = " \x{2f} ";    # " / "
my @SOURCES = ();
our $CUR_FILE = '-';
our $CUR_NO   = 0;

find(
    sub {
        return unless /\.md$/;
        return if /\.zh\.md$/;
        my $name = $File::Find::name;
        return if $name =~ m{/\.git(?:/|$)};
        push @SOURCES, $name;
    },
    $root,
);
@SOURCES = sort @SOURCES;

my %STAT = (
    files            => 0,
    inline           => 0,
    label            => 0,
    vertical_pairs   => 0,
    both_units       => 0,
    zh_only_units    => 0,
);
my @REPORT = ();    # [severity, file, line, message]

sub note { push @REPORT, [@_] }

# ---------------------------------------------------------------- protection

# Position of the FIRST valid " / " EN->ZH boundary, or -1.
sub valid_boundary_pos {
    my ($t) = @_;
    my $pos = -1;
    my $off = 0;
    my $left_clean = 1;
    while ((my $i = index($t, $SEP, $off)) >= 0) {
        $left_clean = 0 if substr($t, $off, $i - $off) =~ $CJK;
        my $right_first = substr($t, $i + 3);
        my $next = index($right_first, $SEP);
        $right_first = substr($right_first, 0, $next) if $next >= 0;
        if ($left_clean && $right_first =~ $CJK) { $pos = $i; last; }
        $off = $i + 3;
    }
    return $pos;
}

sub protect_spans {
    my ($text) = @_;
    my (%map, @order);
    my $n = 0;
    $text =~ s{(`+)((?:(?!\1).)*?)\1}{
        my $span = $&;
        if (valid_boundary_pos($2) >= 0) { $span }        # bilingual span: let it split
        else {
            my $key = "\x{ee}$n\x{ff}";
            $map{$key} = $span;
            push @order, $key;
            $n++;
            $key;
        }
    }gse;
    return ($text, \%map);
}

sub restore { my ($t, $map) = @_; $t =~ s/(\x{ee}\d+\x{ff})/exists $map->{$1} ? $map->{$1} : $1/ge; return $t }

# ---------------------------------------------------------------- splitting

sub split_general {
    my ($t) = @_;
    my $pos = valid_boundary_pos($t);
    return (undef, undef) if $pos < 0;
    my $en = substr($t, 0, $pos);
    my $zh = substr($t, $pos + 3);
    $en =~ s/\s+$//;
    $zh =~ s/^\s+//;
    return ($en, $zh);
}

# Match "EN label / ZH label：" at the head of protected text (list/heading
# prefix already removed). Returns (en_label, zh_label, rest_offset) or ().
# The first " / " must separate a short CJK-free English label from a short
# Chinese label (optionally carrying a Latin prefix such as "CLI 投影夹具")
# followed by a colon; everything after the colon is content.
sub label_head {
    my ($t) = @_;
    my $sep = index($t, $SEP);
    return () if $sep < 0;
    my $en_label = substr($t, 0, $sep);
    my $rest = substr($t, $sep + 3);
    return () if $en_label =~ $CJK;
    return () if length($en_label) > 60 || $en_label !~ /[A-Za-z]/ || $en_label =~ /[.。]$/;
    return () unless $rest =~ /^([A-Za-z0-9 .\-()]{0,20}?$CJK[^\x{2f}：:]{0,11})([：:])\s*/;
    my ($zh_label, $restoff) = ($1, $sep + 3 + $+[0]);
    return ($en_label, $zh_label, $restoff);
}

# Match a bold label pair at the head: "**EN label / ZH label** tail".
# The ZH side may end with a language-neutral status suffix such as
# " — PASS." that is duplicated onto both bold labels. Returns a hashref or ().
sub bold_label_head {
    my ($t) = @_;
    return () unless $t =~ /^\*\*([^\x{2f}*]{1,60}) \x{2f} ([^*]{1,60})\*\*\s*(.*)$/s;
    my ($en, $zh, $tail) = ($1, $2, $3);
    return () if $en =~ $CJK || $zh !~ $CJK;
    my $suffix = '';
    if ($zh =~ /^(.+?)\s+\x{2014}\s*([^\x{4e00}-\x{9fff}*]{1,20})$/) {
        my ($core, $suf) = ($1, $2);
        if ($core =~ $CJK) { ($zh, $suffix) = ($core, " \x{2014} $suf"); }
    }
    return { en => "**$en$suffix**", zh => "**$zh$suffix**", tail => $tail };
}

my $PREFIX_RE = qr/^(\s*(?:\#{1,6}|[-*+]|\d+[.)]|>)\s+)/;

# Process one logical unit (heading/paragraph/list item/quote line).
# Returns hashref {class, en, zh}; class in: inline | both | zh_only | en_only.
sub process_unit {
    my ($raw) = @_;
    my $line = $raw;
    $line =~ s/\s+$//;
    my ($prefix, $body) = ('', $line);
    if ($line =~ $PREFIX_RE) { $prefix = $1; $body = substr($line, length($1)); }

    my ($ptext, $map) = protect_spans($body);
    my $has_cjk = $ptext =~ $CJK ? 1 : 0;

    if ($has_cjk) {
        my $b = bold_label_head($ptext);
        if ($b) {
            my $tail = $b->{tail};
            $tail =~ s/^\s+//;
            $tail =~ s/\s+$//;
            my ($ten, $tzh) = split_general($tail);
            my ($tail_en, $tail_zh);
            if (defined $ten) { ($tail_en, $tail_zh) = ($ten, $tzh); }
            elsif ($tail =~ $CJK) {
                note('WARN', $CUR_FILE, $CUR_NO, "bold label with Chinese-only tail kept whole: $raw");
                return { class => 'both', en => $line, zh => $line };
            }
            else { ($tail_en, $tail_zh) = ($tail, $tail); }
            $STAT{inline}++;
            my $gap = $tail eq '' ? '' : ' ';
            my $en = $prefix . $b->{en} . $gap . restore($tail_en, $map);
            my $zh = $prefix . $b->{zh} . $gap . restore($tail_zh, $map);
            $en =~ s/\s+$//;
            $zh =~ s/\s+$//;
            return { class => 'inline', en => $en, zh => $zh };
        }
        my ($en_l, $zh_l, $roff) = label_head($ptext);
        if (defined $en_l) {
            my $rest = substr($ptext, $roff);
            $rest =~ s/^\s+//;
            my ($ren, $rzh) = split_general($rest);
            if (defined $ren) {
                $STAT{inline}++;
                my $en = $prefix . $en_l . ': ' . restore($ren, $map);
                my $zh = $prefix . $zh_l . '：' . restore($rzh, $map);
                $en =~ s/\s+$//;
                $zh =~ s/\s+$//;
                return { class => 'inline', en => $en, zh => $zh };
            }
            if ($rest =~ $CJK) {
                note('WARN', $CUR_FILE, $CUR_NO, "label pair with Chinese-only content kept whole: $raw");
                return { class => 'both', en => $line, zh => $line };
            }
            $STAT{label}++;
            my $ascii_words = () = restore($rest, $map) =~ /\b[A-Za-z]{2,}\b/g;
            if ($ascii_words >= 4) {
                note('INFO', $CUR_FILE, $CUR_NO, "label content is untranslated English prose: " . substr($raw, 0, 90));
            }
            my $en = $prefix . $en_l . ': ' . restore($rest, $map);
            my $zh = $prefix . $zh_l . '：' . restore($rest, $map);
            $en =~ s/\s+$//;
            $zh =~ s/\s+$//;
            return { class => 'inline', en => $en, zh => $zh };
        }
        my ($en, $zh) = split_general($ptext);
        if (defined $en) {
            $STAT{inline}++;
            return { class => 'inline', en => $prefix . restore($en, $map), zh => $prefix . restore($zh, $map) };
        }
        return { class => 'zh_only', en => undef, zh => $line };
    }

    if (index($ptext, $SEP) >= 0) {
        note('INFO', $CUR_FILE, $CUR_NO, "neutral text keeps ' / ': $raw");
    }
    return { class => 'en_only', en => $line, zh => $line };
}

# Process a table row cell-by-cell.
sub process_row {
    my ($raw) = @_;
    my $line = $raw;
    $line =~ s/\s+$//;
    my ($ptext, $map) = protect_spans($line);
    my @cells = split /\x{7c}/, $ptext, -1;
    if (@cells < 2) { return process_unit($raw) }
    my $lead  = ($cells[0]  =~ /^\s*$/) ? shift @cells : undef;
    my $trail = ($cells[-1] =~ /^\s*$/) ? pop  @cells : undef;
    my (@en, @zh);
    my ($any_split, $any_cjk, $any_zh_cell) = (0, 0, 0);
    for my $c (@cells) {
        my $t = $c;
        $t =~ s/^\s+|\s+$//g;
        $any_cjk = 1 if $t =~ $CJK;
        my $u = process_unit($t);
        if ($u->{class} eq 'inline') { $any_split = 1 }
        if ($u->{class} eq 'zh_only' && $any_split) {
            $any_zh_cell = 1;
            note('WARN', $CUR_FILE, $CUR_NO, "inline row carries a Chinese-only cell: $raw");
        }
        push @en, $u->{en} // '';
        push @zh, $u->{zh} // '';
    }
    my $fmt = sub {
        my @p = @_;
        my $s = join(' | ', map { defined $_ ? $_ : '' } @p);
        return (defined $lead ? '| ' : '') . $s . (defined $trail ? ' |' : '');
    };
    if ($any_split) {
        return { class => 'inline',
                 en => $fmt->(map { restore($_, $map) } @en),
                 zh => $fmt->(map { restore($_, $map) } @zh) };
    }
    return { class => $any_cjk ? 'zh_only' : 'en_only', en => $line, zh => $line };
}

sub is_sep_row { return $_[0] =~ /^\s*\x{7c}[\s:\-|]+\x{7c}\s*$/ ? 1 : 0 }

sub kind_of {
    my ($l) = @_;
    return 'fence'   if $l =~ /^\s*(```|~~~)/;
    return 'heading' if $l =~ /^#{1,6}\s/;
    return 'bullet'  if $l =~ /^\s*[-*+]\s/;
    return 'ordered' if $l =~ /^\s*\d+[.)]\s/;
    return 'table'   if $l =~ /^\s*\x{7c}/;
    return 'quote'   if $l =~ /^\s*>/;
    return 'para';
}

# ---------------------------------------------------------------- document

sub process_file {
    my ($path) = @_;
    open my $fh, '<', $path or die "$path: $!";
    my @lines;
    while (my $l = <$fh>) { $l =~ s/\r?\n$//; push @lines, $l; }
    close $fh;

    # 1. Token stream.
    my @tokens;    # {t=>'fence'|'blank'|'sep'|'unit', ...}
    {
        my $in_fence = 0;
        for my $i (0 .. $#lines) {
            my $l = $lines[$i];
            if ($l =~ /^\s*(```|~~~)/) {
                $in_fence = !$in_fence;
                push @tokens, { t => 'fence', line => $l, no => $i + 1 };
                next;
            }
            if ($in_fence) { push @tokens, { t => 'fence', line => $l, no => $i + 1 }; next; }
            if ($l =~ /^\s*$/) { push @tokens, { t => 'blank', line => $l, no => $i + 1 }; next; }
            if (kind_of($l) eq 'table' && is_sep_row($l)) {
                push @tokens, { t => 'sep', line => $l, no => $i + 1 };
                next;
            }
            $CUR_NO = $i + 1;
            my $u = kind_of($l) eq 'table' ? process_row($l) : process_unit($l);
            push @tokens, { t => 'unit', kind => kind_of($l), u => $u, line => $l, no => $i + 1 };
        }
    }

    # 2. Vertical pairing over subruns of same-kind units.
    my %paired_en = ();    # token ref -> zh token ref
    my %paired_zh = ();
    {
        my @seq = grep { $_->{t} eq 'unit' } @tokens;
        my $i = 0;
        while ($i < @seq) {
            my $start = $i;
            my $kind  = $seq[$i]{kind};
            my $class = $seq[$i]{u}{class};
            $class = 'x' unless $class eq 'en_only' || $class eq 'zh_only';
            $i++;
            while ($i < @seq
                && $seq[$i]{kind} eq $kind
                && do { my $c = $seq[$i]{u}{class}; $c = 'x' unless $c eq 'en_only' || $c eq 'zh_only'; $c eq $class }
                && $seq[$i]{no} - $seq[$i - 1]{no} <= 3)
            {
                $i++;
            }
            my @run = @seq[$start .. $i - 1];
            next if $class eq 'x' || $class eq 'en_only';

            # zh run: search backwards for the nearest en subrun of the same
            # kind; blank/fence/sep tokens and inline table rows are transparent.
            my $j = $start - 1;
            while ($j >= 0 && $seq[$j]{u}{class} eq 'inline' && $seq[$j]{kind} eq 'table') { $j--; }
            if ($j >= 0 && $seq[$j]{kind} eq $kind && $seq[$j]{u}{class} eq 'en_only') {
                my $k = $j;
                while ($k - 1 >= 0
                    && $seq[$k - 1]{kind} eq $kind
                    && $seq[$k - 1]{u}{class} eq 'en_only'
                    && $seq[$k]{no} - $seq[$k - 1]{no} <= 3)
                {
                    $k--;
                }
                my @enrun = @seq[$k .. $j];
                if (@enrun == @run) {
                    $paired_en{$enrun[$_]} = $run[$_] for 0 .. $#run;
                    $paired_zh{$run[$_]}  = $enrun[$_] for 0 .. $#run;
                    $STAT{vertical_pairs} += scalar @run;
                    next;
                }
                note('WARN', $path, $run[0]{no},
                     "vertical run length mismatch: en " . scalar(@enrun) . " vs zh " . scalar(@run) . " (kind $kind)");
            }
            for my $u (@run) {
                $STAT{zh_only_units}++;
                note('WARN', $path, $u->{no}, "unpaired Chinese unit: " . substr($u->{line}, 0, 90));
            }
        }
        for my $tk (@seq) {
            next unless $tk->{u}{class} eq 'en_only' && !exists $paired_en{$tk};
            $tk->{u}{class} = 'both';
            $STAT{both_units}++;
            if ($tk->{kind} ne 'table') {
                note('INFO', $path, $tk->{no}, "unpaired English unit (kept in both editions): " . substr($tk->{line}, 0, 90));
            }
        }
    }

    # 3. Emit editions.
    my (@en, @zh);
    for my $tk (@tokens) {
        if ($tk->{t} ne 'unit') {
            push @en, $tk->{line};
            push @zh, $tk->{line};
            next;
        }
        my $u = $tk->{u};
        if (exists $paired_en{$tk}) { push @en, $u->{en}; next; }
        if (exists $paired_zh{$tk}) { push @zh, $u->{zh}; next; }
        if ($u->{class} eq 'zh_only') { push @zh, $u->{zh}; next; }
        push @en, $u->{en};
        push @zh, $u->{zh};
    }
    return (\@en, \@zh);
}

# ---------------------------------------------------------------- output

# Collapse blank-line runs to a single blank outside fences; fences keep every
# line verbatim. Leading/trailing blanks are dropped.
sub collapse_blanks {
    my (@out) = @_;
    my (@r, $blank, $in_fence);
    for my $l (@out) {
        if ($l =~ /^\s*(```|~~~)/) {
            push @r, '' if @r && $blank && !$in_fence;
            $blank = 0;
            $in_fence = !$in_fence;
            push @r, $l;
            next;
        }
        if ($in_fence) { push @r, $l; next; }
        if ($l =~ /^\s*$/) { $blank = 1; next; }
        push @r, '' if @r && $blank;
        $blank = 0;
        push @r, $l;
    }
    return @r;
}

sub rewrite_links_zh {
    my ($text) = @_;
    $text =~ s{\[([^\]]*)\]\(\s*([^)\s]+)\s*\)}{
        my ($label, $target) = ($1, $2);
        if ($target =~ /\.md$/ && $target !~ m{^[a-z]+://}i) {
            (my $zh_target = $target) =~ s/\.md$/.zh.md/;
            if ($label =~ /^([\s`]*[\w.\/\-]+\.md[\s`]*)$/) {
                (my $zl = $label) =~ s/\.md(?=[\s`]*$)/.zh.md/;
                $label = $zl;
            }
            "[$label]($zh_target)";
        } else {
            "[$label]($target)";
        }
    }ge;
    return $text;
}

sub basename_of { my ($p) = @_; $p =~ s{.*[\\/]}{}; return $p }

my @written = ();
for my $path (@SOURCES) {
    $STAT{files}++;
    local $CUR_FILE = $path;
    my ($en, $zh) = process_file($path);
    my @en = collapse_blanks(@$en);
    my @zh = collapse_blanks(@$zh);
    my $base = basename_of($path);
    my ($name) = $base =~ /^(.*)\.md$/;
    @zh = map { rewrite_links_zh($_) } @zh;
    unshift @en, "**English** | [\x{4e2d}\x{6587}]($name.zh.md)", '';
    unshift @zh, "[English]($name.md) | **\x{4e2d}\x{6587}**", '';
    if ($mode eq '--write') {
        open my $fe, '>', $path or die "$path: $!";
        binmode $fe, ':encoding(UTF-8)';
        print $fe join("\n", @en), "\n";
        close $fe;
        (my $zhpath = $path) =~ s/\.md$/.zh.md/;
        open my $fz, '>', $zhpath or die "$zhpath: $!";
        binmode $fz, ':encoding(UTF-8)';
        print $fz join("\n", @zh), "\n";
        close $fz;
        push @written, $zhpath;
    }
}

print "mode: $mode\n";
printf "files processed:      %d\n", $STAT{files};
printf "inline splits:        %d\n", $STAT{inline};
printf "label-pair heads:     %d\n", $STAT{label};
printf "vertical pair units:  %d\n", $STAT{vertical_pairs};
printf "unpaired en units:    %d\n", $STAT{both_units};
printf "unpaired zh units:    %d\n", $STAT{zh_only_units};
if ($mode eq '--write') { printf "zh editions written:  %d\n", scalar @written; }
print "\n== report (", scalar(@REPORT), " entries) ==\n";
for my $r (@REPORT) {
    printf "[%s] %s:%s %s\n", @$r;
}
