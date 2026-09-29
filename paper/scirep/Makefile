all: preview.pdf

preview.pdf: preview.tex body.tex refs.bib
	pdflatex -interaction=nonstopmode preview.tex >/dev/null
	bibtex preview >/dev/null || true
	pdflatex -interaction=nonstopmode preview.tex >/dev/null
	pdflatex -interaction=nonstopmode preview.tex >/dev/null
	@echo "built preview.pdf"

# Inline every \input so the manuscript can be uploaded as one file.
flatten:
	latexpand --expand-bbl=preview.bbl main.tex > submission.tex 2>/dev/null || \
	  python3 -c "import re,sys;\
s=open('main.tex').read();\
s=re.sub(r'\\\\input\{body\}', open('body.tex').read(), s);\
s=re.sub(r'\\\\input\{\.\./results_prose\}', open('../results_prose.tex').read(), s);\
open('submission.tex','w').write(s)"
	@echo "wrote submission.tex"

clean:
	rm -f *.aux *.log *.out *.bbl *.blg preview.pdf submission.tex
.PHONY: all flatten clean
