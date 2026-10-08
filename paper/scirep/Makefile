# submission.tex is the manuscript and the only source. It is self-contained:
# sync_generated.py inlines the macro block from ../generated/, so a plain
# pdflatex run builds it with no \input to resolve.
#
# There is deliberately no "clean" target that touches submission.tex.

all: submission.pdf

submission.pdf: submission.tex refs.bib
	python3 sync_generated.py
	pdflatex -interaction=nonstopmode submission.tex >/dev/null
	bibtex submission >/dev/null || true
	pdflatex -interaction=nonstopmode submission.tex >/dev/null
	pdflatex -interaction=nonstopmode submission.tex >/dev/null
	@echo "built submission.pdf"

overleaf: submission.pdf
	python3 make_overleaf.py

clean:
	rm -f *.aux *.log *.out *.bbl *.blg

.PHONY: all overleaf clean
