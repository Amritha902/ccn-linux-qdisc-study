# Overleaf upload: the Scientific Reports manuscript

## What to do

1. Overleaf, **New Project**, **Upload Project**, pick `overleaf_paper.zip`.
2. Menu, **Main document**, set it to `paper.tex`.
3. Menu, **Compiler**, pdfLaTeX. The bibliography is BibTeX and Overleaf runs
   it without being asked.
4. Compile. Citations read `[?]` on the first pass and fill on the second;
   Overleaf normally does both.

## What is in the zip

- `paper.tex`, the whole manuscript in one file. Single column in the
  Springer Nature layout that Scientific Reports uses, with a self-contained
  preamble, no `\input` left and no custom `.cls` required, so it compiles on
  a bare Overleaf project. To move to the official Springer Nature template,
  replace the preamble with the template's and keep everything from
  `\begin{document}` onward: sectioning, float style and the Declarations
  block already match, and the bibliography style switches on one line.
- `refs.bib`, 23 of its entries cited by the text.
- 3 PNG figures the manuscript places, flat, named exactly as it
  asks for them.
- 160 further PNG figures from the project, also flat: the remaining
  comparison plots for both workloads, the implementation captures and the
  per-run time series. LaTeX reads only what `\includegraphics` names, so
  these sit in the project without affecting the compile or the page count.
  Adding one to the paper is a single `\includegraphics` line, with no file
  to go and find.

Total 165 files.

## The 3 figures the manuscript places

- `fig08_allparams_steady.png` - every measured quantity against every system, parameter level
- `fig16_scaling_law.png` - the contribution: benefit collapses onto one curve under target/RTT
- `fig17_main_outputs_steady.png` - the four measured outputs compared across all ten configurations

## If something does not compile

- **Citations stay as `[?]`**: recompile once. If they persist, check that
  `refs.bib` is at the project root and not in a folder.
- **A figure is missing**: every filename in the manuscript is a bare
  basename and all PNGs sit at the root, so a missing one means the upload
  dropped it. Re-upload the zip rather than single files.
- **Compile times out**: the project carries the full figure set, and Overleaf
  bills compile time per project rather than per figure used. Deleting the
  unused PNGs from the project is safe; the manuscript names only the
  3 listed above.
- **`IEEEtran.bst` not found**: Overleaf ships it. On a bare local TeX
  install, change `\bibliographystyle{IEEEtran}` to
  `\bibliographystyle{unsrt}`.

## If your advisor wants a specific template

`paper.tex` carries its own preamble and no `\input`, so dropping it into a
publisher template is a matter of replacing that template's `main.tex` body
and uploading the same 3 PNGs plus `refs.bib` to the project root.
Nothing else has to be wired up.

## Figure inventory

The 160 figures beyond the manuscript's own, by group:

- **implementation captures (step*)**: 11 files
- **per-run time series (run*)**: 108 files
- **comparison and analysis plots**: 41 files

