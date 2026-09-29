# Rebuild the paper from the experiment logs.
# Every table and inline figure is generated; none is typed by hand.
RESULTS ?= ../results

all: acape.pdf

generated/facts.tex generated/table_steady.tex: $(wildcard $(RESULTS)/*/summary.json)
	python3 ../src/analyse.py --results $(RESULTS) --outdir generated

acape.pdf: acape.tex generated/facts.tex generated/results_body.tex
	pdflatex -interaction=nonstopmode acape.tex >/dev/null
	pdflatex -interaction=nonstopmode acape.tex >/dev/null
	@echo "built acape.pdf"

clean:
	rm -f *.aux *.log *.out acape.pdf

.PHONY: all clean
