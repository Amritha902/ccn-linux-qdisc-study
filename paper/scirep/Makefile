all: preview.pdf

preview.pdf: preview.tex body.tex refs.bib
	pdflatex -interaction=nonstopmode preview.tex >/dev/null
	bibtex preview >/dev/null || true
	pdflatex -interaction=nonstopmode preview.tex >/dev/null
	pdflatex -interaction=nonstopmode preview.tex >/dev/null
	@echo "built preview.pdf"

flatten:
	@python3 flatten.py

clean:
	rm -f *.aux *.log *.out *.bbl *.blg preview.pdf submission.tex
.PHONY: all flatten clean
