#!/usr/bin/env python3
"""Merge the addendum's online-only songs into Caiet-chitara.md's "Index pe artiști".

For each artist section in Caiet-chitara-addendum.md, duplicate uploads of the
same title are collapsed to the version with the best score on tabulaturi.ro
(hearts + stars: favouriteCount + rating*ratingCount, from /api/artist/<slug>).
The winners are appended to the artist's index line as 🌐-marked external links;
artists absent from the index get a new line at the alphabetical position.

Idempotent: existing 🌐 entries and the legend line are stripped before merging.
"""

import json
import re
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAIET = ROOT / "Caiet-chitara.md"
ADDENDUM = ROOT / "Caiet-chitara-addendum.md"
CACHE = Path(
    "/tmp/claude-1000/-home-traian-chitara/1f3746d6-21fd-4c48-837c-9b899e727c55/scratchpad/tabulaturi-api"
)
API = "https://www.tabulaturi.ro/api/artist/{slug}"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) caiet-chitara-index/1.0"}

# addendum artist name -> index artist name, where diacritic folding isn't enough
ARTIST_ALIASES = {"florian pittis": "florian pitis"}

LEGEND = (
    "*🌐 = piesă disponibilă doar online, pe tabulaturi.ro — linkul duce la "
    "varianta cu cele mai multe aprecieri (inimi și stele).*"
)

RO_DIACRITICS = set("ăâîșțĂÂÎȘȚ")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def parse_addendum():
    """-> {artist_name: {"slug": str, "entries": [(title, url, tabslug)]}}"""
    artists = {}
    artist = None
    for line in ADDENDUM.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^## (.+) \(\d+\)\s*$", line)
        if m:
            artist = m.group(1)
            artists[artist] = {"slug": None, "entries": []}
            continue
        m = re.match(r"^- \[(.+?)\]\((https://www\.tabulaturi\.ro/acorduri/([^/]+)/([^)]+))\)", line)
        if m and artist:
            title, url, aslug, tabslug = m.groups()
            artists[artist]["slug"] = aslug
            artists[artist]["entries"].append((title.strip(), url, tabslug))
    return artists


def fetch_artist(slug: str) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{slug}.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    req = urllib.request.Request(API.format(slug=slug), headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    cached.write_bytes(data)
    time.sleep(0.5)
    return json.loads(data)


def score(tab: dict) -> float:
    return tab.get("favouriteCount", 0) + tab.get("rating", 0) * tab.get("ratingCount", 0)


def pick_best(entries, tabs_by_slug):
    """Collapse (title, url, tabslug) duplicates by normalized title; keep best score."""
    groups = {}
    for title, url, tabslug in entries:
        groups.setdefault(norm(title), []).append((title, url, tabslug))
    picked = []
    for key, group in groups.items():
        def rank(e):
            t = tabs_by_slug.get(e[2], {})
            return (score(t), t.get("ratingCount", 0), t.get("favouriteCount", 0), -t.get("id", 0))
        best = max(group, key=rank)
        # display the most diacritic-rich spelling in the group, matching caiet style
        display = max((t for t, _, _ in group), key=lambda t: sum(c in RO_DIACRITICS for c in t))
        picked.append((key, display, best[1]))
    picked.sort(key=lambda p: p[0])
    return picked


def main():
    addendum = parse_addendum()
    text = CAIET.read_text(encoding="utf-8")

    # idempotence: drop legend + any previously inserted 🌐 entries
    text = text.replace("\n\n" + LEGEND, "")
    text = re.sub(r", 🌐 \[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"^- \*\*[^*]+\*\* — 🌐 .*\n", "", text, flags=re.M)

    lines = text.splitlines(keepends=True)
    start = next(i for i, l in enumerate(lines) if l.startswith("## Index pe artiști"))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("---"))

    index = {}  # norm name -> line number (first occurrence wins)
    for i in range(start, end):
        m = re.match(r"- \*\*(.+?)\*\* — ", lines[i])
        if m:
            index.setdefault(norm(m.group(1)), i)

    stats, missing_meta, new_rows = [], [], []
    for artist, info in addendum.items():
        tabs_by_slug = {t["slug"]: t for t in fetch_artist(info["slug"]).get("tabs", [])}
        for _, _, tabslug in info["entries"]:
            if tabslug not in tabs_by_slug:
                missing_meta.append(f"{artist}: {tabslug}")
        picked = pick_best(info["entries"], tabs_by_slug)
        links = ", ".join(f"🌐 [{title}]({url})" for _, title, url in picked)
        key = ARTIST_ALIASES.get(norm(artist), norm(artist))
        if key in index:
            i = index[key]
            lines[i] = lines[i].rstrip("\n") + ", " + links + "\n"
        else:
            new_rows.append((key, f"- **{artist}** — {links}\n"))
        stats.append((artist, len(info["entries"]), len(picked), key in index))

    # insert new artist rows at their alphabetical (diacritic-folded) position
    for key, row in sorted(new_rows, reverse=True):
        pos = end
        for i in range(start + 1, end):
            m = re.match(r"- \*\*(.+?)\*\* — ", lines[i])
            if m and norm(m.group(1)) > key:
                pos = i
                break
        lines.insert(pos, row)
        end += 1

    lines[start] = lines[start].rstrip("\n") + "\n\n" + LEGEND + "\n"
    CAIET.write_text("".join(lines), encoding="utf-8")

    total_in = sum(s[1] for s in stats)
    total_out = sum(s[2] for s in stats)
    print(f"{len(stats)} artists: {total_in} addendum entries -> {total_out} unique songs inserted")
    print(f"new index rows: {[a for a, r in [(s[0], s[3]) for s in stats] if not r]}")
    if missing_meta:
        print(f"\n{len(missing_meta)} entries without API metadata (kept, score 0):")
        for m in missing_meta[:20]:
            print("  " + m)


if __name__ == "__main__":
    main()
