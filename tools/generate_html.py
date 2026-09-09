#!/usr/bin/env python3
"""Generate the interactive HTML site (docs/) from Caiet-chitara.md.

Reuses tools/make_pdf.py's parser and the fingering tables from
add_guitar_chords.py / add_ukulele_chords.py — this tool never re-derives
chord data, it only re-renders what those already validated.

Usage: python3 tools/generate_html.py
"""
import collections
import html
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import make_pdf
import add_guitar_chords
import add_ukulele_chords

MD = "/home/traian/chitara/Caiet-chitara.md"
OUT_DIR = Path("/home/traian/chitara/docs")
ASSETS_SRC = Path(__file__).parent / "html_assets"


def emit_chords_data(path):
    data = {
        "NOTES": add_guitar_chords.NOTES,
        "ALIAS": add_guitar_chords.ALIAS,
        "FINGERINGS": {
            "guitar": add_guitar_chords.FINGERINGS,
            "ukulele": add_ukulele_chords.FINGERINGS,
        },
    }
    Path(path).write_text(
        "const CHORDS_DATA = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n",
        encoding="utf-8")


def render_pre_interactive(body_lines):
    """Like make_pdf.render_pre, but every chord token gets its own
    <span data-chord="..."> (not one span per whole chord-only line), so
    each can be rewritten independently by chords.js on transpose."""
    out = []
    for ln in body_lines:
        if not ln.strip():
            out.append('<span class="bl"></span>')
            continue
        if make_pdf.is_chord_line(ln):
            pieces, pos = [], 0
            for m in re.finditer(r"\S+", ln):
                pieces.append(html.escape(ln[pos:m.start()], quote=False))
                tok = m.group(0)
                esc_tok = html.escape(tok, quote=False)
                if tok in make_pdf.SKIP_TOKENS:
                    pieces.append(esc_tok)
                else:
                    # data-chord is inside a double-quoted attribute, so it
                    # needs full escaping (quote=True); the visible text
                    # only needs text-node escaping (quote=False) — using
                    # the same escaped value for both would let a literal
                    # '"' in a token break out of the attribute
                    attr = html.escape(tok, quote=True)
                    pieces.append(
                        f'<span class="ch" data-chord="{attr}">{esc_tok}</span>')
                pos = m.end()
            pieces.append(html.escape(ln[pos:], quote=False))
            out.append(f'<span class="ln">{"".join(pieces)}</span>')
        else:
            # Match against the raw line, not a pre-escaped one — escaping
            # ln once, then matching/re-escaping the captured group again,
            # double-escapes any &/</>/" already inside it.
            pieces, pos = [], 0
            for m in re.finditer(r"\[([A-G][^\]]*)\]", ln):
                pieces.append(html.escape(ln[pos:m.start()], quote=False))
                tok = m.group(1)
                attr = html.escape(tok, quote=True)
                text = html.escape(tok, quote=False)
                pieces.append(f'[<span class="ch" data-chord="{attr}">{text}</span>]')
                pos = m.end()
            pieces.append(html.escape(ln[pos:], quote=False))
            out.append(f'<span class="ln">{"".join(pieces)}</span>')
    return "".join(out)


FINGERING_RE = re.compile(r"^\*\*(Chitară|Ukulele):\*\* (.+)$")
INSTRUMENT_KEY = {"Chitară": "guitar", "Ukulele": "ukulele"}


def render_fingering_line(line):
    m = FINGERING_RE.match(line)
    if not m:
        return ""
    label, rest = m.group(1), m.group(2)
    key = INSTRUMENT_KEY[label]
    spans = []
    for pair in rest.split(" · "):
        chord, _, fingering = pair.rpartition(" ")
        # attribute values need full escaping (default quote=True); the
        # visible text only needs text-node escaping (quote=False)
        spans.append(
            f'<span class="fingering" data-chord="{html.escape(chord)}" '
            f'data-fingering="{html.escape(fingering)}" '
            f'data-instrument="{key}">{html.escape(pair, quote=False)}</span>')
    return f'<div class="fingering-line"><b>{label}:</b> ' + " · ".join(spans) + "</div>"


def song_filename(s):
    return f"{s['num']:03d}-{make_pdf.slug(s['title'])}.html"


PART_LABEL = {}  # sec_key -> "I.1 — De munte și de drum" / "Partea a II-a — ..."
def _init_part_labels():
    import reorganize_parts as rp
    for pkey, roman, name, subs in rp.PARTS:
        for sec, subname in (subs or [(pkey, None)]):
            PART_LABEL[sec] = f"{sec} — {subname}" if subname else f"{roman} — {name}"
_init_part_labels()


def render_sidebar(songs, current_num, prefix=""):
    out = ['<nav class="sidebar">']
    cur_part = None
    for s in songs:
        if s["part"] != cur_part:
            cur_part = s["part"]
            out.append(f'<h3>{html.escape(PART_LABEL.get(cur_part, cur_part))}</h3>')
        cls = " current" if s["num"] == current_num else ""
        out.append(
            f'<a class="song-link{cls}" href="{prefix}{song_filename(s)}">'
            f'{s["num"]}. {html.escape(s["title"])}</a>')
    out.append("</nav>")
    return "".join(out)


def song_page(s, prev_s, next_s, songs):
    body_html = render_pre_interactive(s["body"])
    fingerings = "".join(render_fingering_line(s[k]) for k in ("gtr", "uke") if s[k])
    nav_links = []
    if prev_s:
        nav_links.append(f'<a href="{song_filename(prev_s)}">← {html.escape(prev_s["title"])}</a>')
    if next_s:
        nav_links.append(f'<a href="{song_filename(next_s)}">{html.escape(next_s["title"])} →</a>')
    return f"""<!doctype html>
<html lang="ro"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(s["title"])} — Caiet de cântece</title>
<link rel="stylesheet" href="../assets/site.css">
</head><body>
<button type="button" class="sidebar-toggle">☰ Cuprins</button>
{render_sidebar(songs, s["num"], prefix="")}
<main>
<h1>{s["num"]}. {html.escape(s["title"])}</h1>
{f'<div class="meta">{make_pdf.mini_md(s["meta"])}</div>' if s["meta"] else ""}
{fingerings}
<div class="transpose-controls">
<button type="button" data-action="down">▼ semiton</button>
<span class="offset-label">0</span>
<button type="button" data-action="up">▲ semiton</button>
<button type="button" data-action="reset">reset</button>
</div>
<pre>{body_html}</pre>
<div class="song-nav">{" ".join(nav_links)}</div>
</main>
<script src="../assets/chords-data.js"></script>
<script src="../assets/chords.js"></script>
<script src="../assets/nav.js"></script>
</body></html>"""


def book_stats(songs):
    """Counts derived fresh from the current book — never hand-maintained,
    so they can't go stale the way the same numbers in README.md/CLAUDE.md
    quietly did across a session of song moves."""
    part_counts = collections.Counter(s["part"] for s in songs)
    artists = collections.Counter()
    for s in songs:
        m = re.match(r"^\*\*(.+?)\*\*", s["meta"] or "")
        if m:
            artists[m.group(1)] += 1
    n_variants = sum(1 for s in songs if re.search(r" \([IVX]+\)$", s["title"]))
    return {
        "part_counts": part_counts,
        "n_artists": len(artists),
        "n_attributed": sum(artists.values()),
        "n_variants": n_variants,
    }


def content_counts_table(stats):
    import reorganize_parts as rp
    counts = stats["part_counts"]
    rows = []
    for pkey, roman, name, subs in rp.PARTS:
        if subs:
            total = sum(counts[sec] for sec, _ in subs)
            rows.append(f"<tr><td><b>{roman} — {name}</b></td><td><b>{total}</b></td></tr>")
            for sec, subname in subs:
                rows.append(f"<tr><td class='indent'>{sec} — {subname}</td><td>{counts[sec]}</td></tr>")
        else:
            rows.append(f"<tr><td>{roman} — {name}</td><td>{counts[pkey]}</td></tr>")
    return "<table>" + "".join(rows) + "</table>"


SOURCES = [
    ("Cărticică de cântece pentru chitară",
     "https://github.com/traiansf/chitara/blob/main/surse/Eugen%20Karban%20-%20carticica-de-cantece-pentru-chitara-200.pdf",
     "Eugen Karban, v2.0, <a href=\"http://www.eugenkarban.de\">eugenkarban.de</a>", 244),
    ("Caiet Christian Adventure",
     "https://github.com/traiansf/chitara/blob/main/surse/caiet-christian-adventure.pdf",
     "red. Adelina Flavia Iancu", 191),
    ("Caiet cabană RO",
     "https://github.com/traiansf/chitara/blob/main/surse/Caietrom.pdf",
     "<i>caiet_cantececabana_RO</i>, N. Raluca, C. Dragoș, P. Radu și mulți alții, 1998", 178),
    ("Caiet cabană EN",
     "https://github.com/traiansf/chitara/blob/main/surse/Caieteng.pdf",
     "<i>Caieteng</i>, 1998, aceeași echipă", 76),
    ("Colinde, cântece de Crăciun și de iarnă",
     "https://github.com/traiansf/chitara/blob/main/surse/Eugen%20Karban%20-%20culegere-de-colinde-si-cantece-de-iarna-100.pdf",
     "Eugen Karban, 2008", 100),
]


def sources_table():
    rows = "".join(
        f'<tr><td><b><a href="{url}">{html.escape(title)}</a></b> — {credit}</td><td>{n}</td></tr>'
        for title, url, credit, n in SOURCES)
    return f"<table>{rows}</table>"


def index_page(songs):
    stats = book_stats(songs)
    return f"""<!doctype html>
<html lang="ro"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Caiet de cântece pentru chitară</title>
<link rel="stylesheet" href="assets/site.css">
</head><body>
<button type="button" class="sidebar-toggle">☰ Cuprins</button>
{render_sidebar(songs, current_num=None, prefix="songs/")}
<main>
<h1>Caiet de cântece pentru chitară</h1>
<p>Un caiet de <b>{len(songs)} de cântece</b> cu acorduri — de cabană, folk
românesc, repertoriu internațional și colinde — compilat din cinci culegeri
tipărite și scanate.</p>
<p>📦 <a href="https://github.com/traiansf/chitara">github.com/traiansf/chitara</a>
— codul, caietul complet (.md/.pdf) și sursele scanate</p>

<h2>Ce conține</h2>
{content_counts_table(stats)}
<p>{stats["n_artists"]} de artiști în index, {stats["n_attributed"]} de
cântece atribuite. Fiecare cântec poartă digitațiile acordurilor lui,
pentru chitară și pentru ukulele:</p>
<pre>**Chitară:** Am x02210 · E 022100 · C x32010 · Dm xx0231 · G 320003
**Ukulele:** Am 2000 · E 4442 · C 0003 · Dm 2210 · G 0232</pre>
<p>Cifrele sunt poziția pe corzi, de la coarda groasă la cea subțire; <code>x</code>
= coarda nu se cântă. Pune cursorul pe orice acord din pagina unui cântec
ca să vezi digitația.</p>

<p>Acordurile stau fie pe rândul de deasupra versului, aliniate pe silaba unde
se schimbă, fie — la cântecele din Cărticica lui Karban — în text, între
paranteze drepte:</p>
<pre>[Am]Om bun des[E]chide-ne [Am]poarta
[C]Dă-ne o [G]coajă și [E]nu ne goni</pre>

<p>Un cântec care apare în mai multe surse cu acorduri sau versuri diferite e
păstrat de câte ori e nevoie, numerotat <code>(I)</code>, <code>(II)</code>,
<code>(III)</code>, cu variantele una lângă alta — {stats["n_variants"]} astfel
de intrări. Se contopesc doar cele cu aceeași succesiune de acorduri în aceeași
tonalitate.</p>

<h2>Surse</h2>
<p>Caietul nu conține material propriu: e o compilație a cinci culegeri, cu
sursa și pagina notate la fiecare cântec. La unele cântece acordurile au fost
înlocuite cu variante văzute pe YouTube, așa că sursa notată acoperă versurile,
nu neapărat acordurile.</p>
{sources_table()}
<p>Cele două volume ale lui <b>Eugen Karban</b> sunt distribuite de autor ca
<i>cardware</i>, cu cerința de a-i fi creditate. Transcrierile din ele îi
aparțin lui și celor care i-au trimis materiale, creditați individual în
volumele originale.</p>
<p>Drepturile asupra versurilor și muzicii aparțin autorilor și
compozitorilor respectivi. Acest depozit e o compilație de uz personal, nu o
publicație.</p>
</main>
<script src="assets/nav.js"></script>
</body></html>"""


def main():
    intro, songs, index_lines, annex_lines = make_pdf.parse(MD)

    assert songs, "no songs parsed from Caiet-chitara.md"
    filenames = [song_filename(s) for s in songs]
    assert len(set(filenames)) == len(filenames), "duplicate song filenames"

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    (OUT_DIR / "songs").mkdir(parents=True)
    (OUT_DIR / "assets").mkdir()
    (OUT_DIR / ".nojekyll").write_text("", encoding="utf-8")

    for i, s in enumerate(songs):
        prev_s = songs[i - 1] if i > 0 else None
        next_s = songs[i + 1] if i + 1 < len(songs) else None
        (OUT_DIR / "songs" / song_filename(s)).write_text(
            song_page(s, prev_s, next_s, songs), encoding="utf-8")

    (OUT_DIR / "index.html").write_text(index_page(songs), encoding="utf-8")

    for name in ("chords.js", "nav.js", "site.css"):
        shutil.copy(ASSETS_SRC / name, OUT_DIR / "assets" / name)
    emit_chords_data(OUT_DIR / "assets" / "chords-data.js")

    for name in filenames:
        assert (OUT_DIR / "songs" / name).exists(), f"missing {name}"

    print(f"{len(songs)} cântece generate în {OUT_DIR}")


if __name__ == "__main__":
    main()
