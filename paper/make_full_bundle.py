#!/usr/bin/env python3
"""One archive holding everything a submission needs.

Overleaf imports a project from a zip, so the two LaTeX bundles stay zipped
inside this one: extract the outer archive and upload either inner zip
without repacking anything. The rendered PDFs and the deck sit beside them.

Two archives come out of this. The full one carries every figure the analysis
pipeline produces, which is what makes it 52 MB: either project can have any
of them swapped in on Overleaf without going back to the repository. The lean
one keeps only the figures the two documents actually place, three and
seventeen, and fits under the 30 MB that mail and chat attachments allow.
Neither is a subset of the other in text: the .tex, .bib and PDFs are
identical, only the unused figures differ.
"""
import os, re, shutil, sys, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "ACAPE_submission_bundle.zip")
OUT_LEAN = os.path.join(ROOT, "ACAPE_submission_bundle_lean.zip")

ITEMS = [
    ("1_paper_overleaf/overleaf_paper.zip",   "paper/scirep/overleaf_paper.zip"),
    ("2_report_overleaf/overleaf_report.zip", "paper/overleaf_report.zip"),
    ("3_rendered/paper_submission.pdf",       "paper/scirep/submission.pdf"),
    ("3_rendered/technical_report.pdf",       "paper/report.pdf"),
    ("4_deck/ACAPE_2026.pptx",                "deck/ACAPE_2026.pptx"),
    ("4_deck/ACAPE_2026.pdf",                 "deck/ACAPE_2026.pdf"),
    ("SUBMIT.md",                             "SUBMIT.md"),
    ("README.md",                             "README.md"),
]

def lean_zip(src, dest):
    """Repack an Overleaf zip keeping only the figures its .tex places.

    The figure names come from the \\includegraphics calls in the root .tex,
    so a figure stops travelling the moment the document stops placing it and
    there is no list to keep in step by hand.
    """
    with zipfile.ZipFile(src) as z:
        names = z.namelist()
        tex = [n for n in names
               if n.endswith(".tex") and "/" not in n and n != "sn-article-body.tex"]
        placed = set()
        for t in tex:
            body = z.read(t).decode("utf-8", "replace")
            placed |= {os.path.basename(m) for m in
                       re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]*)\}", body)}
        keep = [n for n in names
                if not n.lower().endswith(".png") or os.path.basename(n) in placed]
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as o:
            for n in keep:
                o.writestr(n, z.read(n))
    return len(names), len(keep)


MANIFEST = """ACAPE submission bundle
=======================

1_paper_overleaf/overleaf_paper.zip
    The manuscript. Upload this zip to Overleaf (New Project, Upload
    Project). Root file is paper.tex, 10 pages, Springer Nature
    journal layout, three figures placed. Every figure the analysis
    pipeline produces is in figs/ so any of them can be swapped in.

2_report_overleaf/overleaf_report.zip
    The technical report, same upload route. Root file is report.tex,
    30 pages, seventeen figures placed.

3_rendered/
    Both documents as built here, for reading without compiling.

4_deck/
    Twenty-two slide deck, PowerPoint and PDF.

Authors
    Amritha S            amritha.s2023@vitstudent.ac.in   (corresponding)
    Yugeshwaran P        yugeshwaran.p2023@vitstudent.ac.in
    Deepti Annuncia      deepti.annucia2023@vitstudent.ac.in

One thing to confirm before submitting: the third address spells the
surname "annucia" where the author line spells it "Annuncia". That is how
it reads in the group's own earlier draft, so it is probably the address
VIT issued, but it is worth a look.
"""

LEAN_NOTE = """

This is the lean archive. Both Overleaf projects carry only the figures their
documents place, three and seventeen, so the whole thing fits under 30 MB.
The text, the references and the PDFs are identical to the full archive; if a
figure needs swapping in on Overleaf, take it from the full one or from
figures/ in the repository.
"""


def build(out, inner, note):
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("READ_ME_FIRST.txt", MANIFEST + note)
        for dest, src in ITEMS:
            z.write(inner.get(dest, os.path.join(ROOT, src)), dest)
    print(f"{out}: {len(ITEMS) + 1} entries, {os.path.getsize(out) / 1e6:.1f} MB")


def main():
    missing = [src for _, src in ITEMS if not os.path.exists(os.path.join(ROOT, src))]
    if missing:
        sys.exit("missing, build it first:\n  " + "\n  ".join(missing))

    build(OUT, {}, "")
    for dest, _ in ITEMS:
        print(f"  {dest}")

    tmp = os.path.join(ROOT, ".lean_tmp")
    os.makedirs(tmp, exist_ok=True)
    try:
        inner, counts = {}, []
        for dest, src in ITEMS:
            if not dest.endswith(".zip"):
                continue
            lean = os.path.join(tmp, os.path.basename(dest))
            counts.append(lean_zip(os.path.join(ROOT, src), lean))
            inner[dest] = lean
        build(OUT_LEAN, inner, LEAN_NOTE)
        for (was, now) in counts:
            print(f"  repacked {was} files to {now}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
