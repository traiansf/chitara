# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Depozitul e un caiet de cântece cu acorduri, compilat din cinci culegeri
scanate. `README.md` descrie caietul ca obiect de citit; fișierul de față
descrie cum e construit și cum se lucrează la el.

## Ideea centrală

**`Caiet-chitara.md` e și artefactul, și formatul de lucru.** Nu există bază
de date și nici sursă intermediară din care să se regenereze: uneltele vii
parsează Markdown-ul și îl rescriu pe loc. Orice modificare de conținut se
face în el, direct sau printr-o unealtă, apoi se regenerează PDF-ul.

Un cântec arată așa:

````
#### 176. Miruna (I)

**Pasărea Colibri** · muzica/versuri: … · Sursa: Cărticica Karban, p. 88 · [tabulaturi.ro](…)

**Chitară:** Am x02210 · E 022100

**Ukulele:** Am 2000 · E 4442

```text
…versuri și acorduri…
```
````

**Identitatea stabilă a unui cântec e `titlu || Sursa, p. N`** — unică pe toate
cele 738. Numărul curent și ancora sunt derivate și se schimbă la fiecare
rearanjare, deci nu construi nimic care să indexeze după număr.

## Structura cărții

Patru părți; părțile I și IV au subsecțiuni, II și III nu. Nivelurile de
titlu contează:

| Nivel | Ce e |
|---|---|
| `## Partea a II-a — Repertoriu românesc` | parte |
| `### I.1 — De munte și de drum` | subsecțiune (părțile I și IV) |
| `#### 176. Titlu` | cântec |

`tools/categorii.json` ține încadrarea fiecărui cântec: cheia stabilă →
`{"sectiune": "I.1"…"IV.4", "motiv": …}`. `tools/reorganize_parts.py` e singurul
lucru care atribuie numere, ancore, cuprins și index pe artiști; e idempotent,
deci **a muta un cântec înseamnă o linie schimbată în JSON plus o re-rulare**,
nu o editare manuală a caietului.

`reorganize_parts.py` copie neatinse introducerea (tot ce e înaintea
`## Cuprins`) și anexa cu digitațiile — pe acelea le editezi de mână.

## Comenzi

```bash
python3 tools/reorganize_parts.py          # rearanjează după categorii.json
python3 tools/make_pdf.py                  # regenerează PDF-ul (~2 min)
python3 tools/add_guitar_chords.py         # recalculează digitațiile de chitară
python3 tools/add_ukulele_chords.py        # idem, ukulele
python3 tools/add_guitar_chords.py --check # verifică fiecare digitație contra notelor ei
python3 tools/replace_song_block.py '#### 176. Miruna' continut.txt
python3 tools/collapse_repeated_chords.py  # comprimă acordurile repetate în ^
tools/run.sh                               # reface caietul de la zero (vezi mai jos)
make pdf                                   # = python3 tools/make_pdf.py
make html                                  # regenerează site-ul HTML interactiv (docs/)
```

Cere `python3` cu **pymupdf** (`fitz`), **poppler** (`pdftotext`) și
**google-chrome-stable** (headless, pentru PDF).

## Cele două generații de unelte

`tools/` amestecă unelte vii cu pași istorici. Distincția contează:

**Vii** — citesc și rescriu caietul curent: `reorganize_parts.py`,
`dedup_lib.py` (parserul comun), `make_pdf.py`, `add_guitar_chords.py`,
`add_ukulele_chords.py`, `replace_song_block.py`, `normalize_verses.py`,
`restore_diacritics.py`, `generate_html.py`, `collapse_repeated_chords.py`.

`generate_html.py` citește caietul cu parserul din `make_pdf.py` și
generează integral `docs/` — un site static (o pagină per cântec, cu
butoane de transpunere a acordurilor) publicat pe GitHub Pages din
`main` /docs. Sursa lui vie e `tools/html_assets/` (motorul JS
`chords.js`, testat cu `node --test tools/html_assets/chords.test.js`,
plus `nav.js`/`site.css`), copiată neschimbată în `docs/assets/` la
fiecare rulare; `docs/` însuși nu se editează manual, la fel ca PDF-ul.

Pe site, cântecele cu notație inline sunt afișate ca cele cu acorduri
deasupra versului: fiecare acord (și `^`, ca `/`) e scos din text și
„plutește” deasupra silabei (CSS, `left:Nch` calculat de `layout_floating()`
— nu rescrie linia). Coloana e cea din sursă, decalată spre dreapta doar cât
trebuie ca să nu atingă acordul anterior (acordurile înghesuite cu `=` ajung
deci ușor la dreapta poziției lor "exacte", dar rămân lizibile și separate,
nu lipite).

`make_pdf.py` face la fel pentru orice cântec cu măcar un acord inline
(`s["converted"]`, testat de `has_inline_chords()`) — inclusiv perechile
native acord-deasupra-versului din același cântec, convertite la aceeași
reprezentare, ca pagina să nu sară între două stiluri. Diferă de site pe
două puncte, amândouă pentru că e tipar (nu există derulare orizontală de
rezervă): font proporțional (`'DejaVu Sans'`, nu monospace — cântecele
astea nu poartă informație de aliniere pe coloană oricum) în loc de grid
monospace, iar fiecare ancoră stă chiar la poziția ei naturală din text
(nu la un offset calculat de la începutul rândului), ca împărțirea pe
rânduri (necesară la tipar) să ducă acordurile cu ea automat. Înghesuiala
se rezolvă măsurând lățimea reală a glifelor DejaVu Sans Bold cu pymupdf
(`measured_spacing()`) — un număr de caractere n-are legătură fixă cu
lățimea într-un font proporțional — inserând spații fixe (` `,
imune la restrângerea CSS a spațiilor multiple) exact cât trebuie.
Dimensiunea fontului per cântec vine din `fs_fit_prop()` (căutare binară
pe lățimile măsurate, nu numărătoare de caractere ca `fs_fit()`), cu
bucla obișnuită de verificare/micșorare din `main()` ca plasă de
siguranță pentru ce ratează estimarea.

**Istorice** — au construit caietul și rulează *înaintea* reorganizării, pe
structura plată în trei părți cu cântecele la `###`: `extract_*.py`,
`build_data.py`, `compile_caiet.py`, `karban_merge.py`, `dedup_songs.py`,
`karban_*.py`. `reorganize_parts.py` acceptă ambele niveluri de titlu, deci
ordinea lanțului e: pasul istoric, apoi reorganizarea. `merged_songs.json` nu
e în depozit, așa că `compile_caiet.py` nu poate rula fără a re-rula întâi
extractoarele. `karban_merge.py` cere explicit un caiet dinainte de
încorporarea lui Karban.

Ce face fiecare grup:

- **extragere** — fiecare culegere are propriile capcane: una folosește un
  cifru de font, alta compune diacriticele din literă plus sedilă, alta așază
  strofele pe două coloane (`reconstruct_two_col.py`, `polish_two_col.py`).
- **normalizare** — `restore_diacritics.py` reface ă, ș și ț în textul lui
  Karban, care scrie doar â și î; se sprijină pe dicționarul hunspell din
  `tools/data/`, expandat la formele flexionate de `ro_wordlist.py`.
- **duplicate** — `chord_seq.py` compară succesiunile de acorduri, inclusiv
  transpuse; `dedup_songs.py` și `karban_dedup.py` grupează repetările. Două
  variante se contopesc doar dacă au aceeași succesiune în aceeași tonalitate;
  altfel rămân alături, numerotate `(I)`, `(II)`, `(III)`.
- **tipărire** — `make_pdf.py` construiește PDF-ul cu Chrome headless,
  micșorând fontul până când fiecare cântec încape pe o pagină, iar cele lungi
  trec pe două coloane.

`tools/run.sh` reface caietul din PDF-urile din `surse/`, care sunt în depozit.

## Verificare

**Nu există suită de teste.** După orice unealtă care rescrie caietul, dovada e:

- **738 de cântece** înainte și după, aceleași chei stabile — nimic pierdut,
  nimic duplicat;
- **corpurile identice caracter cu caracter**, dacă unealta nu trebuia să le
  atingă;
- **fiecare ancoră** din cuprins și din indexul pe artiști nimerește un titlu
  real (ancorele sunt slug-uri în stil GitHub, cu sufix numeric la coliziune);
- `make_pdf.py` trebuie să tipărească **`problem songs: none`** — e
  autoverificarea lui că fiecare cântec ocupă exact o pagină, ținând cont de
  paginile de separator dinaintea fiecărei secțiuni;
- `reorganize_parts.py` rulat de două ori la rând nu schimbă niciun octet.

## De reținut

- Editarea introducerii sau a oricărui cântec cere regenerarea PDF-ului;
  introducerea intră în prima pagină a lui.
- **Înainte de orice push, regenerează PDF-ul (`make pdf`) și site-ul
  (`make html`) și include-le în commit.** `docs/` se publică pe GitHub Pages
  direct din `main`, deci un push fără regenerare lasă site-ul și PDF-ul în
  urma caietului.
- Acordurile apar în două notații: pe rândul de deasupra versului, aliniate pe
  silabă, sau în text între paranteze drepte (`[Am]Om bun`) la cântecele lui
  Karban. Uneltele trebuie să le trateze pe amândouă.
- În notația inline, un acord identic cu cel imediat anterior de pe același
  rând (fie el o bătaie în plus fără silabă nouă, fie o vocală prelungită pe
  mai multe lovituri, ex. `Dia[Dm]a[Dm]na`) se scrie `^` în loc să repete
  `[Dm]`; `tools/collapse_repeated_chords.py` face conversia automat. Nu
  se confundă cu `/` de pe rândul de acorduri (deasupra versului), care
  înseamnă altceva: o digitație alternativă pentru acordul precedent.
- `tools/data/ro_forms.txt` e generat (27 MB) și ignorat de git.
- Mesajele de commit și documentația sunt în română; docstring-urile și
  comentariile din cod, în engleză.

## Licențe ale uneltelor

Dicționarul hunspell românesc din `tools/data/` aparține echipei Rospell și e
tri-licențiat GPL 2.0 / LGPL 2.1 / MPL 1.1 — vezi
[`tools/data/PROVENIENTA.md`](tools/data/PROVENIENTA.md).
