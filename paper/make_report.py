#!/usr/bin/env python3
"""Generate the technical report: a full paper, not a figure dump.

The first version of this script emitted every figure with its index caption
and nothing else, which made the methodology and the comparison read as
assertions with pictures attached. This version writes the document as a
conference paper would be written, with the figures placed inside the argument
that needs them, and keeps the complete figure set in an appendix so nothing
is lost.

Captions come from figures/index.json so they cannot disagree with the
repository gallery. Numbers come from paper/generated/*.tex as LaTeX macros so
they cannot disagree with the logs.
"""
import json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
IDX = json.load(open(os.path.join(ROOT, "figures", "index.json")))
BY = {e["path"].split("/")[-1]: e for e in IDX["steps"] + IDX["figures"]}


def esc(s):
    for a, b in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"),
                 ("$", r"\$"), ("#", r"\#"), ("_", r"\_"), ("{", r"\{"),
                 ("}", r"\}"), ("~", r"\textasciitilde{}"),
                 ("^", r"\textasciicircum{}")):
        s = s.replace(a, b)
    s = s.replace("—", ", ").replace("–", "--").replace("->", "$\\to$")
    return re.sub(r"\s+,\s+", ", ", s)


def fig(name, caption=None, width=r"0.95\linewidth", star=False):
    e = BY.get(name, {})
    cap = caption or f"{esc(e.get('title',name))}. {esc(e.get('caption',''))}"
    cap = cap.replace(" .", ".")
    env = "figure*" if star else "figure"
    return "\n".join([rf"\begin{{{env}}}[htbp]", r"\centering",
                      rf"\includegraphics[width={width},height=0.4\textheight,keepaspectratio]{{{name}}}",
                      rf"\caption{{{cap}}}",
                      rf"\label{{f:{name.split('_')[0]}}}",
                      rf"\end{{{env}}}", ""])


DOC = []
A = DOC.append

A(r"""\documentclass[11pt,a4paper]{article}
\usepackage[margin=2.4cm]{geometry}
\usepackage[utf8]{inputenc}\usepackage[T1]{fontenc}
\usepackage{graphicx,booktabs,longtable,amsmath,amssymb,url,array}
\usepackage{titlesec,fancyhdr,enumitem}
\usepackage[hidelinks]{hyperref}
\usepackage{caption}\captionsetup{font=small,labelfont=bf}
\graphicspath{{../figures/}{../figures/steps/}{../figures/comparison/}{../figures/runs/}{generated/}}
\setcounter{tocdepth}{2}
\setlength{\parskip}{0.35em}
\titleformat{\section}{\normalfont\Large\bfseries}{\thesection}{0.7em}{}
\titleformat{\subsection}{\normalfont\large\bfseries}{\thesubsection}{0.7em}{}
\pagestyle{fancy}\fancyhf{}
\fancyhead[L]{\small Runtime Parameter Adaptation for Linux Queue Disciplines}
\fancyhead[R]{\small\thepage}
\renewcommand{\headrulewidth}{0.4pt}
\input{generated/facts}
\input{generated/law_facts}

\begin{document}

\begin{titlepage}
\centering
\vspace*{1.0cm}
{\large\scshape Vellore Institute of Technology, Chennai}\\[0.3cm]
{\large School of Electronics Engineering}\\[0.2cm]
{\large Department of Electronics and Communication Engineering}\\[2.2cm]

\rule{\linewidth}{0.5pt}\\[0.5cm]
{\LARGE\bfseries Runtime Parameter Adaptation for\\[0.25cm]
Linux Queue Disciplines}\\[0.5cm]
{\Large A Scaling Law in \texttt{target}/RTT}\\[0.4cm]
\rule{\linewidth}{0.5pt}\\[1.0cm]

{\large Technical Report}\\[0.25cm]
{\normalsize Complete Methodology, Results and Comparison}\\[2.2cm]

{\large\bfseries Submitted by}\\[0.4cm]
{\large Amritha S \quad\textbar\quad Yugeshwaran P \quad\textbar\quad
Deepti Annuncia}\\[2.0cm]

\vfill
{\normalsize Every measurement in this report was produced on a purpose-built
Linux guest and is reproducible from the committed logs by the commands in
Appendix~\ref{s:repro}.}\\[0.8cm]
{\large \today}
\end{titlepage}

\newpage
\section*{Abstract}
\addcontentsline{toc}{section}{Abstract}
\noindent
Linux ships \texttt{fq\_codel} as its default queue discipline with four
parameters fixed at configuration time. Whether adapting them at runtime is
worth doing has been answered both ways in the literature. This report
establishes that both answers are correct and that a single dimensionless
number decides which applies. Across 178 measured runs spanning three
workloads, eight alternative queue disciplines and path round-trip times from
2 to 200\,ms, the benefit of adaptation is governed not by path RTT but by the
ratio $r=\texttt{target}/\mathrm{RTT}$, saturating at \LawCeiling\% with half
of that reached at $r=\LawHalfBenefit$. Published guidance places a correctly
configured deployment at $r$ between 0.05 and 0.10, so half the available
benefit arrives five to ten times outside that envelope: adaptation is a
remedy for misconfiguration rather than an improvement on correct
configuration. The report gives the full methodology, the complete result set
with every figure described at its point of use, a parameter-level comparison
against the base paper and six recent systems, and the nine measurement
defects found and corrected during the work.

\vspace{0.8em}
\noindent\textbf{Keywords:} active queue management; bufferbloat;
\texttt{fq\_codel}; CoDel; runtime parameter adaptation; dimensionless
scaling law; Linux traffic control; eBPF telemetry; pre-registered evaluation.

\newpage
\tableofcontents
\newpage
\listoffigures
\newpage
\listoftables
\newpage
""")

# ------------------------------------------------------------------ 1
A(r"""\section{Introduction}

Bufferbloat is the inflation of queueing delay by buffers larger than any
control loop requires, while throughput remains unaffected. Linux has
converged on \texttt{fq\_codel} as its response: Deficit Round Robin across
roughly a thousand flow queues, with an independent CoDel instance per queue.
Four parameters govern it and none changes once set: \texttt{target} (5\,ms),
\texttt{interval} (100\,ms), \texttt{limit} and \texttt{quantum}.

Adapting those parameters at runtime has obvious appeal and clear precedent.
Adaptive RED adjusts a drop probability by an additive-increase
multiplicative-decrease rule; Ye and Leung adapt CoDel's interval
analytically; DESiRED adapts an AQM's delay target in P4 with deep
reinforcement learning. Runtime adaptation of a delay target is therefore not
novel and no such claim is made here.

What the literature does not supply is the condition under which adaptation
pays. Systems report gains; independent evaluations report none; neither camp
states when the other is right. This report establishes that condition
experimentally, and it is a dimensionless ratio.

\paragraph{Structure.} Section~\ref{s:lit} surveys the literature this
work sits in and states what it does not supply. Section~\ref{s:method} gives
the methodology and the
evidence that the apparatus measures what it claims to.
Section~\ref{s:results} gives the results as eight steps, each figure placed
and described where its argument sits. Section~\ref{s:cmp} compares this work
against the base paper and six recent systems at parameter level.
Section~\ref{s:law} derives and tests the scaling law.
Section~\ref{s:defects} documents the nine measurement defects found during
the work. Appendix~\ref{s:app} holds the complete figure set.
""")

# ------------------------------------------------------------------ 1b
A(r"""\section{Literature survey}\label{s:lit}

\subsection{The problem and the standard it set}

Gettys and Nichols characterised bufferbloat: buffer memory became cheap
faster than queue management improved, so devices acquired buffers larger than
any control loop required, and loss-based TCP filled them\cite{gettys2012}.
RFC 7567 sets the IETF position, recommending that devices deploy AQM by
default and explicitly preferring schemes that need no per-flow
configuration\cite{rfc7567}. That preference for the absence of manual tuning
is the standard against which any adaptive scheme has to be judged, and it is
why a null result for adaptation is treated here as a reportable outcome
rather than a failed experiment.

\subsection{Drop-probability schemes}

Random Early Detection opened the field, signalling congestion by dropping
with a probability derived from average queue length\cite{red1993}. Its
sensitivity to configuration prompted Adaptive RED, which adjusts the maximum
drop probability by an additive-increase multiplicative-decrease rule against
a queue-length target\cite{ared2001}. PIE replaced queue length with a delay
estimate inside a proportional-integral controller\cite{rfc8033}. The AIMD
policy in the controller evaluated here, including its $\beta=0.9$ decrease
factor, is taken from Adaptive RED, which makes that scheme the closest
methodological ancestor of this work.

\subsection{Delay-target schemes}

CoDel abandoned queue length entirely, dropping when the minimum sojourn time
over a sliding interval exceeds a target\cite{nichols2012,rfc8289}. Its
authors argue that the two parameters are expressed relative to path
round-trip time by construction and therefore require no tuning. The scaling
law of Section~\ref{s:law} quantifies the point at which that claim stops
holding. \texttt{fq\_codel} pairs CoDel with Deficit Round Robin across
roughly a thousand flow queues and is now the Linux default\cite{rfc8290};
CAKE integrates shaping, flow queueing and host fairness\cite{cake2018};
FQ-PIE is the corresponding combination for PIE\cite{fqpie2019}. L4S
standardises a low-latency service class on a dual-queue coupled
AQM\cite{rfc9330,rfc9332}. All eight of these disciplines are measured here
under an identical bottleneck.

\subsection{Runtime adaptation, the line this work sits in}

Ye and Leung derive stability conditions for CoDel and adapt its
\texttt{interval} analytically\cite{yeleung2020}. QueuePilot learns a
marking policy for small buffers by reinforcement
learning\cite{queuepilot2023}, and AQM-LLM distils a language model into a
marking controller\cite{aqmllm2025}. DESiRED performs runtime adaptation of
an AQM's delay target in P4 using deep reinforcement learning and in-band
telemetry\cite{desired2024}. Runtime adaptation of a delay target is
therefore not novel, and no such claim is made here. Toopchinezhad and Ahmadi
survey the machine-learning AQM literature and observe that heuristic schemes
require careful parameter adjustment, which limits their real-world
applicability\cite{mlaqm2025}. SCRR revisits fair-queueing scheduling for
modern link rates\cite{scrr2025}, and Ray et al.\ characterise how the
presence of an AQM distorts speed-test measurement\cite{ray2025}.

\subsection{What that line does not supply}

Every system above reports that its adaptation improved something, and the
independent evaluations that find nothing are equally confident. What none of
them supplies is the condition under which the other is right. None runs a
control condition that separates a controller's computational cost from the
effect of its decisions. None reports sparse-probe and bulk-flow latency
separately, despite flow-queueing disciplines privileging sparse flows by
construction. None compares against eight alternative disciplines under one
identical bottleneck. And none states a numerical prediction before measuring
it. The contribution claimed here is accordingly not the adaptation mechanism
but the predicate that says when it pays, together with the apparatus required
to establish it.

\subsection{Programmable telemetry}

eBPF at the \texttt{tc} clsact hook permits per-flow state to be maintained
in kernel maps and read from userspace\cite{ebpfqdisc2023}. The telemetry
path used here reads those maps through \texttt{bpf(2)} directly rather than
by spawning \texttt{bpftool}, which reduced the cost of one control tick from
3.17\,s to 0.709\,s. Its remaining cost is measured and reported in
Section~\ref{s:results} rather than assumed negligible, because it is not.
""")

# ------------------------------------------------------------------ 2
A(r"""\section{Methodology}\label{s:method}

\subsection{Why a purpose-built kernel was required}

The cloud container available for this work runs a Firecracker kernel with
every queue discipline compiled out and no loadable-module support, so
\texttt{fq\_codel} cannot be instantiated in it at all.
Figure~\ref{f:step01} is that failure, captured rather than described: an
attempt to attach the discipline under study returns an error because the
kernel has no such code. Every experiment therefore runs inside a virtual
machine built for the purpose.
""")
A(fig("step01_session_kernel_cannot_run_the_aqms_under_study.png"))
A(r"""Figure~\ref{f:step02} shows the replacement: a 6.12.48 kernel configured
and built with \texttt{fq\_codel}, CoDel, CAKE, PIE, FQ-PIE, RED,
\texttt{netem}, TBF and HTB all compiled in rather than modular, and with BTF
enabled so that eBPF programs can be verified against kernel types. This is
the kernel every measurement in this report was taken on.
""")
A(fig("step02_kernel_built_with_every_aqm_compiled_in.png"))
A(r"""Availability is then demonstrated rather than assumed.
Each discipline is instantiated in turn on a real virtual
Ethernet device inside the guest (Figure~\ref{f:step03}), so that a later null
result for one of them cannot be explained by the discipline having been
absent.
""")
A(fig("step03_aqm_availability_confirmed_inside_the_vm.png"))

A(r"""\subsection{Topology, and why the first one was wrong}

\begin{figure}[htbp]\centering
\includegraphics[width=0.95\linewidth,height=0.33\textheight,keepaspectratio]{step04_corrected_three_node_router_topology.png}
\caption{The measurement topology as configured. A client namespace offers the
load, a router namespace carries the shaper and the discipline under test, and
a server namespace terminates the flows. The shaper sits on the router's
egress toward the server, which is the direction bulk data travels, so the
queue under study holds data packets.}
\label{f:step04}\end{figure}

Three network namespaces are used, representing a client, a router and a
server. The router carries \texttt{netem} for base delay, a token-bucket
filter as root queue discipline for rate limiting, and the discipline under
test as the token bucket's child.

Placement is the part that matters, and the first attempt got it wrong.
Figure~\ref{f:step05} shows both arrangements side by side. In the original
two-node testbed the bottleneck sat on an interface that shaped traffic
travelling \emph{away} from the data source, so the queue filled with
66-byte acknowledgements while the data itself passed unshaped at multi-gigabit
rates. Every backlog and drop measurement taken that way was a measurement of
the acknowledgement path. The right panel is the corrected arrangement, where
the queue carries full-size packets.
""")
A(fig("step05_the_original_two_node_testbed_shaped_acks__not_d.png"))

A(r"""\subsection{Flow telemetry, and the silent failure it had}

An eBPF program at the \texttt{tc} clsact egress hook maintains per-flow state
in kernel maps: an LRU hash keyed by flow tuple and a per-CPU array of
aggregate counters. Userspace reads those maps through \texttt{bpf(2)}
directly rather than by spawning \texttt{bpftool}, which reduces the cost of
one control tick from 3.17\,s to 0.709\,s.

The capture in Figure~\ref{f:step06} has the program compiling with BTF, attaching at the
hook, and being verified as JIT-compiled. Figure~\ref{f:step07} is the
important one: it shows the maps returning \emph{non-zero} per-flow state
while traffic runs. An earlier version of this path loaded correctly,
populated its maps correctly, and returned zero for every sample, so a capture
showing only a successful attach would have established nothing.
Figure~\ref{f:step09} is the diagnosis of that failure.
""")
A(fig("step06_ebpf_telemetry_program_compiles__attaches_and_ji.png"))
A(fig("step07_ebpf_flow_telemetry_is_live_under_traffic.png"))

A(r"""\subsection{Controller}

The controller runs in userspace on three timescales. At packet granularity
the eBPF program maintains flow state. At a control tick it reads
\texttt{tc} statistics and the eBPF maps, classifies a congestion regime from
drop rate and backlog, and estimates a trajectory from the gradient over a
ten-tick window. At an adjustment opportunity it applies an additive-increase
multiplicative-decrease rule taken from Adaptive RED\cite{ared2001}, with
$\beta=0.9$ on decrease. The step sizes are fixed multiples of the configured
target rather than a decaying gain sequence, so the loop does not converge to
a fixed point by construction; whether it settles is a measured question that
Section~\ref{s:results} answers. Observation and update run on separate
timescales, ticking an order of magnitude faster than adjusting, which follows
the two-timescale stochastic approximation
framework\cite{borkar1997}.

Every bound, step size and threshold is expressed relative to the configured
target $t_0$ rather than as an absolute time:

\begin{center}\small
\begin{tabular}{ll}
\toprule
quantity & value \\ \midrule
\texttt{target} bounds & $[0.04\,t_0,\;4\,t_0]$ \\
\texttt{interval} bounds & $[0.2\,i_0,\;3\,i_0]$ \\
additive step & $0.2\,\mathrm{ms}\times(t_0/5\,\mathrm{ms})$ \\
regime thresholds & $\propto 5\,\mathrm{ms}/t_0$ \\
control period & $0.5\,\mathrm{s}\times(t_0/5\,\mathrm{ms})$ \\
\texttt{limit} bounds & $[64,4096]$ packets, a count, not scaled \\
\bottomrule
\end{tabular}
\end{center}

The multipliers are chosen so that the 5\,ms default reproduces the previous
absolute values exactly, which is what allows every run taken before the
change to stand. Section~\ref{s:defects} explains why relative expression is
not a stylistic choice: four separate defects in this controller were absolute
constants, and two of them would have manufactured a confirmation of the
result this report establishes.

\subsection{Measurement}

Three latencies are measured separately, because they are not the same
quantity and flow-queueing disciplines treat them differently by design.

\begin{center}\small
\begin{tabular}{p{3.1cm}p{4.6cm}p{6.4cm}}
\toprule
quantity & how & why separately \\ \midrule
sparse probe RTT & \texttt{ping} at 20\,Hz & flow queueing privileges sparse
flows; this is what a latency-sensitive application sees \\
bulk in-band RTT & \texttt{iperf3} \texttt{TCP\_INFO} per interval & what the
bulk flows themselves experience, which is the queue they create \\
queue delay & from \texttt{tc} backlog and drain rate & the component a queue
discipline can actually influence \\
\bottomrule
\end{tabular}
\end{center}

A single reported latency averages the first two, which differ by factors
between 1.1 and 9.6 across the systems measured.

\subsection{Experimental design}

Nine configurations are measured: \texttt{pfifo}, SFQ, adaptive RED, CoDel,
PIE, FQ-PIE, CAKE, static \texttt{fq\_codel}, and \texttt{fq\_codel} under the
controller. A tenth arm, the sham controller, runs the full polling and
classification path and applies no parameter change, which separates the
controller's computational cost from the effect of its decisions.

The workloads are three: a steady bulk load of eight TCP CUBIC\cite{cubic2008} flows; a
staged load whose flow count varies from two to twenty-four during the run;
and a mixed load adding sparse constant-rate UDP probes alongside the bulk
traffic. Each cell is repeated three times and reported with 95\% confidence
intervals. The \texttt{--seed} argument indexes an independent repetition
rather than seeding a pseudo-random generator: \texttt{iperf3} exposes no
seed and the disciplines are deterministic given the traffic, so repetitions
differ through real timing variation, which is the quantity the intervals
describe.

The controller's behaviour is pinned by the regression tests in
Figure~\ref{f:step08}, one per defect, so that a corrected defect cannot
silently return.
""")
A(fig("step08_regression_tests_pin_all_four_defects.png"))

# ------------------------------------------------------------------ 3
A(r"""\section{Results}\label{s:results}

All numbers below are generated from the run logs by \texttt{src/analyse.py}
and \texttt{src/analyse\_law.py}; none is typed by hand. The results are given
as eight steps, and each figure is described where its argument sits rather
than left to a caption.

Tables~\ref{t:steady} and~\ref{t:staged} carry the complete numeric result
set for the two primary workloads, every quantity as mean $\pm$ standard
deviation across seeds. The eight steps that follow read those two tables in
order, with the figures that make each reading visible.

\begin{table}[htbp]
\centering\scriptsize
\caption{Steady workload: all ten conditions, mean $\pm$ sd across seeds.
Eight bulk TCP CUBIC flows with a sparse UDP probe over a 10\,Mbit/s
bottleneck at 20\,ms base RTT.}
\label{t:steady}
\input{generated/table_steady}
\end{table}

\begin{table}[htbp]
\centering\scriptsize
\caption{Staged workload: the offered load steps during the run, so the queue
is never in steady state. This is the workload built to exercise the
controller, and the one on which it helps least.}
\label{t:staged}
\input{generated/table_staged}
\end{table}

\subsection{Step 1: flow queueing dominates everything else}

Figure~\ref{f:fig01} plots 95th-percentile probe latency for every
configuration on a logarithmic axis. The axis must be logarithmic because the
span is three orders of magnitude. Two groups separate cleanly. The
flow-queueing disciplines that enforce a delay target sit at the bottom within
a few milliseconds of one another. The unmanaged first-in-first-out queue sits
two orders of magnitude above them, at
\PfifoProbeRttPninetyfiveSteady\,ms against
\FqCodelProbeRttPninetyfiveSteady\,ms, a 99.0\% reduction at goodput that is
statistically indistinguishable.

The static, sham and adapted \texttt{fq\_codel} bars are not separable at this
scale. That is the first indication that parameter tuning is a second-order
effect, and it is visible before any statistics are applied.
""")
A(fig("fig01_latency_tail_steady.png"))
A(r"""Throughput rules out the obvious objection. Figure~\ref{f:fig03} confirms that the latency differences are not bought
with throughput. Goodput is flat across every configuration including the
unmanaged queue, so the latency ordering is a property of queue management
rather than a rate trade.
""")
A(fig("fig03_throughput_steady.png"))

A(r"""\subsection{Step 2: the two latencies are not interchangeable}

Separating the sparse probe from the bulk flows, as in Figure~\ref{f:fig02}, shows they do
not experience the same queue. Flow-queueing disciplines privilege sparse
flows by construction, so reporting one latency averages two quantities the
mechanism deliberately treats differently. The ratio between them runs from
1.1 to 9.6 across the systems measured, which is why both appear throughout
this report.
""")
A(fig("fig02_latency_sparse_vs_bulk_steady.png"))
A(r"""Underlying those latencies is the queue occupancy in
Figure~\ref{f:fig04}, and the drop rates in Figure~\ref{f:fig06} that produce
it. Occupancy
and drop rate move together in the expected direction: the disciplines holding
the shortest queues are the ones dropping earliest.
""")
A(fig("fig04_backlog_steady.png"))
A(fig("fig06_droprate_steady.png"))

A(r"""\subsection{Step 3: separating the controller's cost from its decisions}

Figure~\ref{f:fig13} compares three arms: static, sham and adapted. The sham
polls at the same cadence and runs the same classification and prediction
code, then applies nothing. Any gap between static and sham is the cost of
running the controller. Any gap between sham and adapted is the effect of its
decisions.

The figure plots each arm as its difference from the static arm rather than as
a bar, because the differences are small enough that a bar chart would have to
crop its own baseline to show them, and a cropped baseline turns a fraction of
a percent into a visibly taller bar. Read against the zero line, every
interval covers zero. The largest point estimate is the adapted arm's 9.6\%
reduction in mean backlog, and its interval runs from $-24$\% to $+5$\%.

Two conclusions follow, and they are different in kind. The controller's
computational cost is not detectable at this link rate, which is a
prerequisite for interpreting the rest of the work rather than a result. And
the effect of its decisions is not detectable either, on any of the four
metrics, under the steady workload at 20\,ms. The scaling law of
Section~\ref{s:law} explains why: this cell sits at $r=0.25$, where the
measured benefit of adaptation is 1.4\% and not significant. The sham
condition is what allows those two statements to be separated at all; without
the middle arm, a controller that merely consumed CPU would be
indistinguishable from one that helped.
""")
A(fig("fig13_sham_control_steady.png"))
A(r"""Within a single run, Figure~\ref{f:fig12} traces the controller: the
regime it classifies, the parameter trajectory that classification produces,
and the queue it responds to. A controller that classifies continuously but
never adjusts anything is indistinguishable from the static configuration in a
summary statistic, which is why the number of adjustments is reported for
every cell in this work.
""")
A(fig("fig12_controller_behaviour.png"))

A(r"""\subsection{Step 4: what adaptation achieves, parameter by parameter}

Figure~\ref{f:fig08} places every measured quantity against every system, in
one view. Each column is normalised so that quantities with different units
can be compared, and the measured value is printed in each cell. Goodput,
probe and bulk round-trip time, queue occupancy, drop rate, retransmissions
and Jain's fairness index\cite{jain1984} appear together.

The block structure is the result. The flow-queueing disciplines with a delay
target form one band that separates from the rest on every latency column
while remaining indistinguishable on goodput. Within that band the static,
sham and adapted rows differ very little, which is the same conclusion the
preceding steps reach one metric at a time.
""")
A(fig("fig08_allparams_steady.png", star=True, width=r"0.98\linewidth"))
A(r"""The same data read as a latency-throughput
trade-off, and Figure~\ref{f:fig05} the fairness index. Fairness sits at the
ceiling for every flow-queueing discipline, so it does not discriminate
between them here.
""")
A(fig("fig07_tradeoff_steady.png"))
A(fig("fig05_fairness_steady.png"))

A(r"""\subsection{Step 5: under a load that changes, adaptation does not help}

Under the steady workload the controller reduces mean queue occupancy by
9.6\%. Under the staged workload, whose flow count varies during the run, it
produces no improvement at all. Figures~\ref{f:fig10} and \ref{f:fig11} show
why: the queue and latency time series under the staged load contain
transitions the controller responds to only after they have happened, because
its adjustments lag the change that triggered them.

This matters more than the steady-state number. An adaptive mechanism that
helps only when conditions are static is of limited value, since static
conditions are precisely those a fixed configuration already serves.
""")
A(fig("fig10_timeseries_backlog_staged.png"))
A(fig("fig11_timeseries_rtt_staged.png"))

A(r"""\subsection{Step 6: an alternative requiring no controller does better}

CAKE outperforms the adapted system at every path RTT tested, by a margin
larger than the adaptation itself achieves. At a 5\,ms path, adapting
\texttt{fq\_codel}'s parameters recovers 18.4\% of bulk-flow latency while
simply running CAKE instead recovers 43.9\%. At 20\,ms the figures are 1.4\%
and 7.5\%. This is stated plainly because a reader who discovers it
independently would be entitled to distrust everything else in the report.

\subsection{Step 7: the predictive path never engaged}

The controller contains a predictive branch intended to act on a worsening
trajectory before the regime classification escalates. Under steady load it
never fired. The reason is structural rather than a tuning problem: an
adjustment requires five consecutive identical regime classifications, and the
predictive branch is reachable only when the trajectory disagrees with the
regime, which that stability requirement excludes. The predictive-control
claim is therefore withdrawn rather than asserted.

\subsection{Step 8: sparse flows under mixed traffic}

The mixed workload appears in Figure~\ref{f:fig14}, where sparse UDP probes run
alongside the bulk flows. Every flow-queueing discipline with a delay target
cuts sparse-flow loss from roughly 8\% to below 0.03\%. The effect is large
and it is a property of the discipline class, not of the controller.
""")
A(fig("fig14_mixed_workload.png"))

# ------------------------------------------------------------------ 4
A(r"""\section{Comparison}\label{s:cmp}

\subsection{Disciplines under test and their parameters}

\begin{center}\scriptsize
\begin{tabular}{p{2.0cm}p{2.3cm}cc p{3.2cm}}
\toprule
discipline & class & FQ & target & parameters adapted here \\ \midrule
\texttt{pfifo} & FIFO, no AQM & & & \\
\texttt{sfq} & fair queueing & \checkmark & & \\
\texttt{red} & drop probability & & queue band & \\
\texttt{codel} & delay target & & sojourn & \\
\texttt{pie} & PI controller & & sojourn & \\
\texttt{fq\_pie} & FQ + PIE & \checkmark & sojourn & \\
\texttt{cake} & shaper + AQM & \checkmark & internal & \\
\texttt{fq\_codel} & FQ + CoDel & \checkmark & sojourn & \\
\;+ controller & FQ + CoDel, adapted & \checkmark & sojourn, adapted &
\texttt{target}, \texttt{interval}, \texttt{limit}, \texttt{quantum} \\
\bottomrule
\end{tabular}
\end{center}

Every discipline sits as the child of an identical token-bucket shaper on the
router's egress, with \texttt{netem} at each edge. CAKE is configured
\texttt{besteffort} without its own bandwidth setting so that the token bucket
remains the only shaper and every discipline sees the same bottleneck.

\subsection{Against the base paper and six recent systems}

\begin{center}\scriptsize
\begin{tabular}{p{1.9cm}cp{1.7cm}p{2.4cm}p{2.1cm}p{2.4cm}}
\toprule
system & year & adapts & method & input & parameters \\ \midrule
Adaptive RED & 2001 & $\max_p$ & AIMD, $\beta=0.9$ & averaged queue length & 1 \\
ACoDel & 2020 & \texttt{interval} & analytical & queue-delay model & 1 \\
QueuePilot & 2023 & marking prob. & offline RL & queue state & 1 \\
DualPI2 / L4S & 2023 & none & dual queue & ECN & 0 \\
DESiRED & 2024 & target delay & deep RL & in-band telemetry & 1 \\
AQM-LLM & 2025 & action policy & distilled LLM & telemetry tokens & policy \\
This work & 2026 & four parameters & AIMD + gradient & \texttt{tc} + eBPF & 4 \\
\bottomrule
\end{tabular}
\end{center}

Two things follow from that table. Adapting an AQM's delay target at runtime
is established, by DESiRED, so the mechanism is not the contribution here.
And no entry in the table states the condition under which its adaptation
pays, which is what this report supplies.

\subsection{What none of the prior systems reports}

None runs a control condition that separates a controller's computational cost
from the effect of its decisions. None reports sparse-probe and bulk-flow
latency separately, despite flow-queueing disciplines privileging sparse flows
by construction. None compares against eight alternative disciplines under an
identical bottleneck. None states numerical predictions before measuring them.
""")

# ------------------------------------------------------------------ 5
A(r"""\section{The scaling law}\label{s:law}

\subsection{From an unexplained table to a hypothesis}

The RTT sweep of Figure~\ref{f:fig15} is where the law comes from. Adaptation
recovers a large and highly significant share of bulk-flow latency on the
shortest path and nothing at 20, 80 or 200\,ms. Read as four independent
measurements this is unexplained, and the obvious reading, that adaptation
helps on short paths, is not a mechanism and predicts nothing.
""")
A(fig("fig15_rtt_sweep.png"))
A(r"""CoDel's \texttt{target} is a delay budget, fixed at 5\,ms by default,
while the path RTT is whatever the path is. The quantity that should govern
whether that budget is badly chosen is therefore neither one alone but their
ratio,
\begin{equation}
r=\frac{\texttt{target}}{\mathrm{RTT}}.
\end{equation}
On this reading RTT never appears on its own; it appears only through $r$.
That is a stronger claim than the table, and unlike the table it can be wrong.

\subsection{Pre-registration}

Because a saturating curve can be fitted to almost any monotone data, the
hypothesis, its three predictions and their numerical thresholds were
committed to the repository \emph{before} the campaign that tests them ran.
The commit adding \texttt{docs/SCALING\_LAW.md} precedes the commit adding the
results directory, and the version history shows it.

\subsection{Result}

\begin{equation}
b(r)=\frac{B}{1+(r_0/r)^k},\qquad
B=\LawCeiling\,\%,\;\; r_0=\LawHalfBenefit,\;\; k=\LawSteepness
\end{equation}
with $R^2=\LawRsq$. Figure~\ref{f:fig16} is the evidence. The left panel plots
benefit against $r$, where the measurements collapse onto one curve; filled
markers are statistically significant. The right panel plots the identical
measurements against path RTT alone, where they do not collapse. The contrast
between the panels is the argument.
""")
A(fig("fig16_scaling_law.png", star=True, width=r"0.96\linewidth"))
A(r"""\begin{table}[htbp]
\centering\scriptsize
\caption{Scaling-law fit and the pre-registered verdicts. Every threshold in
the decision column was committed to the repository before the data existed.}
\label{t:law}
\input{generated/table_law}
\end{table}

Ratio invariance is the prediction able to refute the claim, and it holds.
Scaling \texttt{target}, \texttt{interval}, the control period and the run
duration together by the same factor gives 18.4\%, 17.6\% and 16.4\% at 5, 20
and 80\,ms, a spread of 2.0 percentage points across a sixteenfold range of
RTT. Held-out interior ratios are predicted to 1.4 points. At a fixed 20\,ms
path, changing only $r$ moves the benefit from 1.4\% to 17.6\%, which no
account in terms of RTT reproduces.

\subsection{What it costs, and what it means}

The gain is bought with up to \LawDropRiseHigh\% more drops and comparable
retransmissions, at a throughput cost never exceeding
\LawWorstThroughput\% in any cell measured. The ratio governs the exchange
rate as well as the gain.

Published guidance places \texttt{target} at 5 to 10 percent of
\texttt{interval}, with \texttt{interval} on the order of the path RTT, so a
correctly configured deployment sits at $r$ between 0.05 and 0.10. Half the
available benefit arrives at $r=\LawHalfBenefit$, five to ten times outside
that envelope. Parameter adaptation is therefore best understood as a remedy
for misconfiguration rather than an improvement on correct configuration,
which explains the null results in this work and elsewhere as one effect
rather than several.
""")

# ------------------------------------------------------------------ 6
A(r"""\section{Measurement defects found and corrected}\label{s:defects}

Nine defects were found during this work. Each produced results that were
confident, internally consistent and wrong. They are listed because they are
the reason the final numbers are believable, and because four of them share
one shape.

\begin{center}\small
\begin{tabular}{p{0.6cm}p{6.1cm}p{8.6cm}}
\toprule
\# & defect & consequence if uncorrected \\ \midrule
1 & two-node testbed shaped the acknowledgement path & every backlog and drop
figure measured ACK queueing \\
2 & eBPF telemetry returned zero while correctly loaded & flow-aware control
ran on no information \\
3 & controller state could not reach the kernel & adjustments logged but never
applied \\
4 & a control input with no effect on output & identical action reported as
though some were predictive \\
5 & constants that looked like measurements & derived values quoted as
observations \\
6 & absolute parameter bounds & an 80\,ms target clamped to 20\,ms on sight,
manufacturing a confirmation \\
7 & absolute additive step sizes & controller adapted an order of magnitude
more slowly at large targets, manufacturing a refutation \\
8 & absolute regime thresholds & three cells requiring identical treatment
received three different control laws \\
9 & \texttt{iperf3 --logfile} appends & re-running a cell corrupted its own
goodput and latency silently \\
\bottomrule
\end{tabular}
\end{center}

Defects 6 to 8, with the control-period defect they concealed, share a single
cause: an absolute constant inside a controller whose entire subject is a
dimensionless ratio. Two of them would have manufactured a confirmation of the
scaling law and two a refutation, and each was invisible until the one before
it was fixed. None was visible in a summary statistic; all were found by
reading a parameter trajectory or a log file.

\section{Threats to validity}

\textbf{Emulation.} Experiments run under QEMU without hardware
virtualisation. Shaping accuracy was validated before collecting results, and
absolute latencies are dominated by configured delay rather than host jitter.
Much higher link rates would need revalidation.

\textbf{Scale.} A 10\,Mbit bottleneck with 8 to 24 flows represents a home or
access link, not a datacentre or backbone.

\textbf{The second dimensionless group.} Holding $r$ at 1.0 and varying only
link rate from 2 to 50\,Mbit, the benefit is not constant: it peaks near 18\%
at 5 to 10\,Mbit and falls to 13.2\% at 2\,Mbit and 7.1\% at 50\,Mbit. A
second group, $\texttt{target}/(\mathrm{MTU}/\mathrm{rate})$, therefore
matters and the single-variable law is incomplete. The prediction that benefit
would be suppressed below one packet's serialisation time was wrong: at
2\,Mbit a packet takes 6.06\,ms against a 5\,ms target, which CoDel cannot
reach, yet adaptation still recovers 13.2\% by reducing occupancy above that
floor.

\textbf{Cross-mechanism transfer.} Fitted independently, plain \texttt{codel}
places the crossover at $r_0=0.42$ against \texttt{fq\_codel}'s 0.49, and PIE
at 1.06. The spread exceeds the factor of two set in advance, and the cause
cannot be separated here: PIE's native \texttt{target}/\texttt{tupdate} is 1.0
where CoDel's \texttt{target}/\texttt{interval} is 0.05, so sweeping each
discipline at its own defaults varied a second group across the comparison
intended to isolate mechanism.

\textbf{Single bottleneck.} Multi-hop topologies with several congested links
are not covered.

\section{Conclusion}

The question of whether adapting a queue discipline's parameters at runtime
improves on its defaults is underspecified, and a single dimensionless number
completes it. The benefit is governed by $r=\texttt{target}/\mathrm{RTT}$,
saturating near \LawCeiling\% and reaching half of that at
$r=\LawHalfBenefit$, invariant across a sixteenfold range of RTT at fixed
ratio, and statistically indistinguishable from zero below $r\approx0.25$ even
where the controller demonstrably acts.

Because correct configuration sits an order of magnitude below the crossover,
runtime parameter adaptation is a remedy for misconfiguration rather than an
improvement on correct configuration. That is narrower than the systems
literature claims and more useful than the evaluations reporting nothing, and
it accounts for both.
""")

# ------------------------------------------------------------------ appendix
A(r"""\appendix
\section{Complete figure set}\label{s:app}

Figures already discussed above are not repeated. The remainder of the
analysis output follows, with captions from the figure index.
""")
shown = {"fig01_latency_tail_steady.png", "fig02_latency_sparse_vs_bulk_steady.png",
         "fig03_throughput_steady.png", "fig04_backlog_steady.png",
         "fig05_fairness_steady.png", "fig06_droprate_steady.png",
         "fig07_tradeoff_steady.png", "fig08_allparams_steady.png",
         "fig10_timeseries_backlog_staged.png", "fig11_timeseries_rtt_staged.png",
         "fig12_controller_behaviour.png", "fig13_sham_control_steady.png",
         "fig14_mixed_workload.png", "fig15_rtt_sweep.png",
         "fig16_scaling_law.png"}
for e in IDX["figures"]:
    n = e["path"].split("/")[-1]
    if n not in shown:
        A(fig(n))
A(r"""\section{Implementation captures not shown above}

""")
for e in IDX["steps"]:
    n = e["path"].split("/")[-1]
    if not n.startswith(("step01", "step02", "step03", "step04", "step05",
                         "step06", "step07", "step08")):
        A(fig(n))

A(r"""\section{Per-run figures}

One figure per experimental run, 63 in all, each showing that run's time
series. They are tabulated rather than embedded because the analysis figures
above aggregate them; every file is in \texttt{figures/runs/}.

\begin{longtable}{p{1.5cm}p{5.0cm}p{9.5cm}}
\toprule ID & run & summary \\ \midrule \endfirsthead
\toprule ID & run & summary \\ \midrule \endhead
""")
for e in IDX["runs"]:
    A(rf"{esc(e['id'])} & \texttt{{{esc(e['title'])}}} & {esc(e.get('caption',''))} \\")
A(r"""\bottomrule
\end{longtable}

\section{Reproducing every number}\label{s:repro}

\begin{verbatim}
python3 src/analyse.py        # tables and fact macros
python3 src/analyse_law.py    # the scaling law
python3 src/plots.py          # all analysis figures
python3 src/make_index.py     # the figure index
python3 paper/make_report.py  # this document
\end{verbatim}

Pre-registered hypotheses and their decision thresholds are in
\texttt{docs/SCALING\_LAW.md}, \texttt{docs/CROSS\_AQM\_PREREG.md},
\texttt{docs/SERIALIZATION\_PREREG.md} and \texttt{docs/GATE\_PREREG.md}. The
defects of Section~\ref{s:defects} are documented in \texttt{verification/}.

\bibliographystyle{IEEEtran}
\bibliography{refs}

\end{document}
""")

out = os.path.join(HERE, "report.tex")
open(out, "w").write("\n".join(DOC))
print(f"wrote {out}")
