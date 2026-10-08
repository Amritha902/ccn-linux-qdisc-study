# The manuscript

Laid out for *Scientific Reports* (Nature Portfolio), following the Springer
Nature journal template the group supplied.

## Files

| File | Purpose |
|------|---------|
| `submission.tex` | The manuscript. Self-contained, builds with plain `pdflatex` |
| `refs.bib` | 23 references, every one verified against the published record |
| `submission.pdf` | What it compiles to, 10 pages |
| `sync_generated.py` | Rebuilds the inlined macro block from `../generated/` |
| `make_overleaf.py` | Packs `overleaf_paper.zip` with the figures flattened |
| `sn-article-body.tex` | The body alone, for pasting into the official class |

Nothing here needs the publisher's `sn-jnl.cls`, which is not redistributable.
`submission.tex` reproduces the layout with a plain `article` class, so it
compiles on a bare Overleaf project with no class file to install.

## Build

```bash
make                 # sync the macros, compile, 10 pages
make overleaf        # also pack overleaf_paper.zip
```

`sync_generated.py` is the step that matters. Every number in the text comes
from a macro defined in `../generated/*.tex`, which the analysis pipeline
writes from the run logs. Running it after a reanalysis moves the new numbers
into the manuscript; the text never carries a literal that the logs do not
support.

## Upload

Overleaf, **New Project**, **Upload Project**, pick `overleaf_paper.zip`, then
**Menu**, **Main document**, `paper.tex`.

If the official class is wanted, open the Springer Nature template from
Overleaf's gallery and follow the header of `sn-article-body.tex`: paste its
macro block into the template preamble, replace the template body with ours,
upload the figures and `refs.bib`, and switch to
`\bibliographystyle{sn-mathphys-num}`. Sectioning, float style and the
Declarations block already match, so nothing else changes.

## Why the structure is what it is

*Scientific Reports* wants Introduction, Results, Discussion, Methods, in that
order, with Methods last. The testbed and controller design therefore sit in
Methods rather than ahead of the results, the measurement defects and the
threats to validity sit in Discussion, and the journal's Declarations block
(data availability, author contributions, competing interests) is present. The
abstract is 200 words, unstructured and uncited, which is the limit.

Three figures are placed: the four main outputs across all ten systems, the
full parameter sweep, and the scaling law with its hold-out. The complete
figure set travels in the Overleaf zip so any of them can be swapped in.

## The recent work the text engages with

Cited in the argument, not listed for coverage:

| Reference | Year | Where it is used |
|---|---|---|
| DESiRED (P4 AQM, deep RL, in-band telemetry) | 2024 | Introduction, Discussion |
| AQM-LLM (distilled LLM marking controller) | 2026 | Introduction |
| ML-AQM survey | 2025 | Introduction |
| Ray et al., AQM effects on speed-test measurement | 2025 | Discussion |
| Self-clocked round robin (NSDI) | 2025 | Discussion |
| eBPF qdisc proposal | 2023 | Discussion |
| L4S, RFC 9330 and RFC 9332 | 2023 | Introduction, Discussion |

DESiRED is the closest prior work, and the reason the manuscript does not claim
runtime target adaptation as novel. The claim it does defend is the condition
under which that adaptation pays, which none of these works states.
