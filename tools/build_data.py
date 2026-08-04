"""Merge the three caiete: dedup, artist attribution, tabulaturi links."""
import json, re, unicodedata, difflib, collections

def norm(t):
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", t)

from extract_common import is_chord_text

def first_lyric(s, k=5):
    out = []
    for l in s["lines"]:
        t = l.strip()
        if t and not is_chord_text(t) and len(t) > 8:
            out.append(norm(t))
            if len(out) >= k:
                break
    return " ".join(out)

rom = json.load(open("caietrom_songs.json"))
eng = json.load(open("caieteng_songs.json"))
c3 = json.load(open("caiet3_songs.json"))
artist_tabs = json.load(open("artist_tabs.json"))

for s in rom:
    s["artist"] = None
    s["lang"] = "ro"
for s in eng:
    s["lang"] = "intl"
for s in c3:
    s["lang"] = "ro" if s["part"] == 1 else "intl"

# --- tab lookup: normalized tab title -> [(artist_name, artist_slug, tab_slug)]
tab_lookup = collections.defaultdict(list)
for slug, v in artist_tabs.items():
    for t in v["tabs"]:
        tab_lookup[norm(t["title"])].append((v["name"], slug, t["slug"]))

def tab_match(title):
    n = norm(title)
    if n in tab_lookup:
        return tab_lookup[n]
    close = difflib.get_close_matches(n, list(tab_lookup), n=1, cutoff=0.92)
    return tab_lookup[close[0]] if close else []

# --- dedup across sources (priority: caiet3 > caietrom > caieteng)
ALIAS = {"heijude": "heyjude"}
FORCE_MERGE = {"heyjude", "hotelcalifornia"}
all_songs = c3 + rom + eng
groups = {}          # norm title -> list of songs
order = []
for s in all_songs:
    key = ALIAS.get(norm(s["title"]), norm(s["title"]))
    close = difflib.get_close_matches(key, list(groups), n=1, cutoff=0.93)
    k = close[0] if close else key
    # verify same song by first lyric similarity when titles fuzzy-match
    if k in groups and k not in FORCE_MERGE:
        fl_new, fl_old = first_lyric(s), first_lyric(groups[k][0])
        sim = difflib.SequenceMatcher(None, fl_new, fl_old).ratio() if fl_new and fl_old else 0
        if sim < 0.5 and k == key:
            # same title, different song -> keep separate slot
            k = key + "#2"
            while k in groups and difflib.SequenceMatcher(
                    None, first_lyric(s), first_lyric(groups[k][0])).ratio() < 0.5:
                k += "'"
        elif sim < 0.5:
            k = key
    if k not in groups:
        groups[k] = []
        order.append(k)
    groups[k].append(s)

PRIO = {"caiet3": 0, "caietrom": 1, "caieteng": 2}
merged = []
dup_notes = 0
for k in order:
    g = sorted(groups[k], key=lambda s: PRIO[s["src"]])
    main = g[0]
    main["also_in"] = [{"src": x["src"], "page": x["page"]} for x in g[1:]]
    if g[1:]:
        dup_notes += 1
    # artist attribution chain
    if not main.get("artist"):
        for x in g[1:]:
            if x.get("artist"):
                main["artist"] = x["artist"]
                break
    hits = tab_match(main["title"])
    if hits:
        # unique artist among hits?
        names = {h[0] for h in hits}
        h = hits[0]
        main["tab_url"] = f"https://www.tabulaturi.ro/acorduri/{h[1]}/{h[2]}"
        if not main.get("artist") and len(names) == 1 and h[1] != "cantece-de-munte":
            main["artist"] = h[0]
            main["artist_from_tab"] = True
    merged.append(main)

json.dump(merged, open("merged_songs.json", "w"), ensure_ascii=False, indent=1)
print(f"total unique songs: {len(merged)} (from {len(all_songs)}; {dup_notes} had duplicates)")
print("by lang:", collections.Counter(s['lang'] for s in merged))
print("with artist:", sum(1 for s in merged if s.get('artist')),
      "| via tabulaturi:", sum(1 for s in merged if s.get('artist_from_tab')),
      "| with tab link:", sum(1 for s in merged if s.get('tab_url')))
# show attributions from tabulaturi for review
for s in merged:
    if s.get("artist_from_tab"):
        print("  TAB-ATTR:", s["title"], "->", s["artist"])
