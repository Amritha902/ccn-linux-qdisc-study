#!/usr/bin/env python3
"""One archive holding everything a submission needs.

Overleaf imports a project from a zip, so the two LaTeX bundles stay zipped
inside this one: extract the outer archive and upload either inner zip
without repacking anything. The rendered PDFs and the deck sit beside them.
"""
import os, shutil, subprocess, sys, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "ACAPE_submission_bundle.zip")

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


def main():
    missing = [src for _, src in ITEMS if not os.path.exists(os.path.join(ROOT, src))]
    if missing:
        sys.exit("missing, build it first:\n  " + "\n  ".join(missing))

    if os.path.exists(OUT):
        os.remove(OUT)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("READ_ME_FIRST.txt", MANIFEST)
        for dest, src in ITEMS:
            z.write(os.path.join(ROOT, src), dest)

    n = len(ITEMS) + 1
    print(f"{OUT}: {n} entries, {os.path.getsize(OUT) / 1e6:.1f} MB")
    for dest, _ in ITEMS:
        print(f"  {dest}")


if __name__ == "__main__":
    main()
