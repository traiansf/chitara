"""Extract Caieteng.pdf into structured songs JSON."""
import pymupdf as fitz
import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_common import (page_lines, line_text_and_map, is_chord_text,
                            align_chords, standalone_chord_text)

FONT_MAPS = {}  # no Romanian diacritic hacks in this book
TITLE_RE = re.compile(r"^\s*(\d+)\s*\.\s*(.+)$")

doc = fitz.open(Path(__file__).resolve().parent.parent / "surse" / "Caieteng.pdf")
songs = []
cur = None

# titles typeset in decorative WordArt fonts that we drop; recovered from the index
PAGE_TITLE_OVERRIDES = {26: (23, "SEASONS IN THE SUN")}

for pno in range(4, 73):  # pages 5..73
    page = doc[pno]
    if pno + 1 in PAGE_TITLE_OVERRIDES:
        num, title = PAGE_TITLE_OVERRIDES[pno + 1]
        if cur:
            songs.append(cur)
        cur = {"src": "caieteng", "num": num, "title": title,
               "artist": None, "page": pno + 1, "lines": []}
    lines = page_lines(page, FONT_MAPS)
    if not lines:
        continue
    body_x = [l["chars"][0][1] for l in lines
              if l["chars"] and l["chars"][0][4] >= 9.5]
    left_x = min(body_x) if body_x else 36.0
    classified = []
    for l in lines:
        sizes = [c[4] for c in l["chars"] if c[0].strip()]
        maxsz = max(sizes) if sizes else 0
        fonts = {c[5] for c in l["chars"] if c[0].strip()}
        text, xs = line_text_and_map(l, left_x, FONT_MAPS)
        stripped = text.strip()
        if not stripped:
            continue
        kind = "lyric"
        if maxsz >= 13.5 and "Helvetica-Bold" in fonts:
            kind = "title"
        elif re.fullmatch(r"\d+", stripped) and maxsz <= 10.5:
            kind = "pageno"
        elif is_chord_text(stripped):
            kind = "chord"
        elif maxsz <= 9.5:
            kind = "small"  # artist credit or small note
        classified.append({"line": l, "text": text, "xs": xs, "kind": kind})
    merged = []
    for c in classified:
        if c["kind"] == "title" and merged and merged[-1]["kind"] == "title" \
           and c["line"]["y"] - merged[-1]["line"]["y"] < 20:
            merged[-1]["text"] = merged[-1]["text"].rstrip() + " " + c["text"].strip()
        else:
            merged.append(c)
    prev_y = None
    for j, c in enumerate(merged):
        if c["kind"] == "pageno":
            continue
        if c["kind"] == "title":
            m = TITLE_RE.match(c["text"].strip())
            if m:
                if cur:
                    songs.append(cur)
                cur = {"src": "caieteng", "num": int(m.group(1)),
                       "title": m.group(2).strip(), "artist": None,
                       "page": pno + 1, "lines": []}
                prev_y = c["line"]["y"]
                continue
        if cur is None:
            continue
        y = c["line"]["y"]
        if c["kind"] == "small" and not cur["lines"] and cur["artist"] is None:
            cur["artist"] = c["text"].strip()
            prev_y = y
            continue
        if prev_y is not None and y - prev_y > 24:
            if cur["lines"] and cur["lines"][-1] != "":
                cur["lines"].append("")
        prev_y = y
        if c["kind"] == "chord":
            nxt = None
            if j + 1 < len(merged):
                n = merged[j + 1]
                if n["kind"] in ("lyric", "small") and n["line"]["y"] - y < 17:
                    nxt = n
            if nxt is not None:
                cur["lines"].append(align_chords(c["line"], nxt["text"], nxt["xs"], left_x, FONT_MAPS))
            else:
                cur["lines"].append(standalone_chord_text(c["line"], left_x, FONT_MAPS))
        else:
            cur["lines"].append(c["text"])

if cur:
    songs.append(cur)

with open("caieteng_songs.json", "w") as f:
    json.dump(songs, f, ensure_ascii=False, indent=1)
print(f"{len(songs)} songs extracted")
arts = sum(1 for s in songs if s["artist"])
print(f"{arts} with artist line")
for s in songs[:4] + songs[-2:]:
    print(s["num"], s["title"], "|", s["artist"], f"(p.{s['page']}, {len(s['lines'])} l)")
