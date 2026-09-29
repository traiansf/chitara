.PHONY: pdf html all

# UTF-8 I/O on Windows too (a no-op on Linux, where it's the default)
export PYTHONUTF8 := 1

all: pdf html

pdf:
	python3 tools/make_pdf.py

html:
	python3 tools/generate_html.py
