# -*- coding: utf-8 -*-
"""Extract "Eugen Karban - Cărticica de cântece pentru chitară" into JSON.

The PDF's fonts use a custom encoding: printable characters are shifted by
+29, and a handful of code points stand in for the diacritics the book uses
(only â and î — it writes plain a/s/t where ă/ș/ț belong).  Song structure is
carried by the fonts themselves: one font for titles, another for the artist
section headers, the rest for body text.
"""
import pymupdf as fitz
import json, re, sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from extract_common import page_lines

PDF = str(_HERE.parent / "surse" / "Eugen Karban - carticica-de-cantece-pentru-chitara-200.pdf")
OUT = str(_HERE / "karban_carticica.json")
FIRST_PAGE = 8

F_RUNNING = "MSTT31c48000"   # "Carticica de cântece pentru chitara Ver 2.0"
F_TITLE = "MSTT31c4d500"     # song title
F_SECTION = "MSTT31c46000"   # artist section header

# the closing chapter is guitar theory, not songs
SKIP_SECTIONS = {"Notiuni teoretice"}

DIA = {"k": "â", "v": "î", "Ì": "Î", "\x81": "ü"}

# every song ends with a chord dictionary for the chords it uses; the caiet
# has its own annex, so it is dropped rather than read as part of the song
CHORD_DICT = re.compile(r"^[\s\-•]*Dic[țt]ionar de acorduri")
# the Cărticica writes plain t for ț, and is only accented later
FOOTER = re.compile(r"^\s*(\d+\s+)?Visit my homepage|eugenkarban\.de\s*\d*\s*$")


def decode(c):
    return chr(ord(c) + 29) if 3 <= ord(c) <= 95 else DIA.get(c, c)


def render(L):
    """Line dict -> (font, text), inserting a space wherever the gap warrants."""
    chars = sorted(L["chars"], key=lambda t: t[1])
    out, prev = "", None
    for c, x0, x1, ymid, size, font in chars:
        if prev is not None and x0 - prev > 1.3:
            out += " "
        out += decode(c)
        prev = x1
    return chars[0][5], out.rstrip()


def main():
    doc = fitz.open(PDF)
    songs, cur, section = [], None, None

    for p in range(FIRST_PAGE, len(doc)):
        for L in page_lines(doc[p], {}):
            font, text = render(L)
            if not text.strip() or font == F_RUNNING:
                continue
            if font == F_SECTION:
                section = text.strip()
                continue
            if font == F_TITLE:
                cur = dict(title=text.strip(), section=section, page=p + 1, lines=[])
                songs.append(cur)
                continue
            if cur is not None:
                cur["lines"].append(text)

    # split each song's leading metadata off from its body
    for s in songs:
        meta, body = [], list(s["lines"])
        while body:
            l = body[0].strip()
            if "[" in l or not l:
                break
            if len(meta) >= 4:
                break
            meta.append(l)
            body.pop(0)
        s["artist"] = next((m for m in meta
                            if not m.startswith(("(", "-"))), None) or s["section"]
        s["composer"] = next((m for m in meta if m.startswith("(")), None)
        s["credits"] = [m for m in meta if m.startswith("-")]
        body = [l for l in body if not FOOTER.search(l)]
        for i, l in enumerate(body):
            if CHORD_DICT.match(l):
                body = body[:i]
                break
        while body and not body[0].strip():
            body.pop(0)
        while body and not body[-1].strip():
            body.pop()
        s["body"] = body
        del s["lines"]

    songs = [s for s in songs if s["section"] not in SKIP_SECTIONS]
    json.dump(songs, open(OUT, "w"), ensure_ascii=False, indent=1)
    withch = [s for s in songs if any("[" in l for l in s["body"])]
    print(f"{len(songs)} titluri, {len(withch)} cu acorduri, "
          f"{len({s['section'] for s in songs})} secțiuni de artist -> {OUT}")


if __name__ == "__main__":
    main()
