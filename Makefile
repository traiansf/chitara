.PHONY: pdf html all

pdf:
	python3 tools/make_pdf.py

html:
	python3 tools/generate_html.py

all: pdf html
