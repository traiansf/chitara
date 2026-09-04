# -*- coding: utf-8 -*-
"""Repair the extraction damage in "Don't Cry (I)".

The two-column reconstruction of caiet-christian-adventure.pdf p. 192 dropped
the last word of three lines and scattered the stray letters onto lines of
their own.  Every replacement below is verified against that page.
"""
import sys
sys.path.insert(0, "/home/traian/chitara/tools")
from dedup_lib import SRC, load, parse_songs

# old line -> new line (None drops the line)
FIXES = [
    ("There's something in your eye",
     "There's something in your eyes"),
    ("Somethin' is changin' inside yo",
     "Somethin' is changin' inside you"),
    ("Don't you cry tonight I still love",
     "Don't you cry tonight I still love you"),
    ("s", None),                       # tail of "...inside you" / "...love you"
    ("u                  You'll feel better tomorrow",
     "You'll feel better tomorrow"),
    ("                 F      G    C         G/B   Am       G",
     "F      G    C         G/B   Am       G"),
    ("you              And don't you cry tonight there's a",
     "And don't you cry tonight there's a"),
    ("G F       G", "F       G"),      # stray G before the chord line
    # first CHORUS lost the trailing G that the same line keeps in the outro
    ("F     G   C         G/B   Am",
     "F     G   C         G/B   Am       G"),
]


def main():
    lines = load()
    song = next(s for s in parse_songs(lines) if s["title"] == "Don't Cry (I)")
    block = lines[song["start"]:song["end"]]

    for old, new in FIXES:
        assert block.count(old) == 1, f"{old!r} appears {block.count(old)}x"
        i = block.index(old)
        if new is None:
            del block[i]
        else:
            block[i] = new

    lines[song["start"]:song["end"]] = block
    open(SRC, "w", encoding="utf-8").write("\n".join(lines))
    print(f"„Don't Cry (I)” (nr. {song['num']}): {len(FIXES)} rânduri reparate")


if __name__ == "__main__":
    main()
