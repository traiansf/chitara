# Caiet de cântece pentru chitară

Un caiet de **740 de cântece** cu acorduri — de cabană, folk românesc,
repertoriu internațional și colinde — compilat din cinci culegeri tipărite și
scanate.

📖 **[Caiet-chitara.md](Caiet-chitara.md)** — caietul, cu cuprins, index pe
artiști și dicționar de acorduri
🖨️ **[Caiet-chitara.pdf](Caiet-chitara.pdf)** — același caiet pentru tipărit,
757 de pagini, un cântec pe pagină
🔗 **[Caiet-chitara-addendum.md](Caiet-chitara-addendum.md)** — 1755 de piese
ale acelorași artiști, cu linkuri către tabulaturi.ro

## Ce conține

| Partea | Cântece |
|---|---|
| **I — Cântece de cabană** | **162** |
| &nbsp;&nbsp;I.1 — De munte și de drum | 86 |
| &nbsp;&nbsp;I.2 — Naționaliste și de dor de țară | 20 |
| &nbsp;&nbsp;I.3 — Studențești, de chef și deocheate | 56 |
| II — Repertoriu românesc | 367 |
| III — Repertoriu internațional | 95 |
| IV — Colinde și cântece de iarnă | 116 |

179 de artiști în index, 552 de cântece atribuite. Fiecare cântec poartă
digitațiile acordurilor lui, pentru chitară și pentru ukulele:

```
**Chitară:** Am x02210 · E 022100 · C x32010 · Dm xx0231 · G 320003
**Ukulele:** Am 2000 · E 4442 · C 0003 · Dm 2210 · G 0232
```

Cifrele sunt poziția pe corzi, de la coarda groasă la cea subțire; `x` =
coarda nu se cântă.

În PDF fiecare cântec stă pe o singură pagină: fontul se alege cât de mare
încape, iar cele lungi trec pe două coloane — 729 de cântece la 12pt, 49 pe
două coloane.

Acordurile stau fie pe rândul de deasupra versului, aliniate pe silaba unde se
schimbă, fie — la cântecele din Cărticica lui Karban — în text, între
paranteze drepte:

```
[Am]Om bun des[E]chide-ne [Am]poarta
[C]Dă-ne o [G]coajă și [E]nu ne goni
```

Un cântec care apare în mai multe surse cu acorduri sau versuri diferite e
păstrat de câte ori e nevoie, numerotat `(I)`, `(II)`, `(III)`, cu variantele
una lângă alta — 208 astfel de intrări. Se contopesc doar cele cu aceeași
succesiune de acorduri în aceeași tonalitate.

## Surse

Caietul nu conține material propriu: e o compilație a cinci culegeri, cu
sursa și pagina notate la fiecare cântec. La unele cântece acordurile au
fost înlocuite cu variante văzute pe YouTube, așa că sursa notată acoperă
versurile, nu neapărat acordurile.

| Sursă | Cântece |
|---|---|
| **Cărticică de cântece pentru chitară** — Eugen Karban, v2.0, [eugenkarban.de](http://www.eugenkarban.de) | 244 |
| **Caiet Christian Adventure** — red. Adelina Flavia Iancu | 191 |
| **Caiet cabană RO** — *caiet_cantececabana_RO*, 1998 | 178 |
| **Colinde, cântece de Crăciun și de iarnă** — Eugen Karban, 2008 | 100 |
| **Caiet cabană EN** — *Caieteng*, 1998, aceeași echipă | 76 |

Cele două volume ale lui **Eugen Karban** sunt distribuite de autor ca
*cardware*, cu cerința de a-i fi creditate. Transcrierile din ele îi aparțin
lui și celor care i-au trimis materiale, creditați individual în volumele
originale.

Drepturile asupra versurilor și muzicii aparțin autorilor și compozitorilor
respectivi. Acest depozit e o compilație de uz personal, nu o publicație.

Dicționarul hunspell românesc din `tools/data/` aparține echipei Rospell și e
tri-licențiat GPL 2.0 / LGPL 2.1 / MPL 1.1 — vezi
[`tools/data/PROVENIENTA.md`](tools/data/PROVENIENTA.md).

## Cum a fost construit

`tools/` conține tot lanțul, de la PDF la caiet:

- **extragere** — `extract_caietrom.py`, `extract_caieteng.py`,
  `extract_caiet3.py`, `extract_karban_carticica.py`,
  `extract_karban_colinde.py`. Fiecare culegere are propriile capcane: una
  folosește un cifru de font, alta compune diacriticele din literă plus
  sedilă, alta așază strofe pe două coloane.
- **normalizare** — `restore_diacritics.py` reface ă, ș și ț în textul lui
  Karban, care scrie doar â și î; `ro_wordlist.py` expandează dicționarul
  hunspell la formele flexionate; `normalize_verses.py`, `polish_two_col.py`.
- **compilare** — `compile_caiet.py`, `karban_merge.py`,
  `merge_addendum_index.py`, `add_guitar_chords.py`, `add_ukulele_chords.py`
  (ultimele două verifică digitațiile contra notelor pe care le produc:
  `add_guitar_chords.py --check`).
- **duplicate** — `chord_seq.py` compară succesiunile de acorduri (inclusiv
  transpuse), `dedup_songs.py` și `karban_dedup.py` găsesc și grupează
  cântecele care se repetă.
- **tipărire** — `make_pdf.py` construiește PDF-ul cu Chrome headless,
  micșorând fontul până când fiecare cântec încape pe o pagină.

`tools/run.sh` reface caietul din PDF-urile sursă. Sursele nu sunt incluse în
depozit.
