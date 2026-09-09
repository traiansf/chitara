#!/usr/bin/env python3
"""Generate the interactive HTML site (docs/) from Caiet-chitara.md.

Reuses tools/make_pdf.py's parser and the fingering tables from
add_guitar_chords.py / add_ukulele_chords.py — this tool never re-derives
chord data, it only re-renders what those already validated.

Usage: python3 tools/generate_html.py
"""
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
                pieces.append(f'<span class="ch" data-chord="{attr}">[{text}]</span>')
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
