# Overleaf upload: the Scientific Reports manuscript

## Two ways to use this, pick one

### A. Compile as it is (nothing to install)

1. Overleaf, **New Project**, **Upload Project**, pick this zip.
2. Menu, **Main document**, set it to `paper.tex`.
3. Menu, **Compiler**, pdfLaTeX. Compile.

`paper.tex` reproduces the Springer Nature layout with an ordinary
`article` class, so it needs no template file and compiles on a bare
project. Single column, numbered sections in the Scientific Reports order,
superscript affiliations, `Fig. N` captions under figures, table captions
above with `\botrule`, and the Declarations block.

### B. Use the official Springer Nature class

Do this if your supervisor wants the real `sn-jnl.cls`. It is not
redistributable here, so it has to come from Overleaf's gallery.

1. Overleaf, **New Project**, **Templates**, search **Springer Nature**.
2. Open the template and follow the header of `sn-article-body.tex` in this
   zip: paste its macro block into the template's preamble, replace the
   template's body with ours, upload the 3 PNGs and `refs.bib`,
   and set `\bibliographystyle{sn-mathphys-num}`.

The sectioning, float style and Declarations block already match the
template, so nothing else needs rewiring.

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

