#!/usr/bin/env python3
"""Render Caiet-chitara.md to an A4 PDF with exactly one page per song.

Font-size policy: every song body targets 12pt, floor 11pt. Per song the
engine evaluates candidate layouts - single column, two balanced columns
(split at a verse boundary), and wrapped variants of both (lyric lines
wrapped together with their chord line, continuations indented) - and
keeps the one with the largest font (capped at 12pt), preferring simpler
layouts on ties. Blank separator lines render at 55% height. The mono
font is Iosevka Fixed (0.5em advance; ~17% narrower than DejaVu Sans
Mono); its true advance is CALIBRATED at runtime via a probe render, so
layout math follows whatever font fontconfig actually serves.

Verification: every song page carries an invisible white marker (§N§).
After rendering, pymupdf checks each marker sits on its own page, in
sequence, with no horizontal clipping; offenders get their font shrunk
7% and the PDF re-renders until clean. A second pass bakes real TOC page
numbers. Songs that end below the 11pt floor are reported.

Requires google-chrome-stable and pymupdf.
Usage: python3 tools/make_pdf.py [--md PATH] [--lista PATH] [--out PATH]
"""
import argparse
import collections
import functools
import hashlib
import html
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import transpose

_ROOT = Path(__file__).resolve().parent.parent
MD = str(_ROOT / "Caiet-chitara.md")
OUT = str(_ROOT / "Caiet-chitara.pdf")
CHROME = "google-chrome-stable"
MONO_STACK = "'Iosevka Fixed', 'DejaVu Sans Mono', monospace"

# the book's sections, in order; a section with no songs is skipped.  Each gets
# one divider page: the two strings are its upper and lower line.  Subsections
# share their part's line, so a part with subsections needs no page of its own.
SECTIONS = [("I.1", "Partea I — Cântece de cabană", "I.1 — De munte, de drum și de dor"),
            ("I.2", "Partea I — Cântece de cabană", "I.2 — Populare și lăutărești"),
            ("I.3", "Partea I — Cântece de cabană", "I.3 — Naționaliste și de dor de țară"),
            ("I.4", "Partea I — Cântece de cabană", "I.4 — Studențești, de chef și deocheate"),
            ("II.1", "Partea a II-a — Repertoriu românesc", "II.1 — Folk"),
            ("II.2", "Partea a II-a — Repertoriu românesc", "II.2 — Ne-folk"),
            ("III", "Partea a III-a", "Repertoriu internațional"),
            ("IV.1", "Partea a IV-a — Colinde și cântece de iarnă", "IV.1 — Colinde românești"),
            ("IV.2", "Partea a IV-a — Colinde și cântece de iarnă", "IV.2 — Colinde internaționale"),
            ("IV.3", "Partea a IV-a — Colinde și cântece de iarnă", "IV.3 — Cântece de iarnă românești"),
            ("IV.4", "Partea a IV-a — Colinde și cântece de iarnă", "IV.4 — Cântece de iarnă internaționale")]
PART_H = re.compile(r"^## Partea (I|a II-a|a III-a|a IV-a) — ")
SUB_H = re.compile(r"^### ([IV]+\.\d) — ")
PART_KEY = {"I": "I", "a II-a": "II", "a III-a": "III", "a IV-a": "IV"}

# --- geometry (mm) ---
PAGE_W = 210.0
MARG_X, MARG_TOP, MARG_BOT = 8.0, 8.0, 8.0
BODY_W = PAGE_W - 2 * MARG_X            # 194
BODY_H = 281.0
COL_GAP = 7.0
COL_W = (BODY_W - COL_GAP) / 2          # 93.5
PT2MM = 0.352778
LINE_H = 1.08
BLANK_F = 0.55                          # blank separator line height (em)
FS_MAX = 12.0
FS_FLOOR = 11.0
MIN_WRAP = 34                           # never wrap narrower than this
INDENT = 2                              # continuation indent (chars)

ADV = 0.5        # mono advance in em; overwritten by calibrate()
CH_BOLD = True   # bold chords; disabled if bold advance differs

# song_page() is a pure function of one song dict, so its (html, fs, cols,
# wrapped) result is cached per song across runs — see cached_song_page().
# The cache key folds in a hash of this file's own source, so any edit to
# the layout/rendering code below invalidates every entry automatically.
# Bump CACHE_VERSION only for a change that's invisible to that source
# hash: the DejaVu font files (DEJAVU_BOLD/DEJAVU_REG) or the mono font
# fontconfig serves (see ADV) changing content without this file changing.
CACHE_VERSION = 1
CACHE_PATH = Path(__file__).resolve().parent / "_pdf_work" / "song_layout_cache.json"

CHORD_RE = re.compile(
    r"^[A-G](?:#|b)?(?:m|maj|min|dim|aug|\+)?(?:sus)?[0-9]*"
    r"(?:\(?(?:add|sus|maj)?[A-G0-9#b]*\)?)?(?:/[A-G](?:#|b)?m?)?$"
)
# a bare "/" separates alternative ways to play the preceding chord (not a
# bass note — that's "X/Y" attached to the chord token itself)
SKIP_TOKENS = {"FC", "FCG", "[fill]", "/"}


def is_chord_line(ln):
    toks = ln.split()
    return bool(toks) and all(
        t in SKIP_TOKENS or CHORD_RE.match(t) for t in toks)


# an inline chord, [Am] — or [(Am)] for an optional one (play it or not),
# whose label keeps the parentheses so it floats above the lyric as "(Am)"
INLINE_CHORD = r"\[(\([A-G][^\]]*\)|[A-G][^\]]*)\]"
INLINE_CHORD_RE = re.compile(INLINE_CHORD + r"|\^")
MIN_LABEL_GAP = 1  # whole characters of breathing room between adjacent floats


def split_optional(label):
    """(chord, optional) for an inline chord label: "(G)" -> ("G", True),
    "G" -> ("G", False)."""
    if label.startswith("(") and label.endswith(")"):
        return label[1:-1], True
    return label, False


def inline_tokens(ln):
    """[(nominal_column, label)] for each chord/collapsed-repeat token,
    where nominal_column is its position once brackets/^ collapse to zero
    width (i.e. the column its syllable sits at before any crowding-nudge
    widens the gap before it)."""
    tokens, col, i = [], 0, 0
    for m in INLINE_CHORD_RE.finditer(ln):
        col += m.start() - i
        label = m.group(1) if m.group(1) is not None else "/"
        tokens.append((col, label))
        i = m.end()
    return tokens


def layout_floating(tokens, min_gap=MIN_LABEL_GAP):
    """[(spaces_before, left, label)]: nominal columns nudged right just
    enough that no two floated labels touch or overlap. A label at column
    c occupies [c, c+len(label)+min_gap); when the next token's nominal
    column would land inside that span, both the label AND its syllable
    move right by the same amount — spaces_before literal spaces get
    inserted into the rendered lyric text right before that token's
    source position, so the chord stays glued above the syllable it
    belongs to instead of drifting away from it. Nudges cascade left to
    right, so a tightly packed run (e.g. the "=" quick-chord-change
    shorthand, ^=[Bm]=[A]) still renders with every label visible and
    legible, just with a bit of extra space inserted before it.

    min_gap is in "characters" of the surrounding text — exact in a
    monospace context (the HTML site), where a space is exactly as wide
    as any other character. In a proportional font (make_pdf.py's
    converted-song rendering) a space is narrower than an average bold
    letter, so callers there should pass a larger min_gap to compensate;
    len(label) alone would under-reserve room and let labels visually
    fuse together."""
    out, extra, right_edge = [], 0, None
    for col, label in tokens:
        eff_col = col + extra
        spaces_before = 0 if right_edge is None else max(0, right_edge - eff_col)
        extra += spaces_before
        left = eff_col + spaces_before
        out.append((spaces_before, left, label))
        right_edge = left + len(label) + min_gap
    return out


def has_inline_chords(body):
    """True if any non-chord-line in this song body carries a real [Chord]
    bracket — i.e. the song uses Karban-style inline notation rather than
    (or in addition to) chords-above-lyrics."""
    return any(is_text(ln) and not is_chord_line(ln) and REAL_CHORD_RE.search(ln)
               for ln in body)


# ---------------------------------------------------------------- tablature
# A song's body mixes three kinds of line, told apart by type so that every
# step downstream (wrapping, column splitting, sizing, rendering) can keep
# them apart: plain str for the ```text fences (lyrics and chords, the only
# lines ever read for chords), TabLine for the ```tab fences and ProseLine
# for the plain text outside the fences (a note), neither of which is ever
# read for chords. ASCII tablature only means anything on a fixed character
# grid, so it is rendered as its own monospace block that never wraps —
# shrunk to fit instead — even in the proportional layout of converted songs.

REAL_CHORD_RE = re.compile(INLINE_CHORD)


class TabLine(str):
    """A line of a ```tab fence."""


class ProseLine(str):
    """One paragraph of plain text outside the fences, its source lines
    joined as Markdown would join them."""


def is_text(ln):
    """A line of a ```text fence (lyrics, chords) — not tablature or prose."""
    return not isinstance(ln, (TabLine, ProseLine))


def tab_blocks(body_lines):
    """[(start, end)] half-open line ranges, one per tablature block (a run
    of TabLine, i.e. one ```tab fence)."""
    blocks, i, n = [], 0, len(body_lines)
    while i < n:
        if isinstance(body_lines[i], TabLine):
            start = i
            while i < n and isinstance(body_lines[i], TabLine):
                i += 1
            blocks.append((start, i))
        else:
            i += 1
    return blocks


def tab_frame(body_lines):
    """(intro_end, tail_start) for a song whose tablature sits only before
    its lyrics (the ```text fences) and/or after them — the lyrics being
    body_lines[intro_end:tail_start], everything around them tablature
    and notes — or None when it has no tablature, or has some between two
    lyric lines."""
    lyric = [k for k, ln in enumerate(body_lines) if ln.strip() and is_text(ln)]
    blocks = tab_blocks(body_lines)
    if not lyric or not blocks:
        return None
    first, last = lyric[0], lyric[-1]
    if any(b > first and a < last for a, b in blocks):
        return None
    return first, last + 1


REPEAT_CLOSE_RE = re.compile(r"/\s*[xX](\d+)\s*$")


def _visible_slash(text):
    """Index of the first '/' outside any [Chord] bracket, or -1 - a slash
    chord's own bass note (e.g. [G7/4]) is blanked out first (preserving
    indices) so it's never mistaken for a repeat marker."""
    blanked = re.sub(r"\[[^\]]*\]", lambda m: " " * len(m.group(0)), text)
    return blanked.find("/")


def find_repeats(body_lines):
    """[(start, end, count)] for each /.../ xN passage: the source's own
    convention for "repeat this bit N times", a leading '/' and a
    trailing '/ xN' bracketing the repeated lines (which may be just one
    line, or several). The closing xN is unambiguous — a real chord's own
    bass-note '/' (e.g. [G7/4]) never has a literal 'x' right after it —
    but its opening '/' must be the nearest one at or before it within
    the same strophe (a blank-line-separated block): one found only in an
    earlier strophe means the source is missing its own opening '/', so
    that's reported (sys.exit) rather than silently guessed at."""
    strophes, cur = [], []
    for i, ln in enumerate(body_lines):
        if not ln.strip() or not is_text(ln):
            if cur:
                strophes.append(cur)
            cur = []
        else:
            cur.append(i)
    if cur:
        strophes.append(cur)

    spans = []
    for strophe in strophes:
        avail_from = 0  # position in strophe below which lines are already
                         # claimed by an earlier (in reading order) pair
        for pos, idx in enumerate(strophe):
            ln = body_lines[idx]
            m = REPEAT_CLOSE_RE.search(ln)
            if not m:
                continue
            count = int(m.group(1))
            opener_pos = None
            for p in range(pos, avail_from - 1, -1):
                text = body_lines[strophe[p]][:m.start()] if p == pos \
                    else body_lines[strophe[p]]
                if _visible_slash(text) != -1:
                    opener_pos = p
                    break
            if opener_pos is None:
                sys.exit(f"marcaj de repetiție '/x{count}' fără '/' de "
                         f"deschidere în aceeași strofă: {ln!r}")
            spans.append((strophe[opener_pos], idx, count))
            avail_from = pos + 1
    return spans


def mark_repeats(body_lines):
    """body_lines with each /.../ xN repeat passage (find_repeats)
    redrawn as the ASCII repeat-barline convention, ||: ... :|| ×N,
    instead of the source's bare '/' — just ||: ... :|| for x2, since a
    repeat sign alone already means twice. Plain text substitution within
    each line rather than a structural bracket around several, so it
    passes through word-wrap and column-splitting for free — no line-
    index bookkeeping needed downstream. Unicode has real repeat-sign
    glyphs (U+1D106/U+1D107), but DejaVu Sans — the only font this
    project ships or relies on, for both the PDF and the site — has no
    glyphs for them (confirmed via fitz.Font.has_glyph), so they'd
    render as tofu; ||:/:|| is what chord-sheet sites already use for
    the same thing, and is plain ASCII."""
    lines = list(body_lines)
    for start, end, count in find_repeats(lines):
        m = REPEAT_CLOSE_RE.search(lines[end])
        before = lines[end][:m.start()].rstrip()
        lines[end] = f"{before} :||" + (f" ×{count}" if count != 2 else "")
        pos = _visible_slash(lines[start])
        after = lines[start][pos + 1:].lstrip()
        lines[start] = f"{lines[start][:pos]}||: {after}"
    return lines


def slug(text):
    s = unicodedata.normalize("NFC", text).lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    return re.sub(r"\s+", "-", s.strip())


def mini_md(s):
    """bold + links + italics + code -> HTML (meta/intro lines)."""
    s = html.escape(s, quote=False).replace(chr(0x1F310), "↗")
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\[([^\]]+)\]\(#([^)]+)\)", r'<a href="#\2">\1</a>', s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"(?<!\w)\*([^*]+)\*(?!\w)", r"<i>\1</i>", s)
    return s


# ---------------------------------------------------------------- parsing

def parse(md_path):
    lines = Path(md_path).read_text(encoding="utf-8").split("\n")
    text = "\n".join(lines)

    intro = [l for l in lines[:lines.index("## Cuprins")] if l.strip()]

    part_at = {}
    cur_part = SECTIONS[0][0]
    for i, l in enumerate(lines):
        if m := PART_H.match(l):
            cur_part = PART_KEY[m.group(1)]
        elif m := SUB_H.match(l):
            cur_part = m.group(1)
        part_at[i] = cur_part

    songs = []
    anchors = collections.Counter()
    starts = [i for i, l in enumerate(lines) if l.startswith("#### ")]
    for k, i in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(lines)
        for j in range(i + 1, end):
            if lines[j].startswith("## ") or SUB_H.match(lines[j]):
                end = j
                break
        title = re.match(r"^#### (?:\d+\. )?(.*)", lines[i]).group(1).strip()
        # num is an internal per-run id (0..N-1), used only to key the
        # page-tracking/verification maps below — it is never displayed.
        num = k
        base = slug(title)
        n = anchors[base]
        anchors[base] += 1
        anchor = base if n == 0 else f"{base}-{n}"
        meta = uke = gtr = ""
        # the body keeps the song's parts in order — ```text lines as they
        # are, ```tab lines as TabLine, each paragraph of plain text outside
        # the fences as one ProseLine. No blank line goes between parts (the
        # CSS spaces them): split_two_cols() treats a blank line as a verse
        # boundary, and most converted songs have none of their own.
        body, fence, para = [], None, []

        def part_break():
            if para:
                body.append(ProseLine(" ".join(para)))
                para.clear()

        for j in range(i + 1, end):
            ln = lines[j]
            if ln.startswith("```"):
                if fence is None:
                    part_break()
                    fence = ln[3:].strip() or "text"
                else:
                    if ln[3:].strip():  # "```tab" before the open fence's "```"
                        print(f"atenție: {title}, rândul {j + 1}: {ln.strip()} "
                              f"deschis înainte de a închide ```{fence}",
                              file=sys.stderr)
                    fence = None
                    part_break()
                continue
            if fence == "tab":
                body.append(TabLine(ln.rstrip()))
            elif fence is not None:
                body.append(ln.rstrip())
            elif ln.startswith("**Ukulele:**"):
                uke = ln
            elif ln.startswith("**Chitară:**"):
                gtr = ln
            elif ln.strip() and not meta:
                meta = ln.strip()
            elif ln.strip() == "---":
                part_break()  # the rule closing a part, not the song's
            elif ln.strip():
                para.append(ln.strip())
            elif para:
                part_break()
        part_break()
        if fence is not None:
            print(f"atenție: {title}: bloc ```{fence} neînchis", file=sys.stderr)
        while body and not body[-1]:
            body.pop()
        while body and not body[0]:
            body.pop(0)
        body = mark_repeats(body)
        songs.append(dict(num=num, title=title, anchor=anchor, meta=meta,
                          uke=uke, gtr=gtr, body=body, shrink=1.0,
                          part=part_at[i], converted=has_inline_chords(body)))

    def section(start_pat, stop_pat):
        s = re.search(start_pat, text)
        seg = text[s.end():]
        e = re.search(stop_pat, seg)
        if e:
            seg = seg[:e.start()]
        return seg.strip("\n").split("\n")

    index_lines = section(r"## Index pe artiști\n", r"\n## ")
    annex_lines = section(r"## Anexă: dicționar de acorduri\n", r"\Z")
    return intro, songs, index_lines, annex_lines


# --------------------------------------------------------------- wrapping

def rebuild_chord(tokens):
    """[(pos, text)] -> chord line string, ≥1 space between tokens."""
    s = ""
    for pos, txt in tokens:
        pos = max(pos, len(s) + (1 if s else 0))
        s = s + " " * (pos - len(s)) + txt
    return s


def wrap_pair(chord, lyric, maxw):
    """Wrap a chord+lyric pair at spaces in the lyric; chord tokens move
    with the syllables they sit above. Yields (tokens|None, lyric_seg)."""
    toks = [(m.start(), m.group(0)) for m in re.finditer(r"\S+", chord)]
    cur_l, cur_t = lyric, toks
    while True:
        # chord overhang past a short-enough lyric is accepted; the
        # layout math measures the rebuilt line, so it is accounted for
        if len(cur_l) <= maxw:
            yield (cur_t or None), cur_l
            return
        brk = cur_l.rfind(" ", 1, maxw + 1)
        if brk <= 0 or not cur_l[:brk].strip():
            # the only space in range is the continuation indent itself:
            # breaking there would rebuild the same line forever
            brk = cur_l.find(" ", max(brk, 0) + 1)
        if brk <= 0:
            yield (cur_t or None), cur_l
            return
        keep_l = cur_l[:brk].rstrip()
        rest_l = cur_l[brk:].lstrip()
        if len(rest_l) + INDENT >= len(cur_l):
            yield (cur_t or None), cur_l      # a word wider than the column
            return
        shift = len(cur_l) - len(rest_l) - INDENT
        keep_t = [(p, t) for p, t in cur_t if p < brk]
        yield (keep_t or None), keep_l
        cur_l = " " * INDENT + rest_l
        cur_t = [(max(p - shift, INDENT), t) for p, t in cur_t if p >= brk]


def wrap_plain(ln, maxw):
    """Word-wrap a plain line, indenting continuations."""
    out, cur = [], ln.rstrip()
    while len(cur) > maxw:
        brk = cur.rfind(" ", 1, maxw + 1)
        if brk <= 0 or not cur[:brk].strip():
            # the only space in range is the continuation indent itself:
            # breaking there would rebuild the same line forever
            brk = cur.find(" ", max(brk, 0) + 1)
        if brk <= 0:
            break
        nxt = " " * INDENT + cur[brk:].lstrip()
        if len(nxt) >= len(cur):
            break                             # a word wider than the column
        out.append(cur[:brk].rstrip())
        cur = nxt
    out.append(cur)
    return out


def wrap_chord_only(ln, maxw):
    """Wrap an interlude chord row at token boundaries."""
    toks = [(m.start(), m.group(0)) for m in re.finditer(r"\S+", ln)]
    out, cur = [], []
    for p, t in toks:
        cand = cur + [(p if not out else max(p, INDENT), t)]
        if cur and len(rebuild_chord(cand)) > maxw:
            out.append(rebuild_chord(cur))
            cur = [(INDENT, t)]
        else:
            cur = cand
    if cur:
        out.append(rebuild_chord(cur))
    return out


def wrap_body(body, maxw):
    """Tablature blocks (tab_blocks) pass through unwrapped: render_pre()
    shrinks them to fit instead. Prose passes through too: it is rendered
    as ordinary wrapped text."""
    ends = dict(tab_blocks(body))
    out, i = [], 0
    while i < len(body):
        if i in ends:
            out += body[i:ends[i]]
            i = ends[i]
            continue
        ln = body[i]
        if not ln.strip():
            out.append("")
            i += 1
            continue
        if isinstance(ln, ProseLine):
            out.append(ln)
            i += 1
            continue
        nxt = body[i + 1] if i + 1 < len(body) else None
        if is_chord_line(ln) and nxt and nxt.strip() \
                and not is_chord_line(nxt) and is_text(nxt):
            if len(ln) <= maxw and len(nxt) <= maxw:
                out += [ln, nxt]
            else:
                for toks, lseg in wrap_pair(ln, nxt, maxw):
                    if toks:
                        out.append(rebuild_chord(toks))
                    out.append(lseg)
            i += 2
            continue
        if len(ln) <= maxw:
            out.append(ln)
        elif is_chord_line(ln):
            out += wrap_chord_only(ln, maxw)
        else:
            out += wrap_plain(ln, maxw)
        i += 1
    return out


# ---------------------------------------------------------------- layout

def eff_lines(lines):
    return sum(1.0 if l.strip() else BLANK_F for l in lines) or 1.0


TAB_PAD_MM = 4.0    # a .tab block's left border + horizontal padding
TAB_VPAD_MM = 3.0   # its vertical margins + padding
TAB_FS_MIN = 7.0    # a staff printed smaller than this gets hard to read


def tab_scale(lines, width_mm, fs):
    """Font-size factor (at most 1, relative to the song's fs) that lets a
    tablature block's longest line fit width_mm without wrapping."""
    w = max((len(l) for l in lines), default=1)
    fit = (width_mm - TAB_PAD_MM) / (max(w, 1) * ADV * PT2MM)
    return min(1.0, fit / fs)


def tab_fs(cols, width_mm, fs):
    """Smallest font size any tablature block in these columns ends up at
    (infinity when there is none)."""
    return min([float("inf")] + [fs * tab_scale(c[a:b], width_mm, fs)
                                 for c in cols for a, b in tab_blocks(c)])


def layout_score(fs, tab):
    """A layout's font size, minus a point for every point its smallest
    tablature block (tab_fs) falls below TAB_FS_MIN: enough to prefer one
    column when two would crush a staff, not so much that a whole song
    shrinks to spare one staff a fraction of a point."""
    return fs - max(0.0, TAB_FS_MIN - tab)


def fs_fit(lines, width_mm, height_mm):
    """Tablature lines don't constrain the width (they shrink on their
    own, see tab_scale); counting them at full size keeps the height
    estimate on the safe side. Prose wraps like ordinary text, so its
    height can only be measured, not worked out in closed form."""
    if any(isinstance(l, ProseLine) for l in lines):
        height = mono_height_fn(lines, width_mm)
        return max_fs(lambda fs: height(fs) <= height_mm)
    blocks = tab_blocks(lines)
    in_tab = {k for a, b in blocks for k in range(a, b)}
    w = max((len(l) for k, l in enumerate(lines) if k not in in_tab), default=1)
    fs_w = width_mm / (max(w, 1) * ADV * PT2MM)
    fs_h = (height_mm - TAB_VPAD_MM * len(blocks)) \
        / (eff_lines(lines) * LINE_H * PT2MM)
    return min(fs_w, fs_h, FS_MAX)


def split_two_cols(body):
    """Split at the verse boundary best balancing effective heights."""
    best = None
    for b in (i for i, l in enumerate(body) if not l.strip()):
        c1, c2 = body[:b], body[b + 1:]
        n = max(eff_lines(c1), eff_lines(c2))
        if best is None or n < best[0]:
            best = (n, c1, c2)
    if best is None:
        mid = len(body) // 2
        while mid > 1 and (is_chord_line(body[mid - 1])
                           or body[mid].startswith(" " * INDENT)):
            mid -= 1
        for a, b in tab_blocks(body):
            if a < mid < b:  # never inside a tablature block: its nearer end
                mid = a if a > 0 and mid - a <= b - mid else b
        best = (0, body[:mid], body[mid:])
    return best[1], best[2]


FING_PT = 12.0      # the fingering lines under a song's title (Chitară/Ukulele)
FING_MIN_PT = 8.0   # ... never smaller than this: wrap to another line instead
FING_LINE_H = 1.25


def fingering_items(line):
    """('Chitară', [('Am', 'x02210'), ...]) from a '**Chitară:** Am x02210 ·
    …' line."""
    label, _, rest = line.partition(":** ")
    return label.strip("*"), [tuple(it.split(" ", 1)) for it in rest.split(" · ")
                              if " " in it]


def fingering_html(line):
    """A fingering line, each chord name bold and each chord kept whole on
    one line (a chord never wraps away from its own fingering)."""
    label, items = fingering_items(line)
    # the separator is glued to the chord before it, so a row never starts
    # with one
    chords = "\u00a0· ".join(
        f'<span class="fg"><b>{html.escape(c, quote=False)}</b> '
        f'{html.escape(f, quote=False)}</span>' for c, f in items)
    return f'<b class="fl">{html.escape(label, quote=False)}:</b> {chords}'


def fingering_rows(line, fs):
    """How many rows a fingering line wraps into at fs pt across the page,
    measured with the real glyph widths (bold label and chord names), each
    chord kept whole as fingering_html() keeps it."""
    bold, reg = _prop_fonts()
    width = BODY_W / PT2MM * 0.97  # a little slack for Chrome's own metrics
    label, items = fingering_items(line)
    dot, space = reg.text_length(" ·", fs), reg.text_length(" ", fs)
    rows, cur = 1, bold.text_length(label + ": ", fs)
    for i, (c, f) in enumerate(items):
        w = bold.text_length(c, fs) + reg.text_length(" " + f, fs)
        if i == 0:
            cur += w
            continue
        cur += dot  # glued to the previous chord (fingering_html)
        if cur + space + w > width:
            rows, cur = rows + 1, w
        else:
            cur += space + w
    return rows


def fingering_layout(s):
    """(font size, [rows per fingering line]) for a song's fingering lines:
    the fewest rows possible without going below FING_MIN_PT, at the
    largest size (up to FING_PT) that keeps them to that many rows. Both
    lines of a song share the size."""
    if "_fing" not in s:
        lines = [s[k] for k in ("gtr", "uke") if s[k]]
        fs = FING_PT
        if lines:
            n = 1
            while True:
                fits = lambda f: all(fingering_rows(l, f) <= n for l in lines)
                if fits(FING_MIN_PT):
                    fs = max_fs(fits) if not fits(FING_PT) else FING_PT
                    fs = max(fs, FING_MIN_PT)
                    break
                n += 1
        s["_fing"] = (fs, [fingering_rows(l, fs) for l in lines])
    return s["_fing"]


def header_mm(s):
    """Height of a song page's header: title, meta line, fingering lines
    (see fingering_layout), rule."""
    fs, rows = fingering_layout(s)
    fing = sum(n * fs * FING_LINE_H * PT2MM + 0.8 for n in rows)
    return 5.6 + (3.7 if s["meta"] else 0) + fing + 6.5


TAIL_GAP_MM = 3.0  # space between the lyrics and a full-width tablature section


def mono_height_fn(lines, width_mm):
    """fs -> rendered height (mm) of monospace body lines laid out width_mm
    wide, or infinity when a line other than tablature (which shrinks on
    its own) would not fit that width at fs."""
    blocks = tab_blocks(lines)
    in_tab = {k for a, b in blocks for k in range(a, b)}
    prose = [l for l in lines if isinstance(l, ProseLine)]
    grid = [l for k, l in enumerate(lines)
            if k not in in_tab and not isinstance(l, ProseLine)]
    w = max((len(l) for l in grid), default=1)
    width_pt = width_mm / PT2MM

    def height(fs):
        if w * ADV * PT2MM * fs > width_mm:
            return float("inf")
        rows = sum(1.0 if l.strip() else BLANK_F for l in grid) \
            + sum(b - a for a, b in blocks)
        return rows * LINE_H * PT2MM * fs + TAB_VPAD_MM * len(blocks) \
            + sum(prose_height_pt(p, width_pt, fs) for p in prose) * PT2MM

    return height


def framed_layout(s, intro_end, tail_start, h):
    """Layout for a song with tablature only at its start and/or end
    (tab_frame): those sections across the whole page width, so their
    tablature isn't squeezed into a column, and the lyrics between them in
    one column or two, whichever allows the larger font. One font size for
    all of it."""
    def trim(lines):
        lines = list(lines)
        while lines and not lines[-1].strip():
            lines.pop()
        while lines and not lines[0].strip():
            lines.pop(0)
        return lines

    body = s["body"]
    intro = trim(body[:intro_end])
    lyrics = trim(body[intro_end:tail_start])
    tail = trim(body[tail_start:])
    height_fn = prop_height_fn if s["converted"] else mono_height_fn
    fixed = [height_fn(p, BODY_W) for p in (intro, tail) if p]
    best = None
    for cols in (None, split_two_cols(lyrics)):
        parts = [height_fn(c, COL_W) for c in cols] if cols \
            else [height_fn(lyrics, BODY_W)]
        fs = max_fs(lambda f: max(p(f) for p in parts)
                    + sum(TAIL_GAP_MM + x(f) for x in fixed) <= h)
        if best is None or fs > best[0]:
            best = (fs, cols)
    fs, cols = best
    return dict(fs=fs, cols=cols, single=None if cols else lyrics,
                intro=intro or None, tail=tail or None, wrapped=False)


def best_layout(s):
    """The song's layout, font size already scaled by its shrink factor
    (see main()). A song with tablature only at its start and/or end
    (tab_frame) gets framed_layout() when that costs its lyrics nothing,
    or when the regular layout would have to shrink a tablature block to
    fit it in a column — unless the framed one would then print the song
    smaller than TAB_FS_MIN where the regular one wouldn't (a long, narrow
    section, tablature with the lyrics interleaved, reads better in
    columns than squeezed into full-width rows)."""
    h = BODY_H - header_mm(s)
    lay = regular_layout(s, h)
    frame = tab_frame(s["body"])
    if frame is not None:
        framed = framed_layout(s, *frame, h)
        parts, width = (lay["cols"], COL_W) if lay["cols"] else ([lay["single"]], BODY_W)
        squeezed = tab_fs(parts, width, lay["fs"]) < lay["fs"] * 0.999
        if framed["fs"] >= lay["fs"] or (
                squeezed and framed["fs"] >= TAB_FS_MIN):
            lay = framed
    return dict(lay, fs=lay["fs"] * s["shrink"])


def regular_layout(s, h):
    """Maximize font size (cap 12pt); tie-break toward simpler layouts.
    Complexity: 0 single, 1 two-col, 2 single wrapped, 3 two-col wrapped.

    Converted (formerly-inline) songs skip all of this: they render in a
    proportional font via render_converted_body(), which wraps by real
    measured text width (fs_fit_prop()) rather than the character-column
    wrap_* helpers above (which assume a fixed-width font). Still offers
    the same single-vs-two-column choice as the monospace path (reusing
    split_two_cols(), which only looks at blank-line boundaries and
    doesn't care about a song's notation style) — some of these songs are
    exceptionally long even by this book's standards and need it just as
    much as a handful of monospace ones already do. main()'s existing
    verify-and-shrink loop, the same mechanism that already corrects any
    misjudged monospace layout, remains a backstop for whatever this
    measured estimate misses (Chrome's own line breaking rarely matches a
    hand-rolled one exactly).
    """
    def cand(fs, cx, cols, single):
        # the last element is what the smallest tablature block ends up
        # at, for layout_score()
        if cols:
            return (fs, cx, cols, single, tab_fs(cols, COL_W, fs))
        return (fs, cx, cols, single, tab_fs([single], BODY_W, fs))

    body = s["body"]
    if s["converted"]:
        c1, c2 = split_two_cols(body)
        cands = [
            cand(fs_fit_prop(body, BODY_W, h), 0, None, body),
            cand(min(fs_fit_prop(c1, COL_W, h), fs_fit_prop(c2, COL_W, h)),
                 1, (c1, c2), None)]
        fs, _, cols, single, _ = max(
            cands, key=lambda c: (layout_score(c[0], c[4]), -c[1]))
        return dict(fs=fs, cols=cols, single=single, intro=None, tail=None,
                    wrapped=False)
    cands = [cand(fs_fit(body, BODY_W, h), 0, None, body)]
    c1, c2 = split_two_cols(body)
    cands.append(cand(min(fs_fit(c1, COL_W, h), fs_fit(c2, COL_W, h)),
                      1, (c1, c2), None))
    for tgt in (12.0, 11.0):
        ws = int(BODY_W / (tgt * ADV * PT2MM))
        wb = wrap_body(body, ws)
        if wb != body:
            cands.append(cand(fs_fit(wb, BODY_W, h), 2, None, wb))
        wc = max(MIN_WRAP, int(COL_W / (tgt * ADV * PT2MM)))
        wbc = wrap_body(body, wc)
        d1, d2 = split_two_cols(wbc)
        cands.append(cand(min(fs_fit(d1, COL_W, h), fs_fit(d2, COL_W, h)),
                          3, (d1, d2), None))
    fs, cx, cols, single, _ = max(
        cands, key=lambda c: (round(layout_score(c[0], c[4]) * 4), -c[1]))
    return dict(fs=fs, cols=cols, single=single, intro=None, tail=None,
                wrapped=cx >= 2)


# ---------------------------------------------------------------- html

def render_tab(lines, width_mm, fs):
    """A tablature block (tab_blocks): its own monospace box, never
    wrapped, its font shrunk just enough (tab_scale) for the longest line
    to fit width_mm. Chord rows inside keep the chord colour."""
    rows = "".join(
        f'<span class="ln{" ch" if is_chord_line(ln) else ""}">'
        f'{html.escape(ln, quote=False)}</span>' for ln in lines)
    return (f'<span class="tab" style="font-size:'
            f'{tab_scale(lines, width_mm, fs):.3f}em">{rows}</span>')


PROSE_EM = 0.9       # a note's font size, relative to the song's
PROSE_VPAD_EM = 0.6  # its vertical margins, in the song's em


def note_html(text, chord_span):
    """mini_md() of a note, with every `code` span that holds a chord name
    (`C7`, `Em`) handed to chord_span(name) instead: a chord mentioned in
    passing, shown as one but never transposed — a note often refers to a
    tablature example, which stays in its written key."""
    def chord(m):
        name = html.unescape(m.group(1))
        return chord_span(name) if CHORD_RE.match(name) else m.group(0)
    return re.sub(r"<code>([^<]+)</code>", chord, mini_md(text))


def render_prose(text):
    """A paragraph of plain text from outside the fences (a note): ordinary
    wrapping text in the proportional font, whatever the song around it
    uses. Only Markdown's own inline formatting (mini_md) applies, plus
    chord names written as `code` (note_html)."""
    span = lambda c: f'<span class="ch">{html.escape(c, quote=False)}</span>'
    return f'<span class="prose">{note_html(text, span)}</span>'


def render_pre(body_lines, width_mm, fs):
    """Each line is its own block so blank separators can be genuinely
    half-height (inside one <pre>, every line box gets a full-height
    strut from the block font and cannot shrink)."""
    ends = dict(tab_blocks(body_lines))
    out, skip_to = [], 0
    for i, ln in enumerate(body_lines):
        if i < skip_to:
            continue
        if i in ends:
            out.append(render_tab(body_lines[i:ends[i]], width_mm, fs))
            skip_to = ends[i]
            continue
        if isinstance(ln, ProseLine):
            out.append(render_prose(ln))
            continue
        if not ln.strip():
            out.append('<span class="bl"></span>')
            continue
        esc = html.escape(ln, quote=False)
        if is_chord_line(ln):
            out.append(f'<span class="ln ch">{esc}</span>')
        else:
            esc = re.sub(r"\[([A-G][^\]]*)\]",
                         r'<span class="ch">[\1]</span>', esc)
            out.append(f'<span class="ln">{esc}</span>')
    return "".join(out)


def two_row_tokens(chord_line):
    """Same shape as inline_tokens()'s output — [(column, label)] — but
    read from a native chords-above-lyrics line instead of [Chord]/^
    brackets, so both sources can feed the same floating renderer."""
    return [(m.start(), m.group(0)) for m in re.finditer(r"\S+", chord_line)]


DEJAVU_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
DEJAVU_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
PROP_GAP_EM = 0.3  # minimum clearance between one floated label's glyph and the next
# extra clearance on top of PROP_GAP_EM when no lyric word sits between two
# floated labels (e.g. a run of chords/repeats ending a verse) - with no
# syllable to anchor to, they read as one smear unless visibly separated
PROP_GAP_EM_NO_WORD = 0.5
# extra clearance on top of a chord/repeat's own measured width when the
# source marks it as landing early (2+ literal spaces before the next
# syllable) - kept separate from PROP_GAP_EM_NO_WORD so the two can be
# tuned independently; a flat nbsp count sized for "C" would still let a
# wider or annotated chord ("Dm7", not just "C") spill into the syllable
PROP_GAP_EM_EARLY = 0.3
_prop_fonts_cache = {}


def _prop_fonts():
    if not _prop_fonts_cache:
        import pymupdf as fitz
        _prop_fonts_cache["bold"] = fitz.Font(fontfile=DEJAVU_BOLD)
        _prop_fonts_cache["reg"] = fitz.Font(fontfile=DEJAVU_REG)
    return _prop_fonts_cache["bold"], _prop_fonts_cache["reg"]


def measured_spacing(tokens, lyric):
    """[(spaces_before, label)] for each token, using real DejaVu Sans
    (Bold, for the chord labels) glyph widths via pymupdf instead of a
    character count, which is meaningless in a proportional font: a bold
    2-letter chord like Dm can easily be wider than the few plain
    characters of lyric sitting under it, and would visually collide with
    whatever floats next unless something makes room. spaces_before
    counts how many nbsp characters (see render_prop_row) to insert right
    before that token's source position so its label clears the previous
    one by at least PROP_GAP_EM, or PROP_GAP_EM_NO_WORD when no lyric word
    sits between the two, simulating each insertion's effect on a running
    cursor position to decide the next one."""
    bold, reg = _prop_fonts()
    nbsp_w = reg.text_length(" ", 1)
    out, cursor_em, label_end_em, prev_col = [], 0.0, None, 0
    for col, label in tokens:
        gap_text = lyric[prev_col:col]
        cursor_em += reg.text_length(gap_text, 1)
        spaces_before = 0
        if label_end_em is not None:
            target_em = label_end_em
            if not gap_text.strip():
                target_em += PROP_GAP_EM_NO_WORD
            if cursor_em < target_em:
                spaces_before = int(-(-(target_em - cursor_em) // nbsp_w))  # ceil
                cursor_em += spaces_before * nbsp_w
        out.append((spaces_before, label))
        label_end_em = cursor_em + bold.text_length(label, 1) + PROP_GAP_EM
        prev_col = col
    return out


def keep_multispace(text, prev_label=None):
    """A run of 2+ literal spaces in inline-notation lyrics is the source
    convention for "this chord lands half a measure early" - outside a
    <pre>, plain HTML would collapse it to one space and lose that meaning.
    A flat nbsp count sized for a narrow chord like "C" would still let a
    wider or annotated one ("Dm7", not just "Dm") spill past the run and
    into the syllable, so the run becomes a regular space (a wrap point)
    plus enough nbsp to clear prev_label's own measured width - the label
    immediately before this run, i.e. the chord this convention is about -
    plus PROP_GAP_EM_EARLY. prev_label is None when nothing floats right
    before the run (rare); that falls back to PROP_GAP_EM_EARLY alone."""
    bold, reg = _prop_fonts()
    space_w = reg.text_length(" ", 1)
    label_w = bold.text_length(prev_label, 1) if prev_label else 0.0
    min_nbsp = int(-(-(label_w + PROP_GAP_EM_EARLY) // space_w))  # ceil

    def grow(m):
        return " " + " " * max(len(m.group(0)) - 1, min_nbsp)

    return re.sub(r"  +", grow, text)


def render_prop_row(tokens, lyric):
    """One floating-chord row for the proportional (converted) layout:
    tokens is [(column, label)] from either inline_tokens() or
    two_row_tokens(); lyric is the plain text it sits above (already
    stripped of any [Chord]/^ markup). Mirrors generate_html.py's
    approach but each label anchors independently at its own natural
    position in the text (no shared per-row left-from-start reference),
    so normal CSS reflow — required for print, there is no horizontal
    scroll fallback — carries a wrapped continuation's chords with it for
    free instead of leaving them anchored to the wrong visual line."""
    layout = measured_spacing(tokens, lyric)
    pieces, pos, prev_label = [], 0, None
    for (col, _), (spaces_before, label) in zip(tokens, layout):
        pieces.append(html.escape(keep_multispace(lyric[pos:col], prev_label), quote=False))
        if spaces_before:
            # a literal space would be collapsed to one by normal HTML
            # whitespace rules (unlike generate_html.py's <pre>, .pf rows
            # need real word-wrap); nbsp is exempt from collapsing and
            # doesn't itself introduce a wrap point
            pieces.append("\u00a0" * spaces_before)
        pos, prev_label = col, label
        cls = "pf-r" if label == "/" else "pf-c"
        pieces.append(f'<span class="pf-a"><span class="{cls}">'
                      f'{html.escape(label, quote=False)}</span></span>')
    pieces.append(html.escape(keep_multispace(lyric[pos:], prev_label), quote=False))
    return "".join(pieces)



def classify_converted_rows(body_lines):
    """Split a converted song's body into logical rows, one per source
    line (blank lines included) — the single shared classification used
    by both render_converted_body() and fs_fit_prop(), so sizing and
    rendering can never disagree about what a given line is. Yields
    ('blank', None), ('pair', (tokens, lyric)) for both native
    chords-above-lyrics pairs and inline [Chord]/^ lines (both reduce to
    the same (tokens, lyric) shape), ('interlude', [tokens]) for a chord
    row with no lyric under it, ('tab', [lines]) for a whole tablature
    block (tab_blocks), ('prose', text) for a paragraph of plain text
    from outside the fences, or ('plain', text)."""
    ends = dict(tab_blocks(body_lines))
    i, n = 0, len(body_lines)
    while i < n:
        if i in ends:
            yield "tab", body_lines[i:ends[i]]
            i = ends[i]
            continue
        ln = body_lines[i]
        if isinstance(ln, ProseLine):
            yield "prose", ln
            i += 1
            continue
        if not ln.strip():
            yield "blank", None
            i += 1
            continue
        nxt = body_lines[i + 1] if i + 1 < n else None
        if is_chord_line(ln) and nxt is not None and nxt.strip() \
                and not is_chord_line(nxt) and is_text(nxt):
            yield "pair", (two_row_tokens(ln), nxt)
            i += 2
            continue
        if is_chord_line(ln):
            yield "interlude", ln.split()
            i += 1
            continue
        tokens = inline_tokens(ln)
        if not tokens:
            yield "plain", ln
        else:
            yield "pair", (tokens, INLINE_CHORD_RE.sub("", ln))
        i += 1


def render_converted_body(body_lines, width_mm, fs):
    """Proportional-font rendering for a song that uses inline [Chord]/^
    notation anywhere (see has_inline_chords) — including any native
    chords-above-lyrics pairs mixed into the same song, converted to the
    same floating representation so the page doesn't flip between two
    rendering styles mid-song. Each source line is its own block (like
    render_pre), so word-wrap only ever reflows within one sung line, not
    across several."""
    out = []
    for kind, data in classify_converted_rows(body_lines):
        if kind == "blank":
            out.append('<p class="pf-bl"></p>')
        elif kind == "pair":
            tokens, lyric = data
            out.append(f'<p class="pf">{render_prop_row(tokens, lyric)}</p>')
        elif kind == "interlude":
            # a chord row with no lyric under it: nothing to float above,
            # so render its tokens plainly in place, at normal line-height
            # like any other chordless row — no need to reserve headroom
            # for a floated row that doesn't exist here
            toks = [f'<span class="{"pf-r" if t == "/" else "pf-c"}">'
                    f'{html.escape(t, quote=False)}</span>' for t in data]
            out.append(f'<p class="pf-plain">{" ".join(toks)}</p>')
        elif kind == "tab":
            out.append(render_tab(data, width_mm, fs))
        elif kind == "prose":
            out.append(render_prose(data))
        else:
            out.append(f'<p class="pf-plain">{html.escape(data, quote=False)}</p>')
    return "".join(out)


PF_PAD_TOP_EM = 1.25
PF_LINE_H_EM = 1.3
# a chord row's every visual line, a wrapped continuation's too, is this
# tall: the headroom its floated chords need plus the line itself (.pf)
PF_ROW_H_EM = PF_PAD_TOP_EM + PF_LINE_H_EM
# ... of which line-height puts half of the headroom below the text, where
# .pf's negative bottom margin takes it back
PF_ROW_LEAD_EM = (PF_ROW_H_EM - PF_LINE_H_EM) / 2
PF_BLANK_EM = 1.9  # a verse break needs to read as clearly bigger than the
                    # headroom already reserved above every chord-bearing
                    # row, not blend in with it


def prop_row_plain(tokens, lyric):
    """The same text render_prop_row() turns into HTML, minus the markup
    — lyric with measured_spacing()'s nbsp padding applied, for wrap-width
    measurement in fs_fit_prop()."""
    layout = measured_spacing(tokens, lyric)
    pieces, pos = [], 0
    for (col, _), (spaces_before, _label) in zip(tokens, layout):
        pieces.append(lyric[pos:col])
        if spaces_before:
            pieces.append(" " * spaces_before)
        pos = col
    pieces.append(lyric[pos:])
    return "".join(pieces)


def prose_height_pt(text, width_pt, fs):
    """Rendered height (pt) of one render_prose() paragraph."""
    f = fs * PROSE_EM
    return wrap_count_prop(text, width_pt, f) * PF_LINE_H_EM * f \
        + PROSE_VPAD_EM * fs


def wrap_count_prop(text, width_pt, fontsize):
    """How many visual lines `text` wraps into at `fontsize`pt within
    `width_pt` points of a proportional font, measured with real DejaVu
    Sans glyph widths — a monospace character count would be meaningless
    here. Splits on plain spaces only, so an inline nbsp run (see
    measured_spacing) is never itself a break point, matching the CSS."""
    _, reg = _prop_fonts()
    words = text.split(" ")
    space_w = reg.text_length(" ", fontsize)
    lines, cur_w = 1, 0.0
    for w in words:
        ww = reg.text_length(w, fontsize)
        add = ww if cur_w == 0 else space_w + ww
        if cur_w > 0 and cur_w + add > width_pt:
            lines += 1
            cur_w = ww
        else:
            cur_w += add
    return max(lines, 1)


def prop_height_fn(body_lines, width_mm):
    """fs -> rendered height (mm) of a converted song's body lines laid
    out width_mm wide, measured via wrap_count_prop() rather than assumed
    from a character count. Everything that doesn't depend on fs is
    worked out once, up front, since callers probe many font sizes."""
    width_pt = width_mm / PT2MM
    rows = list(classify_converted_rows(body_lines))
    texts = [prop_row_plain(*data) if kind == "pair" else
             " ".join(data) if kind == "interlude" else
             (data if kind in ("plain", "prose") else "")
             for kind, data in rows]

    def height(fs):
        total = 0.0
        for (kind, data), text in zip(rows, texts):
            if kind == "blank":
                total += PF_BLANK_EM * fs
            elif kind == "tab":
                # never wraps, and its font is at most fs: counting every
                # line at full size errs on the safe side
                total += len(data) * LINE_H * fs + TAB_VPAD_MM / PT2MM
            elif kind == "prose":
                total += prose_height_pt(text, width_pt, fs)
            else:
                # only a "pair" row floats chords above itself and needs the
                # headroom, above each line it wraps into (PF_ROW_H_EM); a
                # chordless plain/interlude row renders at plain line-height,
                # same as render_converted_body
                line_h = PF_ROW_H_EM if kind == "pair" else PF_LINE_H_EM
                total += wrap_count_prop(text, width_pt, fs) * line_h * fs
        return total * PT2MM

    return height


def max_fs(fits):
    """The largest font size (capped at FS_MAX) for which fits(fs) holds,
    fits being monotone — true up to some size, false beyond. 24 halvings
    easily get sub-hundredth-pt precision without an actual Chrome
    render."""
    if fits(FS_MAX):
        return FS_MAX
    lo, hi = 1.0, FS_MAX
    for _ in range(24):
        mid = (lo + hi) / 2
        if fits(mid):
            lo = mid
        else:
            hi = mid
    return lo


def fs_fit_prop(body_lines, width_mm, height_mm):
    """fs_fit()'s proportional-font counterpart: the largest font size
    (capped at FS_MAX) whose rendered height (prop_height_fn) fits
    height_mm. Height never decreases as the font grows (bigger text only
    ever wraps to more lines, never fewer), so max_fs() applies."""
    height = prop_height_fn(body_lines, width_mm)
    return max_fs(lambda fs: height(fs) <= height_mm)


CSS = f"""
@page {{ size: A4; margin: 0; }}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'DejaVu Sans', sans-serif; color: #111; }}
.page {{ min-height: 280mm; padding: {MARG_TOP}mm {MARG_X}mm {MARG_BOT}mm;
        break-after: page; }}
.page:last-child {{ break-after: auto; }}
pre {{ font-family: {MONO_STACK}; line-height: {LINE_H};
      white-space: pre; font-feature-settings: "liga" 0, "calt" 0; }}
.ln {{ display: block; white-space: pre; }}
.bl {{ display: block; height: {BLANK_F * LINE_H:.3f}em; }}
.ch {{ color: #8b1a1a; {'font-weight: bold;' if CH_BOLD else ''} }}
/* Converted (formerly-inline) songs: proportional font instead of the
   monospace grid, since inline notation carries no column-alignment
   information to preserve anyway. Chords float above their syllable via
   a zero-width, zero-height inline anchor (.pf-a) placed exactly at that
   syllable's own position in the text — not at a computed offset from
   the row's start — so normal word-wrap (required in print; there is no
   scroll fallback) carries a wrapped continuation's chords with it
   automatically instead of leaving them pinned to the wrong visual row.
   The generous line-height (PF_ROW_H_EM) reserves headroom above EVERY
   wrapped line of a row, not just its first, for exactly the same
   reason — a continuation's chords would otherwise float into the line
   above. Line-height splits that headroom half above the text, half
   below; padding-top tops up the half above and the negative bottom
   margin takes back the half below, so a row that doesn't wrap sits
   exactly where padding-top: PF_PAD_TOP_EM + line-height: PF_LINE_H_EM
   would put it. */
.pf-body {{ font-family: 'DejaVu Sans', sans-serif; }}
.pf {{ padding-top: {PF_PAD_TOP_EM - PF_ROW_LEAD_EM:.3f}em; line-height: {PF_ROW_H_EM:.2f};
      margin: 0 0 -{PF_ROW_LEAD_EM:.3f}em; }}
.pf-plain {{ line-height: 1.3; margin: 0; }}
.pf-bl {{ height: {PF_BLANK_EM:.2f}em; margin: 0; }}
/* display: inline, not inline-block - an inline-block is an atomic
   inline-level box that Chrome is free to give its own line-break
   opportunity even with no whitespace around it, which stranded the
   chord on the previous line while its syllable wrapped down. Plain
   inline has no content of its own (the label is taken out of flow by
   position: absolute) so it still occupies zero width, but now breaks
   only where the surrounding text actually does. */
.pf-a {{ position: relative; display: inline; }}
/* a floated label keeps the plain line-height: .pf's taller one would
   centre it higher above its anchor */
.pf-a > span {{ position: absolute; left: 0; bottom: 0.75em; white-space: nowrap;
              font-weight: bold; line-height: {PF_LINE_H_EM}; }}
.pf-c {{ color: #8b1a1a; }}
/* Tablature (tab_blocks): a monospace box of its own, never wrapped —
   render_tab() shrinks its font-size instead, only as far as needed for
   the longest line to fit; that font-size is relative to the song's, so
   the same markup works inside both <pre> and .pf-body. */
.tab {{ display: block; font-family: {MONO_STACK}; line-height: {LINE_H};
       white-space: pre; font-feature-settings: "liga" 0, "calt" 0;
       background: #f3f3f3; border-left: 0.6mm solid #bbb;
       padding: 0.5mm 1.5mm; margin: 1mm 0; }}
.tab .ln {{ white-space: pre; }}
.intro {{ margin-bottom: {TAIL_GAP_MM}mm; }}
/* A note from outside the fences: ordinary wrapping text, whatever the
   song around it uses (render_prose). */
.prose {{ display: block; font-family: 'DejaVu Sans', sans-serif;
         font-size: {PROSE_EM}em; line-height: {PF_LINE_H_EM};
         white-space: normal; color: #333;
         margin: {PROSE_VPAD_EM / 2 / PROSE_EM:.3f}em 0; }}
.tail {{ margin-top: {TAIL_GAP_MM}mm; }}
.pf-r {{ color: #444; }}
code {{ font-family: {MONO_STACK}; font-size: 92%; }}
.mk {{ color: #ffffff; font-size: 3pt; }}
h2.song {{ font-size: 12.5pt; margin-bottom: 1.2mm; }}
.meta {{ font-size: 7.5pt; color: #444; margin-bottom: 0.8mm; }}
.meta a, .toc a, .idx a {{ color: #1a4d8b; text-decoration: none; }}
.uke {{ font-size: {FING_PT}pt; line-height: {FING_LINE_H}; color: #333;
       margin-bottom: 0.8mm; }}
.uke b {{ color: #8b1a1a; }}
.uke b.fl {{ color: #555; }}
.fg {{ white-space: nowrap; }}
.rule {{ border-bottom: 0.3mm solid #ccc; margin-bottom: 2mm;
        line-height: 0.5; }}
.cols {{ display: flex; gap: {COL_GAP}mm; }}
.cols pre, .cols > div {{ flex: 1 1 0; min-width: 0; }}
.divider {{ display: flex; align-items: center; justify-content: center; }}
.divider h1 {{ font-size: 22pt; text-align: center; color: #333;
              line-height: 1.6; }}
h1.front {{ font-size: 24pt; margin: 20mm 0 8mm; }}
.front-txt p {{ font-size: 9.5pt; margin-bottom: 3mm; line-height: 1.45; }}
.front-txt li {{ font-size: 9.5pt; margin-left: 6mm; line-height: 1.45; }}
h1.toc-h {{ font-size: 16pt; margin-bottom: 4mm; }}
h2.toc-part {{ font-size: 11pt; margin: 2.5mm 0; }}
.toc {{ columns: 2; column-gap: 8mm; }}
.toc-e {{ font-size: 7.6pt; line-height: 1.38; display: flex;
         break-inside: avoid; }}
.toc-e .t {{ white-space: nowrap; overflow: hidden;
            text-overflow: ellipsis; }}
.toc-e .dots {{ flex: 1; border-bottom: 0.2mm dotted #999;
               margin: 0 1mm 1mm; min-width: 2mm; }}
.toc-e .pg {{ color: #444; }}
h1.sec {{ font-size: 16pt; margin-bottom: 4mm; }}
.idx {{ font-size: 7.6pt; line-height: 1.5; list-style: none; }}
.idx li {{ margin-bottom: 1.2mm; }}
.annex p {{ font-size: 8.5pt; margin-bottom: 2.5mm; line-height: 1.4;
           max-width: 170mm; }}
.annex pre {{ font-size: 9pt; }}
"""


def song_page(s):
    lay = best_layout(s)
    fs = lay["fs"]
    parts = [f'<div class="page" id="{s["anchor"]}">']
    parts.append(f'<h2 class="song">{html.escape(s["title"])}</h2>')
    if s["meta"]:
        parts.append(f'<div class="meta">{mini_md(s["meta"])}</div>')
    for key in ("gtr", "uke"):
        if s[key]:
            parts.append(f'<div class="uke" style="font-size:{fingering_layout(s)[0]:.2f}pt">'
                         f'{fingering_html(s[key])}</div>')
    parts.append(f'<div class="rule"><span class="mk">§{s["num"]}§</span>'
                 f'</div>')
    style = f'font-size:{fs:.2f}pt'
    if lay["intro"]:
        if s["converted"]:
            parts.append(f'<div class="pf-body intro" style="{style}">'
                         f'{render_converted_body(lay["intro"], BODY_W, fs)}</div>')
        else:
            parts.append(f'<pre class="intro" style="{style}">'
                         f'{render_pre(lay["intro"], BODY_W, fs)}</pre>')
    if s["converted"] and lay["cols"]:
        c1, c2 = lay["cols"]
        parts.append(f'<div class="cols pf-body" style="{style}">'
                     f'<div>{render_converted_body(c1, COL_W, fs)}</div>'
                     f'<div>{render_converted_body(c2, COL_W, fs)}</div></div>')
    elif s["converted"]:
        parts.append(f'<div class="pf-body" style="{style}">'
                     f'{render_converted_body(lay["single"], BODY_W, fs)}</div>')
    elif lay["cols"]:
        c1, c2 = lay["cols"]
        parts.append(f'<div class="cols">'
                     f'<pre style="{style}">{render_pre(c1, COL_W, fs)}</pre>'
                     f'<pre style="{style}">{render_pre(c2, COL_W, fs)}</pre></div>')
    else:
        parts.append(f'<pre style="{style}">'
                     f'{render_pre(lay["single"], BODY_W, fs)}</pre>')
    if lay["tail"]:
        if s["converted"]:
            parts.append(f'<div class="pf-body tail" style="{style}">'
                         f'{render_converted_body(lay["tail"], BODY_W, fs)}</div>')
        else:
            parts.append(f'<pre class="tail" style="{style}">'
                         f'{render_pre(lay["tail"], BODY_W, fs)}</pre>')
    parts.append("</div>")
    return "\n".join(parts), fs, bool(lay["cols"]), lay["wrapped"]


# ------------------------------------------------------------ layout cache
# song_page(s) is deterministic in s alone (plus ADV/CH_BOLD, folded into
# _layout_version below), and it's the dominant cost of build() - most of
# it best_layout()'s binary-search font fit. Caching it per song means an
# edit to one song only re-lays-out that song; everything else is a dict
# lookup. Content-addressed: the key is a hash of every input, so a stale
# entry for a song that no longer exists just goes unused (and gets pruned
# on save) rather than needing explicit invalidation.
_layout_cache = {}
_layout_cache_seen = set()


@functools.lru_cache(maxsize=1)
def _layout_version():
    """Cached: ADV/CH_BOLD are fixed by calibrate() before any song_page
    call and don't change mid-run, so this file's bytes need hashing once,
    not once per song."""
    src = Path(__file__).read_bytes()
    h = hashlib.sha256()
    h.update(str(CACHE_VERSION).encode())
    h.update(src)
    h.update(f"|{ADV:.6f}|{CH_BOLD}".encode())
    return h.hexdigest()


def _song_cache_key(s, version):
    # num and anchor are embedded in song_page()'s output (the §N§ marker
    # verify() reads, and the page's id) - both must be in the key, even
    # though num itself never renders: an edit elsewhere in the caiet that
    # shifts num (adding/removing/reordering songs) must not reuse a page
    # carrying the wrong marker.
    body_key = [(type(ln).__name__, str(ln)) for ln in s["body"]]
    payload = repr((version, s["num"], s["anchor"], s["title"], s["meta"],
                    s["gtr"], s["uke"], s["converted"],
                    round(s["shrink"], 6), body_key))
    return hashlib.sha256(payload.encode()).hexdigest()


def lista_cache_path(lista_path):
    """A --lista run's own cache file: most of its songs are untransposed
    (transpose_song() returns the caiet's own dict unchanged when a song
    already starts on the requested key), so its keys mostly coincide with
    the main cache's - but it must save to its own file, or saving would
    prune the main cache down to just this lista's songs."""
    h = hashlib.sha256(str(Path(lista_path).resolve()).encode()).hexdigest()[:16]
    return CACHE_PATH.with_name(f"song_layout_cache.lista-{h}.json")


def load_layout_cache(*paths):
    """Seed the in-memory cache from one or more JSON files (missing or
    corrupt ones are skipped), later paths winning on key clashes - there
    are none in practice, since keys are content hashes."""
    global _layout_cache
    _layout_cache = {}
    for p in paths:
        try:
            _layout_cache.update(json.loads(p.read_text(encoding="utf-8")))
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    _layout_cache_seen.clear()


def save_layout_cache(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    pruned = {k: v for k, v in _layout_cache.items() if k in _layout_cache_seen}
    path.write_text(json.dumps(pruned), encoding="utf-8")


def cached_song_page(s):
    key = _song_cache_key(s, _layout_version())
    _layout_cache_seen.add(key)
    hit = _layout_cache.get(key)
    if hit is not None:
        return tuple(hit)
    result = song_page(s)
    _layout_cache[key] = list(result)
    return result


def toc_entries(ss, page_of):
    """Table-of-contents lines for songs ss — title, artist, page number
    (page_of, from the previous pass; dots until there is one)."""
    es = []
    for s in ss:
        pg = page_of.get(s["num"]) or "···"
        artist = ""
        m = re.match(r"\*\*(.+?)\*\*", s["meta"])
        if m and m.group(1) != "Anonim":
            artist = f" — {m.group(1)}"
        label = html.escape(f'{s["title"]}{artist}')
        es.append(f'<div class="toc-e"><span class="t">'
                  f'<a href="#{s["anchor"]}">{label}</a></span>'
                  f'<span class="dots"></span>'
                  f'<span class="pg">{pg}</span></div>')
    return "\n".join(es)


def html_doc(title, pages):
    return ('<!doctype html><html lang="ro"><head><meta charset="utf-8">'
            f"<title>{html.escape(title)}</title>"
            f"<style>{CSS}</style></head><body>" + "\n".join(pages)
            + "</body></html>")


def build_html(intro, songs, index_lines, annex_lines, page_of):
    P = []
    P.append('<div class="page"><h1 class="front">Caiet de cântece pentru '
             'chitară</h1><div class="front-txt">')
    for ln in intro[1:]:
        if ln.startswith("- "):
            P.append(f"<li>{mini_md(ln[2:])}</li>")
        else:
            P.append(f"<p>{mini_md(ln)}</p>")
    P.append("</div></div>")

    parts = [(top, low, [s for s in songs if s["part"] == n])
             for n, top, low in SECTIONS]
    parts = [(top, low, ss) for top, low, ss in parts if ss]

    toc = ['<div class="page"><h1 class="toc-h">Cuprins</h1>']
    for top, low, ss in parts:
        title = low if low.startswith("I.") else f"{top} — {low}"
        toc.append(f'<h2 class="toc-part">{html.escape(title)} ({len(ss)})</h2>'
                   f'<div class="toc">{toc_entries(ss, page_of)}</div>')
    P.append("".join(toc) + "</div>")

    stats = []
    for top, low, ss in parts:
        P.append(f'<div class="page divider" id="{slug(low)}">'
                 f'<h1>{html.escape(top)}<br>{html.escape(low)}</h1></div>')
        for s in ss:
            pg, fs, cols, wrapped = cached_song_page(s)
            P.append(pg)
            stats.append((s["num"], fs, cols, wrapped))

    P.append('<div class="page" id="index-pe-artiști">'
             '<span class="mk">§IDX§</span>'
             '<h1 class="sec">Index pe artiști</h1><ul class="idx">')
    for ln in index_lines:
        if ln.startswith("- "):
            P.append(f"<li>{mini_md(ln[2:])}</li>")
    P.append("</ul></div>")

    P.append('<div class="page" id="anexă-dicționar-de-acorduri">'
             '<h1 class="sec">Anexă: dicționar de acorduri</h1>'
             '<div class="annex">')
    in_f, pre = False, []
    for ln in annex_lines:
        if ln.startswith("```"):
            if in_f:
                P.append(f"<pre>{html.escape(chr(10).join(pre))}</pre>")
            in_f = not in_f
            continue
        if in_f:
            pre.append(ln)
        elif ln.strip():
            P.append(f"<p>{mini_md(ln)}</p>")
    P.append("</div></div>")

    return html_doc("Caiet de cântece pentru chitară", P), stats


# ------------------------------------------------------------- calibrate

def run_chrome(html_path, pdf_path):
    subprocess.run(
        [CHROME, "--headless", "--disable-gpu", "--no-sandbox",
         "--disable-dev-shm-usage", "--no-pdf-header-footer",
         "--generate-pdf-document-outline",
         f"--print-to-pdf={pdf_path}", str(html_path)],
        check=True, capture_output=True, timeout=300)


def calibrate(workdir):
    """Measure the real advance width (and bold parity) of the mono stack
    as Chrome renders it. Returns (advance_em, bold_ok, diacritics_ok)."""
    import pymupdf as fitz
    probe = workdir / "probe.html"
    ppdf = workdir / "probe.pdf"
    probe.write_text(
        '<!doctype html><meta charset="utf-8"><style>'
        '@page{size:A4;margin:0}body{margin:4mm}'
        f'pre{{font-family:{MONO_STACK};font-size:10pt;'
        'font-feature-settings:"liga" 0,"calt" 0;}}</style>'
        f'<pre>{"M" * 40}\n<b>{"M" * 40}</b>\năâîșțĂÂÎȘȚ</pre>',
        encoding="utf-8")
    run_chrome(probe, ppdf)
    doc = fitz.open(ppdf)
    words = sorted(doc[0].get_text("words"), key=lambda w: w[1])
    doc.close()
    reg, bold = words[0], words[1]
    adv = (reg[2] - reg[0]) / (len(reg[4]) * 10)
    bold_adv = (bold[2] - bold[0]) / (len(bold[4]) * 10)
    if len(reg[4]) != 40:
        sys.exit(f"probe line clipped ({len(reg[4])}/40 chars) - "
                 f"cannot calibrate")
    bold_ok = abs(bold_adv - adv) / adv < 0.005
    dia_ok = any("ș" in w[4] for w in words)
    return adv, bold_ok, dia_ok


# ---------------------------------------------------------------- verify

def verify(pdf_path, songs, first_of_part=None):
    """(page_of, bad song nums, page count). first_of_part: the songs a
    part divider page comes before — by default the first of each part
    (SECTIONS) present in songs."""
    import pymupdf as fitz
    x_limit = (PAGE_W - MARG_X + 3) * 72 / 25.4
    doc = fitz.open(pdf_path)
    marker_on = {}
    wide_pages = set()
    idx_page = -1
    for p in range(doc.page_count):
        t = doc[p].get_text()
        for m in re.finditer(r"§(\d+)§", t):
            marker_on.setdefault(int(m.group(1)), []).append(p + 1)
        if "§IDX§" in t:
            idx_page = p + 1
        if max((w[2] for w in doc[p].get_text("words")), default=0) \
                > x_limit:
            wide_pages.add(p + 1)
    total = doc.page_count
    doc.close()

    page_of, bad = {}, set()
    for s in songs:
        pl = marker_on.get(s["num"], [])
        page_of[s["num"]] = pl[0] if pl else -1
        if len(pl) != 1 or pl[0] in wide_pages:
            bad.add(s["num"])
    # a song takes exactly one page, except where a part divider comes
    # between two of them
    if first_of_part is None:
        first_of_part = {ss[0]["num"] for ss in
                         ([s for s in songs if s["part"] == n] for n, _, _ in SECTIONS)
                         if ss}
    for k in range(1, len(songs)):
        a, b = page_of[songs[k - 1]["num"]], page_of[songs[k]["num"]]
        if a < 0 or b < 0:
            continue
        expected = 2 if songs[k]["num"] in first_of_part else 1
        if b - a != expected:
            bad.add(songs[k - 1]["num"])
    last = songs[-1]["num"]
    if idx_page > 0 and page_of.get(last, -1) > 0 \
            and idx_page - page_of[last] != 1:
        bad.add(last)
    return page_of, sorted(bad), total


# ---------------------------------------------------------------- lista
# make_pdf.py --lista Lista-mea.md: a songbook of chosen songs only, in the
# list's own order after a table of contents, each moved to the key its
# line names by the chord it should start on:
#
#     # Lista mea
#     - Mă întorc și pașii-s grei [Dm]

LIST_ITEM_RE = re.compile(r"^- (.+?)\s*\[([^\]]+)\]\s*$")


def read_list(path):
    """(heading, [(song title, starting chord)]) from a list file: its
    "# " heading and one "- Title [Chord]" line per song."""
    heading, entries = "", []
    for ln in Path(path).read_text(encoding="utf-8").split("\n"):
        if ln.startswith("# ") and not heading:
            heading = ln[2:].strip()
        elif ln.startswith("- "):
            m = LIST_ITEM_RE.match(ln)
            if not m:
                sys.exit(f"{path}: rând fără acord între paranteze drepte: {ln!r}")
            entries.append((m.group(1), m.group(2)))
    return heading or Path(path).stem, entries


def first_chord(body):
    """The first chord of a song body's ```text fences, on a chord line or
    in an inline bracket (an optional one's chord too); None if none."""
    for ln in body:
        if isinstance(ln, (TabLine, ProseLine)):
            continue
        if is_chord_line(ln):
            chords = [t for t in ln.split() if t not in SKIP_TOKENS]
        else:
            chords = [split_optional(c)[0] for c in REAL_CHORD_RE.findall(ln)]
        if chords:
            return chords[0]
    return None


def transpose_song(s, key):
    """A copy of song s moved so that it starts on chord key, s itself if
    it already does. Moves the chords of its ```text fences — a chord
    line's keep their columns, unless the one before grew into them, and
    inline ones their brackets — and of its fingering lines, and says so
    on its meta line. Tablature and notes stay as they are: a tab's
    frets can't be transposed (as on the site), and a note's `C7` is
    usually about the tab."""
    first = first_chord(s["body"])
    if first is None:
        print(f"atenție: {s['title']} n-are acorduri, rămâne cum e",
              file=sys.stderr)
        return s
    n = transpose.interval(first, key)
    flats = transpose.uses_flats(key)

    def move(chord):
        return transpose.transpose_chord(chord, n, flats)

    # only the root moves: "C" asked to start on "Am" starts on "A"
    if transpose.ROOT_RE.match(first).group(2) != transpose.ROOT_RE.match(key).group(2):
        print(f"atenție: {s['title']} începe cu {first}, deci transpus "
              f"începe cu {move(first)}, nu cu {key}", file=sys.stderr)
    if n == 0:
        return s

    def inline(m):
        chord, optional = split_optional(m.group(1))
        return f"[({move(chord)})]" if optional else f"[{move(chord)}]"

    body = []
    for ln in s["body"]:
        if isinstance(ln, (TabLine, ProseLine)):
            body.append(ln)
        elif is_chord_line(ln):
            body.append(rebuild_chord([
                (m.start(), m.group(0) if m.group(0) in SKIP_TOKENS
                 else move(m.group(0))) for m in re.finditer(r"\S+", ln)]))
        else:
            body.append(REAL_CHORD_RE.sub(inline, ln))
    t = dict(s, body=body, meta=f"{s['meta']} · transpus: {first} → {move(first)}")
    for k in ("gtr", "uke"):
        if s[k]:
            t[k] = transpose.transpose_fingering_line(s[k], n, flats)
    return t


def pick_songs(entries, songs):
    """The songs entries name, in their order, each transposed
    (transpose_song) to start on its entry's chord. Titles are matched
    whole, ignoring case; one the caiet doesn't have exactly once, a
    title listed twice or a chord with no root is an error."""
    by_title = collections.defaultdict(list)
    for s in songs:
        by_title[unicodedata.normalize("NFC", s["title"]).casefold()].append(s)
    picked, errors, seen = [], [], set()
    for title, key in entries:
        k = unicodedata.normalize("NFC", title).casefold()
        hits = by_title.get(k, [])
        if len(hits) != 1:
            errors.append(f"{title}: {len(hits)} cântece cu titlul ăsta în caiet")
        elif k in seen:
            errors.append(f"{title}: apare de două ori în listă")
        elif transpose.root_pitch(key) is None:
            errors.append(f"{title}: [{key}] nu e un acord")
        else:
            picked.append(transpose_song(hits[0], key))
        seen.add(k)
    if errors:
        sys.exit("lista nu se potrivește cu caietul:\n  " + "\n  ".join(errors))
    return picked


def build_list_html(heading, songs, page_of):
    """The --lista songbook: its heading over a table of contents, then
    one page per song."""
    P = [f'<div class="page"><h1 class="toc-h">{html.escape(heading)}</h1>'
         f'<div class="toc">{toc_entries(songs, page_of)}</div></div>']
    stats = []
    for s in songs:
        pg, fs, cols, wrapped = cached_song_page(s)
        P.append(pg)
        stats.append((s["num"], fs, cols, wrapped))
    return html_doc(heading, P), stats


# ---------------------------------------------------------------- main

def main():
    global ADV, CH_BOLD, CSS
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", default=MD)
    ap.add_argument("--lista", metavar="LISTA.md",
                    help="doar cântecele din listă, transpuse (vezi read_list)")
    ap.add_argument("--out", help=f"implicit {OUT}, iar cu --lista "
                                  "lista, cu extensia .pdf")
    args = ap.parse_args()
    out = args.out or (str(Path(args.lista).with_suffix(".pdf"))
                       if args.lista else OUT)

    intro, songs, index_lines, annex_lines = parse(args.md)
    print(f"parsed {len(songs)} songs")
    if args.lista:
        heading, entries = read_list(args.lista)
        caiet = {s["num"]: s for s in songs}
        songs = pick_songs(entries, songs)
        moved = sum(s is not caiet[s["num"]] for s in songs)
        print(f"lista: {len(songs)} songs, {moved} transposed")

        def build(page_of):
            return build_list_html(heading, songs, page_of)
        first_of_part, html_name = set(), "lista.html"
    else:
        def build(page_of):
            return build_html(intro, songs, index_lines, annex_lines, page_of)
        first_of_part, html_name = None, "caiet.html"

    workdir = Path(__file__).resolve().parent / "_pdf_work"
    workdir.mkdir(parents=True, exist_ok=True)

    ADV, bold_ok, dia_ok = calibrate(workdir)
    print(f"mono advance: {ADV:.4f} em, bold-same-width: {bold_ok}, "
          f"diacritics: {dia_ok}")
    if not dia_ok:
        sys.exit("mono font lacks Romanian diacritics - aborting")
    if not bold_ok:
        CH_BOLD = False
        CSS = CSS.replace("font-weight: bold;", "")

    # --lista gets its own cache file, seeded from the main cache (most of
    # its songs are untransposed and so share the main cache's keys) but
    # saved separately, so a lista run never prunes the main cache down to
    # just its own songs.
    if args.lista:
        save_cache_path = lista_cache_path(args.lista)
        load_layout_cache(CACHE_PATH, save_cache_path)
    else:
        save_cache_path = CACHE_PATH
        load_layout_cache(CACHE_PATH)

    html_path = workdir / html_name
    page_of = {}
    by_num = {s["num"]: s for s in songs}
    stats = []
    for attempt in range(1, 7):
        doc_html, stats = build(page_of)
        html_path.write_text(doc_html, encoding="utf-8")
        run_chrome(html_path, out)
        prev_pages = page_of
        page_of, bad, total = verify(out, songs, first_of_part)
        print(f"pass {attempt}: {total} pages, problem songs: "
              f"{bad or 'none'}")
        save_layout_cache(save_cache_path)
        if not bad:
            if prev_pages == page_of:
                break
        for n in bad:
            by_num[n]["shrink"] *= 0.93
    else:
        sys.exit("could not converge to one page per song")

    at12 = sum(1 for _, f, _, _ in stats if f >= 11.99)
    mid = sorted((round(f, 1), n) for n, f, _, _ in stats
                 if FS_FLOOR <= f < 11.99)
    low = sorted((round(f, 1), n) for n, f, _, _ in stats if f < FS_FLOOR)
    print(f"font sizes: {at12} songs at 12pt, "
          f"{len(mid)} songs in [11,12): {mid or ''}")
    print(f"below 11pt floor: {low or 'none'}")
    print(f"two-column: {sum(1 for _, _, c, _ in stats if c)}, "
          f"wrapped: {sum(1 for _, _, _, w in stats if w)}")
    shrunk = [(s["num"], round(s["shrink"], 2)) for s in songs
              if s["shrink"] < 1]
    print(f"shrunk to fit: {shrunk or 'none'}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
