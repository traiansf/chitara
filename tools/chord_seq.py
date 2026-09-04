# -*- coding: utf-8 -*-
"""Extract the chord progression of a song block, for comparing variants."""
import re, sys
sys.path.insert(0, "/home/traian/chitara/tools")
from extract_common import is_chord_text

INLINE = re.compile(r"\[([A-G][b#]?[^\]]*)\]")
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
ALIAS = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#",
         "Cb": "B", "Fb": "E", "E#": "F", "B#": "C"}


def split_chord(tok):
    """'Am7/G' -> (root_index, 'm7')   returns None if not parseable.

    Speaker markers like ``B:`` / ``F:`` (bărbat / femeie in the duets) look
    like chords but are not, so anything ending in ':' is rejected.
    """
    if tok.endswith(":"):
        return None
    m = re.match(r"^([A-G][b#]?)(.*)$", tok)
    if not m:
        return None
    root = ALIAS.get(m.group(1), m.group(1))
    if root not in NOTES:
        return None
    return NOTES.index(root), m.group(2).split("/")[0]


def chords(body):
    """Ordered chord tokens of a song body (chord lines + inline markers)."""
    out = []
    for l in body:
        t = l.strip()
        if not t:
            continue
        inline = INLINE.findall(l)
        if inline:
            out += inline
        elif is_chord_text(t):
            out += t.split()
    return [c for c in out if split_chord(c)]


def dedupe_runs(seq):
    """Collapse immediate repeats: C C G G -> C G."""
    out = []
    for c in seq:
        if not out or out[-1] != c:
            out.append(c)
    return out


def normalize(seq, shift):
    """Transpose a chord sequence by `shift` semitones."""
    out = []
    for c in seq:
        r, q = split_chord(c)
        out.append(NOTES[(r + shift) % 12] + q)
    return out


def best_match(a, b):
    """-> (shift, ratio) of the transposition that makes a most like b."""
    from difflib import SequenceMatcher
    best = (0, 0.0)
    for sh in range(12):
        r = SequenceMatcher(None, normalize(a, sh), b, autojunk=False).ratio()
        if r > best[1]:
            best = (sh, r)
    return best
