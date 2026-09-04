# -*- coding: utf-8 -*-
"""Group the duplicates across the three corpora and assign each song a part."""
import collections, json, re, sys

sys.path.insert(0, "/home/traian/chitara/tools")
from karban_songs import all_songs, strip_accents
from karban_dedup import find_pairs, same_progression

RO_FORMS = "/home/traian/chitara/tools/data/ro_forms.txt"
MERGE_SEQ = 0.9


def romanian_share(songs):
    """Fraction of each song's words that are real Romanian, for part I vs II."""
    # lyric_words strips the diacritics off, so the dictionary has to be
    # flattened the same way before the two can be compared
    needed = {w for s in songs for w in s["words"]}
    known = set()
    with open(RO_FORMS, encoding="utf-8") as f:
        for w in f:
            w = strip_accents(w.strip())
            if w in needed:
                known.add(w)
    # judge by the opening verses: a song can carry translations after them
    # ("La Mulți Ani!" prints the English and German words too)
    out = {}
    for s in songs:
        ws = [w for w in s["words"] if len(w) > 2][:40]
        out[id(s)] = sum(w in known for w in ws) / max(len(ws), 1)
    return out


def groups(songs, pairs):
    parent = list(range(len(songs)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j, seq, cont in pairs:
        a, b = find(i), find(j)
        if a != b:
            parent[a] = b
    out = collections.defaultdict(list)
    for i in range(len(songs)):
        out[find(i)].append(i)
    return [v for v in out.values() if len(v) > 1]


def main():
    songs = all_songs()
    pairs = find_pairs(songs)
    # pairs inside the caiet are already resolved as (I)/(II)
    pairs = [p for p in pairs
             if not (songs[p[0]]["src"] == "caiet" and songs[p[1]]["src"] == "caiet")]

    gs = groups(songs, pairs)
    print(f"{len(gs)} grupuri de duplicate, {sum(len(g) for g in gs)} cântece implicate")
    print("  mărimi:", dict(collections.Counter(len(g) for g in gs)))

    share = romanian_share(songs)
    colinde_titles = {s["title"] for s in songs if s["src"] == "colinde"}

    part = {}
    for s in songs:
        if s["src"] == "colinde":
            p = 3
        elif s["src"] == "carticica" and s.get("section") == "Colinde":
            p = 3
        elif s["src"] == "caiet":
            p = s["part"]
        else:
            p = 1 if share[id(s)] >= 0.6 else 2
        part[id(s)] = p

    # a group settles on one part: colinde wins, else the caiet's, else majority
    for g in gs:
        ps = [part[id(songs[i])] for i in g]
        target = 3 if 3 in ps else next((part[id(songs[i])] for i in g
                                         if songs[i]["src"] == "caiet"),
                                        collections.Counter(ps).most_common(1)[0][0])
        for i in g:
            part[id(songs[i])] = target

    counts = collections.Counter(part[id(s)] for s in songs)
    print("\nrepartiție pe părți (înainte de fuziuni):", dict(sorted(counts.items())))

    merges = sum(1 for i, j, seq, cont in pairs
                 if same_progression(songs[i]["chords"], songs[j]["chords"]) and seq > MERGE_SEQ)
    print(f"perechi care fuzionează: {merges}")
    print(f"total estimat: {len(songs) - merges} cântece")

    foreign = [s for s in songs if s["src"] == "carticica" and part[id(s)] == 2]
    print(f"\ndin Cărticica în Partea a II-a ({len(foreign)}):",
          [s["title"][:26] for s in foreign][:12])
    return songs, pairs, gs, part


if __name__ == "__main__":
    main()
