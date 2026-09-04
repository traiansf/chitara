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
Usage: python3 tools/make_pdf.py [--md PATH] [--out PATH]
"""
import argparse
import html
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

MD = "/home/traian/chitara/Caiet-chitara.md"
OUT = "/home/traian/chitara/Caiet-chitara.pdf"
CHROME = "google-chrome-stable"
MONO_STACK = "'Iosevka Fixed', 'DejaVu Sans Mono', monospace"

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

CHORD_RE = re.compile(
    r"^[A-G](?:#|b)?(?:m|maj|min|dim|aug|\+)?(?:sus)?[0-9]*"
    r"(?:\(?(?:add|sus|maj)?[A-G0-9#b]*\)?)?(?:/[A-G](?:#|b)?m?)?$"
)
SKIP_TOKENS = {"FC", "FCG"}


def is_chord_line(ln):
    toks = ln.split()
    return bool(toks) and all(
        t in SKIP_TOKENS or CHORD_RE.match(t) for t in toks)


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

    songs = []
    starts = [i for i, l in enumerate(lines) if re.match(r"^### \d+\. ", l)]
    for k, i in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(lines)
        for j in range(i + 1, end):
            if lines[j].startswith("## "):
                end = j
                break
        m = re.match(r"^### (\d+)\. (.*)", lines[i])
        num, title = int(m.group(1)), m.group(2).strip()
        meta = uke = ""
        body, in_f = [], False
        for j in range(i + 1, end):
            ln = lines[j]
            if ln.startswith("```"):
                in_f = not in_f
                continue
            if in_f:
                body.append(ln.rstrip())
            elif ln.startswith("**Ukulele:**"):
                uke = ln
            elif ln.strip() and not meta:
                meta = ln.strip()
        while body and not body[-1]:
            body.pop()
        while body and not body[0]:
            body.pop(0)
        songs.append(dict(num=num, title=title, meta=meta, uke=uke,
                          body=body, shrink=1.0))

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
        if brk <= 0:
            brk = cur_l.find(" ", maxw)
        if brk <= 0:
            yield (cur_t or None), cur_l
            return
        keep_l = cur_l[:brk].rstrip()
        rest_l = cur_l[brk:].lstrip()
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
        if brk <= 0:
            brk = cur.find(" ", maxw)
        if brk <= 0:
            break
        out.append(cur[:brk].rstrip())
        cur = " " * INDENT + cur[brk:].lstrip()
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
    out, i = [], 0
    while i < len(body):
        ln = body[i]
        if not ln.strip():
            out.append("")
            i += 1
            continue
        nxt = body[i + 1] if i + 1 < len(body) else None
        if is_chord_line(ln) and nxt and nxt.strip() \
                and not is_chord_line(nxt):
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


def fs_fit(lines, width_mm, height_mm):
    w = max((len(l) for l in lines), default=1)
    fs_w = width_mm / (max(w, 1) * ADV * PT2MM)
    fs_h = height_mm / (eff_lines(lines) * LINE_H * PT2MM)
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
        best = (0, body[:mid], body[mid:])
    return best[1], best[2]


def header_mm(s):
    uke_lines = (1 + len(s["uke"]) // 135) if s["uke"] else 0
    return 5.6 + (3.7 if s["meta"] else 0) + 3.7 * uke_lines + 6.5


def best_layout(s):
    """Maximize font size (cap 12pt); tie-break toward simpler layouts.
    Complexity: 0 single, 1 two-col, 2 single wrapped, 3 two-col wrapped.
    """
    h = BODY_H - header_mm(s)
    body = s["body"]
    cands = [(fs_fit(body, BODY_W, h), 0, None, body)]
    c1, c2 = split_two_cols(body)
    cands.append((min(fs_fit(c1, COL_W, h), fs_fit(c2, COL_W, h)),
                  1, (c1, c2), None))
    for tgt in (12.0, 11.0):
        ws = int(BODY_W / (tgt * ADV * PT2MM))
        wb = wrap_body(body, ws)
        if wb != body:
            cands.append((fs_fit(wb, BODY_W, h), 2, None, wb))
        wc = max(MIN_WRAP, int(COL_W / (tgt * ADV * PT2MM)))
        wbc = wrap_body(body, wc)
        d1, d2 = split_two_cols(wbc)
        cands.append((min(fs_fit(d1, COL_W, h), fs_fit(d2, COL_W, h)),
                      3, (d1, d2), None))
    fs, cx, cols, single = max(cands, key=lambda c: (round(c[0] * 4), -c[1]))
    return dict(fs=fs * s["shrink"], cols=cols, single=single,
                wrapped=cx >= 2)


# ---------------------------------------------------------------- html

def render_pre(body_lines):
    """Each line is its own block so blank separators can be genuinely
    half-height (inside one <pre>, every line box gets a full-height
    strut from the block font and cannot shrink)."""
    out = []
    for ln in body_lines:
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
code {{ font-family: {MONO_STACK}; font-size: 92%; }}
.mk {{ color: #ffffff; font-size: 3pt; }}
h2.song {{ font-size: 12.5pt; margin-bottom: 1.2mm; }}
h2.song .n {{ color: #888; font-weight: normal; }}
.meta {{ font-size: 7.5pt; color: #444; margin-bottom: 0.8mm; }}
.meta a, .toc a, .idx a {{ color: #1a4d8b; text-decoration: none; }}
.uke {{ font-size: 7.5pt; color: #333; margin-bottom: 0.8mm; }}
.uke b {{ color: #8b1a1a; }}
.rule {{ border-bottom: 0.3mm solid #ccc; margin-bottom: 2mm;
        line-height: 0.5; }}
.cols {{ display: flex; gap: {COL_GAP}mm; }}
.cols pre {{ flex: 1 1 0; }}
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
    anchor = slug(f'{s["num"]}. {s["title"]}')
    parts = [f'<div class="page" id="{anchor}">']
    parts.append(f'<h2 class="song"><span class="n">{s["num"]}.</span> '
                 f'{html.escape(s["title"])}</h2>')
    if s["meta"]:
        parts.append(f'<div class="meta">{mini_md(s["meta"])}</div>')
    if s["uke"]:
        parts.append(f'<div class="uke">{mini_md(s["uke"])}</div>')
    parts.append(f'<div class="rule"><span class="mk">§{s["num"]}§</span>'
                 f'</div>')
    style = f'font-size:{fs:.2f}pt'
    if lay["cols"]:
        c1, c2 = lay["cols"]
        parts.append(f'<div class="cols">'
                     f'<pre style="{style}">{render_pre(c1)}</pre>'
                     f'<pre style="{style}">{render_pre(c2)}</pre></div>')
    else:
        parts.append(f'<pre style="{style}">'
                     f'{render_pre(lay["single"])}</pre>')
    parts.append("</div>")
    return "\n".join(parts), fs, bool(lay["cols"]), lay["wrapped"]


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

    part1 = [s for s in songs if s["num"] <= 313]
    part2 = [s for s in songs if s["num"] > 313]

    def toc_entries(ss):
        es = []
        for s in ss:
            pg = page_of.get(s["num"]) or "···"
            artist = ""
            m = re.match(r"\*\*(.+?)\*\*", s["meta"])
            if m and m.group(1) != "Anonim":
                artist = f" — {m.group(1)}"
            label = html.escape(f'{s["num"]}. {s["title"]}{artist}')
            anchor = slug(f'{s["num"]}. {s["title"]}')
            es.append(f'<div class="toc-e"><span class="t">'
                      f'<a href="#{anchor}">{label}</a></span>'
                      f'<span class="dots"></span>'
                      f'<span class="pg">{pg}</span></div>')
        return "\n".join(es)

    P.append('<div class="page"><h1 class="toc-h">Cuprins</h1>'
             '<h2 class="toc-part">Partea I — Cântece de munte și folk '
             'românesc (313)</h2>'
             f'<div class="toc">{toc_entries(part1)}</div>'
             '<h2 class="toc-part">Partea a II-a — Repertoriu internațional '
             '(92)</h2>'
             f'<div class="toc">{toc_entries(part2)}</div></div>')

    P.append('<div class="page divider" id="partea-i"><h1>Partea I<br>'
             'Cântece de munte și folk românesc</h1></div>')
    stats = []
    for s in part1:
        pg, fs, cols, wrapped = song_page(s)
        P.append(pg)
        stats.append((s["num"], fs, cols, wrapped))
    P.append('<div class="page divider" id="partea-ii"><h1>Partea a II-a'
             '<br>Repertoriu internațional</h1></div>')
    for s in part2:
        pg, fs, cols, wrapped = song_page(s)
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

    return ('<!doctype html><html lang="ro"><head><meta charset="utf-8">'
            "<title>Caiet de cântece pentru chitară</title>"
            f"<style>{CSS}</style></head><body>" + "\n".join(P)
            + "</body></html>"), stats


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
    import fitz
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

def verify(pdf_path, songs):
    import fitz
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
    for k in range(1, len(songs)):
        a, b = page_of[songs[k - 1]["num"]], page_of[songs[k]["num"]]
        if a < 0 or b < 0:
            continue
        expected = 2 if songs[k]["num"] == 314 else 1
        if b - a != expected:
            bad.add(songs[k - 1]["num"])
    if idx_page > 0 and page_of.get(405, -1) > 0 \
            and idx_page - page_of[405] != 1:
        bad.add(405)
    return page_of, sorted(bad), total


# ---------------------------------------------------------------- main

def main():
    global ADV, CH_BOLD, CSS
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", default=MD)
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args()

    intro, songs, index_lines, annex_lines = parse(args.md)
    print(f"parsed {len(songs)} songs")

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

    html_path = workdir / "caiet.html"
    page_of = {}
    by_num = {s["num"]: s for s in songs}
    stats = []
    for attempt in range(1, 7):
        doc_html, stats = build_html(intro, songs, index_lines,
                                     annex_lines, page_of)
        html_path.write_text(doc_html, encoding="utf-8")
        run_chrome(html_path, args.out)
        prev_pages = page_of
        page_of, bad, total = verify(args.out, songs)
        print(f"pass {attempt}: {total} pages, problem songs: "
              f"{bad or 'none'}")
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
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
