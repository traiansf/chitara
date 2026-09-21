# -*- coding: utf-8 -*-
"""Group the duplicate songs of Caiet-chitara.md.

Fifteen songs appear twice in the caiet under different titles (the three
source booklets overlap).  Only where the two blocks share the *same chord
progression in the same key* is one of them dropped and its metadata folded
into the survivor.  Everywhere else both blocks are kept — the chords or the
lyrics genuinely differ — but they are retitled ``<base> (I)`` / ``<base> (II)``
and moved next to each other, following the caiet's existing convention for
same-titled songs.

Song bodies are never touched: inline ``[C]`` chord markers stay as they are.

.. note:: This runs before tools/reorganize_parts.py, on the flat three-part
   layout with songs at ``###``.  reorganize_parts.py reads either level, so the
   pipeline order is: this step, then the reorganization.
"""
import collections, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dedup_lib import SRC, HEAD_RE, gh_slug, sortkey, load, parse_songs

T = "https://www.tabulaturi.ro/acorduri"

# --- identical chord progression, same key: keep one, merge the metadata ----
# keep -> (dropped, merged metadata line)
MERGES = {
    48: (184, f"**Carmen Ciocolata** · alt titlu: „Ninge” · Sursa: Caiet Christian Adventure, p. 38 · Caiet cabană RO, p. 29 · [tabulaturi.ro]({T}/mihai-margineanu/cand-te-scuturi-de-zapada-2817) · [tabulaturi.ro („Ninge”)]({T}/cantece-de-munte/ninge-596)"),
    94: (200, "**Bmby** · alt titlu: „Ochii căprui” · Sursa: Caiet Christian Adventure, p. 61 · Caiet cabană RO, p. 54"),
}

# --- chords and/or lyrics differ: keep both, side by side, as (I) and (II) ---
# (I) is always the song that already carries the shared base title.
VARIANTS = [
    (12, 24),    # Amintiri din Făgăraș      / Azi totul pare schimbat
    (27, 234),   # Balada fulgerată de vânt  / Rău mă dor ochii mă dor
    (52, 203),   # Cântec șoptit             / Odată am ucis o vrabie...
    (101, 156),  # Dragoste în fân           / La strâns de fân
    (111, 108),  # Fata munților             / Fata din Crai
    (112, 199),  # Fată verde                / Ochi negri, ochi de țigan
    (132, 235),  # Imnul Dianei              / Refugiul Diana
    (178, 206),  # Moartea unui alpinist     / Omagiul unui alpinist
    (190, 169),  # Nu te mai iubesc          / Mai ții minte seara-n care?
    (195, 161),  # Nunta pe Caraiman         / Logodnă pe Caraiman
    (248, 193),  # Scrisoare de rămas bun    / Numărători de ploi
    (304, 305),  # Visul                     / Visul (II)
    (322, 326),  # Don't Cry                 / "Dust in the Wind"
]

# "Omagiul unui alpinist (II)" is a different song by Darwin, not a variant;
# once the pair above moves under "Moartea unui alpinist" it is the only song
# left with that title, so it loses the now-meaningless suffix.
RETITLE = {207: "Omagiul unui alpinist"}

# The caiet prints Guns'n'Roses' "Don't Cry" twice, the second time under the
# wrong title and artist; say so rather than repeating the error.
# "Visul (III)" (Karma) shares the title but is a different song; now that it
# sits right below the two real variants, say so.
DISAMBIGUATE = {
    306: "alt cântec cu același titlu",
}

VARIANT_META = {
    326: "variantă a cântecului „Don't Cry” · Sursa: Caiet Christian Adventure, p. 193 (unde apare greșit intitulat „Dust in the Wind”, atribuit Kansas)",
}

ROMAN = re.compile(r" \((?:I{1,3}|IV|V)\)$")
DROPPED = {d for d, _ in MERGES.values()}
SECOND = {b: a for a, b in VARIANTS}


def variant_meta(meta, base, own_title):
    """Metadata line for a (II) block: keep it, prefixed with the variant note."""
    note = f"variantă a cântecului „{base}”"
    plain = ROMAN.sub("", own_title)
    if plain != base:
        note += f", cu titlul „{plain}”"
    m = re.match(r"^(\*\*.+?\*\* · )(.*)$", meta)
    return (m.group(1) + note + " · " + m.group(2)) if m else note + " · " + meta


def main():
    lines = load()
    songs = parse_songs(lines)
    byn = {s["num"]: s for s in songs}
    assert set(MERGES) | DROPPED | set(SECOND) | {b for _, b in VARIANTS} <= set(byn)

    # ---- new title + metadata for every surviving song ----
    for s in songs:
        s["new_title"] = RETITLE.get(s["num"], s["title"])
        s["new_meta"] = s["meta"]

    for keep, (_, meta) in MERGES.items():
        byn[keep]["new_meta"] = meta

    for num, note in DISAMBIGUATE.items():
        byn[num]["new_meta"] = note + " · " + byn[num]["meta"]

    for first, second in VARIANTS:
        base = byn[first]["title"]
        byn[first]["new_title"] = f"{base} (I)"
        byn[second]["new_title"] = f"{base} (II)"
        byn[second]["new_meta"] = VARIANT_META.get(
            second, variant_meta(byn[second]["meta"], base, byn[second]["title"]))

    # ---- order: original sequence, each (II) pulled up next to its (I) ----
    kept = [s for s in songs if s["num"] not in DROPPED and s["num"] not in SECOND]
    order = []
    for s in kept:
        order.append(s)
        if s["num"] in dict(VARIANTS):
            order.append(byn[dict(VARIANTS)[s["num"]]])
    assert len(order) == len(songs) - len(MERGES)

    # ---- renumber, rebuild each block ----
    new = {}
    for num, s in enumerate(order, 1):
        block = list(lines[s["start"]:s["end"]])
        block[0] = f"### {num}. {s['new_title']}"
        if s["meta_idx"] is not None:
            block[s["meta_idx"] - s["start"]] = s["new_meta"]
        am = re.match(r"^\*\*(.+?)\*\*", s["new_meta"])
        new[num] = dict(num=num, title=s["new_title"], part=s["part"],
                        artist=am.group(1) if am else None, lines=block)

    anchors = collections.Counter()
    for num, s in new.items():
        s["anchor"] = gh_slug(f"{num}. {s['title']}", anchors)

    p1 = [s for s in new.values() if s["part"] == 1]
    p2 = [s for s in new.values() if s["part"] == 2]

    def toc(entries):
        return [f"{s['num']}. [{s['title']}" +
                (f" — {s['artist']}" if s["artist"] else "") +
                f"](#{s['anchor']})" for s in entries]

    # ---- artist index: rebuild book links, keep the 🌐 online links as-is ----
    ITEM = re.compile(r", (?=(?:🌐 )?\[)")
    idx_start = lines.index("## Index pe artiști")
    online, artists = {}, []
    for l in lines[idx_start:]:
        if not l.startswith("- **"):
            continue
        art, items = l[4:].split("** — ", 1)
        online[art] = [i for i in ITEM.split(items) if i.startswith("🌐")]
        artists.append(art)

    by_artist = collections.defaultdict(list)
    for s in new.values():
        if s["artist"]:
            by_artist[s["artist"]].append(s)

    index_lines = []
    for art in artists:
        book = sorted(by_artist.pop(art, []), key=lambda s: sortkey(s["title"]))
        items = [f"[{s['title']}](#{s['anchor']})" for s in book] + online[art]
        if items:
            index_lines.append(f"- **{art}** — " + ", ".join(items))
    assert not by_artist, f"artist missing from index: {list(by_artist)}"

    # ---- reassemble ----
    def block(s):
        b = list(lines[s["start"]:s["end"]])
        while b and b[-1] in ("", "---"):
            b.pop()
        return b

    def part_block(entries):
        out = []
        for s in entries:
            out += new[s["num"]]["lines"] + [""]
        return out + ["---", ""]

    for num, s in new.items():
        s["lines"] = block(order[num - 1])
        s["lines"][0] = f"### {num}. {s['title']}"
        mi = order[num - 1]["meta_idx"]
        if mi is not None:
            s["lines"][mi - order[num - 1]["start"]] = order[num - 1]["new_meta"]

    P1H = next(l for l in lines if l.startswith("## Partea I — "))
    P2H = next(l for l in lines if l.startswith("## Partea a II-a — "))
    IDXH = "## Index pe artiști"

    out, i = [], 0
    while i < len(lines):
        l = lines[i]
        if l.startswith("**[Partea I —"):
            out.append(re.sub(r"\(\d+ cântece\)", f"({len(p1)} cântece)", l))
        elif l.startswith("**[Partea a II-a —"):
            out.append(re.sub(r"\(\d+ cântece\)", f"({len(p2)} cântece)", l))
        elif l == "### Partea I (alfabetic)":
            out += [l, ""] + toc(p1)
            while lines[i + 1] != "### Partea a II-a (alfabetic)":
                i += 1
            out.append("")
        elif l == "### Partea a II-a (alfabetic)":
            out += [l, ""] + toc(p2)
            while lines[i + 1] != "---":
                i += 1
            out.append("")
        elif l == P1H:
            out += [l, ""] + part_block(p1)
            while lines[i + 1] != P2H:
                i += 1
        elif l == P2H:
            out += [l, ""] + part_block(p2)
            while lines[i + 1] != IDXH:
                i += 1
        elif l.startswith("- **") and i > idx_start:
            out += index_lines
            while i + 1 < len(lines) and lines[i + 1].startswith("- **"):
                i += 1
        else:
            out.append(l)
        i += 1

    open(SRC, "w", encoding="utf-8").write("\n".join(out))
    print(f"{len(order)} songs (Partea I: {len(p1)}, Partea a II-a: {len(p2)}); "
          f"{len(MERGES)} eliminate, {len(VARIANTS)} perechi marcate (I)/(II)")


if __name__ == "__main__":
    main()
