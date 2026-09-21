"""Shared parsing helpers for the duplicate-song removal pass."""
import re, unicodedata, collections
from pathlib import Path

SRC = str(Path(__file__).resolve().parent.parent / "Caiet-chitara.md")
# Songs sit one level below their part's subsection since tools/reorganize_parts.py
# introduced subsections for Part I and Part IV; ### is still accepted so that the
# older pipeline steps, which write the flat layout, can be read back.
# the running number is gone from live (####-level) headings, but a ###-level
# song only ever occurs in the historic flat layout (no subsections yet, so no
# "### I.1 — ..." subsection header to confuse it with) and is always numbered
HEAD_RE = re.compile(r"^(?:#### (?:(\d+)\. )?|### (\d+)\. )(.+)$")
PART_H = re.compile(r"^## Partea (I|a II-a|a III-a|a IV-a) — ")
SUB_H = re.compile(r"^### ([IV]+\.\d) — ")
PART_KEY = {"I": "I", "a II-a": "II", "a III-a": "III", "a IV-a": "IV"}


def gh_slug(text, anchors=None):
    """GitHub-style anchor, matching tools/compile_caiet.py."""
    t = text.strip().lower()
    t = re.sub(r"[^\w\- ]", "", t, flags=re.UNICODE)
    t = re.sub(r" ", "-", t)
    if anchors is None:
        return t
    n = anchors[t]
    anchors[t] += 1
    return t if n == 0 else f"{t}-{n}"


def sortkey(t):
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"^[^a-z0-9]+", "", t)


def load(path=SRC):
    return open(path, encoding="utf-8").read().split("\n")


def parse_songs(lines):
    """-> list of dicts: num, title, part, start, end, meta_idx, meta, artist.

    ``part`` is the section key the song sits in: "I.1", "I.2", "I.3", "II",
    "III" or "IV".
    """
    heads = [(i, m) for i, l in enumerate(lines) if (m := HEAD_RE.match(l))]
    part_of = {}
    part = None
    for i, l in enumerate(lines):
        if m := PART_H.match(l):
            part = PART_KEY[m.group(1)]
        elif m := SUB_H.match(l):
            part = m.group(1)
        elif l.startswith("## "):
            part = None
        part_of[i] = part

    songs = []
    for k, (i, m) in enumerate(heads):
        if part_of[i] is None:
            continue
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        for j in range(i + 1, end):
            if lines[j].startswith("## ") or SUB_H.match(lines[j]):
                end = j
                break
        meta_idx, meta = None, ""
        for j in range(i + 1, end):
            if lines[j].startswith("```"):
                break
            if lines[j].strip() and not lines[j].startswith("**Ukulele:**"):
                meta_idx, meta = j, lines[j].strip()
                break
        am = re.match(r"^\*\*(.+?)\*\*", meta)
        num = m.group(1) or m.group(2)
        songs.append(dict(num=int(num) if num else None,
                          title=m.group(3).strip(),
                          part=part_of[i], start=i, end=end,
                          meta_idx=meta_idx, meta=meta,
                          artist=am.group(1) if am else None))
    return songs


def body(lines, s):
    """Lines inside the ```text fence of song s."""
    out, inb = [], False
    for l in lines[s["start"] + 1:s["end"]]:
        if l.startswith("```"):
            inb = not inb
            continue
        if inb:
            out.append(l)
    return out
