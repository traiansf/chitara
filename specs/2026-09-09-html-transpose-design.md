# Site HTML cu transpunere de acorduri — design

Data: 2026-09-09

## Scop

`Caiet-chitara.md` afișat pe github.com nu poate rula JS (GitHub sanitizează
markdown-ul randat, elimină `<script>`/`onXxx`). Construim în schimb un site
static separat, publicat pe GitHub Pages, cu butoane per cântec pentru
transpunerea acordurilor cu un semiton (▲/▼), care actualizează live atât
acordurile din versuri cât și digitațiile de chitară/ukulele.

Caietul (`Caiet-chitara.md`) rămâne artefactul canonic; site-ul e un export
generat, ca și PDF-ul — regenerat dintr-o unealtă, nu editat manual.

## Structura fișierelor

```
docs/                       # servit de GitHub Pages (branch main, /docs)
  index.html                # cuprins complet, pe părți/subsecțiuni
  songs/
    001-slug.html
    002-slug.html
    ...                     # 738 fișiere, unul per cântec
  assets/
    site.css
    chords.js               # motorul de transpunere + tabelele de digitații
tools/
  generate_html.py          # unealtă nouă, generează tot ce e în docs/
Makefile                    # ținte: pdf, html, all
```

`docs/` e regenerat integral la fiecare rulare a `generate_html.py` — nu se
editează manual nimic în el, la fel cum PDF-ul nu se editează manual.

## Unealta `tools/generate_html.py`

- Reutilizează `tools/dedup_lib.py` (`parse_songs`, `body`) pentru a citi
  cântecele curente din `Caiet-chitara.md`.
- Reutilizează logica de randare a versurilor din `tools/make_pdf.py`
  (`render_pre` sau echivalent): aceleași două notații de acorduri (linie
  deasupra versului, sau `[Acord]` inline), clasificate identic —
  **exclusiv la generare, în Python**, cu același criteriu ca acum:
  - o linie e "linie de acorduri" doar dacă *toate* token-urile ei au forma
    unui acord (regex `CHORD_RE`, ca în `make_pdf.py`/`add_guitar_chords.py`);
  - altfel, doar substring-urile `[Acord]` explicite sunt acorduri.

  Doar token-urile care trec acest filtru sunt înfășurate în
  `<span class="ch">...</span>` în HTML. **Nu există scanare de acorduri la
  runtime în JS** — un cuvânt ca „Am” dintr-un vers normal nu e niciodată
  candidat, pentru că nu apare nici pe o linie doar-acorduri, nici între
  paranteze.

- Pentru linia `**Chitară:**`/`**Ukulele:**`, generează markup mai granular
  decât acum (care e doar `**bold**` → `<b>`): fiecare pereche acord+digitație
  devine `<span class="fingering" data-chord="Am">Am x02210</span>`, ca JS să
  poată rescrie fiecare bucată independent.

- Pentru fiecare cântec, generează `docs/songs/NNN-slug.html` cu:
  - sidebar cu cuprinsul complet (identic pe toate paginile, cântecul curent
    evidențiat), ascuns sub un buton „☰ Cuprins” pe ecrane mici;
  - titlu, sursă, link tabulaturi.ro (ca acum);
  - versurile randate ca mai sus;
  - linia Chitară/Ukulele cu markup granular + butoanele ▲ / ▼ / reset;
  - linkuri „← anterior” / „următor →” către cântecele vecine în ordinea
    cuprinsului.
- Generează `docs/index.html` cu cuprinsul pe părți/subsecțiuni, ca în md.
- Verificare la generare (aceeași disciplină ca `reorganize_parts.py`):
  738 de cântece generate, niciun link anterior/următor rupt, ancorele din
  index rezolvă la o pagină reală.

## Motorul de acorduri (`docs/assets/chords.js`)

Modul JS pur, fără dependințe externe, trei funcții testabile separat:

1. **`parseChord(tok)`** — portă `normalize()` + tabelul `ALIAS` din
   `add_guitar_chords.py` (typo-uri și prescurtări incluse: `Cm#`→`C#m`,
   `CaddG`→`C`, etc.). Separă rădăcină / calitate / bas opțional.
2. **`transposeName(parsed, semitones)`** — deplasează doar clasa de notă a
   rădăcinii (și a basului, dacă există) pe scala cromatică cu 12 note,
   notație doar-diez (ca în carte: `NOTES = [C, C#, D, D#, E, F, F#, G, G#,
   A, A#, B]`). Calitatea acordului nu se schimbă.
3. **`fingerFor(name, instrument)`** — rezolvă digitația, în ordine:
   1. potrivire exactă în tabelul curat portat din
      `add_guitar_chords.py`/`add_ukulele_chords.py` (deja complet pe toate
      cele 12 rădăcini pentru major, minor, `7`, `m7`, `dim7` — acestea nu
      ajung niciodată la pașii de mai jos);
   2. pentru acorduri cu bas (`X/Y`) fără formă proprie: cade pe forma
      acordului simplu `X` (fără bas) — pe ukulele, acordurile cu bas
      colapsează mereu direct la acordul simplu, ca și acum;
   3. pentru calitățile cu goluri în tabel (`maj7`, `sus2`, `sus4`, `add9`,
      `6`, `9`): digitație obținută prin **deplasarea unei forme existente**
      din tabelul curat, ca formă mobilă — exact tehnica reală de chitară
      (ex. F/F#/G# major din tabel sunt deja forma E deplasată cu 1/2/4
      frete). Concret: dintre rădăcinile care *au* deja o formă curată pentru
      acea calitate, aleg cea mai apropiată circular de rădăcina țintă (distanță
      minimă în semitonuri, ca fretele rezultate să rămână mici), calculez
      deplasarea `d` = distanța în semitonuri, și pentru fiecare coardă
      nemut ("x" rămâne "x") adaug `d` la fretul din șablon. Corect prin
      construcție (forma întreagă se mută solidar, deci intervalele dintre
      corzi — și deci calitatea acordului — nu se schimbă), nu un calcul
      independent per coardă care ar putea produce o formă nejucabilă;
   4. fallback ultim (foarte rar întâlnit): triada majoră/minoră simplă,
      mereu prezentă în tabel.

Pe pagină: la încărcare, scriptul indexează `.ch` și `[data-chord]`, ține un
contor `offset` (semitonuri, inițial 0). Butoanele ▲/▼ modifică `offset` și
rescriu textul acelor elemente direct (fără reload de pagină); „reset” pune
`offset` înapoi la 0. Dacă un element marcat `.ch` nu se parsează cu
`parseChord` (n-ar trebui să se întâmple, dat fiind filtrul de la generare),
e lăsat netușat — nu se modifică text la întâmplare.

Nu persistăm transpunerea între pagini (fiecare cântec e o încărcare de
pagină nouă) — fără `localStorage`, cf. deciziei de simplitate.

## UX

- **Desktop**: sidebar fix în stânga cu cuprinsul, scroll propriu, cântecul
  curent evidențiat; zona principală cu titlu/sursă/versuri/digitații/butoane;
  navigare anterior/următor la final.
- **Mobil**: sidebar ascuns sub buton „☰ Cuprins”, se deschide ca overlay
  deja scrolat pe cântecul curent; alegerea unui cântec e navigare normală de
  pagină (overlay-ul se închide automat, fiind altă pagină); anterior/următor
  ca butoane mari, tappable. Fără gesturi swipe.
- Fără auto-micșorare de font (ca la PDF) — pagina web scrollează normal.

## Publicare

- `docs/` committed pe `main`, regenerat local cu `make html` (sau
  `python3 tools/generate_html.py`), la fel cum `Caiet-chitara.pdf` e generat
  local și committed acum.
- GitHub Pages configurat manual, o singură dată: Settings → Pages → Deploy
  from branch: `main` / `docs`. Fără GitHub Actions nou.

## Makefile

```makefile
pdf:
	python3 tools/make_pdf.py

html:
	python3 tools/generate_html.py

all: pdf html
```

## Verificare

- `generate_html.py`: 738 de cântece generate, linkuri anterior/următor
  intacte, ancorele din cuprins rezolvă.
- Test JS/Node (port al `check()` din `add_guitar_chords.py`): rulează
  motorul pe toate cele 738 de cântece × toate cele 12 transpuneri posibile,
  verifică notele produse contra calității declarate a acordului (aceeași
  tehnică de verificare, doar aplicată exhaustiv pe toate transpunerile, nu
  doar pe digitațiile din carte).
- Verificare manuală: `python -m http.server` local în `docs/`; verific
  vizual un cântec cu notație pe rând deasupra silabei, unul cu `[Acord]`
  inline (sursă Karban), transpunerea în ambele; comportamentul mobil
  (responsive devtools) pentru sidebar/overlay.

## În afara scopului (YAGNI)

- Persistarea transpunerii între pagini/sesiuni.
- Deploy automat via GitHub Actions.
- Auto-micșorare font sau paginare „un cântec pe ecran” ca la PDF.
- Forme mobile de digitații alese manual pentru toate calitățile — motorul
  algoritmic le acoperă pe cele lipsă din tabel.
