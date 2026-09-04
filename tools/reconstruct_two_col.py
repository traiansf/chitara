#!/usr/bin/env python3
"""Re-extract a two-column song page with a FORCED column split.

For pages where extract_caiet3.split_columns() fails (columns nearly touch,
e.g. p.62), so the compiled caiet got the columns interleaved. Reuses the
pipeline's own line clustering / chord alignment, emits the corrected body:
left column top-to-bottom, then right column.

Safe wrap-joining: consecutive lyric lines closer than WRAP_GAP with no chord
row between them are joined with a single space (they are one wrapped lyric
line in the PDF). Wraps that interact with chord rows are left split for
manual polish.

Usage: reconstruct_two_col.py <printed-page> [--split X] [--pdf PATH] [--no-join]
"""
import argparse
import re
import sys

sys.path.insert(0, "/home/traian/chitara/tools")
import fitz
from extract_common import (page_lines, line_text_and_map, is_chord_text,
                            align_chords, standalone_chord_text)

FONT_MAPS = {}
CHAR_W, SPACE_W = 7.2, 3.6
WRAP_GAP = 18.0       # p.62 style: wraps at 15px, new lines at 21px
STANZA_GAP = 25.0     # between 1x and 2x line pitch (p.62: 21/42, p.90: 15/30)
CHORD_ATTACH_GAP = 24.0


def norm_dia(s):
    return (s.replace("Ş", "Ș").replace("ş", "ș")
             .replace("Ţ", "Ț").replace("ţ", "ț"))


def classify(stream_lines, left_x):
    out = []
    for l in stream_lines:
        if not l["chars"]:
            continue
        text, xs = line_text_and_map(l, left_x, FONT_MAPS, char_w=CHAR_W, space_w=SPACE_W)
        stripped = text.strip()
        if not stripped:
            continue
        sizes = [c[4] for c in l["chars"] if c[0].strip()]
        if sizes and max(sizes) >= 16:
            continue  # page title
        if re.fullmatch(r"\d+", stripped):
            continue  # page number
        kind = "chord" if is_chord_text(stripped) else "lyric"
        out.append({"line": l, "text": text, "xs": xs, "kind": kind, "y": l["y"]})
    return out


def render_column(classified, left_x, join_wraps=True):
    rows = []  # [kind, text, y_start, y_end]
    for j, c in enumerate(classified):
        if c["kind"] == "chord":
            nxt = classified[j + 1] if j + 1 < len(classified) else None
            if nxt and nxt["kind"] == "lyric" and nxt["y"] - c["y"] < CHORD_ATTACH_GAP:
                text = align_chords(c["line"], nxt["text"], nxt["xs"],
                                    left_x, FONT_MAPS, space_w=SPACE_W)
            else:
                text = standalone_chord_text(c["line"], left_x, FONT_MAPS, char_w=CHAR_W)
            rows.append(["chord", text, c["y"], c["y"]])
        else:
            rows.append(["lyric", c["text"], c["y"], c["y"]])
    # join wrapped lyric continuations (lyric directly after lyric, small y-gap)
    if join_wraps:
        joined = []
        for kind, text, y0, y1 in rows:
            if (kind == "lyric" and joined and joined[-1][0] == "lyric"
                    and y0 - joined[-1][3] < WRAP_GAP):
                prev = joined[-1][1].rstrip()
                sep = "" if prev.endswith("-") else " "
                joined[-1][1] = prev + sep + text.strip()
                joined[-1][3] = y1
            else:
                joined.append([kind, text, y0, y1])
        rows = joined
    # blank lines between stanzas (gap measured from previous row's END y)
    out = []
    prev_end = None
    for kind, text, y0, y1 in rows:
        if prev_end is not None and y0 - prev_end > STANZA_GAP and kind != "chord":
            if out and out[-1] != "":
                out.append("")
        out.append(norm_dia(text))
        prev_end = y1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("page", type=int, help="printed page number (PDF page = page)")
    ap.add_argument("--split", type=float, default=310.0)
    ap.add_argument("--pdf", default="/home/traian/chitara/caiet-christian-adventure.pdf")
    ap.add_argument("--no-join", action="store_true",
                    help="disable wrap-joining (pages whose line pitch equals the wrap gap)")
    ap.add_argument("--stanza-gap", type=float, default=None)
    ap.add_argument("--marker", action="store_true",
                    help="emit a <<<COL2>>> line at the column seam (for polish_two_col.py)")
    args = ap.parse_args()
    global STANZA_GAP
    if args.stanza_gap:
        STANZA_GAP = args.stanza_gap

    doc = fitz.open(args.pdf)
    lines_all = page_lines(doc[args.page - 1], FONT_MAPS)
    body = [l for l in lines_all
            if not any(c[4] >= 16 for c in l["chars"] if c[0].strip())]
    left, right = [], []
    for l in body:
        lc = [c for c in l["chars"] if c[1] < args.split]
        rc = [c for c in l["chars"] if c[1] >= args.split]
        if lc:
            left.append({"y": l["y"], "chars": lc})
        if rc:
            right.append({"y": l["y"], "chars": rc})
    lx = min((l["chars"][0][1] for l in left), default=58)
    rx = min((l["chars"][0][1] for l in right), default=args.split)
    out = render_column(classify(left, lx), lx, not args.no_join)
    if right:
        if out and out[-1] != "":
            out.append("")
        if args.marker:
            out.append("<<<COL2>>>")
        out += render_column(classify(right, rx), rx, not args.no_join)
    print("\n".join(out))


if __name__ == "__main__":
    main()
