#!/usr/bin/env python3
"""Polish reconstruct_two_col.py output: per-column dedent, artifact removal,
and conservative wrap-joining.

Join rule: a fragment line of <=3 words starting lowercase, whose previous
line is a lyric (not a chord row) that ends without sentence punctuation,
is a wrap continuation -> joined with a space (or no space after a hyphen).

Usage: polish_two_col.py <raw> <out> --seam '<stripped prefix of first right-column line>'
"""
import argparse
import re
import sys

sys.path.insert(0, "/home/traian/chitara/tools")
from extract_common import is_chord_text

NO_JOIN_END = tuple(".,!?:;")
MAX_FRAG = 3


def dedent(chunk):
    pads = [len(l) - len(l.lstrip()) for l in chunk if l.strip()]
    p = min(pads) if pads else 0
    return [l[p:] if l.strip() else l for l in chunk]


def clean(chunk):
    out = []
    for l in chunk:
        if l.strip() == ".":
            continue  # stray period row
        out.append(re.sub(r"^\.(\s+)", r" \1", l))  # stray period artifact -> space (keep width)
    return out


def joinwraps(chunk):
    out = []
    for l in chunk:
        s = l.strip()
        prev = out[-1].rstrip() if out else ""
        if (s and out and prev and len(s.split()) <= MAX_FRAG and s[0].islower()
                and not is_chord_text(prev.strip()) and not prev.endswith(NO_JOIN_END)):
            sep = "" if prev.endswith("-") else " "
            out[-1] = prev + sep + s
        else:
            out.append(l)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("out")
    ap.add_argument("--seam", default="<<<COL2>>>",
                    help="stripped prefix of the first right-column line (default: marker)")
    ap.add_argument("--no-join", action="store_true")
    ap.add_argument("--max-frag", type=int, default=3)
    args = ap.parse_args()
    global MAX_FRAG
    MAX_FRAG = args.max_frag
    lines = open(args.raw, encoding="utf-8").read().split("\n")
    seam = next(i for i, l in enumerate(lines) if l.strip().startswith(args.seam))
    right = lines[seam:]
    if right and right[0].strip() == "<<<COL2>>>":
        right = right[1:]
    cols = [dedent(clean(lines[:seam])), dedent(clean(right))]
    if not args.no_join:
        cols = [joinwraps(c) for c in cols]
    body = cols[0] + cols[1]
    open(args.out, "w", encoding="utf-8").write("\n".join(body).rstrip() + "\n")
    print(f"seam at {seam}; {len(lines)} -> {len(body)} lines")


if __name__ == "__main__":
    main()
