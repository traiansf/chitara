# Site HTML cu transpunere de acorduri — plan de implementare

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un site static (`docs/`, servit de GitHub Pages) cu o pagină HTML per cântec, generat din `Caiet-chitara.md`, cu butoane ▲/▼ care transpun live acordurile din versuri și digitațiile de chitară/ukulele.

**Architecture:** O unealtă nouă `tools/generate_html.py` reutilizează `make_pdf.parse()` (parsing existent) și emite 738 pagini + un index, plus un tabel de digitații (`docs/assets/chords-data.js`) generat direct din dicționarele Python existente (o singură sursă de adevăr, fără retranscriere). Un motor JS mic și fără dependințe (`docs/assets/chords.js`) transpune numele acordurilor pe scala cromatică și rezolvă digitațiile în două nivele: potrivire exactă în tabelul curat, altfel deplasează forma *deja cunoscută* a acelui acord în acel cântec (mereu definită, corectă prin construcție).

**Tech Stack:** Python 3 (generator, reutilizează `tools/make_pdf.py`, `tools/add_guitar_chords.py`, `tools/add_ukulele_chords.py`), JS vanilla fără dependințe (motor + interacțiune), Node 22 (`node --test` built-in, fără npm install) pentru testele motorului JS.

**Spec:** `specs/2026-09-09-html-transpose-design.md`

## Global Constraints

- `docs/` e regenerat integral de `generate_html.py` — nimic din `docs/` se editează manual.
- Identificarea acordurilor se face **exclusiv la generare, în Python**, cu același criteriu ca `make_pdf.py`/`add_guitar_chords.py` (`CHORD_RE`, linie-doar-acorduri sau `[Acord]` inline) — JS nu scanează niciodată text liber la runtime.
- Notație doar-diez (fără bemoli) pentru orice nume de acord recalculat de motor, ca în restul caietului.
- Fără dependințe npm — Node e folosit doar pentru `node --test` din `node:test`/`node:assert` (ambele built-in).
- La offset 0 (netranspus), orice element afișează **exact** textul original (byte-identic cu ce a scris deja `add_guitar_chords.py`/`add_ukulele_chords.py`/sursa) — motorul nu "corectează" typo-uri sau ortografii decât după ce utilizatorul apasă efectiv un buton de transpunere.
- Fără `localStorage`, fără persistare a transpunerii între pagini.

---

## Fișiere noi/modificate

```
tools/
  generate_html.py                 # nou — generatorul
  html_assets/
    chords.js                      # nou — motorul de transpunere (sursă, hand-written)
    chords.test.js                 # nou — teste Node
    nav.js                         # nou — toggle sidebar mobil + scroll la cântecul curent
    site.css                       # nou — stiluri site (sursă, hand-written)
docs/                               # nou, generat integral, committed
  index.html
  songs/NNN-slug.html               # 738 fișiere
  assets/{chords.js,chords-data.js,nav.js,site.css}
Makefile                            # nou
```

`chords-data.js` e singurul fișier generat din date Python (JSON dump din `add_guitar_chords.FINGERINGS`/`ALIAS`/`add_ukulele_chords.FINGERINGS`); `chords.js`/`nav.js`/`site.css` sunt scrise o dată în `tools/html_assets/` și copiate verbatim în `docs/assets/` la fiecare rulare.

---

### Task 1: Motorul JS — nume de acorduri (parse + transpunere)

**Files:**
- Create: `tools/html_assets/chords.js`
- Create: `tools/html_assets/chords.test.js`

**Interfaces:**
- Produces: `normalizeToken(tok: string): string`, `transposeName(normalizedName: string, semitones: number): string`, `transposeNote(note: string, semitones: number): string` — folosite de Task 2.
- Consumes: o variabilă globală `CHORDS_DATA` cu forma `{ NOTES: string[12], ALIAS: {[spelling: string]: string} }` (în test, un fixture mic scris de mână; în producție, `docs/assets/chords-data.js`, generat la Task 4).

- [ ] **Step 1: Scrie fișierul de test cu fixture-ul minim și primele cazuri**

```js
// tools/html_assets/chords.test.js
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

// chords.js e un script simplu (fără module/bundler, încărcat cu <script> în
// pagină) care se sprijină pe variabila globală CHORDS_DATA definită de
// chords-data.js. Aici punem un fixture mic înainte de a-l încărca.
global.CHORDS_DATA = {
  NOTES: ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"],
  ALIAS: {
    Db: "C#", Eb: "D#", Gb: "F#", Ab: "G#", Bb: "A#",
    Dbm: "C#m", Ebm: "D#m", Gbm: "F#m", Abm: "G#m", Bbm: "A#m",
    Cb: "B", Fb: "E", "E#": "F", "B#": "C",
    "Cm#": "C#m", "Fm#": "F#m", CaddG: "C",
  },
  FINGERINGS: { guitar: {}, ukulele: {} },
};
const src = fs.readFileSync(path.join(__dirname, "chords.js"), "utf8");
new Function("module", "exports", src)(module, module.exports);
const { normalizeToken, transposeNote, transposeName } = module.exports;

test("normalizeToken passes through a plain chord", () => {
  assert.equal(normalizeToken("Am"), "Am");
});

test("normalizeToken resolves a flat to its sharp spelling", () => {
  assert.equal(normalizeToken("Db"), "C#");
});

test("normalizeToken keeps the bass note when resolving the root", () => {
  assert.equal(normalizeToken("Db/F"), "C#/F");
});

test("normalizeToken fixes the source typo Cm#", () => {
  assert.equal(normalizeToken("Cm#"), "C#m");
});

test("transposeNote wraps around the octave upward", () => {
  assert.equal(transposeNote("B", 1), "C");
});

test("transposeNote wraps around the octave downward", () => {
  assert.equal(transposeNote("C", -1), "B");
});

test("transposeName shifts only the root, keeps quality and bass", () => {
  assert.equal(transposeName("D/F#", 2), "E/G#");
});

test("transposeName at offset 0 is a no-op", () => {
  assert.equal(transposeName("Am7", 0), "Am7");
});
```

- [ ] **Step 2: Rulează testele, verifică că pică (fișierul sursă nu există încă)**

Run: `node --test tools/html_assets/chords.test.js`
Expected: FAIL — `ENOENT` la citirea `chords.js` (fișierul nu există).

- [ ] **Step 3: Scrie `chords.js` cu logica minimă necesară**

```js
// tools/html_assets/chords.js
// Motor de transpunere a acordurilor — fără dependințe, rulează direct în
// browser (variabilele de mai jos ajung globale printr-un <script> simplu).
// Depinde de CHORDS_DATA (NOTES, ALIAS, FINGERINGS), definit în
// chords-data.js, generat din tools/add_guitar_chords.py / add_ukulele_chords.py —
// nu retranscrie acele tabele aici.

function normalizeToken(tok) {
  tok = tok.replace(/^[()]+|[()]+$/g, "").replace(/[:.]+$/, "");
  const m = /^([A-G](?:#|b)?)(.*)$/.exec(tok);
  if (!m) return tok;
  const root = m[1];
  let rest = m[2];
  let bass = "";
  const slash = rest.indexOf("/");
  if (slash !== -1) {
    bass = "/" + rest.slice(slash + 1);
    rest = rest.slice(0, slash);
  }
  const full = CHORDS_DATA.ALIAS[root + rest];
  if (full) return full + bass;
  return (CHORDS_DATA.ALIAS[root] || root) + rest + bass;
}

function transposeNote(note, semitones) {
  const i = CHORDS_DATA.NOTES.indexOf(note);
  if (i === -1) return note;
  return CHORDS_DATA.NOTES[((i + semitones) % 12 + 12) % 12];
}

function splitRootBass(name) {
  const m = /^([A-G]#?)(.*)$/.exec(name);
  if (!m) return null;
  let rest = m[2];
  let bass = null;
  const slash = rest.indexOf("/");
  if (slash !== -1) {
    bass = rest.slice(slash + 1);
    rest = rest.slice(0, slash);
  }
  return { root: m[1], rest, bass };
}

function transposeName(normalizedName, semitones) {
  const parts = splitRootBass(normalizedName);
  if (!parts) return normalizedName;
  const root = transposeNote(parts.root, semitones);
  const bass = parts.bass ? transposeNote(parts.bass, semitones) : null;
  return root + parts.rest + (bass ? "/" + bass : "");
}

if (typeof module !== "undefined") {
  module.exports = { normalizeToken, transposeNote, transposeName, splitRootBass };
}
```

- [ ] **Step 4: Rulează testele, verifică că trec**

Run: `node --test tools/html_assets/chords.test.js`
Expected: toate cele 8 teste PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/html_assets/chords.js tools/html_assets/chords.test.js
git commit -m "Adaugă motorul JS de transpunere: parsare și redenumire acorduri

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AFDuLRSP4qfStzu6MVmrVm"
```

---

### Task 2: Motorul JS — rezolvarea digitațiilor (tabel curat + deplasare de formă)

**Files:**
- Modify: `tools/html_assets/chords.js`
- Modify: `tools/html_assets/chords.test.js`

**Interfaces:**
- Consumes: `normalizeToken`, `transposeName` din Task 1; `CHORDS_DATA.FINGERINGS.{guitar,ukulele}` (obiect `{numeAcord: "stringDigitații"}`, digitații = un caracter hex per coardă, `"x"` = mut).
- Produces: `lookupFingering(name: string, table: object): string|null`, `shiftFingering(fingering: string, semitones: number): string`, `fingerFor(rawToken: string, semitones: number, originalFingering: string, table: object): {name: string, fingering: string}`, `transposedLabel(rawToken: string, semitones: number): string` — folosite de Task 3.

- [ ] **Step 1: Extinde fixture-ul de test cu digitații și scrie testele**

Adaugă în `CHORDS_DATA.FINGERINGS` din `chords.test.js` (înlocuiește liniile `FINGERINGS: { guitar: {}, ukulele: {} },`):

```js
  FINGERINGS: {
    guitar: {
      Am: "x02210", Cm: "x35543", "C#m": "x46654",
      G: "320003", D6: "xx0202",
    },
    ukulele: { Am: "2000", Db: "1114" },
  },
```

Adaugă testele:

```js
const { lookupFingering, shiftFingering, fingerFor, transposedLabel } = module.exports;

test("lookupFingering finds an exact match", () => {
  assert.equal(lookupFingering("Am", CHORDS_DATA.FINGERINGS.guitar), "x02210");
});

test("lookupFingering returns null when nothing matches", () => {
  assert.equal(lookupFingering("F#maj7", CHORDS_DATA.FINGERINGS.guitar), null);
});

test("lookupFingering falls back to the enharmonic-flat spelling", () => {
  // ukulele table only has "Db", not "C#" — a transposed target named "C#"
  // must still find it.
  assert.equal(lookupFingering("C#", CHORDS_DATA.FINGERINGS.ukulele), "1114");
});

test("shiftFingering moves every fretted string by the same amount", () => {
  // Am (x02210) up 3 semitones is the same shape as the curated Cm (x35543)
  assert.equal(shiftFingering("x02210", 3), "x35543");
});

test("shiftFingering takes the shorter circular direction when possible", () => {
  // Am up 3 or down 9 land on the same chord; the shorter step (+3) is used
  assert.equal(shiftFingering("x02210", 3), shiftFingering("x02210", -9));
});

test("shiftFingering never produces a negative fret", () => {
  const r = shiftFingering("x02210", -1); // Am down 1 semitone -> open string would go to -1
  assert.ok(!/-/.test(r));
});

test("shiftFingering falls back to the long way around when the short direction would fret a string below 0", () => {
  // G (320003) down 1 semitone can't be played by un-fretting an open
  // string, so the shape moves up 11 semitones instead — correct (still the
  // same chord), just far up the neck. Accepted limitation: tier 1 (the
  // curated table) covers every root for major/minor/7/m7/dim7, so this
  // path only ever fires for the rarer qualities that have gaps in the
  // curated table, and it never returns a wrong chord, only an awkward one.
  assert.equal(shiftFingering("320003", -1), "edbbbe");
});

test("shiftFingering returns null when no direction keeps every fret within 0-15", () => {
  // Dadd9 (x54230, guitar's real curated shape) down 1 semitone: the short
  // direction takes the open string (fret 0) to -1; the long way around
  // pushes the fret-5 string to 16, past a single hex digit. Neither
  // direction is representable, so there is no valid shift.
  assert.equal(shiftFingering("x54230", -1), null);
});

test("fingerFor prefers the curated exact match over shifting", () => {
  const r = fingerFor("Am", 3, "x02210", CHORDS_DATA.FINGERINGS.guitar);
  assert.deepEqual(r, { name: "Cm", fingering: "x35543" });
});

test("fingerFor falls back to shifting the song's own shape when no curated match exists", () => {
  // "D" isn't in this tiny fixture table at all, so tier 2 must fire
  const r = fingerFor("D", 1, "xx0232", CHORDS_DATA.FINGERINGS.guitar);
  assert.equal(r.name, "D#");
});

test("fingerFor at offset 0 returns the original untouched", () => {
  const r = fingerFor("Cm#", 0, "x46654", CHORDS_DATA.FINGERINGS.guitar);
  assert.deepEqual(r, { name: "Cm#", fingering: "x46654" });
});

test("fingerFor passes through a null fingering when no valid shift exists and no curated match covers the target", () => {
  // "Dadd9" transposed down 1 semitone targets "C#add9", not in this tiny
  // fixture table, so tier 2 fires and (per the shiftFingering test above)
  // returns null — callers (Task 3) must handle this, never display it as-is
  const r = fingerFor("Dadd9", -1, "x54230", CHORDS_DATA.FINGERINGS.guitar);
  assert.deepEqual(r, { name: "C#add9", fingering: null });
});

test("transposedLabel renders the normalized+transposed name", () => {
  assert.equal(transposedLabel("Cm#", 0), "Cm#"); // offset 0: untouched
  // Cm# normalizes to C#m; C#m up 1 semitone is Dm, not "D"
  assert.equal(transposedLabel("Cm#", 1), "Dm");
});
```

- [ ] **Step 2: Rulează testele, verifică că pică**

Run: `node --test tools/html_assets/chords.test.js`
Expected: FAIL — `lookupFingering is not defined` (și restul funcțiilor noi).

- [ ] **Step 3: Implementează în `chords.js`, înainte de blocul `if (typeof module ...)`**

```js
function lookupFingering(name, table) {
  const tryName = (n) => {
    if (table[n]) return table[n];
    const base = n.split("/")[0];
    if (table[base]) return table[base];
    let m = /^([A-G]#?)([0-9])$/.exec(base);
    if (m && m[2] === "5") return table[m[1]] || null;
    if (m && m[2] === "4") return table[m[1] + "sus4"] || null;
    m = /^([A-G]#?(?:m)?)(?:dim|aug|\+)([0-9]*)$/.exec(base);
    if (m) return table[m[1] + "dim7"] || table[m[1]] || null;
    if (base.endsWith("+")) return table[base.slice(0, -1) + "aug"] || table[base.slice(0, -1)] || null;
    return null;
  };
  const direct = tryName(name);
  if (direct) return direct;
  // the curated tables mix sharp and flat spellings for the same pitch
  // (e.g. ukulele only lists "Db", not "C#") — try the enharmonic flip too
  const parts = splitRootBass(name);
  if (!parts) return null;
  const FLAT = { "C#": "Db", "D#": "Eb", "F#": "Gb", "G#": "Ab", "A#": "Bb" };
  const flat = FLAT[parts.root];
  if (!flat) return null;
  return tryName(flat + parts.rest + (parts.bass ? "/" + parts.bass : ""));
}

function shiftFingering(fingering, semitones) {
  const n = ((semitones % 12) + 12) % 12;      // 0..11
  const delta = n > 6 ? n - 12 : n;            // shortest circular step, -5..6
  const apply = (d) => {
    const out = [];
    for (const ch of fingering) {
      if (ch === "x") { out.push("x"); continue; }
      const fret = parseInt(ch, 16) + d;
      // a fret must fit one hex digit (0-15); either direction can miss —
      // the short one by going negative (an open string can't un-fret),
      // the long one by pushing an already-high fret past 15
      if (fret < 0 || fret > 15) return null;
      out.push(fret.toString(16));
    }
    return out.join("");
  };
  return apply(delta) ?? apply(delta < 0 ? delta + 12 : delta - 12);
  // both can return null (e.g. guitar's curated "Dadd9": "x54230" shifted
  // by -1: short direction takes the open string to -1, long direction
  // pushes fret 5 to 16) — callers must treat a null result as "no
  // fingering available", never as a string to display as-is.
}

function fingerFor(rawToken, semitones, originalFingering, table) {
  if (semitones === 0) return { name: rawToken, fingering: originalFingering };
  const targetName = transposeName(normalizeToken(rawToken), semitones);
  const exact = lookupFingering(targetName, table);
  if (exact) return { name: targetName, fingering: exact };
  return { name: targetName, fingering: shiftFingering(originalFingering, semitones) };
}

function transposedLabel(rawToken, semitones) {
  if (semitones === 0) return rawToken;
  return transposeName(normalizeToken(rawToken), semitones);
}
```

Actualizează și exportul de la finalul fișierului:

```js
if (typeof module !== "undefined") {
  module.exports = {
    normalizeToken, transposeNote, transposeName, splitRootBass,
    lookupFingering, shiftFingering, fingerFor, transposedLabel,
  };
}
```

- [ ] **Step 4: Rulează testele, verifică că trec**

Run: `node --test tools/html_assets/chords.test.js`
Expected: toate testele PASS (verifică mai întâi că ai corectat linia semnalată la Step 1).

- [ ] **Step 5: Commit**

```bash
git add tools/html_assets/chords.js tools/html_assets/chords.test.js
git commit -m "Adaugă rezolvarea digitațiilor: potrivire exactă + deplasare de formă

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AFDuLRSP4qfStzu6MVmrVm"
```

---

### Task 3: Motorul JS — cablarea în pagină (butoane, sidebar mobil)

**Files:**
- Modify: `tools/html_assets/chords.js`
- Create: `tools/html_assets/nav.js`

**Interfaces:**
- Consumes: `fingerFor`, `transposedLabel` din Task 2 — `fingerFor` poate returna `fingering: null` (nicio formă valabilă, vezi `shiftFingering`), tratat mai jos ca "arată doar numele acordului"; markup-ul generat de Task 4/5 (`.transpose-controls button[data-action]`, `.ch[data-chord]`, `.fingering[data-chord][data-fingering][data-instrument]`, `.offset-label`, `.sidebar-toggle`, `.sidebar`, `.current`).
- Produces: comportament la runtime, verificat manual în browser la Task 6 (fără test Node — necesită DOM, nu logică pură).

- [ ] **Step 1: Adaugă la finalul `chords.js` (înainte de blocul `module.exports`) cablarea DOM**

```js
function renderAll(offset) {
  document.querySelectorAll(".ch[data-chord]").forEach((el) => {
    const raw = el.dataset.chord;
    el.textContent = offset === 0 ? raw : transposedLabel(raw, offset);
  });
  document.querySelectorAll(".fingering[data-chord]").forEach((el) => {
    const raw = el.dataset.chord;
    const orig = el.dataset.fingering;
    if (offset === 0) {
      el.textContent = `${raw} ${orig}`;
      return;
    }
    const table = CHORDS_DATA.FINGERINGS[el.dataset.instrument];
    const { name, fingering } = fingerFor(raw, offset, orig, table);
    // fingering is null when no fret shape fits (see chords.js
    // shiftFingering) — show the chord name alone rather than "null"
    el.textContent = fingering ? `${name} ${fingering}` : name;
  });
  const label = document.querySelector(".offset-label");
  if (label) label.textContent = offset > 0 ? `+${offset}` : String(offset);
}

function initTranspose() {
  const controls = document.querySelector(".transpose-controls");
  if (!controls) return;
  let offset = 0;
  controls.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    if (btn.dataset.action === "up") offset += 1;
    else if (btn.dataset.action === "down") offset -= 1;
    else offset = 0;
    renderAll(offset);
  });
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", initTranspose);
}
```

(`typeof document !== "undefined"` ferește testele Node, care nu au DOM, de o eroare la `require`.)

- [ ] **Step 2: Scrie `nav.js` — toggle sidebar mobil + scroll la cântecul curent**

```js
// tools/html_assets/nav.js
document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.querySelector(".sidebar-toggle");
  const sidebar = document.querySelector(".sidebar");
  if (!toggle || !sidebar) return;
  toggle.addEventListener("click", () => {
    const opening = !sidebar.classList.contains("open");
    sidebar.classList.toggle("open", opening);
    if (opening) {
      const current = sidebar.querySelector(".current");
      if (current) current.scrollIntoView({ block: "center" });
    }
  });
});
```

- [ ] **Step 3: Rulează suita de teste existentă, verifică că n-ai stricat nimic**

Run: `node --test tools/html_assets/chords.test.js`
Expected: toate testele PASS (nimic din acest task nu afectează logica testată — `document` e `undefined` sub Node, deci `initTranspose` nu e apelat).

- [ ] **Step 4: Commit**

```bash
git add tools/html_assets/chords.js tools/html_assets/nav.js
git commit -m "Cablează motorul de transpunere pe pagină și adaugă toggle-ul de sidebar mobil

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AFDuLRSP4qfStzu6MVmrVm"
```

---

### Task 4: `generate_html.py` — emiterea datelor și randarea versurilor/digitațiilor

**Files:**
- Create: `tools/generate_html.py`

**Interfaces:**
- Consumes: `make_pdf.parse(md_path) -> (intro, songs, index_lines, annex_lines)` unde fiecare `song` e `dict(num, title, meta, uke, gtr, body, shrink, part)`; `make_pdf.CHORD_RE`, `make_pdf.SKIP_TOKENS`, `make_pdf.is_chord_line`; `add_guitar_chords.NOTES`, `add_guitar_chords.ALIAS`, `add_guitar_chords.FINGERINGS`; `add_ukulele_chords.FINGERINGS`.
- Produces: `render_pre_interactive(body_lines: list[str]) -> str`, `render_fingering_line(line: str) -> str` (deduce singur "guitar"/"ukulele" din prefixul `**Chitară:**`/`**Ukulele:**` al liniei), `emit_chords_data(path: str) -> None` — folosite de Task 5 pentru asamblarea paginilor.

- [ ] **Step 1: Scrie scheletul unelte și `emit_chords_data`**

```python
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
```

- [ ] **Step 2: Verifică manual `emit_chords_data`**

Run:
```bash
mkdir -p /tmp/chords-data-check && python3 -c "
import sys; sys.path.insert(0, 'tools')
from generate_html import emit_chords_data
emit_chords_data('/tmp/chords-data-check/chords-data.js')
"
head -c 300 /tmp/chords-data-check/chords-data.js
```
Expected: fișierul începe cu `const CHORDS_DATA = {"NOTES": ["C", "C#", ...`. (Nu e nevoie de suită de teste pentru asta — e o serializare directă a unor dicționare deja verificate de `add_guitar_chords.py --check`; codebase-ul n-are convenție de teste pytest, verificarea se face prin inspecție, ca la celelalte unelte din `tools/`.)

- [ ] **Step 3: Adaugă `render_pre_interactive` — versuri cu acorduri individuale marcate**

```python
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
                    # the same escaped value for both, as an earlier draft
                    # did, would let a literal '"' in a token break out of
                    # the attribute
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
```

- [ ] **Step 4: Verifică manual pe un cântec real din caiet, în ambele notații**

Run:
```bash
python3 -c "
import sys; sys.path.insert(0, 'tools')
from generate_html import render_pre_interactive
import make_pdf
_, songs, _, _ = make_pdf.parse('Caiet-chitara.md')
by_title = {s['title']: s for s in songs}
print(render_pre_interactive(by_title['Mă întorc și pașii-s grei']['body'][:4]))
"
```
Expected: fiecare token de acord (`[Em]`, `[G]`, `[C]`) apare ca `<span class="ch" data-chord="Em">[Em]</span>` etc., restul versului netușat. Repetă cu un cântec care are notația pe rând deasupra silabei (ex. `by_title['Strunga (II)']`) și verifică că fiecare acord de pe linia de acorduri e propriul `<span class="ch" data-chord="...">`, cu spațiile originale între ele păstrate ca text simplu.

- [ ] **Step 5: Adaugă `render_fingering_line` — linia Chitară/Ukulele cu perechi individuale**

```python
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
```

- [ ] **Step 6: Verifică manual**

Run:
```bash
python3 -c "
import sys; sys.path.insert(0, 'tools')
from generate_html import render_fingering_line
import make_pdf
_, songs, _, _ = make_pdf.parse('Caiet-chitara.md')
by_title = {s['title']: s for s in songs}
s = by_title['Mă întorc și pașii-s grei']
print(render_fingering_line(s['gtr']))
print(render_fingering_line(s['uke']))
"
```
Expected: `<div class="fingering-line"><b>Chitară:</b> <span class="fingering" data-chord="Em" data-fingering="022000" data-instrument="guitar">Em 022000</span> · ...</div>` (și analog pentru Ukulele).

- [ ] **Step 7: Commit**

```bash
git add tools/generate_html.py
git commit -m "Adaugă generate_html.py: emiterea tabelului de digitații și randarea versurilor

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AFDuLRSP4qfStzu6MVmrVm"
```

---

### Task 5: `generate_html.py` — asamblarea paginilor, sidebar, index, CSS

**Files:**
- Modify: `tools/generate_html.py`
- Create: `tools/html_assets/site.css`

**Interfaces:**
- Consumes: `render_pre_interactive`, `render_fingering_line`, `emit_chords_data` din Task 4; `make_pdf.slug`, `make_pdf.mini_md`; `reorganize_parts.PARTS` (structura părților/subsecțiunilor, pentru etichetele din sidebar).
- Produces: `docs/index.html`, `docs/songs/NNN-slug.html` × 738, `docs/assets/*` — verificate la Step 6 (count + linkuri).

- [ ] **Step 1: Filename și sidebar**

```python
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
```

- [ ] **Step 2: Verifică manual sidebar-ul**

Run:
```bash
python3 -c "
import sys; sys.path.insert(0, 'tools')
from generate_html import render_sidebar
import make_pdf
_, songs, _, _ = make_pdf.parse('Caiet-chitara.md')
html_out = render_sidebar(songs, 60)
assert html_out.count('song-link') == 738
assert 'current' in html_out
print('sidebar ok,', len(html_out), 'chars')
"
```
Expected: `sidebar ok, <N> chars` fără eroare de assert.

- [ ] **Step 3: Pagina unui cântec**

```python
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
```

- [ ] **Step 4: Index și funcția principală**

```python
def index_page(songs):
    return f"""<!doctype html>
<html lang="ro"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Caiet de cântece pentru chitară</title>
<link rel="stylesheet" href="assets/site.css">
</head><body>
<main>
<h1>Caiet de cântece pentru chitară</h1>
<p>{len(songs)} de cântece. Alege unul din listă.</p>
{render_sidebar(songs, current_num=None, prefix="songs/")}
</main>
</body></html>"""


def main():
    intro, songs, index_lines, annex_lines = make_pdf.parse(MD)

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    (OUT_DIR / "songs").mkdir(parents=True)
    (OUT_DIR / "assets").mkdir()

    for i, s in enumerate(songs):
        prev_s = songs[i - 1] if i > 0 else None
        next_s = songs[i + 1] if i + 1 < len(songs) else None
        (OUT_DIR / "songs" / song_filename(s)).write_text(
            song_page(s, prev_s, next_s, songs), encoding="utf-8")

    (OUT_DIR / "index.html").write_text(index_page(songs), encoding="utf-8")

    for name in ("chords.js", "nav.js", "site.css"):
        shutil.copy(ASSETS_SRC / name, OUT_DIR / "assets" / name)
    emit_chords_data(OUT_DIR / "assets" / "chords-data.js")

    # ---- verification, same discipline as reorganize_parts.py
    assert len(songs) == 738, f"expected 738 songs, got {len(songs)}"
    filenames = {song_filename(s) for s in songs}
    assert len(filenames) == len(songs), "duplicate song filenames"
    for name in filenames:
        assert (OUT_DIR / "songs" / name).exists(), f"missing {name}"

    print(f"{len(songs)} cântece generate în {OUT_DIR}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Scrie `tools/html_assets/site.css`**

```css
* { box-sizing: border-box; }
body { margin: 0; font-family: sans-serif; color: #111; background: #fdfdfb; }
main { max-width: 900px; margin: 0 auto; padding: 12px 16px 40px; }
h1 { font-size: 1.4rem; }
.meta { font-size: 0.85rem; color: #444; margin-bottom: 6px; }
.meta a { color: #1a4d8b; }
.fingering-line { font-size: 0.85rem; color: #333; margin-bottom: 4px; }
.fingering-line b { color: #8b1a1a; }
.fingering { white-space: nowrap; }
pre {
  font-family: 'DejaVu Sans Mono', monospace;
  white-space: pre-wrap;
  overflow-x: auto;
  line-height: 1.35;
  font-size: 0.95rem;
}
.ln { display: block; white-space: pre-wrap; }
.bl { display: block; height: 0.7em; }
.ch { color: #8b1a1a; font-weight: bold; }
.transpose-controls { margin: 10px 0; display: flex; gap: 8px; align-items: center; }
.transpose-controls button {
  font-size: 1rem; padding: 4px 10px; cursor: pointer;
}
.offset-label { min-width: 2ch; text-align: center; font-weight: bold; }
.song-nav { margin-top: 24px; display: flex; justify-content: space-between; }
.song-nav a { color: #1a4d8b; text-decoration: none; }

.sidebar-toggle { display: none; }
.sidebar { border-right: 1px solid #ddd; padding: 10px; overflow-y: auto; }
.sidebar h3 { font-size: 0.8rem; color: #888; margin: 12px 0 4px; }
.sidebar a.song-link {
  display: block; font-size: 0.85rem; padding: 2px 4px; color: #222;
  text-decoration: none; border-radius: 3px;
}
.sidebar a.song-link.current { background: #f0e6d2; font-weight: bold; }

body:has(main) {
  display: flex; align-items: flex-start;
}
.sidebar { position: sticky; top: 0; height: 100vh; width: 260px; flex: none; }

@media (max-width: 800px) {
  body:has(main) { display: block; }
  .sidebar-toggle {
    display: block; position: fixed; top: 8px; right: 8px; z-index: 10;
    font-size: 1rem; padding: 6px 10px;
  }
  .sidebar {
    position: fixed; inset: 0; width: auto; z-index: 9;
    background: #fdfdfb; transform: translateX(-100%);
    transition: transform 0.15s ease-out;
  }
  .sidebar.open { transform: translateX(0); }
}
```

- [ ] **Step 6: Rulează generatorul și verifică**

Run:
```bash
python3 tools/generate_html.py
find docs/songs -name '*.html' | wc -l
```
Expected: `738 cântece generate în /home/traian/chitara/docs`, urmat de `738`.

- [ ] **Step 7: Commit**

```bash
git add tools/generate_html.py tools/html_assets/site.css docs/
git commit -m "Generează site-ul HTML complet: 738 pagini, index, sidebar, stiluri

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AFDuLRSP4qfStzu6MVmrVm"
```

---

### Task 6: Makefile, verificare manuală în browser, publicare

**Files:**
- Create: `Makefile`

**Interfaces:**
- Consumes: `tools/make_pdf.py` (existent), `tools/generate_html.py` (Task 5).

- [ ] **Step 1: Scrie `Makefile`**

```makefile
.PHONY: pdf html all

pdf:
	python3 tools/make_pdf.py

html:
	python3 tools/generate_html.py

all: pdf html
```

- [ ] **Step 2: Verifică țintele**

Run: `make html`
Expected: aceeași ieșire ca la Task 5 Step 6 (`738 cântece generate...`).

- [ ] **Step 3: Verificare manuală în browser**

Run (în fundal sau într-un terminal separat): `python3 -m http.server 8000 --directory docs`

Deschide `http://localhost:8000/` și verifică:
- cuprinsul index-ului leagă la un cântec real;
- pe pagina cântecului 60 (`Mă întorc și pașii-s grei`, notație inline `[Em]`): apasă ▲ o dată; versul trebuie să arate `[Fm]` în loc de `[Em]` (E minor + 1 semiton = F minor, nu F major), și linia Chitară trebuie să arate digitația corectă pentru `Fm`;
- pe un cântec cu notație pe rând deasupra silabei (ex. „Strunga (II)”): verifică aceeași transpunere;
- apasă „reset”: totul revine exact la textul original (byte-identic, inclusiv orice typo sursă);
- redimensionează fereastra sub 800px (sau devtools responsive mode): sidebar-ul se ascunde, apare butonul „☰ Cuprins”, la apăsare se deschide scrolat pe cântecul curent evidențiat.

Oprește serverul (`Ctrl+C`) după verificare.

- [ ] **Step 4: Commit**

```bash
git add Makefile
git commit -m "Adaugă Makefile pentru regenerarea PDF-ului și a site-ului HTML

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01AFDuLRSP4qfStzu6MVmrVm"
```

- [ ] **Step 5: Anunță pasul manual rămas (publicarea)**

Nu configura Pages automat din agent — e o setare de cont GitHub. Spune-i utilizatorului:
> „Site-ul e generat și committed în `docs/`. Ca să-l publici: Settings → Pages → Deploy from branch → `main` / `docs`, o singură dată. După aceea orice `make html` + push actualizează site-ul live.”

---

## Self-review (efectuat la scrierea planului)

- **Acoperirea spec-ului:** scop/arhitectură (Task 4-6), motor de acorduri (Task 1-3), UX desktop+mobil (Task 5 CSS, Task 3 nav.js), Makefile (Task 6), publicare (Task 6 Step 5). Verificarea automată full-corpus (738×12) din spec e restrânsă la teste unitare ale funcțiilor pure (Task 1-2) — nivelul 2 al motorului (deplasare de formă) e corect prin construcție matematică (adunarea aceluiași `d` la fiecare coardă nemută păstrează intervalele), deci nu are nevoie de o baraj empiric peste tot corpusul; nivelul 1 (tabelul curat) e exact dicționarul deja validat de `add_guitar_chords.py --check`, importat, nu retranscris.
- **Fără placeholder-uri:** fiecare pas are cod real, nu descrieri.
- **Consistență de tip/nume:** `fingerFor`/`transposedLabel`/`lookupFingering`/`shiftFingering` au aceleași semnături în Task 2 și în utilizarea din Task 3; `render_pre_interactive`/`render_fingering_line` din Task 4 sunt exact cele apelate în Task 5.
