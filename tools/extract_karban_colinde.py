# -*- coding: utf-8 -*-
"""Extract "Eugen Karban - Colinde, cântece de Crăciun și de iarnă" into JSON.

A LaTeX-produced PDF.  Two things need care:

* Diacritics arrive as a base letter plus a combining cedilla or breve, and the
  mark may belong to the letter before it (``s¸`` -> ș) or after it (``¸t`` ->
  ț).  The mark is drawn back over its letter but advances the pen past it, so
  it is composed away at the character level, before any spacing or chord
  alignment is computed — normalising later would shift every column.
* Chords are positioned over the syllable where they change, exactly as in the
  caiet, so they are re-aligned from their x coordinates rather than listed.
* Long songs continue in a second column (once in a third), often only for
  part of the page.  Each band of columns is read column by column, and the
  chord dictionary at the foot of a column ends that column, not the song.
"""
import pymupdf as fitz
import json, re, sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from extract_common import (page_lines, line_text_and_map, align_chords,
                            standalone_chord_text, is_chord_text)

PDF = str(_HERE.parent / "surse" / "Eugen Karban - culegere-de-colinde-si-cantece-de-iarna-100.pdf")
OUT = str(_HERE / "karban_colinde.json")
FIRST_PAGE, LAST_PAGE = 6, 113

F_TITLE = "Helvetica-Bold"
F_NOTE = "Helvetica-Oblique"
F_CHORD = "CMR7"
# an italic line before the body is an attribution only if it looks like one;
# the rest are performance notes ("Intro C", "Urarea se recită pe cadența:…")
# and belong with the song, not in its byline
ATTRIB = re.compile(r"^\(|^(tradi[țt]ional|popular|necunoscut)\b", re.I)

# as in the Cărticica, each song closes with a dictionary of its own chords
CHORD_DICT = re.compile(r"^[\s\-•]*Dic[țt]ionar de acorduri")
# the Cărticica writes plain t for ț, and is only accented later
FOOTER = re.compile(r"eugenkarban\.de")
F_LYRIC = "Helvetica"
DECOR = {"LCIRCLE10", "CMSY10", "CMSY7", "CMR10", "CMR5", "CMMI7", "CMMI10"}

CEDILLA, BREVE = "¸", "˘"
AFTER = {("s", CEDILLA): "ș", ("S", CEDILLA): "Ș", ("t", CEDILLA): "ț",
         ("T", CEDILLA): "Ț", ("a", BREVE): "ă", ("A", BREVE): "Ă",
         ("ı", BREVE): "ă", ("i", BREVE): "ă"}
BEFORE = {(CEDILLA, "s"): "ș", (CEDILLA, "S"): "Ș", (CEDILLA, "t"): "ț",
          (CEDILLA, "T"): "Ț", (BREVE, "a"): "ă", (BREVE, "A"): "Ă"}
LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "♯": "#", "♭": "b", "–": "-", "—": "-"}


def compose(chars):
    """Fold combining marks into their base letter, keeping the base's box."""
    out = []
    i = 0
    while i < len(chars):
        c, x0, x1, ymid, size, font = chars[i]
        if c in (CEDILLA, BREVE):
            if out and (out[-1][0], c) in AFTER:
                p = out[-1]
                out[-1] = (AFTER[(p[0], c)],) + p[1:]
                i += 1
                continue
            if i + 1 < len(chars) and (c, chars[i + 1][0]) in BEFORE:
                n = chars[i + 1]
                out.append((BEFORE[(c, n[0])],) + n[1:])
                i += 2
                continue
        # a ligature stands for two characters; both share the glyph's box
        for ch in LIGATURES.get(c, c):
            out.append((ch, x0, x1, ymid, size, font))
        i += 1
    return out


HEADER_Y, FOOTER_Y = 35.0, 810.0   # running header "artist: title" / footer
SEG_GAP = 12.0                     # a wider gap than this separates two columns
TAB_SEG = re.compile(r"^[\d\s|_\-EADGBe]*$")


def cluster(chars):
    """Group characters into visual lines by vertical position, as page_lines."""
    lines = []
    for ch in sorted(chars, key=lambda t: t[3]):
        if lines and abs(ch[3] - lines[-1][-1][3]) <= 3.0:
            lines[-1].append(ch)
        else:
            lines.append([ch])
    out = []
    for cl in lines:
        cl.sort(key=lambda t: t[1])
        out.append({"y": sum(t[3] for t in cl) / len(cl), "chars": cl})
    return out


def segments(chars):
    """Runs of text characters (no chords) separated by a column-sized gap."""
    segs = []
    for c in chars:
        if c[5] == F_CHORD or not c[0].strip():
            continue
        if segs and c[1] - segs[-1][-1][2] < SEG_GAP:
            segs[-1].append(c)
        else:
            segs.append([c])
    return segs


def find_column_edges(lines, lo=150.0, hi=450.0, min_hits=5):
    """x of each column start after the first on a multi-column page.

    Karban sets long songs on two columns (once on three), and sometimes only
    part of the page: verses beside verses, then a full-width note, then
    columns again.  A column shows up as many text runs starting at one and
    the same x in the middle of the page; tablature digits, the only other
    thing that lines up there, are left out.
    """
    starts = {}
    for L in lines:
        for seg in segments(L["chars"]):
            x0 = seg[0][1]
            text = "".join(c[0] for c in seg)
            if lo <= x0 <= hi and not TAB_SEG.match(text):
                starts.setdefault(round(x0 / 2), []).append(x0)
    edges = []
    for k in sorted(starts, key=lambda k: -len(starts[k])):
        hits = [x for j in (k - 1, k, k + 1) for x in starts.get(j, [])]
        if len(hits) < min_hits:
            break
        if all(abs(min(hits) - e) > 60 for e in edges):
            edges.append(min(hits))
    # a column's verses may be indented past its chord-led or note lines:
    # the column starts at the leftmost run just before the busiest x
    return sorted(min(x for v in starts.values() for x in v if e - 20 <= x <= e)
                  for e in edges)


def column_parts(chars):
    """The page's characters as parts in reading order.

    Each part is (column, lines), column 0 being the leftmost: for a
    multi-column band, its columns left to right; a line running across a
    column edge (a note, a long verse) closes the band and is a part of its
    own, column None.
    """
    lines = cluster(chars)
    edges = find_column_edges(lines)
    if not edges:
        return [(None, lines)]

    def crosses(L):
        """True for a line running across a column edge.

        A long verse may end within a few points of the next column, closer
        than SEG_GAP; any blank space right where a column starts still
        tells the two apart.
        """
        for seg in segments(L["chars"]):
            if TAB_SEG.match("".join(c[0] for c in seg)):
                continue                   # see tab_column() below
            for e in edges:
                if not (seg[0][1] < e - SEG_GAP and seg[-1][2] > e + 2):
                    continue
                if not any(abs(b[1] - e) < 1.5 and b[1] - a[2] > 1.5
                           for a, b in zip(seg, seg[1:])):
                    return True
        return False

    def column(c):
        return sum(1 for e in edges if c[1] >= e - 4)

    def tab_column(L):
        """{char: column} for tablature runs, which hang left of their column.

        A tablature's string names (E B G D A E) stand in the gutter, before
        the column the tablature belongs to, so a tab run joins the column
        where it ends, not where it starts.
        """
        out = {}
        for seg in segments(L["chars"]):
            if TAB_SEG.match("".join(c[0] for c in seg)):
                for c in seg:
                    out[id(c)] = column(seg[-1])
        segs = segments(L["chars"])
        for a, b in zip(segs, segs[1:]):
            # a lone string name in the gutter, its digits past the edge
            name = "".join(c[0] for c in a)
            if (len(name) == 1 and name in "EADGBe" and column(a[0]) < column(b[0])
                    and any(0 < e - a[0][1] < 30 for e in edges)):
                out[id(a[0])] = column(b[0])
        return out

    full_ys = [L["y"] for L in lines if crosses(L)]

    def over_full(c):
        # a chord over a full-width line belongs to that line
        return c[5] == F_CHORD and any(0 < y - c[3] < 15 for y in full_ys)

    parts, band = [], [[] for _ in range(len(edges) + 1)]

    def flush():
        for i, col in enumerate(band):
            if col:
                parts.append((i, cluster(col)))
            col.clear()

    for L in lines:
        if crosses(L):
            flush()
            held = [c for M in lines for c in M["chars"]
                    if over_full(c) and 0 < L["y"] - c[3] < 15]
            text = [c for c in L["chars"] if c[5] != F_CHORD]
            parts.append((None, cluster(held + text)))
            continue
        tabs = tab_column(L)
        for c in L["chars"]:
            if not over_full(c):
                band[tabs.get(id(c), column(c))].append(c)
    flush()
    return parts


def classify(chars):
    font = chars[0][5]
    if font == F_CHORD:
        return "chord"
    if font == F_TITLE:
        return "title" if round(chars[0][4], 1) > 10.5 else "artist"
    if font == F_NOTE:
        return "note"
    return "lyric"


def main():
    doc = fitz.open(PDF)
    songs, cur = [], None

    for p in range(FIRST_PAGE, LAST_PAGE + 1):
        # compose per visual line: a cedilla sits lower than its letter, so
        # only the line clustering keeps the two side by side
        chars = []
        for L in page_lines(doc[p], {}):
            kept = [c for c in L["chars"] if c[5] not in DECOR]
            if kept and HEADER_Y < L["y"] < FOOTER_Y:
                chars += compose(kept)

        items = []
        for col, lines in column_parts(chars):
            in_dict = False
            for L in lines:
                text, xs = line_text_and_map(L, L["chars"][0][1], {})
                if not text.strip():
                    continue
                # the chord dictionary closes its column, not the page: on
                # a two-column page the right column still follows it
                if CHORD_DICT.match(text):
                    in_dict = True
                if in_dict:
                    continue
                items.append({"kind": classify(L["chars"]), "line": L,
                              "text": text, "xs": xs, "y": L["y"]})

        for j, it in enumerate(items):
            if it["kind"] == "title":
                cur = dict(title=it["text"].strip(), page=p + 1, artist=None,
                           composer=None, credits=[], body=[])
                songs.append(cur)
                continue
            if cur is None:
                continue
            t = it["text"].strip()
            if it["kind"] == "artist" and not cur["body"]:
                cur["artist"] = None if t == "***" else t
            elif it["kind"] == "note" and not cur["body"]:
                if t.startswith("-"):
                    cur["credits"].append(t)
                elif ATTRIB.match(t) and cur["composer"] is None:
                    cur["composer"] = t
                elif t != "***":
                    cur["body"].append(t)
            elif it["kind"] == "chord":
                nxt = items[j + 1] if j + 1 < len(items) else None
                if nxt and nxt["kind"] in ("lyric", "artist", "note") and nxt["y"] - it["y"] < 15:
                    cur["body"].append(align_chords(it["line"], nxt["text"], nxt["xs"],
                                                    it["line"]["chars"][0][1], {},
                                                    tok_gap=0.5))
                    nxt["kind"] = "lyric"
                else:
                    cur["body"].append(standalone_chord_text(it["line"], it["line"]["chars"][0][1], {}))
            else:
                cur["body"].append(it["text"])

    for s in songs:
        s["title"] = re.sub(r"\s+", " ", s["title"])
        s["body"] = [l for l in s["body"] if not FOOTER.search(l)]
        for i, l in enumerate(s["body"]):
            if CHORD_DICT.match(l):
                s["body"] = s["body"][:i]
                break
        while s["body"] and not s["body"][0].strip():
            s["body"].pop(0)
        while s["body"] and not s["body"][-1].strip():
            s["body"].pop()

    # the closing pages (changelog, tool list) parse as songs but carry no chords
    songs = [s for s in songs
             if len(s["body"]) >= 3 and any(is_chord_text(l) for l in s["body"])]
    json.dump(songs, open(OUT, "w"), ensure_ascii=False, indent=1)
    left = sum(l.count(CEDILLA) + l.count(BREVE) for s in songs for l in s["body"])
    print(f"{len(songs)} colinde, {left} diacritice nerezolvate -> {OUT}")


if __name__ == "__main__":
    main()
