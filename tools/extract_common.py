"""Common PDF songbook extraction: line clustering, diacritic restore, chord alignment."""
import pymupdf as fitz
import re

CHORD_CORE = r"[A-G](?:#|b)?(?:m|maj|min|dim|aug|sus|add)?[0-9]{0,2}(?:sus[0-9]?|maj[0-9]|add[0-9]+|\+|-)?(?:/[A-G](?:#|b)?)?"
CHORD_TOKEN = re.compile(r"^\(?%s\)?[:.]?$" % CHORD_CORE)
EXTRA_TOKENS = {"x2", "x3", "x4", "(x2)", "(x3)", "(x4)", "(2x)", "(3x)", "|", "||", "|:", ":|", "%", "-", "*", "**"}
SPACE_W = 3.34  # approx space width for Helvetica 12
CHAR_W = 6.0    # approx char width for indent purposes

# fonts that carry only decorations (ASCII art, musical dingbats) - drop entirely
DROP_FONTS = {"TTE1AF87A8t00", "TTE1AF42F8t00", "TTE1AFD3B8t00",
              "TTE1B711F8t00", "TTE19DB3A0t00", "TTE247A390t00"}


def restore_char(c, font, prev_alpha, font_maps):
    """Map a control-code char to its diacritic via per-font map, case-adjusted."""
    m = font_maps.get(font)
    if not m:
        return ""  # decorative font control char -> drop
    ch = m.get(ord(c))
    if ch is None:
        return ""
    if prev_alpha:
        if prev_alpha.isupper():
            return ch.upper()
        if prev_alpha.islower():
            return ch.lower()
    return ch


def page_lines(page, font_maps):
    """Extract visual lines: cluster all chars by baseline y, sort by x.
    Returns list of dicts: y, chars=[(char, x0, x1, size, font)] (diacritics restored later per line)."""
    d = page.get_text("rawdict")
    allchars = []
    for block in d["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                if span["font"] in DROP_FONTS:
                    continue
                for ch in span["chars"]:
                    c = ch["c"]
                    x0, y0, x1, y1 = ch["bbox"]
                    ymid = (y0 + y1) / 2
                    allchars.append((c, x0, x1, ymid, span["size"], span["font"]))
    if not allchars:
        return []
    # cluster by ymid
    allchars.sort(key=lambda t: t[3])
    lines = []
    cur = [allchars[0]]
    for ch in allchars[1:]:
        if abs(ch[3] - cur[-1][3]) <= 3.0:
            cur.append(ch)
        else:
            lines.append(cur)
            cur = [ch]
    lines.append(cur)
    out = []
    for cl in lines:
        cl.sort(key=lambda t: t[1])
        y = sum(t[3] for t in cl) / len(cl)
        out.append({"y": y, "chars": cl})
    out.sort(key=lambda l: l["y"])
    return out


def line_text_and_map(line, left_x, font_maps, char_w=CHAR_W, space_w=SPACE_W):
    """Render a line to a string with approximate spacing; return (text, xs)
    where xs[i] = x0 of rendered char i (None for inserted spaces)."""
    s = []
    xs = []
    prev_x1 = None
    prev_alpha = None
    indent = max(0, round((line["chars"][0][1] - left_x) / char_w))
    s.extend(" " * indent)
    xs.extend([None] * indent)
    for (c, x0, x1, ymid, size, font) in line["chars"]:
        if ord(c) < 32:
            c = restore_char(c, font, prev_alpha, font_maps)
            if not c:
                continue
        if prev_x1 is not None:
            gap = x0 - prev_x1
            if gap > 1.2:
                nsp = max(1, round(gap / space_w))
                # avoid huge gaps blowing up columns
                nsp = min(nsp, 60)
                s.extend(" " * nsp)
                xs.extend([None] * nsp)
        if c == " ":
            if s and s[-1] != " ":
                s.append(" ")
                xs.append(None)
        else:
            s.append(c)
            xs.append(x0)
        prev_x1 = x1
        if c.strip():
            prev_alpha = c if c.isalpha() else None
    text = "".join(s).rstrip()
    xs = xs[: len(text)]
    return text, xs


def is_chord_text(text):
    toks = text.split()
    if not toks:
        return False
    core = [t for t in toks if t not in EXTRA_TOKENS and t != "R:"]
    if not core:
        return False
    return all(CHORD_TOKEN.match(t) for t in core)


def align_chords(chord_line, lyric_text, lyric_xs, left_x, font_maps, space_w=SPACE_W,
                 tok_gap=2.0):
    """Place chord tokens of chord_line above lyric_text using x coordinates.

    `tok_gap` is the gap that separates two chords; it has to be smaller than
    the spacing of the book at hand, or neighbouring chords run together into
    one token (Karban's colinde set them as little as 1.3 apart).
    """
    # build tokens from chord line chars
    toks = []
    cur = ""
    cur_x = None
    prev_x1 = None
    for (c, x0, x1, ymid, size, font) in chord_line["chars"]:
        if ord(c) < 32:
            continue
        if c == " ":
            if cur:
                toks.append((cur, cur_x))
                cur = ""
            prev_x1 = x1
            continue
        split = prev_x1 is not None and cur and x0 - prev_x1 > tok_gap
        # chords are sometimes set so tight that they touch or overlap, and no
        # gap can separate them; there the chord itself says where it ends
        if not split and cur and CHORD_TOKEN.match(cur) and not CHORD_TOKEN.match(cur + c):
            split = True
        if split:
            toks.append((cur, cur_x))
            cur = ""
        if not cur:
            cur_x = x0
        cur += c
        prev_x1 = x1
    if cur:
        toks.append((cur, cur_x))
    # map x -> index in lyric string
    out = []
    for tok, cx in toks:
        idx = None
        for i, x in enumerate(lyric_xs):
            if x is not None and x >= cx - 1.5:
                idx = i
                break
        if idx is None:
            last_x = max((x for x in lyric_xs if x is not None), default=left_x)
            idx = len(lyric_text) + max(1, round((cx - last_x) / space_w)) if cx > last_x else len(lyric_text) + 1
        out.append((tok, idx))
    # render
    buf = []
    for tok, idx in out:
        if buf and idx <= len(buf):
            idx = len(buf) + 1
        buf.extend(" " * (idx - len(buf)))
        buf.extend(tok)
    return "".join(buf)


def standalone_chord_text(chord_line, left_x, font_maps, char_w=CHAR_W):
    text, _ = line_text_and_map(chord_line, left_x, font_maps, char_w=char_w, space_w=char_w)
    return text
