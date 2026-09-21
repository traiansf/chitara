"""Extract caiet-christian-adventure.pdf into structured songs JSON."""
import pymupdf as fitz
import json, re, statistics, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_common import (page_lines, line_text_and_map, is_chord_text,
                            align_chords, standalone_chord_text)

FONT_MAPS = {}
CHAR_W, SPACE_W = 7.2, 3.6

def norm_dia(s):
    return (s.replace("Ş", "Ș").replace("ş", "ș")
             .replace("Ţ", "Ț").replace("ţ", "ț"))

# ---------- 1. parse the index for (book_page -> title, artist, part) ----------
idx = {}
txt = open("caiet-christian-adventure.txt").read()
lines = txt.split("\n")
part = 1
artist_header = None
ENTRY = re.compile(r"^\s*\d+\.\s*(.+?)\s*\.{3,}\s*,?\.*\s*(\d+)\s*$")
HDR = re.compile(r"^\s{0,8}([A-Z0-9][^.]{1,40})$")
for i, ln in enumerate(lines):
    if i > 330:
        break
    if "PARTEA A II-A" in ln:
        part = 2
        continue
    ln2 = ln.rstrip()
    m = ENTRY.match(ln2)
    if m:
        body, page = m.group(1), int(m.group(2))
        body = re.sub(r"[\s.,]+$", "", body)
        am = re.search(r"\(([^()]*)\)?\s*$", body)
        if am and "(" in body:
            artist = am.group(1).strip()
            title = body[: am.start()].strip()
        else:
            artist = artist_header
            title = body.strip()
        title = re.sub(r"\.{2,}", "", title).strip()
        idx[page] = {"title": norm_dia(title), "artist": norm_dia(artist) if artist else None, "part": part}
    elif part == 2:
        h = ln.strip()
        if h and not h.isdigit() and "pag" not in h.lower() and "TRUPE" not in h and len(h) < 40 and not h.startswith("PARTEA"):
            artist_header = h

print(f"index entries: {len(idx)} (part1: {sum(1 for v in idx.values() if v['part']==1)}, part2: {sum(1 for v in idx.values() if v['part']==2)})")

# ---------- 2. extract pages ----------
doc = fitz.open(Path(__file__).resolve().parent.parent / "surse" / "caiet-christian-adventure.pdf")
songs = []

def split_columns(lines_all):
    """Detect a two-column layout; return split x or None.
    A split is only accepted if virtually no text line flows across it."""
    gaps = []
    for l in lines_all:
        chars = [c for c in l["chars"] if c[0].strip()]
        if len(chars) < 4:
            continue
        for a, b in zip(chars, chars[1:]):
            gap = b[1] - a[2]
            if gap > 50 and a[2] < 360 and b[1] > 280:
                gaps.append((a[2] + b[1]) / 2)
    right_starts = sum(1 for l in lines_all if l["chars"] and l["chars"][0][1] > 320)
    if len(gaps) < 3 and right_starts < 6:
        return None
    split = statistics.median(gaps) if gaps else 330.0
    crossing = total = 0
    for l in lines_all:
        chars = [c for c in l["chars"] if c[0].strip()]
        if len(chars) < 4:
            continue
        total += 1
        left = [c for c in chars if c[1] < split]
        right = [c for c in chars if c[1] >= split]
        if left and right:
            lmax = max(c[2] for c in left)
            rmin = min(c[1] for c in right)
            if rmin - lmax < 25:
                crossing += 1
    if total and crossing / total > 0.12:
        return None
    return split

def process_stream(stream_lines, left_x, song):
    classified = []
    for l in stream_lines:
        if not l["chars"]:
            continue
        text, xs = line_text_and_map(l, left_x, FONT_MAPS, char_w=CHAR_W, space_w=SPACE_W)
        stripped = text.strip()
        if not stripped:
            continue
        sizes = [c[4] for c in l["chars"] if c[0].strip()]
        maxsz = max(sizes) if sizes else 0
        if maxsz >= 16:  # title, already handled
            continue
        if re.fullmatch(r"\d+", stripped):
            continue
        kind = "chord" if is_chord_text(stripped) else "lyric"
        classified.append({"line": l, "text": text, "xs": xs, "kind": kind})
    prev_y = None
    for j, c in enumerate(classified):
        y = c["line"]["y"]
        if prev_y is not None and y - prev_y > 22:
            if song["lines"] and song["lines"][-1] != "":
                song["lines"].append("")
        prev_y = y
        if c["kind"] == "chord":
            nxt = None
            if j + 1 < len(classified):
                n = classified[j + 1]
                if n["kind"] == "lyric" and n["line"]["y"] - y < 18:
                    nxt = n
            if nxt is not None:
                song["lines"].append(align_chords(c["line"], nxt["text"], nxt["xs"], left_x, FONT_MAPS, space_w=SPACE_W))
            else:
                song["lines"].append(standalone_chord_text(c["line"], left_x, FONT_MAPS, char_w=CHAR_W))
        else:
            song["lines"].append(c["text"])

for bpage, meta in sorted(idx.items()):
    pno = bpage - 1
    if pno >= len(doc):
        continue
    lines_all = page_lines(doc[pno], FONT_MAPS)
    if not lines_all:
        continue
    # page title (18pt, near top of page)
    title_txt = []
    for l in lines_all:
        sizes = [c[4] for c in l["chars"] if c[0].strip()]
        if sizes and max(sizes) >= 16 and l["y"] < 150:
            t, _ = line_text_and_map(l, 0, FONT_MAPS, char_w=CHAR_W, space_w=SPACE_W)
            title_txt.append(t.strip())
    body_lines = [l for l in lines_all
                  if not (any(c[4] >= 16 for c in l["chars"] if c[0].strip()))]
    song = {"src": "caiet3", "part": meta["part"], "page": bpage,
            "title": meta["title"], "page_title": norm_dia(" ".join(title_txt)) or None,
            "artist": meta["artist"], "lines": []}
    split = split_columns(body_lines)
    if split:
        left, right = [], []
        for l in body_lines:
            lc = [c for c in l["chars"] if c[1] < split]
            rc = [c for c in l["chars"] if c[1] >= split]
            if lc:
                left.append({"y": l["y"], "chars": lc})
            if rc:
                right.append({"y": l["y"], "chars": rc})
        lx = min((l["chars"][0][1] for l in left if l["chars"]), default=58)
        rx = min((l["chars"][0][1] for l in right if l["chars"]), default=split)
        process_stream(left, lx, song)
        if right:
            if song["lines"] and song["lines"][-1] != "":
                song["lines"].append("")
            process_stream(right, rx, song)
    else:
        lx = min((l["chars"][0][1] for l in body_lines if l["chars"]), default=58)
        process_stream(body_lines, lx, song)
    song["lines"] = [norm_dia(l) for l in song["lines"]]
    songs.append(song)

# ---------- 3. reconcile titles/artists: the page title is authoritative ----------
import difflib, unicodedata

def normt(t):
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", t)

index_by_norm = {}
for v in idx.values():
    index_by_norm.setdefault(normt(v["title"]), v)

norm_keys = list(index_by_norm)
fixed_art, fixed_title = 0, 0
for s in songs:
    pt = s.get("page_title")
    if not pt:
        continue
    key = normt(pt)
    hit = index_by_norm.get(key)
    if hit is None:
        close = difflib.get_close_matches(key, norm_keys, n=1, cutoff=0.75)
        hit = index_by_norm[close[0]] if close else None
    if hit:
        if normt(s["title"]) != key:
            fixed_title += 1
        s["title"] = hit["title"]
        s["artist"] = hit["artist"]
    else:
        s["title"] = pt.capitalize()
print("titles reconciled from page:", fixed_title)

with open("caiet3_songs.json", "w") as f:
    json.dump(songs, f, ensure_ascii=False, indent=1)
print(f"{len(songs)} songs extracted")
empty = [(s['page'], s['title']) for s in songs if len([l for l in s['lines'] if l.strip()]) < 4]
print("near-empty:", empty[:10])
chordless = sum(1 for s in songs if not any(is_chord_text(l.strip()) for l in s['lines'] if l.strip()))
print("songs without any chord line:", chordless)
