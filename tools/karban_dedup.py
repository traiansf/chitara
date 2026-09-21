# -*- coding: utf-8 -*-
"""Find songs shared between the caiet and the two Karban volumes.

Same rule as the caiet's own de-duplication: songs whose chord progression is
identical in the same key collapse into one entry, everything else is kept as
a pair of variants.
"""
import collections, itertools, sys
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from karban_songs import all_songs


def candidates(songs, n=5, minshare=3):
    """Pairs sharing several rare word n-grams — cheap filter before scoring."""
    index = collections.defaultdict(set)
    for i, s in enumerate(songs):
        w = s["words"]
        for j in range(max(len(w) - n + 1, 0)):
            index[" ".join(w[j:j + n])].add(i)
    shared = collections.Counter()
    for group in index.values():
        if 1 < len(group) <= 8:
            for a, b in itertools.combinations(sorted(group), 2):
                shared[(a, b)] += 1
    return [p for p, c in shared.items() if c >= minshare]


def score(a, b):
    ca, cb = collections.Counter(a["words"]), collections.Counter(b["words"])
    inter = sum((ca & cb).values())
    if not inter:
        return 0.0, 0.0
    cont = inter / min(sum(ca.values()), sum(cb.values()))
    seq = SequenceMatcher(None, a["text"], b["text"], autojunk=False).ratio()
    return seq, cont


def same_progression(a, b, minlen=4):
    """True when two chord sequences agree as far as both go.

    The caiet usually writes chords over the first verse only, while Karban
    marks every verse, so one sequence is often the other continued.  What
    matters is whether they start out the same, in the same key.
    """
    if not a or not b:
        return False
    n = min(len(a), len(b))
    return n >= minlen and a[:n] == b[:n]


def find_pairs(songs):
    out = []
    for i, j in candidates(songs):
        a, b = songs[i], songs[j]
        seq, cont = score(a, b)
        if seq > 0.55 or cont > 0.8:
            out.append((i, j, seq, cont))
    return sorted(out, key=lambda t: -max(t[2], t[3]))


if __name__ == "__main__":
    songs = all_songs()
    pairs = find_pairs(songs)
    print(f"{len(pairs)} perechi peste prag\n")
    by = collections.Counter()
    for i, j, seq, cont in pairs:
        a, b = songs[i], songs[j]
        by[tuple(sorted((a["src"], b["src"])))] += 1
    for k, v in by.most_common():
        print(f"  {v:4d}  {k[0]} <-> {k[1]}")
    print()
    for i, j, seq, cont in pairs[:25]:
        a, b = songs[i], songs[j]
        same = "ACORDURI IDENTICE" if a["chords"] == b["chords"] else "acorduri diferite"
        print(f"  seq={seq:.2f} cont={cont:.2f} {same:18s} | "
              f"{a['src'][:9]:9s} {a['title'][:32]:32s} <-> {b['src'][:9]:9s} {b['title'][:32]}")
