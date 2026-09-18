"""Transpose chord names and their fingerings by a number of semitones.

The Python counterpart of the transposing half of html_assets/chords.js,
which does the same live on the site: make_pdf.py --lista uses it to
print chosen songs in the key they're sung in.
"""
import re

import add_guitar_chords
import add_ukulele_chords

SHARPS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLATS = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
PITCH = {**{n: i for i, n in enumerate(SHARPS)},
         **{n: i for i, n in enumerate(FLATS)},
         "Cb": 11, "Fb": 4, "E#": 5, "B#": 0}
# majors whose signature has flats although their name has none (F), or
# whose relative minor's name has none (Dm, Gm, Cm, Fm)
FLAT_MAJORS = {PITCH[n] for n in ("F", "Bb", "Eb", "Ab")}

ROOT_RE = re.compile(r"^([A-G][#b]?)(.*)$")
BASS_RE = re.compile(r"^(.*?)/([A-G][#b]?)(.*)$")

# the fingering tables of each instrument, by its label on a fingering line
TABLES = {"Chitară": add_guitar_chords, "Ukulele": add_ukulele_chords}


def root_pitch(chord):
    """Pitch class (0 = C) of a chord name's root, or None if it has none."""
    m = ROOT_RE.match(chord)
    return PITCH.get(m.group(1)) if m else None


def interval(src, dst):
    """Semitones from src's root to dst's, the shorter way round (-5..6)."""
    n = (root_pitch(dst) - root_pitch(src)) % 12
    return n - 12 if n > 6 else n


def uses_flats(key):
    """Whether chords in the key a chord name stands for ("F", "Dm", "A")
    are spelled with flats (Bb) rather than sharps (A#): a flat in the
    name itself says so, and so does a flat key signature."""
    root, rest = ROOT_RE.match(key).groups()
    if len(root) == 2:
        return root[1] == "b"
    minor = rest.startswith("m") and not rest.startswith("maj")
    return (PITCH[root] + 3) % 12 in FLAT_MAJORS if minor \
        else PITCH[root] in FLAT_MAJORS


def _note(pitch, flats):
    return (FLATS if flats else SHARPS)[pitch % 12]


def transpose_chord(chord, n, flats):
    """chord moved n semitones, its root (and bass note, after a "/")
    spelled with flats or sharps; the rest ("m7", "(add9)") stays as it
    is. A name with no root it can read comes back unchanged."""
    m = ROOT_RE.match(chord)
    if n == 0 or not m or m.group(1) not in PITCH:
        return chord
    root, rest = m.groups()
    if b := BASS_RE.match(rest):
        rest = f"{b.group(1)}/{_note(PITCH[b.group(2)] + n, flats)}{b.group(3)}"
    return _note(PITCH[root] + n, flats) + rest


def respelled(chord):
    """The same chord with its root's other spelling (C# <-> Db): the
    fingering tables list some chords under only one of the two."""
    m = ROOT_RE.match(chord)
    if not m or len(m.group(1)) != 2 or m.group(1) not in PITCH:
        return chord
    other = (FLATS if m.group(1)[1] == "#" else SHARPS)[PITCH[m.group(1)]]
    return other + m.group(2)


def shift_fingering(fingering, n):
    """fingering ("x02210") with every fretted or open string moved n
    frets, the shorter way round, else the other way; None if neither
    keeps every fret within one hex digit (0-15). As chords.js does."""
    n %= 12
    delta = n - 12 if n > 6 else n

    def apply(d):
        out = []
        for ch in fingering:
            if ch == "x":
                out.append("x")
                continue
            fret = int(ch, 16) + d
            if not 0 <= fret <= 15:
                return None
            out.append(format(fret, "x"))
        return "".join(out)

    return apply(delta) or apply(delta + 12 if delta < 0 else delta - 12)


def transpose_fingering_line(line, n, flats):
    """A '**Chitară:** Em 022000 · G 320003' line with every chord moved n
    semitones. Each new chord's fingering is looked up in that
    instrument's table, under either spelling of its root; one missing
    from it gets the old shape moved n frets instead."""
    label, _, rest = line.partition(":** ")
    table = TABLES[label.strip("*")]
    items = []
    for item in rest.split(" · "):
        chord, _, fingering = item.partition(" ")
        new = transpose_chord(chord, n, flats)
        found = table.lookup(new) or table.lookup(respelled(new)) \
            or shift_fingering(fingering, n)
        items.append(f"{new} {found}" if found else new)
    return f"{label}:** " + " · ".join(items)
