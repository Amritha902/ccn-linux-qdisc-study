#!/usr/bin/env python3
"""Generate the full technical report from figures/index.json.

Two documents come out of this project and they are not the same thing.

  paper/acape.tex   the conference paper. Selective: nine figures, each one
                    carrying an argument the text depends on.
  paper/report.tex  this. Every implementation capture and every analysis
                    figure, full size, with the captions already written in
                    the index, plus the per-run figures as an appendix.

Captions are taken verbatim from figures/index.json rather than rewritten, so
the report cannot disagree with the figure index or with the gallery.
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IDX = json.load(open(os.path.join(ROOT, "figures", "index.json")))


def tex_escape(s):
    """Escape the characters that matter in a caption."""
    for a, b in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"),
                 ("$", r"\$"), ("#", r"\#"), ("_", r"\_"), ("{", r"\{"),
                 ("}", r"\}"), ("~", r"\textasciitilde{}"),
                 ("^", r"\textasciicircum{}")):
        s = s.replace(a, b)
    # the index uses an en dash and a right arrow in places
    return s.replace("—", ", ").replace("–", "--").replace("->", "$\\to$")


def figure(path, cid, title, caption, width=r"\linewidth"):
    return "\n".join([
        r"\begin{figure}[htbp]", r"\centering",
        rf"\includegraphics[width={width},height=0.42\textheight,keepaspectratio]{{{path}}}",
        rf"\caption{{\textbf{{{tex_escape(cid)}}}: {tex_escape(title)}. {tex_escape(caption)}}}",
        r"\end{figure}", ""])


def main():
    L = [r"\documentclass[11pt,a4paper]{article}",
         r"\usepackage[margin=2.2cm]{geometry}",
         r"\usepackage[utf8]{inputenc}",
         r"\usepackage{graphicx,booktabs,longtable,url,amsmath}",
         r"\usepackage[hidelinks]{hyperref}",
         r"\graphicspath{{../figures/}{../figures/steps/}{../figures/comparison/}"
         r"{../figures/runs/}{generated/}}",
         r"\setcounter{tocdepth}{2}",
         r"\title{Runtime Parameter Adaptation for Linux Queue Disciplines\\"
         r"\large Technical Report: Full Implementation and Results Evidence}",
         r"\author{Amritha S \and Yugeshwaran P \and Deepti Annuncia\\"
         r"\small Vellore Institute of Technology, Chennai}",
         r"\date{\today}",
         r"\begin{document}", r"\maketitle",
         r"""
\begin{abstract}
\noindent
This report accompanies the paper and carries the complete visual record of
the work: every capture of the implementation as it was built and verified,
and every analysis figure generated from the measurement logs. It exists
because the paper is necessarily selective, carrying only the figures its
argument depends on, while a reader checking the work needs to see all of it.

Nothing here is drawn by hand. Each implementation capture is a verbatim
record of a command that was executed, and each analysis figure is produced by
\texttt{src/plots.py} from the committed logs. The captions are taken from
\texttt{figures/index.json}, the same source the repository gallery uses, so
this report cannot disagree with either.
\end{abstract}
""",
         r"\tableofcontents", r"\newpage",
         r"\section{Implementation evidence}",
         r"""
Each capture below is a verbatim record of a command that ran, in the order
the apparatus was built. Together they establish that the measurement
environment exists and behaves as described, rather than asking the reader to
assume it.
""", ""]

    for e in IDX["steps"]:
        L.append(figure(os.path.basename(e["path"]), e["id"], e["title"],
                        e.get("caption", "")))

    L += [r"\clearpage", r"\section{Analysis figures}",
          r"""
Every figure in this section is generated from the committed logs by
\texttt{src/plots.py} and \texttt{src/analyse\_law.py}. None is redrawn or
adjusted by hand. Where a figure appears in the paper it is the same file.
""", ""]

    for e in IDX["figures"]:
        L.append(figure(os.path.basename(e["path"]), e["id"], e["title"],
                        e.get("caption", "")))

    L += [r"\clearpage", r"\section{Per-run figures}",
          r"""
One figure per experimental run, 63 in total, each showing that run's
time series. They are listed here rather than embedded, since the analysis
figures above aggregate them and the per-run detail is for checking a
specific run rather than for reading through. Every file is in
\texttt{figures/runs/} in the repository.
""", "",
          r"\begin{longtable}{p{1.6cm}p{5.2cm}p{7.6cm}}",
          r"\toprule ID & Run & Summary \\ \midrule",
          r"\endfirsthead", r"\toprule ID & Run & Summary \\ \midrule",
          r"\endhead"]
    for e in IDX["runs"]:
        L.append(rf"{tex_escape(e['id'])} & \texttt{{{tex_escape(e['title'])}}} & "
                 rf"{tex_escape(e.get('caption',''))} \\")
    L += [r"\bottomrule", r"\end{longtable}", "",
          r"\section{Where the numbers come from}",
          r"""
Every quantity in the paper and in this report is produced by the analysis
pipeline and read into \LaTeX{} as a generated macro, so prose cannot drift
from data. To regenerate everything from the committed logs:

\begin{verbatim}
python3 src/analyse.py          # tables, fact macros
python3 src/analyse_law.py      # the scaling law, its table and macros
python3 src/plots.py            # all analysis figures
python3 src/make_index.py       # the figure index this report is built from
python3 paper/make_report.py    # this document
\end{verbatim}

\noindent
The measurement defects found and corrected during the work, including the
four that would have decided the scaling-law result rather than measuring it,
are documented in the \texttt{verification/} directory. The pre-registered
hypotheses and their decision thresholds, committed before the data existed,
are in \texttt{docs/SCALING\_LAW.md}, \texttt{docs/CROSS\_AQM\_PREREG.md},
\texttt{docs/SERIALIZATION\_PREREG.md} and \texttt{docs/GATE\_PREREG.md}.
""",
          r"\end{document}", ""]

    out = os.path.join(HERE, "report.tex")
    open(out, "w").write("\n".join(L))
    n = len(IDX["steps"]) + len(IDX["figures"])
    print(f"wrote {out}")
    print(f"  {len(IDX['steps'])} implementation captures")
    print(f"  {len(IDX['figures'])} analysis figures")
    print(f"  {n} embedded figures, {len(IDX['runs'])} per-run figures tabulated")


if __name__ == "__main__":
    main()
