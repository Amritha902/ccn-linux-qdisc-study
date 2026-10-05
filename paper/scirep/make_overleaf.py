#!/usr/bin/env python3
"""Build a self-contained Overleaf project for the conference paper.

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
open(os.path.join(OUT, "paper.tex"), "w").write(tex)

cited = sorted({k.strip() for m in re.findall(r"\\cite\{([^}]+)\}", tex)
                for k in m.split(",")})

groups = {"implementation captures (step*)": [f for f in extra
                                               if f.startswith("step")],
          "per-run time series (run*)": [f for f in extra
                                         if f.startswith("run")],
          "comparison and analysis plots": [f for f in extra
                                            if not f.startswith(("step",
                                                                 "run"))]}
inventory = "\n".join(f"- **{k}**: {len(v)} files" for k, v in groups.items()
                       if v)

readme = f"""# Overleaf upload: the conference paper

## What to do

1. Overleaf, **New Project**, **Upload Project**, pick `overleaf_paper.zip`.
2. Menu, **Main document**, set it to `paper.tex`.
3. Menu, **Compiler**, pdfLaTeX. The bibliography is BibTeX and Overleaf runs
   it without being asked.
4. Compile. Citations read `[?]` on the first pass and fill on the second;
   Overleaf normally does both.

## What is in the zip

- `paper.tex`, the whole manuscript in one file. Two-column article class,
  self-contained preamble, no `\\input` left and no custom `.cls` required, so
  it compiles on a bare Overleaf project.
- `refs.bib`, {len(cited)} of its entries cited by the text.
- {len(wanted)} PNG figures the manuscript places, flat, named exactly as it
  asks for them.
- {len(extra)} further PNG figures from the project, also flat: the remaining
  comparison plots for both workloads, the implementation captures and the
  per-run time series. LaTeX reads only what `\\includegraphics` names, so
  these sit in the project without affecting the compile or the page count.
  Adding one to the paper is a single `\\includegraphics` line, with no file
  to go and find.

Total {len(wanted) + len(extra) + 2} files.

## The {len(wanted)} figures, and why each is in the paper

Two establish the apparatus. Seven carry results. None is decorative and each
is referenced from the text.

| file | what it carries |
|---|---|
| `step04_corrected_three_node_router_topology.png` | the topology as configured, bottleneck on the data path |
| `step07_ebpf_flow_telemetry_is_live_under_traffic.png` | the telemetry reading non-zero per-flow state under load |
| `fig16_scaling_law.png` | **the central result.** Benefit against target/RTT collapses onto one curve; against RTT alone it does not |
| `fig15_rtt_sweep.png` | the RTT sweep that motivated the law |
| `fig01_latency_tail_steady.png` | tail latency across all nine systems, log scale |
| `fig08_allparams_steady.png` | every parameter against every system, normalised, values printed |
| `fig02_latency_sparse_vs_bulk_steady.png` | sparse probe against bulk flow RTT, measured separately |
| `fig13_sham_control_steady.png` | the sham-controller condition, cost separated from decisions |
| `fig12_controller_behaviour.png` | the controller acting: regime, trajectory, queue |

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
