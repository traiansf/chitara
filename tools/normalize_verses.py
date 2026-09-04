"""Normalize verse layout in Caiet-chitara.md song blocks.

- Removes leading spaces from all lines inside ```text song blocks.
- Moves inline verse markers (``1.``, ``R:``, ``Refren:``, ``Refren x2:``)
  onto their own line before the verse (before its chord line, if any).
- Chord lines are rebuilt token-wise, shifted by the same amount as the
  lyric line below them so chord-over-syllable alignment is preserved.

The annex chord dictionary (after "## Index pe artiști") is left untouched.
"""
import re
import sys

sys.path.insert(0, "/home/traian/chitara/tools")
from extract_common import is_chord_text

SRC = sys.argv[1] if len(sys.argv) > 1 else "/home/traian/chitara/Caiet-chitara.md"

MARKER_RE = re.compile(r"^(\d{1,2}\.(?!\d)|R\d?\s?:|(?i:refren)(?:\s*[xX]\s*\d+)?\s*:)\s*")
TOKEN_RE = re.compile(r"\S+")

stats = {"deindented": 0, "markers_moved": 0, "chord_rebuilt": 0, "bumped_tokens": 0}


def rebuild_chord_line(line, shift):
    """Shift chord tokens left by `shift`, keeping token order; clamp at col 0."""
    buf = ""
    for m in TOKEN_RE.finditer(line):
        col = max(m.start() - shift, 0)
        if buf and col < len(buf) + 1:
            col = len(buf) + 1
            stats["bumped_tokens"] += 1
        buf = buf.ljust(col) + m.group()
    return buf


def transform_block(lines):
    lines = [l.rstrip() for l in lines]
    n = len(lines)
    kind = []
    for l in lines:
        s = l.strip()
        if not s:
            kind.append("blank")
        elif is_chord_text(s):
            kind.append("chord")
        else:
            kind.append("text")

    shifts = [0] * n
    markers = [None] * n  # marker text to hoist, keyed by the lyric line index
    newtext = list(lines)

    for i, l in enumerate(lines):
        if kind[i] != "text":
            continue
        lead = len(l) - len(l.lstrip(" "))
        s = l.strip()
        m = MARKER_RE.match(s)
        if m and m.end() < len(s):
            marker = re.sub(r"\s+:", ":", s[: m.end()].strip())
            markers[i] = marker
            shifts[i] = lead + m.end()
            newtext[i] = s[m.end():]
            stats["markers_moved"] += 1
        else:
            shifts[i] = lead
            newtext[i] = s
        if lead:
            stats["deindented"] += 1

    for i, l in enumerate(lines):
        if kind[i] != "chord":
            continue
        # pair with the next text line in the same paragraph
        shift = len(l) - len(l.lstrip(" "))
        j = i + 1
        while j < n and kind[j] == "chord":
            j += 1
        if j < n and kind[j] == "text":
            shift = shifts[j]
        newtext[i] = rebuild_chord_line(l, shift)
        if shift:
            stats["chord_rebuilt"] += 1

    out = []
    for i in range(n):
        if markers[i] is not None:
            # insert before the contiguous chord run directly above
            k = len(out)
            while k > 0 and out[k - 1][0] == "chord":
                k -= 1
            out.insert(k, ("marker", markers[i]))
        out.append((kind[i], newtext[i]))
    return [t for _, t in out]


def main():
    src = open(SRC).read().splitlines()
    out = []
    in_block = False
    enabled = True
    block = []
    for line in src:
        if line.startswith("## Index pe artiști"):
            enabled = False
        if not in_block and line.strip() == "```text" and enabled:
            in_block = True
            out.append(line)
            block = []
            continue
        if in_block:
            if line.strip() == "```":
                out.extend(transform_block(block))
                out.append(line)
                in_block = False
            else:
                block.append(line)
            continue
        out.append(line)
    assert not in_block, "unterminated block"
    open(SRC, "w").write("\n".join(out) + "\n")
    print(stats)


if __name__ == "__main__":
    main()
