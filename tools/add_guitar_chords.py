#!/usr/bin/env python3
"""Insert a per-song guitar fingering line into Caiet-chitara.md.

Mirrors add_ukulele_chords.py: for every song (### N. Title) it collects the
chords used — chord-only lines plus inline [X] brackets inside the ```text
block, in order of first appearance — and writes

    **Chitară:** C x32010 · G 320003 · Am x02210 · ...

immediately before the **Ukulele:** line.

Fingerings are for standard EADGBE tuning, one digit per string from the low
E (6th) to the high E (1st); ``x`` = string not played.  Same conventions as
the ukulele line: power chords (X5) are given as the corresponding major,
slash chords (X/Y) keep the bass note where the shape allows it, "X4" reads
as Xsus4, and "Cm#" (a typo in the source) as C#m.

Run ``--check`` to verify every fingering sounds the notes its name claims.

Idempotent: an existing **Chitară:** line is replaced.
"""
import re
import sys

DEFAULT_PATH = "/home/traian/chitara/Caiet-chitara.md"

FINGERINGS = {
    # majors
    "C": "x32010", "C#": "x43121", "D": "xx0232", "D#": "xx1343",
    "E": "022100", "F": "133211", "F#": "244322", "G": "320003",
    "G#": "466544", "A": "x02220", "A#": "x13331", "B": "x24442",
    # minors
    "Cm": "x35543", "C#m": "x46654", "Dm": "xx0231", "D#m": "xx1342",
    "Em": "022000", "Fm": "133111", "F#m": "244222", "Gm": "355333",
    "G#m": "466444", "Am": "x02210", "A#m": "x13321", "Bm": "x24432",
    # dominant sevenths
    "C7": "x32310", "C#7": "x43424", "D7": "xx0212", "D#7": "xx1323",
    "E7": "020100", "F7": "131211", "F#7": "242322", "G7": "320001",
    "G#7": "464544", "A7": "x02020", "A#7": "x13131", "B7": "x21202",
    # minor sevenths
    "Cm7": "x35343", "C#m7": "x46454", "Dm7": "xx0211", "D#m7": "xx1322",
    "Em7": "020000", "Fm7": "131111", "F#m7": "242222", "Gm7": "353333",
    "G#m7": "464444", "Am7": "x02010", "A#m7": "x13121", "Bm7": "x24232",
    # major sevenths
    "Cmaj7": "x32000", "Dmaj7": "xx0222", "Emaj7": "021100",
    "Fmaj7": "xx3210", "Gmaj7": "320002", "Amaj7": "x02120",
    "Bmaj7": "x24342",
    # suspended
    "Csus4": "x33011", "Dsus4": "xx0233", "Esus4": "022200",
    "Fsus4": "133311", "F#sus4": "244422", "Gsus4": "330013",
    "Asus4": "x02230", "Bsus4": "x24452",
    "Csus2": "x30033", "Dsus2": "xx0230", "Gsus2": "300233",
    "Asus2": "x02200",
    "C7sus4": "x3331x", "D7sus4": "xx0213", "D7sus2": "xx0210",
    # added ninths
    "Cadd9": "x32030", "Dadd9": "x54230", "Fadd9": "xx3213",
    "Gadd9": "320203", "Aadd9": "x02420",
    # sixths
    "C6": "x32210", "D6": "xx0202", "F6": "133231", "G6": "320000",
    "A6": "x02222",
    # ninths
    "C9": "x32333", "D9": "x54555", "E9": "020102", "A9": "x02423",
    # diminished sevenths (symmetric, repeating every three frets)
    "Cdim7": "xx1212", "C#dim7": "xx2323", "Ddim7": "xx0101",
    "D#dim7": "xx1212", "Edim7": "xx2323", "Fdim7": "xx3434",
    "F#dim7": "xx4545", "Gdim7": "xx5656", "G#dim7": "xx0101",
    "Adim7": "xx4545", "A#dim7": "xx2323", "Bdim7": "xx3434",
    # augmented
    "Caug": "x32110", "Eaug": "032110", "Aaug": "x03221",
    "Daug": "xx0332", "Gaug": "321003", "Faug": "xx3221",
    # slash chords worth their own shape (the bass note is the point)
    "C/E": "032010", "C/G": "332010", "D/A": "x00232", "D/F#": "200232",
    "D/G": "3x0232", "E/B": "x22100", "E/G#": "4x2100", "E/A": "x02100",
    "G/B": "x20003", "Am/G": "302210", "Bm/A": "x04432",
    "A/C#": "x42220", "Bb/A": "x03331", "C/A#": "x1201x", "Em/B": "x22000",
    "Dm/B": "x20231", "Am/F#": "2x2210",
}

# equivalent spellings
ALIAS = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#",
         "Dbm": "C#m", "Ebm": "D#m", "Gbm": "F#m", "Abm": "G#m", "Bbm": "A#m",
         "Cb": "B", "Fb": "E", "E#": "F", "B#": "C",
         # typos and shorthands from the sources
         "Cm#": "C#m", "Fm#": "F#m", "CaddG": "C"}

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

NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
OPEN = [4, 9, 2, 7, 11, 4]          # E A D G B E as pitch classes


def normalize(tok):
    """Strip the decoration a chord picks up in the sources."""
    tok = tok.strip("()").rstrip(":.")
    m = re.match(r"^([A-G](?:#|b)?)(.*)$", tok)
    if not m:
        return tok
    root, rest = m.group(1), m.group(2)
    bass = ""
    if "/" in rest:
        rest, _, bass = rest.partition("/")
        bass = "/" + bass
    full = ALIAS.get(root + rest, None)
    if full:
        return full + bass
    return ALIAS.get(root, root) + rest + bass


def lookup(tok):
    """Fingering for a chord token, reducing it to a known shape if needed."""
    tok = normalize(tok)
    if tok in FINGERINGS:
        return FINGERINGS[tok]
    base = tok.split("/")[0]                       # no shape for that bass
    if base in FINGERINGS:
        return FINGERINGS[base]
    m = re.match(r"^([A-G]#?)([0-9])$", base)
    if m and m.group(2) == "5":                    # power chord -> major
        return FINGERINGS.get(m.group(1))
    if m and m.group(2) == "4":                    # "D4" is Dsus4
        return FINGERINGS.get(m.group(1) + "sus4")
    m = re.match(r"^([A-G]#?(?:m)?)(?:dim|aug|\+)([0-9]*)$", base)
    if m:
        return FINGERINGS.get(m.group(1) + "dim7") or FINGERINGS.get(m.group(1))
    if base.endswith("+"):
        return FINGERINGS.get(base[:-1] + "aug") or FINGERINGS.get(base[:-1])
    return None


# ------------------------------------------------------------------ check

QUALITY = {
    "": [0, 4, 7], "m": [0, 3, 7], "7": [0, 4, 7, 10], "m7": [0, 3, 7, 10],
    "maj7": [0, 4, 7, 11], "sus4": [0, 5, 7], "sus2": [0, 2, 7],
    "7sus4": [0, 5, 7, 10], "7sus2": [0, 2, 7, 10], "add9": [0, 2, 4, 7],
    "6": [0, 4, 7, 9], "9": [0, 2, 4, 7, 10], "dim7": [0, 3, 6, 9],
    "aug": [0, 4, 8],
}


def sounded(fing):
    out = set()
    for s, ch in enumerate(fing):
        if ch != "x":
            out.add((OPEN[s] + int(ch, 16)) % 12)
    return out


def check():
    """Verify each fingering sounds the notes its name claims.

    Two liberties that guitar voicings routinely take are allowed: the fifth
    may be dropped (there are only six strings), and a slash chord may sound
    its named bass note even though the chord itself does not contain it.
    """
    bad = []
    for name, fing in FINGERINGS.items():
        norm = normalize(name)
        base, _, bass = norm.partition("/")
        m = re.match(r"^([A-G]#?)(.*)$", base)
        if not m or m.group(2) not in QUALITY:
            bad.append((name, fing, "calitate necunoscută"))
            continue
        root, qual = NOTES.index(m.group(1)), m.group(2)
        want = {(root + i) % 12 for i in QUALITY[qual]}
        allowed = set(want)
        if bass:
            allowed.add(NOTES.index(normalize(bass)))
        got = sounded(fing)
        extra = got - allowed
        missing = want - got - {(root + 7) % 12}      # fifth may be dropped
        if extra or missing:
            bad.append((name, fing,
                        f"în plus {[NOTES[n] for n in sorted(extra)]}, "
                        f"lipsă {[NOTES[n] for n in sorted(missing)]}"))
    for name, fing, why in bad:
        print(f"  {name:9s} {fing}  {why}")
    print(f"{len(FINGERINGS) - len(bad)}/{len(FINGERINGS)} digitații corecte")
    return not bad


def line_is_chords(line):
    toks = line.split()
    return bool(toks) and all(t in SKIP_TOKENS or CHORD_RE.match(t)
                              for t in toks)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PATH
    lines = open(path, encoding="utf-8").read().split("\n")

    starts = [i for i, ln in enumerate(lines) if re.match(r"^#### \d+\. ", ln)]
    bounds = []
    for start in starts:
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if lines[j].startswith(("#### ", "### ", "## ")):
                end = j
                break
        bounds.append((start, end))

    out, prev_end = [], 0
    inserted = unknown = 0
    missing = set()

    for start, end in bounds:
        out.extend(lines[prev_end:start])
        prev_end = end
        song = [ln for ln in lines[start:end]
                if not ln.startswith("**Chitară:**")]

        chords, seen = [], set()
        in_fence = False
        for ln in song:
            if ln.startswith("```"):
                in_fence = not in_fence
                continue
            if not in_fence:
                continue
            toks = (ln.split() if line_is_chords(ln)
                    else [t for t in re.findall(r"\[([^\]]*)\]", ln)
                          if CHORD_RE.match(t)])
            for t in toks:
                if t in SKIP_TOKENS or t in seen:
                    continue
                seen.add(t)
                f = lookup(t)
                if f is None:
                    missing.add(t)
                    unknown += 1
                    continue
                chords.append((t, f))

        if chords:
            note = "**Chitară:** " + " · ".join(f"{c} {f}" for c, f in chords)
            uke = next((i for i, ln in enumerate(song)
                        if ln.startswith("**Ukulele:**")), None)
            if uke is None:
                uke = next(i for i, ln in enumerate(song)
                           if ln.startswith("```"))
                song[uke:uke] = [note, ""]
            else:
                song[uke:uke] = [note]
            inserted += 1
        out.extend(song)

    out.extend(lines[prev_end:])
    open(path, "w", encoding="utf-8").write("\n".join(out))
    print(f"songs: {len(bounds)}, guitar lines inserted: {inserted}")
    if missing:
        print(f"unknown chord tokens, no fingering defined: {sorted(missing)}")


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.exit(0 if check() else 1)
    main()
