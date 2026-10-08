# What to submit, and what is in it

## Everything in one archive

`python3 paper/make_full_bundle.py` writes two archives. Both hold both
Overleaf projects, both rendered PDFs and the deck; extract either and read
`READ_ME_FIRST.txt`. The two inner zips stay zipped on purpose: that is the
form Overleaf imports, so neither needs repacking.

| archive | size | figures in the Overleaf projects |
|---|---|---|
| `ACAPE_submission_bundle.zip` | 52 MB | every figure the pipeline produces, so any can be swapped in without going back to the repository |
| `ACAPE_submission_bundle_lean.zip` | 7.5 MB | only the three and seventeen the documents place, which fits an email attachment |

The text, the references and the PDFs are identical in the two. All four inner
projects were extracted into empty directories and compiled from scratch: ten
and thirty pages, no errors, no undefined references, no missing figures.

## The submission

`paper/scirep/overleaf_paper.zip`, or `1_paper_overleaf/` inside the bundle.

Overleaf -> **New Project** -> **Upload Project** -> pick the zip ->
Menu -> **Main document** -> `paper.tex` -> compile.

10 pages, Springer Nature layout as Scientific Reports uses it, three
figures at 300 dpi, 23 references. No class file to install: `paper.tex`
reproduces the layout with a plain `article` class, so it compiles on a bare
project.

If your supervisor wants the official `sn-jnl.cls`, it is not redistributable
here. Open the Springer Nature template from Overleaf's gallery and follow the
header of `sn-article-body.tex` in the zip: paste its macro block into the
template's preamble, replace the body with ours, upload the three PNGs and
`refs.bib`, and switch to `\bibliographystyle{sn-mathphys-num}`. The
sectioning, float style and Declarations block already match.

## Before you submit

Check one thing. The three addresses are taken from the original IEEE draft in
`filespr/`: `amritha.s2023@`, `yugeshwaran.p2023@` and `deepti.annucia2023@`,
all at `vitstudent.ac.in`. The third spells the surname *annucia* while the
author line spells it *Annuncia*. That is how the original file has it, so it
is probably the address VIT issued, but confirm it before submitting: a wrong
corresponding address is expensive to fix later.

Scientific Reports also asks for figures as separate files. The zip already
contains them as individual PNGs.

## The other documents

| file | what it is |
|---|---|
| `ACAPE_submission_bundle.zip` | all of the below, in one file |
| `ACAPE_submission_bundle_lean.zip` | the same, small enough to email |
| `paper/scirep/submission.pdf` | what the zip compiles to, for checking |
| `paper/report.pdf` | the technical report, 30 pages, 17 figures. The evidence record, not a paper. |
| `paper/overleaf_report.zip` | the same report as an Overleaf project |
| `deck/ACAPE_2026.pptx` | 22 slides, built from `deck/build.js` |

The paper and the report say the same things. The report carries the full
methodology, the implementation captures and the measurement defects found
during the work; the paper carries the argument and the three figures that
compare this work against the alternatives.

## What the submission claims

That whether adapting an AQM's parameters pays is decided by `r = target/RTT`,
with half the benefit at `r = 0.50` while correct configuration sits five to
ten times below that. The mechanism is not new and the paper says so. The
contribution is the predicate, the apparatus needed to establish it, and the
boundary on it: the ratio fixes the shape of the curve but not its ceiling,
which moves with link rate.

One of four pre-registered tests failed and is reported as failed. That is
deliberate.

## Checks that pass

- 0 LaTeX errors, 0 undefined references, 0 missing figures, in both the
  working copy and the flattened bundle
- every quoted number regenerates from the committed logs; rerunning the
  analysis reproduces the fact files byte for byte
- three regression suites pass
- abstract exactly 200 words, the Scientific Reports limit
- no em-dashes in the paper, the report or the deck
- sentence-length CV 0.60 in the paper and 0.61 in the report, with a quarter
  of sentences under thirteen words and a sixth over forty; no flagged
  vocabulary in either
