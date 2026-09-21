#!/usr/bin/env python3
"""Insert a per-song ukulele fingering line into Caiet-chitara.md.

For every song (### N. Title), collects the chords used (chord-only lines
plus inline [X] bracket chords inside the ```text block, order of first
appearance) and inserts, right before the fenced block:

    **Ukulele:** C 0003 · G 0232 · Am 2000 · ...

Fingerings are for standard GCEA tuning, digits = fret per string in
G-C-E-A order, 0 = open string. Conventions:
  - power chords (X5) are rendered as the corresponding major chord;
  - slash chords (X/Y) as the upper chord X (no bass strings on a uke);
  - "Cm#" (source typo) is treated as C#m, "CaddG" as plain C (a uke C
    already contains G);
  - "FC"/"FCG" are run-together F C (G) from the source layout and are
    skipped (their components appear separately in the same song).

Idempotent: existing **Ukulele:** lines are replaced. Regenerating the
caiet via run.sh drops these lines - rerun this script afterwards (same
caveat as normalize_verses.py). Optional arg: path to the markdown file.
"""
import re
import sys
from pathlib import Path

DEFAULT_PATH = str(Path(__file__).resolve().parent.parent / "Caiet-chitara.md")

# label as printed in the song -> GCEA fingering
FINGERINGS = {
    # majors
    "A": "2100", "B": "4322", "C": "0003", "D": "2220", "E": "4442",
    "F": "2010", "G": "0232",
    "Bb": "3211", "D#": "0331", "Eb": "0331", "F#": "3121", "G#": "5343",
    # minors
    "Am": "2000", "Bm": "4222", "Cm": "0333", "C#m": "1104", "Dm": "2210",
    "D#m": "3321", "Ebm": "3321",
    "Em": "0432", "Fm": "1013", "F#m": "2120", "Gm": "0231",
    "Cm#": "1104",  # source typo for C#m
    # sevenths
    "A7": "0100", "B7": "2322", "C7": "0001", "D7": "2223", "E7": "1202",
    "F7": "2313", "G7": "0212", "F#7": "3424", "G#7": "1323",
    # minor sevenths
    "Am7": "0000", "Bm7": "2222", "Dm7": "2213", "Em7": "0202", "Gm7": "0211",
    # extensions & colors
    "Fmaj7": "2413", "F6": "2213", "C9": "0201", "D9": "2423",
    "Cadd9": "0203", "Dadd9": "2425", "Fadd9": "0010", "CaddG": "0003",
    "Csus4": "0013", "Dsus4": "0230", "Gsus4": "0233", "F#sus4": "4124",
    "C7sus4": "0011", "D7sus4": "2233", "D7sus2": "2203",
    "Cdim": "2323", "E+": "1003",
    # power chords -> corresponding major
    "A5": "2100", "B5": "4322", "C5": "0003", "D5": "2220", "E5": "4442",
    "F5": "2010", "F#5": "3121", "G5": "0232", "G#5": "5343",
    # slash chords -> upper chord
    "A/C#": "2100", "Bb/A": "3211", "Bm/A": "4222", "C/A#": "0003",
    "C/E": "0003", "D/G": "2220", "E/B": "4442", "E/G#": "4442",
    "G/B": "0232",
    # from the Karban volumes
    "A#": "3211", "Db": "1114", "Bbm": "3111", "Fm#": "2120",
    "Asus4": "2200", "Dsus2": "2200", "Fsus4": "3011", "Esus4": "4452",
    "Cmaj7": "0002", "Amaj7": "1100", "Dmaj7": "2224", "Gmaj7": "0222",
    "Adim7": "2323", "Edim7": "0101", "Ebdim7": "2323", "F#dim7": "2323",
    "Bdim7": "1212", "Ddim7": "1212", "Fdim7": "1212",
    "A#dim7": "0101", "Bbdim7": "0101",
    "Adim": "2323", "E+5": "1003",
    "Am6": "2423",
}

# a chord we have no entry for often reduces to one we do
def lookup(tok):
    if tok in FINGERINGS:
        return FINGERINGS[tok]
    base = tok.split("/")[0]                       # X/Y is played as X on a uke
    if base != tok and base in FINGERINGS:
        return FINGERINGS[base]
    m = re.match(r"^([A-G](?:#|b)?(?:m|maj|dim|aug)?)([0-9])$", tok)
    if m and m.group(2) == "4" and m.group(1) + "sus4" in FINGERINGS:
        return FINGERINGS[m.group(1) + "sus4"]     # "D4" is "Dsus4"
    if base in FINGERINGS:
        return FINGERINGS[base]
    if base.endswith("dim") and base + "7" in FINGERINGS:
        return FINGERINGS[base + "7"]              # a "dim" is played as dim7
    return None

# tokens allowed on a chord line that aren't themselves a chord: "FC"/"FCG"
# are run-together chords from the source layout (their components appear
# separately); "[fill]" marks an instrumental fill, not a chord to play; a
# bare "/" separates alternative ways to play the preceding chord (not a
# bass note — that's "X/Y" attached to the chord token itself)
SKIP_TOKENS = {"FC", "FCG", "[fill]", "/"}

CHORD_RE = re.compile(
    r"^[A-G](?:#|b)?"
    r"(?:m|maj|min|dim|aug|\+)?"
    r"(?:sus)?[0-9]*"
    r"(?:\(?(?:add|sus|maj)?[A-G0-9#b]*\)?)?"
    r"(?:/[A-G](?:#|b)?)?$"
)


def is_chord_token(tok):
    return tok in SKIP_TOKENS or bool(CHORD_RE.match(tok))


def unwrap_optional(tok):
    """An optional inline chord, [(G)], needs the same fingering as G."""
    return tok[1:-1] if tok.startswith("(") and tok.endswith(")") else tok


def line_is_chords(line):
    toks = line.split()
    return bool(toks) and all(is_chord_token(t) for t in toks)


def content_start(song):
    """Index of the first line of a song's content — its first fence, or a
    note written outside the fences before it — past the title, the
    meta line and the **Chitară:** line: where the **Ukulele:** line goes."""
    head = next((i for i, ln in enumerate(song) if ln.startswith("**Chitară:**")),
                None)
    if head is None:
        head = next((i for i in range(1, len(song)) if song[i].strip()), 0)
        if song[head].startswith("```"):
            return head
    return next((i for i in range(head + 1, len(song)) if song[i].strip()),
                len(song))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH
    lines = open(path, encoding="utf-8").read().split("\n")

    song_starts = [i for i, ln in enumerate(lines)
                   if ln.startswith("#### ")]
    bounds = []
    for k, start in enumerate(song_starts):
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if lines[j].startswith(("#### ", "### ", "## ")):
                end = j
                break
        bounds.append((start, end))

    out = []
    prev_end = 0
    n_inserted = n_no_chords = 0
    unknown = set()

    for start, end in bounds:
        out.extend(lines[prev_end:start])
        prev_end = end

        # drop any existing Ukulele line (idempotence), remembering position
        song = [ln for ln in lines[start:end]
                if not ln.startswith("**Ukulele:**")]
        # collapse double blanks left by a removed line
        cleaned = []
        for ln in song:
            if ln == "" and cleaned and cleaned[-1] == "":
                continue
            cleaned.append(ln)
        song = cleaned

        # collect chords in order of first appearance
        chords, seen = [], set()
        in_fence = False
        first_fence = None
        for idx, ln in enumerate(song):
            if ln.startswith("```"):
                if first_fence is None:
                    first_fence = idx
                in_fence = not in_fence
                continue
            if not in_fence:
                # a chord named in a note outside the fences: `C7`
                toks = [t for t in re.findall(r"`([^`]+)`", ln)
                        if CHORD_RE.match(t)]
            elif line_is_chords(ln):
                toks = ln.split()
            else:
                toks = [t for t in map(unwrap_optional,
                                       re.findall(r"\[([^\]]*)\]", ln))
                        if CHORD_RE.match(t)]
            for t in toks:
                if t in SKIP_TOKENS or t in seen:
                    continue
                seen.add(t)
                if lookup(t) is None:
                    unknown.add(t)
                    continue
                chords.append(t)

        if chords and first_fence is not None:
            pairs = " · ".join(f"{c} {lookup(c)}" for c in chords)
            at = content_start(song)
            song[at:at] = [f"**Ukulele:** {pairs}", ""]
            n_inserted += 1
        else:
            n_no_chords += 1

        out.extend(song)

    out.extend(lines[prev_end:])

    if unknown:
        sys.exit(f"unknown chord tokens, no fingering defined: "
                 f"{sorted(unknown)}")

    open(path, "w", encoding="utf-8").write("\n".join(out))
    print(f"songs: {len(bounds)}, ukulele lines inserted: {n_inserted}, "
          f"songs without chords: {n_no_chords}")


if __name__ == "__main__":
    main()
