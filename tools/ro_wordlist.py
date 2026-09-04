# -*- coding: utf-8 -*-
"""Expand the Romanian hunspell dictionary into a plain set of word forms.

Song lyrics are full of inflected forms, so the 181k dictionary stems are not
enough on their own; the affix rules in ro_RO.aff turn them into the forms that
actually appear in the text.  Only the pieces of the hunspell format this
dictionary uses are implemented: single-character flags, SFX and PFX rules with
a strip, an addition and a regex condition.
"""
import re, sys

AFF = "/home/traian/chitara/tools/data/ro_RO.aff"
DIC = "/home/traian/chitara/tools/data/ro_RO.dic"
OUT = "/home/traian/chitara/tools/data/ro_forms.txt"


def load_affixes(path=AFF):
    sfx, pfx = {}, {}
    for line in open(path, encoding="utf-8"):
        parts = line.split()
        if len(parts) < 4 or parts[0] not in ("SFX", "PFX"):
            continue
        table = sfx if parts[0] == "SFX" else pfx
        flag = parts[1]
        if parts[2] in ("Y", "N") and len(parts) == 4:
            table.setdefault(flag, [])          # header line
            continue
        strip, add, cond = parts[2], parts[3], parts[4] if len(parts) > 4 else "."
        strip = "" if strip == "0" else strip
        add = "" if add == "0" else add
        try:
            rx = re.compile(cond + "$" if parts[0] == "SFX" else "^" + cond)
        except re.error:
            continue
        table.setdefault(flag, []).append((strip, add, rx))
    return sfx, pfx


def expand(path=DIC, limit=None):
    sfx, pfx = load_affixes()
    forms = set()
    with open(path, encoding="utf-8") as f:
        next(f)                                  # entry count
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            word, _, flags = line.partition("/")
            word = word.split("\t")[0]
            if not word:
                continue
            forms.add(word)
            suffixed = {word}
            for fl in flags:
                for strip, add, rx in sfx.get(fl, []):
                    if rx.search(word) and (not strip or word.endswith(strip)):
                        w = word[: len(word) - len(strip)] + add if strip else word + add
                        forms.add(w)
                        suffixed.add(w)
            for fl in flags:
                for strip, add, rx in pfx.get(fl, []):
                    for base in suffixed:
                        if rx.match(base) and (not strip or base.startswith(strip)):
                            forms.add(add + base[len(strip):])
            if limit and i > limit:
                break
    return forms


if __name__ == "__main__":
    forms = expand()
    forms = {w.lower() for w in forms if w and not w[0].isdigit()}
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(forms)))
    print(f"{len(forms)} forme -> {OUT}")
