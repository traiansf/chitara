# -*- coding: utf-8 -*-
"""Rearrange Caiet-chitara.md into the four-part structure declared in categorii.json.

Part I gets three subsections; parts II-IV are flat.  Songs keep their bodies
untouched: only the header line and the anchors change.  Running it over its
own output changes nothing, so it is safe to re-run after editing
categorii.json.
"""
import collections, json, re, sys, unicodedata

MD = "/home/traian/chitara/Caiet-chitara.md"
CATS = "/home/traian/chitara/tools/categorii.json"

# (cheie, titlu roman, denumire, subsecțiuni) — ordinea din carte
PARTS = [
    ("I", "Partea I", "Cântece de cabană", [
        ("I.1", "De munte și de drum"),
        ("I.2", "Naționaliste și de dor de țară"),
        ("I.3", "Studențești, de chef și deocheate"),
    ]),
    ("II", "Partea a II-a", "Repertoriu românesc", []),
    ("III", "Partea a III-a", "Repertoriu internațional", []),
    ("IV", "Partea a IV-a", "Colinde și cântece de iarnă", [
        ("IV.1", "Colinde românești"),
        ("IV.2", "Colinde internaționale"),
        ("IV.3", "Cântece de iarnă românești"),
        ("IV.4", "Cântece de iarnă internaționale"),
    ]),
]
# the running number is gone from live (####-level) headings, but a ###-level
# song only ever occurs in the historic flat layout (no subsections yet, so no
# "### I.1 — ..." subsection header to confuse it with) and is always numbered
SONG_RE = re.compile(r"^(?:#### (?:\d+\. )?|### \d+\. )(.+)$")


def gh_slug(text, anchors):
    t = re.sub(r"[^\w\- ]", "", text.strip().lower(), flags=re.UNICODE).replace(" ", "-")
    n = anchors[t]
    anchors[t] += 1
    return t if n == 0 else f"{t}-{n}"


def sortkey(t):
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"^[^a-z0-9]+", "", t)


def parse(lines):
    """Every song in the file, as (title, source-key, body-lines-after-header)."""
    heads = [(i, m) for i, l in enumerate(lines) if (m := SONG_RE.match(l))]
    songs = []
    for k, (i, m) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        for j in range(i + 1, end):
            if lines[j].startswith("## ") or re.match(r"^### [IV]+(\.\d)? — ", lines[j]):
                end = j
                break
        block = lines[i + 1:end]
        while block and (not block[-1].strip() or block[-1].strip() == "---"):
            block.pop()  # the separator before the next part heading is not the song's
        meta = next((l for l in block if l.strip() and not l.startswith("**Ukulele:**")), "")
        src = re.search(r"Sursa: ([^·]+)", meta)
        title = m.group(1).strip()
        songs.append(dict(title=title,
                          key=f"{title} || {src.group(1).strip() if src else '?'}",
                          block=block))
    return songs


def main():
    lines = open(MD, encoding="utf-8").read().split("\n")
    cats = json.load(open(CATS, encoding="utf-8"))
    songs = parse(lines)

    missing = [s["key"] for s in songs if s["key"] not in cats]
    if missing:
        sys.exit(f"{len(missing)} cântece lipsesc din categorii.json, primul: {missing[0]}")

    # ---- distribute into sections, alphabetically, and number 1..N across the book
    buckets = collections.defaultdict(list)
    for s in songs:
        buckets[cats[s["key"]]["sectiune"]].append(s)
    order = [(p, sub) for p, _, _, subs in PARTS for sub in (subs or [(p, None)])]
    unknown = set(buckets) - {sub[0] for _, sub in order}
    if unknown:
        sys.exit(f"secțiuni necunoscute în categorii.json: {sorted(unknown)}")

    anchors = collections.Counter()
    for _, (sec, _) in order:
        for s in sorted(buckets[sec], key=lambda s: sortkey(s["title"])):
            s["slug"] = gh_slug(s["title"], anchors)

    # ---- rebuild the file: intro and annex are kept verbatim
    intro = lines[:lines.index("## Cuprins")]
    annex = lines[lines.index("## Anexă: dicționar de acorduri"):]

    out = list(intro)
    out += ["## Cuprins", ""]
    for pkey, roman, name, subs in PARTS:
        total = sum(len(buckets[s[0]]) for s in (subs or [(pkey, None)]))
        head = f"{roman} — {name}"
        out += [f"**[{head}](#{gh_slug(head, anchors)})** ({total} cântece)", ""]
        for sec, subname in subs:
            label = f"{sec} — {subname}"
            out += [f"- [{label}](#{gh_slug(label, anchors)}) ({len(buckets[sec])} cântece)"]
        if subs:
            out += [""]
    out += ["**[Index pe artiști](#index-pe-artiști)** · "
            "**[Anexă: dicționar de acorduri](#anexă-dicționar-de-acorduri)**", ""]

    for pkey, roman, name, subs in PARTS:
        for sec, subname in (subs or [(pkey, None)]):
            title = f"{sec} — {subname}" if subname else f"{roman} — {name}"
            out += [f"### {title} (alfabetic)", ""]
            for s in sorted(buckets[sec], key=lambda s: sortkey(s["title"])):
                out.append(f"- [{s['title']}](#{s['slug']})")
            out += [""]

    artist_index = collections.defaultdict(list)
    for pkey, roman, name, subs in PARTS:
        out += ["---", "", f"## {roman} — {name}", ""]
        for sec, subname in (subs or [(pkey, None)]):
            if subname:
                out += [f"### {sec} — {subname}", ""]
            for s in sorted(buckets[sec], key=lambda s: sortkey(s["title"])):
                out += [f"#### {s['title']}"] + s["block"] + [""]
                meta = next((l for l in s["block"] if l.strip()), "")
                if (am := re.match(r"^\*\*(.+?)\*\*", meta)):
                    artist_index[am.group(1)].append((s["title"], s["slug"]))

    out += ["---", "", "## Index pe artiști", ""]
    for a in sorted(artist_index, key=sortkey):
        links = ", ".join(f"[{t}](#{sl})" for t, sl in artist_index[a])
        out.append(f"- **{a}** — {links}")
    out += [""] + annex

    open(MD, "w", encoding="utf-8").write("\n".join(out))
    print(f"{len(songs)} cântece rearanjate")
    for _, (sec, _) in order:
        print(f"  {sec:4} {len(buckets[sec]):4}")


if __name__ == "__main__":
    main()
