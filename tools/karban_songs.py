# -*- coding: utf-8 -*-
"""Load the caiet and both Karban volumes as one comparable list of songs."""
import json, re, sys, unicodedata
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from dedup_lib import load, parse_songs, body
from extract_common import is_chord_text
from chord_seq import chords, dedupe_runs, best_match

CARTICICA = str(_HERE / "karban_carticica.json")
COLINDE = str(_HERE / "karban_colinde.json")
INLINE = re.compile(r"\[[^\]]*\]")
MARKER = re.compile(r"^\s*(\d{1,2}\.(?!\d)|R\d?\s*:|(?i:refren)(?:\s*[xX]\s*\d+)?\s*:?|"
                    r"(?i:bis)|(?i:strofa\s*\d*)\s*:?|(?i:solo|intro|final|bridge)\s*:?)\s*$")


def strip_accents(s):
    s = s.replace("ș", "s").replace("ş", "s").replace("ț", "t").replace("ţ", "t")
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def lyric_words(lines):
    out = []
    for l in lines:
        # a chord sits inside the word it falls on ("traia[C]sca"), so it is
        # removed rather than replaced, or the word comes apart
        t = INLINE.sub("", l).strip()
        if not t or is_chord_text(t) or MARKER.match(t):
            continue
        t = re.sub(r"^\s*(\d{1,2}\.(?!\d)|R\d?\s*:|(?i:refren)(?:\s*[xX]\s*\d+)?\s*:)\s*", "", t)
        out += re.sub(r"[^a-z0-9\s]", " ", strip_accents(t.lower())).split()
    return out


def all_songs():
    """-> list of dicts with src, title, artist, body, words, chords."""
    out = []

    lines = load()
    for s in parse_songs(lines):
        b = body(lines, s)
        out.append(dict(src="caiet", num=s["num"], title=s["title"], part=s["part"],
                        artist=s["artist"], meta=s["meta"], body=b))

    for s in json.load(open(CARTICICA)):
        out.append(dict(src="carticica", title=s["title"], part=None,
                        artist=s.get("artist") or s.get("section"),
                        section=s.get("section"), composer=s.get("composer"),
                        credits=s.get("credits", []), page=s["page"], body=s["body"]))

    for s in json.load(open(COLINDE)):
        out.append(dict(src="colinde", title=s["title"], part=None,
                        artist=s.get("artist"), composer=s.get("composer"),
                        credits=s.get("credits", []), page=s["page"], body=s["body"]))

    for s in out:
        s["words"] = lyric_words(s["body"])
        s["text"] = " ".join(s["words"])
        s["chords"] = dedupe_runs(chords(s["body"]))
    return out
