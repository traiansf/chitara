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
"""
import fitz, json, re, sys

sys.path.insert(0, "/home/traian/chitara/tools")
from extract_common import (page_lines, line_text_and_map, align_chords,
                            standalone_chord_text, is_chord_text)

PDF = "/home/traian/chitara/Eugen Karban - culegere-de-colinde-si-cantece-de-iarna-100.pdf"
OUT = "/home/traian/chitara/tools/karban_colinde.json"
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


def find_gutter(lines, lo=240.0, hi=380.0):
    """x of the gutter splitting a two-column page, else None.

    A few pages set a recited stanza beside the sung verses; read in y order
    the two interleave.  No band is ever completely empty — a note line spans
    the full width — so the gutter is the x that the fewest glyphs cross, and
    it counts only if both sides carry real content.
    """
    spans = [(c[1], c[2]) for L in lines if L["y"] > 95 for c in L["chars"]]
    if len(spans) < 40:
        return None
    best, best_n = None, None
    x = lo
    while x < hi:
        n = sum(1 for a, b in spans if a < x < b)
        if best_n is None or n < best_n:
            best, best_n = x, n
        x += 2.0
    left = sum(1 for a, b in spans if b <= best)
    right = sum(1 for a, b in spans if a >= best)
    if best_n <= 3 and left >= 40 and right >= 40:
        return best
    return None


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
        raw = []
        for L in page_lines(doc[p], {}):
            chars = [c for c in L["chars"] if c[5] not in DECOR]
            if chars:
                raw.append({"y": L["y"], "chars": compose(chars)})

        gutter = find_gutter(raw)
        if gutter is None:
            columns = [raw]
        else:
            # a clustered line spans both columns, so split its characters —
            # unless it is a single run of text that merely reaches across,
            # such as a full-width note, which stays whole on its own side
            left, right = [], []
            for L in raw:
                a = [c for c in L["chars"] if c[1] < gutter]
                b = [c for c in L["chars"] if c[1] >= gutter]
                if a and b and b[0][1] - a[-1][2] < 40:
                    (left if len(a) >= len(b) else right).append(L)
                    continue
                if a:
                    left.append({"y": L["y"], "chars": a})
                if b:
                    right.append({"y": L["y"], "chars": b})
            columns = [left, right]

        items = []
        for col in columns:
            for L in col:
                text, xs = line_text_and_map(L, L["chars"][0][1], {})
                if text.strip():
                    items.append({"kind": classify(L["chars"]), "line": L,
                                  "text": text, "xs": xs, "y": L["y"]})

        if items and items[0]["kind"] == "lyric":
            items.pop(0)                       # running header "artist: title"

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
