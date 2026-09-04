# -*- coding: utf-8 -*-
"""Restore ă, ș, ț in the Cărticica text.

Karban's Cărticica types only â and î; where ă, ș and ț belong it writes plain
a, s and t.  The rest of the caiet spells them out, so the caiet itself — plus
Karban's own colinde volume, which is fully accented — is the reference corpus:
same genre, same vocabulary, and already proof-read.

A word is only rewritten when the corpus is decisive about it.  Everything
uncertain is listed rather than guessed at.
"""
import collections, json, re, sys

sys.path.insert(0, "/home/traian/chitara/tools")
from dedup_lib import load, parse_songs, body

CAIET = "/home/traian/chitara/Caiet-chitara.md"
COLINDE = "/home/traian/chitara/tools/karban_colinde.json"
CARTICICA = "/home/traian/chitara/tools/karban_carticica.json"
RO_FORMS = "/home/traian/chitara/tools/data/ro_forms.txt"

# the letters Cărticica drops; â and î it already writes
FLAT = str.maketrans("ăĂșȘțȚşŞţŢ", "aAsStTsStT")
WORD = re.compile(r"[A-Za-zÀ-ÿĂăȘșȚțÎîÂâ]+")
CHORD_MARK = re.compile(r"\[[^\]]*\]")

# a dominant form must be at least this share of the sightings
DOMINANCE = 0.8


def flat(w):
    return w.translate(FLAT)


def build_dictionary(keys):
    """flat form -> the real Romanian words that flatten to it.

    Only keys the Cărticica actually uses are kept, so the two million
    expanded forms never all sit in memory at once.
    """
    index = collections.defaultdict(set)
    with open(RO_FORMS, encoding="utf-8") as f:
        for w in f:
            w = w.strip()
            k = flat(w)
            if k in keys:
                index[k].add(w)
    return index


def corpus_lines():
    """Accented reference text: the caiet, minus what this script produced.

    Once the Cărticica is merged in, the caiet contains its own restored
    output; feeding that back would let a wrong guess reinforce itself.
    Karban's colinde stay — their diacritics come from the source.
    """
    lines = load(CAIET)
    text = [l for s in parse_songs(lines)
            if "Cărticica Karban" not in s["meta"]
            for l in body(lines, s)]
    for s in json.load(open(COLINDE)):
        text += s["body"] + [s["title"], s["artist"] or "", s["composer"] or ""]
    return [[w.lower() for w in WORD.findall(CHORD_MARK.sub(" ", l))] for l in text]


def build_lexicon():
    """Frequencies and one-word context, learned from the accented corpus.

    Whether a flat ``ca`` is *ca* or *că* cannot be settled by a dictionary —
    both are words — but the neighbouring word usually settles it.  Context is
    keyed on the *flat* neighbour, because at the point of use the neighbours
    are themselves still unaccented.
    """
    prior = collections.defaultdict(collections.Counter)
    left = collections.defaultdict(collections.Counter)
    right = collections.defaultdict(collections.Counter)
    for seq in corpus_lines():
        for i, w in enumerate(seq):
            k = flat(w)
            prior[k][w] += 1
            if i:
                left[(k, flat(seq[i - 1]))][w] += 1
            if i + 1 < len(seq):
                right[(k, flat(seq[i + 1]))][w] += 1
    return prior, left, right


def from_context(k, prev, nxt, tables, minn=3, dom=0.8):
    prior, left, right = tables
    for tab, key in ((left, (k, prev)), (right, (k, nxt))):
        c = tab.get(key)
        if c and sum(c.values()) >= minn:
            top, n = c.most_common(1)[0]
            if n / sum(c.values()) >= dom:
                return top
    return None


def match_case(src, dst):
    if src.isupper() and len(src) > 1:
        return dst.upper()
    if src[:1].isupper():
        return dst[:1].upper() + dst[1:]
    return dst


def main():
    tables = build_lexicon()
    corpus = tables[0]
    songs = json.load(open(CARTICICA))

    # every flat form the Cărticica uses, chords lifted out so that a word
    # split by an inline chord is still seen whole
    keys = set()
    for s in songs:
        for l in s["body"] + [s["title"], s.get("artist") or ""]:
            for w in WORD.findall(CHORD_MARK.sub("", l)):
                keys.add(flat(w).lower())
    words = build_dictionary(keys)

    stats = collections.Counter()
    ambiguous, unknown = collections.Counter(), collections.Counter()

    def fix_word(w, prev=None, nxt=None):
        key = flat(w).lower()
        cands = words.get(key, set())
        freq = corpus.get(key, collections.Counter())

        if len(cands) == 1:
            pick = next(iter(cands))
        elif cands:
            # the dictionary allows several spellings; let the caiet decide
            scored = collections.Counter({c: freq.get(c, 0) for c in cands})
            top, n = scored.most_common(1)[0]
            total = sum(scored.values())
            if total and n / total >= DOMINANCE:
                pick = top
            else:
                pick = from_context(key, prev, nxt, tables)
                if pick is None or pick not in cands:
                    ambiguous[key] += 1
                    stats["ambiguu"] += 1
                    return w
                stats["din_context"] += 1
        elif freq:
            top, n = freq.most_common(1)[0]
            if n / sum(freq.values()) >= DOMINANCE:
                pick = top
            else:
                pick = from_context(key, prev, nxt, tables)
                if pick is None:
                    ambiguous[key] += 1
                    stats["ambiguu"] += 1
                    return w
                stats["din_context"] += 1
        else:
            unknown[w.lower()] += 1
            stats["necunoscut"] += 1
            return w

        if len(pick) != len(w):
            stats["necunoscut"] += 1
            return w
        out = match_case(w, pick)
        stats["corectat" if out != w else "neschimbat"] += 1
        return out

    def fix_line(l):
        """Fix a line's words with the inline chords lifted out of the way.

        Chords are written inside the word they fall on — ``des[E]chide`` —
        so they have to be removed before the word can be recognised.  Every
        substitution is a same-length letter swap (a->ă, s->ș, t->ț), so the
        chords go back at the offsets they came from.
        """
        marks, plain, pos = [], [], 0
        for m in CHORD_MARK.finditer(l):
            plain.append(l[pos:m.start()])
            marks.append((sum(len(x) for x in plain), m.group(0)))
            pos = m.end()
        plain.append(l[pos:])
        text = "".join(plain)

        toks = list(WORD.finditer(text))
        flats = [flat(m.group(0)).lower() for m in toks]
        pieces, pos = [], 0
        for i, m in enumerate(toks):
            pieces.append(text[pos:m.start()])
            pieces.append(fix_word(m.group(0),
                                   flats[i - 1] if i else None,
                                   flats[i + 1] if i + 1 < len(toks) else None))
            pos = m.end()
        pieces.append(text[pos:])
        fixed = "".join(pieces)
        assert len(fixed) == len(text), (text, fixed)

        out, prev = [], 0
        for off, mark in marks:
            out.append(fixed[prev:off])
            out.append(mark)
            prev = off
        out.append(fixed[prev:])
        return "".join(out)

    for s in songs:
        s["body"] = [fix_line(l) for l in s["body"]]
        s["title"] = fix_line(s["title"])
        for k in ("artist", "composer", "section"):
            if s.get(k):
                s[k] = fix_line(s[k])

    json.dump(songs, open(CARTICICA, "w"), ensure_ascii=False, indent=1)
    tot = sum(stats.values())
    print(f"dicționar: {len(words)} forme plate relevante | corpus: {len(corpus)} forme")
    print(f"{tot} cuvinte: corectate {stats['corectat']}, deja corecte "
          f"{stats['neschimbat']}, decise din context {stats['din_context']}, "
          f"ambigue {stats['ambiguu']}, necunoscute {stats['necunoscut']}")
    print(f"\nambiguități rămase ({len(ambiguous)} forme, {sum(ambiguous.values())} apariții):")
    for k, n in ambiguous.most_common(12):
        print(f"   {k:16s} x{n:<4d} {sorted(words.get(k, []))[:5]}")
    print(f"\nnecunoscute ({len(unknown)} forme):", [w for w, _ in unknown.most_common(15)])


if __name__ == "__main__":
    main()
