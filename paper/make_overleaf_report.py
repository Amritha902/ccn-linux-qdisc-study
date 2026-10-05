#!/usr/bin/env python3
"""Build a self-contained Overleaf project for the technical report.

Overleaf gets one flat folder, so three things have to change relative to the
local build: every \input is inlined, \graphicspath is dropped and every
figure is copied next to the .tex under its bare filename, and refs.bib comes
along. Nothing in the document then refers outside the project root.
"""
import os, re, shutil, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "overleaf_report")
FIGDIRS = [os.path.join(ROOT, "figures", d) for d in
           ("", "steps", "comparison", "runs")] + [os.path.join(HERE, "generated")]

os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    os.remove(os.path.join(OUT, f))


def resolve_input(name):
    for cand in (name, name + ".tex"):
        p = os.path.normpath(os.path.join(HERE, cand))
        if os.path.exists(p):
            return p
    return None


def inline(text, depth=0):
    if depth > 6:
        return text

    def sub(m):
        p = resolve_input(m.group(1).strip())
        if not p:
            raise SystemExit(f"unresolved \\input{{{m.group(1)}}}")
        body = open(p).read()
        return inline(body, depth + 1)
    return re.sub(r"\\input\{([^}]+)\}", sub, text)


src = open(os.path.join(HERE, "report.tex")).read()
tex = inline(src)

# flat project: no graphicspath, and the figure index comment goes too
tex = re.sub(r"\\graphicspath\{[^\n]*\}\n", "", tex)

# every image the document actually asks for, copied flat
wanted = sorted(set(re.findall(r"\\includegraphics\[[^\]]*\]\{([^}]+)\}", tex)))
missing = []
for name in wanted:
    base = os.path.basename(name)
    for d in FIGDIRS:
        cand = os.path.join(d, base)
        if os.path.exists(cand):
            shutil.copy2(cand, os.path.join(OUT, base))
            break
    else:
        missing.append(base)
if missing:
    raise SystemExit("figures not found: " + ", ".join(missing))

# every remaining project figure travels with the project, so one can be added
# to the report without going to find its file. LaTeX reads only what
# \includegraphics names, so these do not affect the compile.
extra = []
for d in FIGDIRS:
    if not os.path.isdir(d):
        continue
    for f in sorted(os.listdir(d)):
        if not f.lower().endswith(".png"):
            continue
        dest = os.path.join(OUT, f)
        if os.path.exists(dest):
            continue
        shutil.copy2(os.path.join(d, f), dest)
        extra.append(f)

shutil.copy2(os.path.join(HERE, "refs.bib"), os.path.join(OUT, "refs.bib"))
open(os.path.join(OUT, "report.tex"), "w").write(tex)

readme = f"""# Overleaf upload: the technical report

## What to do

1. Overleaf, **New Project**, **Upload Project**, pick `overleaf_report.zip`.
2. Menu, **Main document**, set it to `report.tex`.
3. Menu, **Compiler**, pdfLaTeX. Bibliography is BibTeX, which Overleaf runs
   on its own.
4. Compile. The first pass leaves the citations as `[?]`; a second pass fills
   them. Overleaf usually does both without being asked.

## What is in the zip

- `report.tex`, the whole report in one file. Every `\\input` is already
  inlined, so the generated fact macros, the three result tables and the
  scaling-law table are all inside it. Nothing has to be regenerated.
- `refs.bib`, 23 references.
- {len(wanted)} PNG figures the document places, flat, named exactly as it
  asks for them.
- {len(extra)} further project figures, also flat: the per-run time series the
  report tabulates rather than embeds, and the remaining captures. LaTeX reads
  only what `\\includegraphics` names, so they sit in the project without
  affecting the compile or the page count, and adding one takes a single line
  with no file to go and find.

Total {len(wanted) + len(extra) + 2} files.

## If something does not compile

- **Citations stay as `[?]`**: recompile once. If they persist, check that
  `refs.bib` sits at the project root and not inside a folder.
- **A figure is missing**: every filename in the document is a bare basename
  and all PNGs are at the root, so this means a file did not upload. Re-upload
  the zip rather than individual files.
- **Compile times out**: Overleaf bills compile time per project, and this one
  carries the full figure set. Deleting the unused PNGs is safe; the document
  names only the {len(wanted)} it places.
- **`IEEEtran.bst` not found**: Overleaf ships it. If a local TeX install does
  not, change `\\bibliographystyle{{IEEEtran}}` to `\\bibliographystyle{{unsrt}}`.

## Structure

Title page, abstract with keywords, contents, list of figures, list of tables,
then: Introduction, Literature survey, Methodology, Results in eight steps,
Comparison, The scaling law, Measurement defects, Threats to validity,
Conclusion, and four appendices holding the complete figure set, the
implementation captures, the 63 per-run figures and the reproduction commands.
"""
open(os.path.join(OUT, "README.md"), "w").write(readme)

zpath = os.path.join(HERE, "overleaf_report.zip")
with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted(os.listdir(OUT)):
        z.write(os.path.join(OUT, f), f)

n = len(os.listdir(OUT))
mb = os.path.getsize(zpath) / 1e6
print(f"{OUT}: {n} files "
      f"({len(wanted)} placed + {len(extra)} supporting figures)")
print(f"{zpath}: {mb:.1f} MB")
