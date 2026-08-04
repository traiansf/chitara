#!/bin/bash
# Regenerates Caiet-chitara.md + addendum from the 3 source PDFs.
# Needs: python3 with pymupdf (pip install pymupdf), pdftotext (poppler).
set -e
cd "$(dirname "$0")"
pdftotext -layout ../caiet-christian-adventure.pdf caiet-christian-adventure.txt
python3 extract_caietrom.py
python3 extract_caieteng.py
python3 extract_caiet3.py
# build_data.py needs artist_tabs.json + matched_artists.json (tabulaturi.ro API snapshots);
# compile_caiet.py additionally needs addendum.json
python3 build_data.py
python3 compile_caiet.py
