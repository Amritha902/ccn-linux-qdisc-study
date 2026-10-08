# Overleaf upload: the technical report

## What to do

1. Overleaf, **New Project**, **Upload Project**, pick `overleaf_report.zip`.
2. Menu, **Main document**, set it to `report.tex`.
3. Menu, **Compiler**, pdfLaTeX. Bibliography is BibTeX, which Overleaf runs
   on its own.
4. Compile. The first pass leaves the citations as `[?]`; a second pass fills
   them. Overleaf usually does both without being asked.

## What is in the zip

- `report.tex`, the whole report in one file. Every `\input` is already
  inlined, so the generated fact macros, the three result tables and the
  scaling-law table are all inside it. Nothing has to be regenerated.
- `refs.bib`, 23 references.
- 17 PNG figures the document places, flat, named exactly as it
  asks for them.
- 146 further project figures, also flat: the per-run time series the
  report tabulates rather than embeds, and the remaining captures. LaTeX reads
  only what `\includegraphics` names, so they sit in the project without
  affecting the compile or the page count, and adding one takes a single line
  with no file to go and find.

Total 165 files.

## If something does not compile

- **Citations stay as `[?]`**: recompile once. If they persist, check that
  `refs.bib` sits at the project root and not inside a folder.
- **A figure is missing**: every filename in the document is a bare basename
  and all PNGs are at the root, so this means a file did not upload. Re-upload
  the zip rather than individual files.
- **Compile times out**: Overleaf bills compile time per project, and this one
  carries the full figure set. Deleting the unused PNGs is safe; the document
  names only the 17 it places.
- **`IEEEtran.bst` not found**: Overleaf ships it. If a local TeX install does
  not, change `\bibliographystyle{IEEEtran}` to `\bibliographystyle{unsrt}`.

## Structure

Title page, abstract with keywords, contents, list of figures, list of tables,
then: Introduction, Literature survey, Methodology, Results in eight steps,
Comparison, The scaling law, Measurement defects, Threats to validity,
Conclusion, and four appendices holding the complete figure set, the
implementation captures, the 63 per-run figures and the reproduction commands.
