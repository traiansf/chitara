"""Extract Caietrom.pdf into structured songs JSON."""
import fitz, json, re, sys
from extract_common import (page_lines, line_text_and_map, is_chord_text,
                            align_chords, standalone_chord_text)

FONT_MAPS = {
    "TTE1602088t00": {1: "Ș", 2: "Ă", 3: "Ț"},
    "TTE1ACF518t00": {1: "Ș", 2: "ă", 3: "ș", 4: "ț", 5: "Ț", 6: "Ă"},
    "TTE1AEC7B8t00": {1: "ș", 2: "ț", 3: "ă", 4: "Ț", 5: "Ă", 6: "Ș"},
}

TITLE_RE = re.compile(r"^\s*(\d+)\s*\.\s*(.+)$")

doc = fitz.open("/home/traian/chitara/surse/Caietrom.pdf")
songs = []
cur = None

for pno in range(6, 170):  # pages 7..170
    page = doc[pno]
    lines = page_lines(page, FONT_MAPS)
    if not lines:
        continue
    # song-body left margin: min x0 among non-title, size>=10 chars
    body_x = [l["chars"][0][1] for l in lines
              if l["chars"] and l["chars"][0][4] >= 9.5]
    left_x = min(body_x) if body_x else 36.0
    prev_y = None
    i = 0
    processed = []
    # first pass: classify
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
        if maxsz >= 13.5 and ("Helvetica-Bold" in fonts or "TTE1AEC7B8t00" in fonts):
            kind = "title"
        elif re.fullmatch(r"\d+", stripped) and maxsz <= 10.5:
            kind = "pageno"
        elif maxsz <= 9.5 or is_chord_text(stripped):
            kind = "chord" if is_chord_text(stripped) else "lyric"
        classified.append({"line": l, "text": text, "xs": xs, "kind": kind})
    # merge consecutive title lines
    merged = []
    for c in classified:
        if c["kind"] == "title" and merged and merged[-1]["kind"] == "title" \
           and c["line"]["y"] - merged[-1]["line"]["y"] < 20:
            merged[-1]["text"] = merged[-1]["text"].rstrip() + " " + c["text"].strip()
        else:
            merged.append(c)
    # second pass: build song lines with chord alignment + blank lines
    for j, c in enumerate(merged):
        if c["kind"] == "pageno":
            continue
        if c["kind"] == "title":
            m = TITLE_RE.match(c["text"].strip())
            if m:
                if cur:
                    songs.append(cur)
                cur = {"src": "caietrom", "num": int(m.group(1)),
                       "title": m.group(2).strip(), "page": pno + 1, "lines": []}
                prev_y = c["line"]["y"]
                continue
            # title-sized but not numbered: treat as subtitle/comment
        if cur is None:
            continue
        y = c["line"]["y"]
        if prev_y is not None and y - prev_y > 24:
            if cur["lines"] and cur["lines"][-1] != "":
                cur["lines"].append("")
        prev_y = y
        if c["kind"] == "chord":
            # find next non-chord line close below
            nxt = None
            if j + 1 < len(merged):
                n = merged[j + 1]
                if n["kind"] == "lyric" and n["line"]["y"] - y < 17:
                    nxt = n
            if nxt is not None:
                cur["lines"].append(align_chords(c["line"], nxt["text"], nxt["xs"], left_x, FONT_MAPS))
            else:
                cur["lines"].append(standalone_chord_text(c["line"], left_x, FONT_MAPS))
        else:
            cur["lines"].append(c["text"])

if cur:
    songs.append(cur)

with open("caietrom_songs.json", "w") as f:
    json.dump(songs, f, ensure_ascii=False, indent=1)
print(f"{len(songs)} songs extracted")
for s in songs[:5]:
    print(s["num"], s["title"], f"(p.{s['page']}, {len(s['lines'])} lines)")
print("...")
for s in songs[-3:]:
    print(s["num"], s["title"], f"(p.{s['page']}, {len(s['lines'])} lines)")
