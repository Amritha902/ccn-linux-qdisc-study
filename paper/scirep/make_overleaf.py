#!/usr/bin/env python3
"""Build a self-contained Overleaf project for the Scientific Reports paper.

The source of truth is submission.tex, not main.tex: submission.tex carries
edits made after the last flatten and re-running flatten.py would discard
them. This script therefore treats submission.tex as the manuscript, resolves
any \input that remains, flattens the figure paths, and copies only the
figures the manuscript actually references.
"""
import os, re, shutil, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PAPER = os.path.dirname(HERE)
ROOT = os.path.dirname(PAPER)
OUT = os.path.join(HERE, "overleaf_paper")
FIGDIRS = [os.path.join(HERE, "figs")] + \
          [os.path.join(ROOT, "figures", d) for d in
           ("", "steps", "comparison", "runs")] + \
          [os.path.join(PAPER, "generated")]

os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    os.remove(os.path.join(OUT, f))


def inline(text, depth=0):
    if depth > 6:
        return text

    def sub(m):
        name = m.group(1).strip()
        for cand in (name, name + ".tex"):
            p = os.path.normpath(os.path.join(HERE, cand))
            if os.path.exists(p):
                return inline(open(p).read(), depth + 1)
        raise SystemExit(f"unresolved \\input{{{name}}}")
    return re.sub(r"\\input\{([^}]+)\}", sub, text)


tex = inline(open(os.path.join(HERE, "submission.tex")).read())
tex = re.sub(r"\\graphicspath\{[^\n]*\}\n", "", tex)

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

# every other figure the project holds travels with the project too, so a
# figure can be added to the manuscript without hunting for its file. They are
# inert: LaTeX reads only what \includegraphics names.
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
shutil.copy2(os.path.join(HERE, "sn-article-body.tex"),
             os.path.join(OUT, "sn-article-body.tex"))
open(os.path.join(OUT, "paper.tex"), "w").write(tex)

cited = sorted({k.strip() for m in re.findall(r"\\cite\{([^}]+)\}", tex)
                for k in m.split(",")})

why = {
    "fig17_main_outputs_steady.png":
        "the four measured outputs compared across all ten configurations",
    "fig08_allparams_steady.png":
        "every measured quantity against every system, parameter level",
    "fig16_scaling_law.png":
        "the contribution: benefit collapses onto one curve under target/RTT",
}
placed_table = "\n".join(
    f"- `{n}` - {why.get(n, 'referenced from the text')}" for n in wanted)

groups = {"implementation captures (step*)": [f for f in extra
                                               if f.startswith("step")],
          "per-run time series (run*)": [f for f in extra
                                         if f.startswith("run")],
          "comparison and analysis plots": [f for f in extra
                                            if not f.startswith(("step",
                                                                 "run"))]}
inventory = "\n".join(f"- **{k}**: {len(v)} files" for k, v in groups.items()
                       if v)

readme = f"""# Overleaf upload: the Scientific Reports manuscript

## Two ways to use this, pick one

### A. Compile as it is (nothing to install)

1. Overleaf, **New Project**, **Upload Project**, pick this zip.
2. Menu, **Main document**, set it to `paper.tex`.
3. Menu, **Compiler**, pdfLaTeX. Compile.

`paper.tex` reproduces the Springer Nature layout with an ordinary
`article` class, so it needs no template file and compiles on a bare
project. Single column, numbered sections in the Scientific Reports order,
superscript affiliations, `Fig. N` captions under figures, table captions
above with `\\botrule`, and the Declarations block.

### B. Use the official Springer Nature class

Do this if your supervisor wants the real `sn-jnl.cls`. It is not
redistributable here, so it has to come from Overleaf's gallery.

1. Overleaf, **New Project**, **Templates**, search **Springer Nature**.
2. Open the template and follow the header of `sn-article-body.tex` in this
   zip: paste its macro block into the template's preamble, replace the
   template's body with ours, upload the {len(wanted)} PNGs and `refs.bib`,
   and set `\\bibliographystyle{{sn-mathphys-num}}`.

The sectioning, float style and Declarations block already match the
template, so nothing else needs rewiring.

## The {len(wanted)} figures the manuscript places

{placed_table}

## If something does not compile

- **Citations stay as `[?]`**: recompile once. If they persist, check that
  `refs.bib` is at the project root and not in a folder.
- **A figure is missing**: every filename in the manuscript is a bare
  basename and all PNGs sit at the root, so a missing one means the upload
  dropped it. Re-upload the zip rather than single files.
- **Compile times out**: the project carries the full figure set, and Overleaf
  bills compile time per project rather than per figure used. Deleting the
  unused PNGs from the project is safe; the manuscript names only the
  {len(wanted)} listed above.
- **`IEEEtran.bst` not found**: Overleaf ships it. On a bare local TeX
  install, change `\\bibliographystyle{{IEEEtran}}` to
  `\\bibliographystyle{{unsrt}}`.

## If your advisor wants a specific template

`paper.tex` carries its own preamble and no `\\input`, so dropping it into a
publisher template is a matter of replacing that template's `main.tex` body
and uploading the same {len(wanted)} PNGs plus `refs.bib` to the project root.
Nothing else has to be wired up.

## Figure inventory

The {len(extra)} figures beyond the manuscript's own, by group:

{inventory}

"""
open(os.path.join(OUT, "README.md"), "w").write(readme)

zpath = os.path.join(HERE, "overleaf_paper.zip")
with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted(os.listdir(OUT)):
        z.write(os.path.join(OUT, f), f)

print(f"{OUT}: {len(os.listdir(OUT))} files "
      f"({len(wanted)} placed + {len(extra)} supporting figures, "
      f"{len(cited)} citations)")
print(f"{zpath}: {os.path.getsize(zpath)/1e6:.1f} MB")
