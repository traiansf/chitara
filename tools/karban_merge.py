# -*- coding: utf-8 -*-
"""Merge both Karban volumes into Caiet-chitara.md.

Run this against the caiet *before* the Karban songs were added: it reads the
markdown as its starting point, so running it over its own output would merge
the two volumes in a second time.  ``git checkout <commit-before> --
Caiet-chitara.md`` first.

Songs that already exist in the caiet are kept side by side with Karban's
reading as ``<titlu> (I)`` / ``(II)``, unless the two share a chord progression
in the same key *and* near-identical words, in which case one entry is enough.
Karban's metadata wins wherever the two disagree.  The colinde become a third
part of the book, and the caiet's own carols move there with them.

.. note:: This runs before tools/reorganize_parts.py, on the flat three-part
   layout with songs at ``###``.  reorganize_parts.py reads either level, so the
   pipeline order is: this step, then the reorganization.
"""
import collections, json, re, sys

sys.path.insert(0, "/home/traian/chitara/tools")
from dedup_lib import SRC, HEAD_RE, gh_slug, sortkey, load, parse_songs, body
from karban_songs import all_songs
from karban_dedup import find_pairs, same_progression
from karban_plan import romanian_share, groups, MERGE_SEQ

LABEL = {"carticica": "Cărticica Karban", "colinde": "Colinde Karban"}
ROMAN = ["I", "II", "III", "IV", "V", "VI"]
PART_TITLE = {
    1: "## Partea I — Cântece de munte și folk românesc",
    2: "## Partea a II-a — Repertoriu internațional",
    3: "## Partea a III-a — Colinde și cântece de iarnă",
}
PART_TOC = {1: "### Partea I (alfabetic)", 2: "### Partea a II-a (alfabetic)",
            3: "### Partea a III-a (alfabetic)"}
PART_LINK = {
    1: "**[Partea I — Cântece de munte și folk românesc](#partea-i--cântece-de-munte-și-folk-românesc)**",
    2: "**[Partea a II-a — Repertoriu internațional](#partea-a-ii-a--repertoriu-internațional)**",
    3: "**[Partea a III-a — Colinde și cântece de iarnă](#partea-a-iii-a--colinde-și-cântece-de-iarnă)**",
}
VARIANT_SUFFIX = re.compile(r"\s*\((?:variant[ăa]|II|III)\)\s*$", re.I)


def base_title(t):
    return VARIANT_SUFFIX.sub("", re.sub(r"\s*\((I{1,3})\)\s*$", "", t)).strip()


def karban_meta(s):
    """Metadata line for a song coming from one of Karban's volumes."""
    bits = []
    artist = s.get("artist") or s.get("section")
    if artist and not artist.lower().startswith("cântece"):
        bits.append(f"**{artist}**")
    comp = (s.get("composer") or "").strip("()").strip()
    if comp and comp not in ("???", ""):
        bits.append(f"muzica/versuri: {comp}")
    bits.append(f"Sursa: {LABEL[s['src']]}, p. {s['page']}")
    return " · ".join(bits)


def caiet_meta(s, extra_artist=None):
    meta = s["meta"]
    if extra_artist and not meta.startswith("**"):
        meta = f"**{extra_artist}** · {meta}"
    return meta


def build():
    songs = all_songs()
    pairs = find_pairs(songs)
    pairs = [p for p in pairs
             if not (songs[p[0]]["src"] == "caiet" and songs[p[1]]["src"] == "caiet")]

    # --- collapse the pairs that are genuinely the same reading ---
    dropped = set()
    for i, j, seq, cont in pairs:
        if i in dropped or j in dropped:
            continue
        if same_progression(songs[i]["chords"], songs[j]["chords"]) and seq > MERGE_SEQ:
            # Karban's reading is preferred over the caiet's, and between his
            # two volumes the colinde win: their diacritics are native, not
            # reconstructed
            rank = {"colinde": 0, "carticica": 1, "caiet": 2}
            keep, drop = sorted((i, j), key=lambda k: rank[songs[k]["src"]])
            dropped.add(drop)
            songs[keep].setdefault("also", []).append(songs[drop])

    # --- parts ---
    share = romanian_share(songs)
    part = {}
    for s in songs:
        if s["src"] == "colinde" or (s["src"] == "carticica" and s.get("section") == "Colinde"):
            part[id(s)] = 3
        elif s["src"] == "caiet":
            part[id(s)] = s["part"]
        else:
            part[id(s)] = 1 if share[id(s)] >= 0.6 else 2

    gs = groups(songs, pairs)
    for g in gs:
        ps = [part[id(songs[i])] for i in g]
        target = 3 if 3 in ps else next(
            (part[id(songs[i])] for i in g if songs[i]["src"] == "caiet"),
            collections.Counter(ps).most_common(1)[0][0])
        for i in g:
            part[id(songs[i])] = target

    # --- variant lettering, group by group ---
    group_of = {}
    for gi, g in enumerate(gs):
        for i in g:
            group_of[i] = gi

    titles = {}
    for gi, g in enumerate(gs):
        members = [i for i in g if i not in dropped]
        if not members:
            continue
        caiet_first = sorted(members, key=lambda i: (songs[i]["src"] != "caiet",
                                                     songs[i]["src"] != "carticica",
                                                     songs[i]["title"]))
        base = base_title(songs[caiet_first[0]]["title"])
        if len(members) == 1:
            titles[caiet_first[0]] = base
        else:
            for n, i in enumerate(caiet_first):
                titles[i] = f"{base} ({ROMAN[n]})"

    out = []
    for i, s in enumerate(songs):
        if i in dropped:
            continue
        title = titles.get(i, base_title(s["title"]) if i in group_of else s["title"])
        if s["src"] == "caiet":
            artist = None
            for other in [songs[j] for j in gs[group_of[i]]] if i in group_of else []:
                if other["src"] != "caiet" and other.get("artist"):
                    artist = other["artist"]         # Karban's attribution wins
                    break
            meta = caiet_meta(s, artist)
            for extra in s.get("also", []):
                meta += f" · {LABEL[extra['src']]}, p. {extra['page']}"
            lines = list(s["body"])
        else:
            meta = karban_meta(s)
            for extra in s.get("also", []):
                meta += (f" · {LABEL[extra['src']]}, p. {extra['page']}"
                         if extra["src"] != "caiet" else "")
            lines = list(s["body"])
        m = re.match(r"^\*\*(.+?)\*\*", meta)
        out.append(dict(title=title, meta=meta, body=lines, part=part[id(s)],
                        artist=m.group(1) if m else None, src=s["src"]))

    out.sort(key=lambda s: (s["part"], sortkey(s["title"])))
    for n, s in enumerate(out, 1):
        s["num"] = n
    anchors = collections.Counter()
    for s in out:
        s["anchor"] = gh_slug(f"{s['num']}. {s['title']}", anchors)
    return out


if __name__ == "__main__":
    songs = build()
    c = collections.Counter(s["part"] for s in songs)
    print(f"{len(songs)} cântece: P1={c[1]} P2={c[2]} P3={c[3]}")
    print("surse:", dict(collections.Counter(s["src"] for s in songs)))
    var = [s for s in songs if re.search(r"\((I{1,3})\)$", s["title"])]
    print(f"intrări marcate ca variante: {len(var)}")


# --------------------------------------------------------------- emission

INTRO_SOURCES = [
    "- **Cărticica Karban** — *Cărticică de cântece pentru chitară*, Eugen Karban (v2.0, eugenkarban.de)",
    "- **Colinde Karban** — *Colinde, cântece de Crăciun și de iarnă*, Eugen Karban (2008)",
]


def emit(songs, src=SRC):
    old = load(src)
    parts = {p: [s for s in songs if s["part"] == p] for p in (1, 2, 3)}

    def toc(entries):
        return [f"{s['num']}. [{s['title']}" +
                (f" — {s['artist']}" if s["artist"] else "") +
                f"](#{s['anchor']})" for s in entries]

    def blocks(entries):
        out = []
        for s in entries:
            out += [f"### {s['num']}. {s['title']}", "", s["meta"], "", "```text"]
            out += [l.rstrip() for l in s["body"]]
            out += ["```", ""]
        return out + ["---", ""]

    # ---- artist index: keep the 🌐 links, rebuild the book links ----
    ITEM = re.compile(r", (?=(?:🌐 )?\[)")
    idx_start = old.index("## Index pe artiști")
    online, order = {}, []
    for l in old[idx_start:]:
        if not l.startswith("- **"):
            continue
        art, items = l[4:].split("** — ", 1)
        online[art] = [i for i in ITEM.split(items) if i.startswith("🌐")]
        order.append(art)

    by_artist = collections.defaultdict(list)
    for s in songs:
        if s["artist"]:
            by_artist[s["artist"]].append(s)
    for art in by_artist:
        if art not in online:
            online[art] = []
            order.append(art)
    order.sort(key=sortkey)

    index_lines = []
    for art in order:
        book = sorted(by_artist.get(art, []), key=lambda s: sortkey(s["title"]))
        items = [f"[{s['title']}](#{s['anchor']})" for s in book] + online[art]
        if items:
            index_lines.append(f"- **{art}** — " + ", ".join(items))

    # ---- reassemble ----
    out, i = [], 0
    while i < len(old):
        l = old[i]
        if l.startswith("- **Caiet Christian Adventure**"):
            out += [l] + INTRO_SOURCES
        elif l.startswith("**[Partea I —"):
            out.append(f"{PART_LINK[1]} ({len(parts[1])} cântece)")
        elif l.startswith("**[Partea a II-a —"):
            out += [f"{PART_LINK[2]} ({len(parts[2])} cântece)", "",
                    f"{PART_LINK[3]} ({len(parts[3])} cântece)"]
        elif l == PART_TOC[1]:
            out += [l, ""] + toc(parts[1]) + [""]
            while old[i + 1] != PART_TOC[2]:
                i += 1
        elif l == PART_TOC[2]:
            out += [l, ""] + toc(parts[2]) + ["", PART_TOC[3], ""] + toc(parts[3]) + [""]
            while old[i + 1] != "---":
                i += 1
        elif l == PART_TITLE[1]:
            out += [l, ""] + blocks(parts[1])
            out += [PART_TITLE[2], ""] + blocks(parts[2])
            out += [PART_TITLE[3], ""] + blocks(parts[3])
            while old[i + 1] != "## Index pe artiști":
                i += 1
        elif l.startswith("- **") and i > idx_start:
            out += index_lines
            while i + 1 < len(old) and old[i + 1].startswith("- **"):
                i += 1
        else:
            out.append(l)
        i += 1

    open(src, "w", encoding="utf-8").write("\n".join(out))
    return parts
