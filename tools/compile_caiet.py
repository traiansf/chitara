"""Compile the unified Markdown caiet + addendum from merged data."""
import json, re, unicodedata, collections, subprocess, datetime

def norm(t):
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", t)

def sortkey(t):
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"^[^a-z0-9]+", "", t)

merged = json.load(open("merged_songs.json"))
addendum = json.load(open("addendum.json"))

# ---------------- proper nouns: trusted (caiet3 titles/artists) + body evidence ----------------
proper_strong = {}
body_seen = collections.Counter()
body_case = {}

def note_strong(w):
    if len(w) >= 2 and w[0].isupper() and not w.isupper():
        proper_strong.setdefault(norm(w), w)
    elif w.isupper() and 2 <= len(w) <= 4:  # acronyms like URSS
        proper_strong.setdefault(norm(w), w)

STOP_RO = {"de", "la", "cu", "in", "în", "din", "pe", "și", "si", "sau", "pentru",
           "fără", "fara", "ca", "o", "un", "lui", "cel", "cea", "cele", "care",
           "nu", "mai", "sa", "să", "se", "am", "a", "ai", "e", "e-n", "prin",
           "ne", "mi", "te", "ce", "către", "peste", "sub", "dintre", "între", "unui",
           "unei", "al", "ale", "asta", "dar", "deci", "iar", "tot", "își", "isi"}

for s in merged:
    if s["src"] == "caiet3":
        ws = re.findall(r"[\w'’-]+", s["title"], re.UNICODE)
        for w in ws[1:]:  # skip first word: sentence capital, not a proper noun
            if norm(w) not in STOP_RO:
                note_strong(w)
    if s.get("artist"):
        for w in re.findall(r"[\w'’-]+", s["artist"], re.UNICODE):
            note_strong(w)

WORD = re.compile(r"[\w'’-]+", re.UNICODE)
for s in merged:
    for l in s["lines"]:
        for m in WORD.finditer(l):
            w = m.group()
            if not (w[0].isupper() and len(w) > 2 and not w.isupper()):
                continue
            # look at what precedes the word: must be a lowercase letter-ending word
            before = l[: m.start()].rstrip()
            if not before or not before[-1].isalpha() or not before[-1].islower():
                continue  # line start / after punctuation -> sentence capital, not proper
            if norm(w) in STOP_RO:
                continue
            body_seen[norm(w)] += 1
            body_case.setdefault(norm(w), w)

# manual proper nouns seen in RO/EN caps titles that the trusted set misses
MANUAL_PROPER = ["Manole", "Eminescu", "Putna", "Bucegii", "Bucegilor", "Diana",
                 "Dianei", "Caraiman", "Carpați", "România", "Moldova", "Paraschivo",
                 "Foii", "Crai", "Craiului", "Piatra", "Plaiul", "Johana", "Carol",
                 "Susanna", "Anna", "Marie", "Bonnie", "Michelle", "Jude", "Robinson",
                 "Rigby", "Alice", "California", "Popa", "Nan", "Făgăraș", "Retezat",
                 "Decembre", "Martie"]
proper = dict(proper_strong)
for w in MANUAL_PROPER:
    proper.setdefault(norm(w), w)
# body-derived nouns only when strongly evidenced
for n, cnt in body_seen.items():
    if cnt >= 4 and n not in proper and len(n) >= 5:
        proper[n] = body_case[n]

SMALL_EN = {"a", "an", "the", "and", "or", "but", "of", "in", "on", "at", "to",
            "for", "from", "with", "by"}
ROMAN = re.compile(r"^[IVX]+$")

def genitive_hit(n):
    """Trusted proper noun whose stem matches (Diana ~ Dianei)."""
    if len(n) < 5:
        return False
    for p in proper_strong:
        if len(p) >= 5:
            common = 0
            for a, b in zip(p, n):
                if a != b:
                    break
                common += 1
            if common >= 4 and common >= min(len(p), len(n)) - 2:
                return True
    return False

def recase(title, lang):
    letters = [c for c in title if c.isalpha()]
    if not letters:
        return title
    # RO titles already in mixed case are left alone; intl titles are always
    # normalized to English title case for consistency
    if lang == "ro" and sum(1 for c in letters if c.isupper()) / len(letters) < 0.7:
        return title
    words = re.split(r"(\s+|-|,|\.|'|’|\(|\)|!|\?)", title)
    out = []
    first = True
    after_apos = False
    for w in words:
        if not re.match(r"[\wĂÂÎȘȚăâîșț]+$", w, re.UNICODE):
            out.append(w)
            if w in ("'", "’"):
                after_apos = True
            elif w.strip():
                after_apos = False
            continue
        lw = w.lower()
        n = norm(w)
        if after_apos and len(w) <= 2:
            out.append(lw)      # contraction tails: don't, heaven's, she'll
            after_apos = False
            continue
        after_apos = False
        if first:
            out.append(lw.capitalize())
            first = False
            continue
        if ROMAN.match(w) and len(w) >= 2:
            out.append(w)
        elif lang == "intl":
            out.append(lw if lw in SMALL_EN else lw.capitalize())
        elif n in STOP_RO:
            out.append(lw)
        elif n in proper and proper[n].lower() == lw:
            out.append(proper[n])
        elif genitive_hit(n):
            out.append(lw.capitalize())
        else:
            out.append(lw)
    t = "".join(out)
    return t[0].upper() + t[1:] if t else t

# hand overrides after review (norm(original title) -> fixes)
OVERRIDES = {
    "mrtambourineman": {"artist": "Bob Dylan"},
    "johnlenon": {},
}
ARTIST_FIX = {"John Lenon": "John Lennon", "Ducu Berti": "Ducu Bertzi",
              "Pasarea Colibri": "Pasărea Colibri", "Mihai Margineanu": "Mihai Mărgineanu",
              "Stefan Hrușcă": "Ștefan Hrușcă", "Carmen Silva CIocolată": "Carmen Silva Ciocolată",
              "Ion CIoroiu": "Ion Cioroiu"}

SRC_LABEL = {"caietrom": "Caiet cabană RO", "caieteng": "Caiet cabană EN",
             "caiet3": "Caiet Christian Adventure"}

TITLE_OVERRIDES = {
    "baladablondeloriubiri": "Balada blondelor iubiri",
    "dacadragostenue": "Dacă dragoste nu e...",
    "imposibilanunta": "Imposibila nuntă",
    "nuinimicastae": "Nu-i nimic, asta e!",
    "haimandruto": "Hai, mândruțo!",
    "calugaruldinvechiulschit": "Călugărul din vechiul schit",
    "micutablonda": "Micuța blondă",
    "pecinesicatecarari": "Pe cine și câte cărări",
    "papusa": "Păpușa",
    "ploaieinlunaluimarte": "Ploaie în luna lui marte",
    "santoarcemtimpul": "Să-ntoarcem timpul",
    "resemnarepaterna": "Resemnare paternă",
    "troninapuseniii": "Tron în Apuseni (II)",
    "theicelander": "The Islander",
    "heijude": "Hey Jude",
    "windofchanges": "Wind of Change",
    "taize": "Taizé",
    "whatsup": "What's Up",
    "vreauominune": "Vreau o minune!",
    "ohcarol": "Oh, Carol!",
}

for s in merged:
    s["disp_title"] = recase(s["title"], s["lang"]).strip()
    if norm(s["title"]) in TITLE_OVERRIDES:
        s["disp_title"] = TITLE_OVERRIDES[norm(s["title"])]
    a = s.get("artist")
    if a:
        s["artist"] = ARTIST_FIX.get(a, a)
    ov = OVERRIDES.get(norm(s["title"]))
    if ov:
        s.update(ov)

# disambiguate identical display titles (real variant songs)
seen_disp = {}
for s in merged:
    k = (s["lang"], s["disp_title"].lower())
    if k in seen_disp:
        seen_disp[k] += 1
        s["disp_title"] += f" ({'I' * (seen_disp[k])})" if seen_disp[k] <= 3 else f" ({seen_disp[k]})"
    else:
        seen_disp[k] = 1

# ---------------- markdown emission ----------------
anchors = collections.Counter()
def gh_slug(text):
    t = text.strip().lower()
    t = re.sub(r"[^\w\- ]", "", t, flags=re.UNICODE)
    t = re.sub(r" ", "-", t)
    base = t
    n = anchors[base]
    anchors[base] += 1
    return base if n == 0 else f"{base}-{n}"

def song_md(s, num):
    hdr = f"### {num}. {s['disp_title']}"
    slug = gh_slug(f"{num}. {s['disp_title']}")
    meta = []
    if s.get("artist"):
        who = s["artist"]
        meta.append(f"**{who}**")
    srcs = [f"{SRC_LABEL[s['src']]}, p. {s['page']}"]
    for x in s.get("also_in", []):
        srcs.append(f"{SRC_LABEL[x['src']]}, p. {x['page']}")
    meta.append("Sursa: " + " · ".join(srcs))
    if s.get("tab_url"):
        meta.append(f"[tabulaturi.ro]({s['tab_url']})")
    body = []
    prev_blank = True
    for l in s["lines"]:
        l = l.rstrip()
        if not l.strip():
            if not prev_blank:
                body.append("")
            prev_blank = True
        else:
            body.append(l)
            prev_blank = False
    while body and not body[-1]:
        body.pop()
    lines = [hdr, "", " · ".join(meta), "", "```text"]
    lines += body
    lines += ["```", ""]
    return slug, "\n".join(lines)

ro = sorted([s for s in merged if s["lang"] == "ro"], key=lambda s: sortkey(s["disp_title"]))
intl = sorted([s for s in merged if s["lang"] == "intl"], key=lambda s: sortkey(s["disp_title"]))

today = "4 august 2026"
out = []
out.append("# Caiet de cântece pentru chitară")
out.append("")
out.append(f"*Compilat din trei caiete de cabană — {today}.*")
out.append("")
out.append("**Surse:**")
out.append("")
out.append("- **Caiet cabană RO** — *caiet_cantececabana_RO* (1998, versuri@barcaciu.ro)")
out.append("- **Caiet cabană EN** — *Caieteng* (1998, aceeași echipă)")
out.append("- **Caiet Christian Adventure** — red. Adelina Flavia Iancu")
out.append("")
out.append("**Cum citești acordurile:** fiecare cântec e într-un bloc monospațiat; "
           "acordurile sunt scrise pe rândul de deasupra versului, aliniate deasupra "
           "silabei pe care se schimbă acordul. `R:` = refren; strofele sunt numerotate "
           "ca în caietele originale. Vezi și [anexa cu digitațiile acordurilor](#anexă-dicționar-de-acorduri).")
out.append("")
out.append("Cântecele artiștilor din acest caiet care există și pe tabulaturi.ro au link direct; "
           "**alte** cântece ale acelorași artiști (necuprinse aici) sunt listate în "
           "[addendumul cu linkuri](Caiet-chitara-addendum.md) — 1755 de piese de la 47 de artiști.")
out.append("")

# TOC
out.append("## Cuprins")
out.append("")
out.append(f"**[Partea I — Cântece de munte și folk românesc](#partea-i--cântece-de-munte-și-folk-românesc)** ({len(ro)} cântece)")
out.append("")
out.append(f"**[Partea a II-a — Repertoriu internațional](#partea-a-ii-a--repertoriu-internațional)** ({len(intl)} cântece)")
out.append("")
out.append("**[Index pe artiști](#index-pe-artiști)** · **[Anexă: dicționar de acorduri](#anexă-dicționar-de-acorduri)**")
out.append("")

toc_ro, toc_intl = [], []
body_ro, body_intl = [], []
artist_index = collections.defaultdict(list)

for i, s in enumerate(ro, 1):
    slug, md = song_md(s, i)
    label = s["disp_title"] + (f" — {s['artist']}" if s.get("artist") else "")
    toc_ro.append(f"{i}. [{label}](#{slug})")
    body_ro.append(md)
    if s.get("artist"):
        artist_index[s["artist"]].append((s["disp_title"], slug))
for i, s in enumerate(intl, len(ro) + 1):
    slug, md = song_md(s, i)
    label = s["disp_title"] + (f" — {s['artist']}" if s.get("artist") else "")
    toc_intl.append(f"{i}. [{label}](#{slug})")
    body_intl.append(md)
    if s.get("artist"):
        artist_index[s["artist"]].append((s["disp_title"], slug))

out.append("### Partea I (alfabetic)")
out.append("")
out += toc_ro
out.append("")
out.append("### Partea a II-a (alfabetic)")
out.append("")
out += toc_intl
out.append("")
out.append("---")
out.append("")
out.append("## Partea I — Cântece de munte și folk românesc")
out.append("")
out += body_ro
out.append("---")
out.append("")
out.append("## Partea a II-a — Repertoriu internațional")
out.append("")
out += body_intl

# artist index
out.append("---")
out.append("")
out.append("## Index pe artiști")
out.append("")
for a in sorted(artist_index, key=sortkey):
    links = ", ".join(f"[{t}](#{sl})" for t, sl in artist_index[a])
    out.append(f"- **{a}** — {links}")
out.append("")

# chord dictionary annex from Caietrom pages 171-172
res = subprocess.run(["pdftotext", "-layout", "-f", "171", "-l", "172",
                      "/home/traian/chitara/Caietrom.pdf", "-"],
                     capture_output=True, text=True)
annex = []
for l in res.stdout.replace("\x0c", "").split("\n"):
    ls = l.strip()
    if ls in {"171", "172", ""}:
        if annex and annex[-1] != "":
            annex.append("")
        continue
    annex.append(l.rstrip())
out.append("---")
out.append("")
out.append("## Anexă: dicționar de acorduri")
out.append("")
out.append("Digitații preluate din caietul RO (paginile 171–172). Cifrele sunt poziția pe "
           "corzi de la Mi grav (coarda 6) la Mi subțire (coarda 1); `x` = coarda nu se cântă.")
out.append("")
out.append("```text")
out += annex
out.append("```")
out.append("")

open("/home/traian/chitara/Caiet-chitara.md", "w").write("\n".join(out))
print(f"main caiet: {len(out)} lines, {len(ro)} RO + {len(intl)} INTL songs")

# ---------------- addendum ----------------
ad = []
ad.append("# Addendum — alte cântece ale artiștilor din caiet, pe tabulaturi.ro")
ad.append("")
ad.append(f"*Generat {today}. Liste de piese suplimentare (cu acorduri) pentru artiștii "
          "prezenți în [caietul principal](Caiet-chitara.md), disponibile pe "
          "[tabulaturi.ro](https://www.tabulaturi.ro). Piesele deja incluse în caiet nu apar aici.*")
ad.append("")
total = sum(len(v["tabs"]) for v in addendum.values())
ad.append(f"**{len(addendum)} artiști · {total} cântece.**")
ad.append("")
names = sorted(({"slug": k, **v} for k, v in addendum.items()),
               key=lambda v: sortkey(v["name"]))
anchors.clear()
slug_map = {v["name"]: gh_slug(f"{v['name']} ({len(v['tabs'])})") for v in names}
ad.append("Artiști: " + " · ".join(
    f"[{v['name']}](#{slug_map[v['name']]})" for v in names))
ad.append("")
for v in names:
    ad.append(f"## {v['name']} ({len(v['tabs'])})")
    ad.append("")
    for t in v["tabs"]:
        ad.append(f"- [{t['title']}](https://www.tabulaturi.ro/acorduri/{v['slug']}/{t['slug']})")
    ad.append("")
open("/home/traian/chitara/Caiet-chitara-addendum.md", "w").write("\n".join(ad))
print(f"addendum: {len(ad)} lines, {total} linked songs, {len(addendum)} artists")
