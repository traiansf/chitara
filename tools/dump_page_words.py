#!/usr/bin/env python3
"""Dump a PDF page as y-grouped words annotated with x-coordinates.

Used to untangle two-column song pages (e.g. Caiet Christian Adventure) where
plain extraction interleaves the columns: the dump shows each word's x-range,
so column membership (left ~x<300, right ~x>=300 for A4 two-column pages) and
chord-to-lyric alignment can be read off directly.

Usage: python3 dump_page_words.py <pdf> <page> [<last-page>]
Pages are 1-indexed. Output: one line per y-row, "y=... | [x0-x1]word ...".
"""
import sys
from collections import defaultdict

import fitz


def dump_page(page):
    rows = defaultdict(list)
    for x0, y0, x1, y1, word, *_ in page.get_text("words"):
        rows[round(y0, 1)].append((x0, x1, word))
    for y in sorted(rows):
        words = sorted(rows[y])
        print(f"y={y:7.1f} | " + "  ".join(f"[{x0:.0f}-{x1:.0f}]{w}" for x0, x1, w in words))


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    pdf, first = sys.argv[1], int(sys.argv[2])
    last = int(sys.argv[3]) if len(sys.argv) > 3 else first
    doc = fitz.open(pdf)
    for pno in range(first, last + 1):
        print(f"=== page {pno} ===")
        dump_page(doc[pno - 1])


if __name__ == "__main__":
    main()
