# What to submit, and what is in it

## The submission

`paper/scirep/overleaf_paper.zip`.

Overleaf → **New Project** → **Upload Project** → pick the zip →
Menu → **Main document** → `paper.tex` → compile.

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

One edit, and it needs you: the corresponding-author address near the top of
`paper.tex` is a personal one. Swap it for an institutional address if you
have one.

Scientific Reports also asks for figures as separate files. The zip already
contains them as individual PNGs.

## The other documents

| file | what it is |
|---|---|
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
- no em-dashes, no flagged vocabulary, sentence-length CV 0.59
