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


def build_song_filenames(songs):
    """Stable filenames, derived from the title slug rather than the
    running number — moving a song (which shifts every number after it)
    no longer renames the other 737 files. Collisions get a numeric
    suffix, same convention as dedup_lib.gh_slug's anchor collisions,
    though none exist today: every title is already unique (variant-
    numbered or artist-suffixed)."""
    seen = collections.Counter()
    filenames = {}
    for s in songs:
        base = make_pdf.slug(s["title"])
        n = seen[base]
        seen[base] += 1
        filenames[id(s)] = f"{base}.html" if n == 0 else f"{base}-{n}.html"
    return filenames


def song_filename(s, filenames):
    return filenames[id(s)]


PART_LABEL = {}  # sec_key -> "I.1 — De munte și de drum" / "Partea a II-a — ..."
def _init_part_labels():
    import reorganize_parts as rp
    for pkey, roman, name, subs in rp.PARTS:
        for sec, subname in (subs or [(pkey, None)]):
            PART_LABEL[sec] = f"{sec} — {subname}" if subname else f"{roman} — {name}"
_init_part_labels()


def render_sidebar(songs, filenames, current_num, prefix=""):
    out = ['<nav class="sidebar">']
    cur_part = None
    for s in songs:
        if s["part"] != cur_part:
            cur_part = s["part"]
            out.append(f'<h3>{html.escape(PART_LABEL.get(cur_part, cur_part))}</h3>')
        cls = " current" if s["num"] == current_num else ""
        out.append(
            f'<a class="song-link{cls}" href="{prefix}{song_filename(s, filenames)}">'
            f'{s["num"]}. {html.escape(s["title"])}</a>')
    out.append("</nav>")
    return "".join(out)


def song_page(s, filenames, prev_s, next_s, songs):
    body_html = render_pre_interactive(s["body"])
    fingerings = "".join(render_fingering_line(s[k]) for k in ("gtr", "uke") if s[k])
    nav_links = []
    if prev_s:
        nav_links.append(f'<a href="{song_filename(prev_s, filenames)}">← {html.escape(prev_s["title"])}</a>')
    if next_s:
        nav_links.append(f'<a href="{song_filename(next_s, filenames)}">{html.escape(next_s["title"])} →</a>')
    return f"""<!doctype html>
<html lang="ro"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(s["title"])} — Caiet de cântece</title>
<link rel="stylesheet" href="../assets/site.css">
</head><body>
<button type="button" class="sidebar-toggle">☰ Cuprins</button>
{render_sidebar(songs, filenames, s["num"], prefix="")}
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


README_PATH = Path("/home/traian/chitara/README.md")
GITHUB_REPO = "https://github.com/traiansf/chitara"


def rewrite_relative_links(md_text):
    """Any markdown link whose target isn't already absolute (http(s)/#)
    points at a repo file or folder that isn't under docs/ (Caiet-chitara.md,
    the PDF, surse/*) — on the deployed site that 404s, so point it at
    GitHub instead. Keeps README.md the single source of truth: nothing
    here needs updating when a source file moves or a new one is added."""
    def sub(m):
        target = m.group(1)
        if re.match(r"^(https?://|#)", target):
            return m.group(0)
        kind = "blob" if "." in target.rsplit("/", 1)[-1] else "tree"
        return f"]({GITHUB_REPO}/{kind}/main/{target})"
    return re.sub(r"\]\(([^)]+)\)", sub, md_text)


def markdown_block_to_html(text):
    """Converts the small subset of GFM README.md actually uses — headers,
    paragraphs, fenced code blocks, pipe tables — reusing make_pdf.mini_md
    for inline formatting (bold/italic/code/links) within each block."""
    lines = text.split("\n")
    out = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1
            continue
        if ln.startswith("```"):
            j = i + 1
            code = []
            while j < len(lines) and not lines[j].startswith("```"):
                code.append(lines[j])
                j += 1
            out.append(f"<pre>{html.escape(chr(10).join(code), quote=False)}</pre>")
            i = j + 1
            continue
        if ln.startswith("## "):
            out.append(f"<h2>{make_pdf.mini_md(ln[3:])}</h2>")
            i += 1
            continue
        if ln.lstrip().startswith("|"):
            j = i
            rows = []
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                rows.append(lines[j])
                j += 1
            rows = [r for r in rows if not re.match(r"^\s*\|[\s:|-]+\|\s*$", r)]
            trs = []
            for r in rows:
                cells = [c.strip() for c in r.strip().strip("|").split("|")]
                trs.append("<tr>" + "".join(f"<td>{make_pdf.mini_md(c)}</td>" for c in cells) + "</tr>")
            out.append("<table>" + "".join(trs) + "</table>")
            i = j
            continue
        j = i
        para = []
        while j < len(lines) and lines[j].strip() and not lines[j].startswith(("```", "## ")) and not lines[j].lstrip().startswith("|"):
            para.append(lines[j])
            j += 1
        out.append(f"<p>{make_pdf.mini_md(' '.join(para))}</p>")
        i = j
    return "\n".join(out)


def readme_content_html(stats):
    """The site's front page is README.md, converted, minus the opening
    file-links block (those point at raw repo files, not this deployed
    site — replaced by one link to the repo) — so index.html can never
    describe the book differently from what README.md says, and the
    Surse table in particular can never quietly drop a source."""
    text = README_PATH.read_text(encoding="utf-8")
    lines = text.split("\n")
    first_h2 = next(i for i, l in enumerate(lines) if l.startswith("## "))
    intro_block = "\n".join(lines[1:first_h2]).strip()
    intro_para = re.split(r"\n\s*\n", intro_block, maxsplit=1)[0]
    body_md = rewrite_relative_links("\n".join(lines[first_h2:]))

    html_out = (
        f"<p>{make_pdf.mini_md(intro_para.replace(chr(10), ' '))}</p>\n"
        f'<p>📦 <a href="{GITHUB_REPO}">'
        "github.com/traiansf/chitara</a> — codul, caietul complet "
        "(.md/.pdf) și sursele scanate</p>\n"
        + markdown_block_to_html(body_md)
    )
    # the "Ce conține" table is the one piece worth keeping generated
    # rather than converted verbatim — it's the number most likely to go
    # stale between a song move and the next time someone edits README.md
    html_out = re.sub(r"<table>.*?</table>", content_counts_table(stats),
                       html_out, count=1, flags=re.DOTALL)
    return html_out


def index_page(songs, filenames):
    stats = book_stats(songs)
    return f"""<!doctype html>
<html lang="ro"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Caiet de cântece pentru chitară</title>
<link rel="stylesheet" href="assets/site.css">
</head><body>
<button type="button" class="sidebar-toggle">☰ Cuprins</button>
{render_sidebar(songs, filenames, current_num=None, prefix="songs/")}
<main>
<h1>Caiet de cântece pentru chitară</h1>
{readme_content_html(stats)}
</main>
<script src="assets/nav.js"></script>
</body></html>"""


def main():
    intro, songs, index_lines, annex_lines = make_pdf.parse(MD)

    assert songs, "no songs parsed from Caiet-chitara.md"
    filenames = build_song_filenames(songs)
    filename_values = list(filenames.values())
    assert len(set(filename_values)) == len(filename_values), "duplicate song filenames"

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    (OUT_DIR / "songs").mkdir(parents=True)
    (OUT_DIR / "assets").mkdir()
    (OUT_DIR / ".nojekyll").write_text("", encoding="utf-8")

    for i, s in enumerate(songs):
        prev_s = songs[i - 1] if i > 0 else None
        next_s = songs[i + 1] if i + 1 < len(songs) else None
        (OUT_DIR / "songs" / song_filename(s, filenames)).write_text(
            song_page(s, filenames, prev_s, next_s, songs), encoding="utf-8")

    (OUT_DIR / "index.html").write_text(index_page(songs, filenames), encoding="utf-8")

    for name in ("chords.js", "nav.js", "site.css"):
        shutil.copy(ASSETS_SRC / name, OUT_DIR / "assets" / name)
    emit_chords_data(OUT_DIR / "assets" / "chords-data.js")

    for name in filename_values:
        assert (OUT_DIR / "songs" / name).exists(), f"missing {name}"

    print(f"{len(songs)} cântece generate în {OUT_DIR}")


if __name__ == "__main__":
    main()
