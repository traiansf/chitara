#!/usr/bin/env python3
"""Replace the ```text block of a song in Caiet-chitara.md.

Usage: replace_song_block.py '<header prefix, e.g. "#### Miruna">' <content-file>
"""
import sys
from pathlib import Path

MD = str(Path(__file__).resolve().parent.parent / "Caiet-chitara.md")

def main():
    header_prefix, content_path = sys.argv[1], sys.argv[2]
    lines = open(MD, encoding="utf-8").read().split("\n")
    h = next(i for i, l in enumerate(lines) if l.startswith(header_prefix))
    start = next(i for i in range(h, h + 12) if lines[i].strip() == "```text")
    end = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == "```")
    new = open(content_path, encoding="utf-8").read().rstrip("\n").split("\n")
    lines[start + 1:end] = new
    open(MD, "w", encoding="utf-8").write("\n".join(lines))
    print(f"{header_prefix}: replaced lines {start + 2}..{end} with {len(new)} lines")

if __name__ == "__main__":
    main()
