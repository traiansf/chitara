#!/usr/bin/env python3
"""Collapse repeated inline chord brackets into the "^" hold marker.

In the inline [X]word notation, a chord is sometimes re-struck with no
lyric change (an extra beat) or split mid-word across several strikes
(e.g. a prolonged vowel written as "Dia[Dm]a[Dm]na"). Repeating the
bracket for each strike is noisy and, above a couple of repeats, hard to
read. Where a bracket's chord is identical to the bracket immediately
before it on the same line, this replaces the redundant bracket with a
bare "^", leaving every other character untouched:

    [Dm]Și-am por[Dm]nit să [C]reclă[C]dim [Dm]Dia[Dm]a[Dm]na[Dm]
    -> [Dm]Și-am por^nit să [C]reclă^dim [Dm]Dia^a^na^

Only the immediately preceding bracket counts: a chord that differs from
its predecessor is always kept, even if the same chord recurs a couple
of tokens later (Dm C Dm keeps both Dm's as brackets, since neither is
adjacent to a like chord). Comparison resets at each line: the first
bracket on a line is never collapsed against the previous line's chord.

Chord-only lines (chords on their own line above the lyrics) are left
alone entirely -- there "/" already means something else (an alternate
voicing of the preceding chord), and there is no attached syllable to
hold across.

Idempotent: a line with no repeats left is unchanged.
"""
import re
import sys

DEFAULT_PATH = "/home/traian/chitara/Caiet-chitara.md"

CHORD_RE = re.compile(
    r"^[A-G](?:#|b)?"
    r"(?:m|maj|min|dim|aug|\+)?"
    r"(?:sus)?[0-9]*"
    r"(?:\(?(?:add|sus|maj)?[A-G0-9#b]*\)?)?"
    r"(?:/[A-G](?:#|b)?)?$"
)
SKIP_TOKENS = {"FC", "FCG", "[fill]", "/"}
# [Am], or [(Am)] for an optional chord: one is never collapsed into "^"
# nor is it a repeat of the plain chord before it, but it still stands
# between two plain ones, so [D]..[(G)]..[D] keeps its second [D]
INLINE_RE = re.compile(r"\[(\([A-G][^\]]*\)|[A-G][^\]]*)\]")


def line_is_chords(line):
    toks = line.split()
    return bool(toks) and all(t in SKIP_TOKENS or CHORD_RE.match(t)
                              for t in toks)


def collapse_line(line):
    """-> (new_line, n_collapsed). Verifies the lyric text is unchanged."""
    matches = list(INLINE_RE.finditer(line))
    out, stripped, last_end, prev_chord, n = [], [], 0, None, 0
    for m in matches:
        gap = line[last_end:m.start()]
        out.append(gap)
        stripped.append(gap)
        chord = m.group(1)
        repeat = chord == prev_chord and not chord.startswith("(")
        out.append("^" if repeat else m.group(0))
        n += repeat
        prev_chord, last_end = chord, m.end()
    tail = line[last_end:]
    out.append(tail)
    stripped.append(tail)
    new_line = "".join(out)

    old_stripped = INLINE_RE.sub("", line)
    assert old_stripped == "".join(stripped), (line, new_line)
    return new_line, n


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH
    lines = open(path, encoding="utf-8").read().split("\n")

    fence, collapsed, touched_songs = None, 0, set()
    song = None
    out = []
    for ln in lines:
        if ln.startswith("#### "):
            song = ln
        if ln.startswith("```"):
            # the fence's language, or None once closed: only ```text
            # fences hold lyrics, ```tab ones hold tablature
            fence = (ln[3:].strip() or "text") if fence is None else None
            out.append(ln)
            continue
        if fence not in (None, "tab") and not line_is_chords(ln):
            new_ln, n = collapse_line(ln)
            if n:
                collapsed += n
                touched_songs.add(song)
            out.append(new_ln)
        else:
            out.append(ln)

    open(path, "w", encoding="utf-8").write("\n".join(out))
    print(f"chords collapsed: {collapsed}, songs touched: {len(touched_songs)}")


if __name__ == "__main__":
    main()
