.PHONY: pdf html all

all: pdf html

pdf:
	python3 tools/make_pdf.py

html:
	python3 tools/generate_html.py
