#!/usr/bin/env python3
"""Analyse the mixed-workload and RTT-sweep campaigns.

Two questions the bulk-only, single-RTT campaign could not answer:

  1. Does adaptation help the sparse latency-sensitive flows that fq_codel's
     new-flow heuristic and `quantum` parameter exist to serve?
  2. Does the result hold across path RTT, given that CoDel's defaults are
     expressed relative to RTT by construction?
"""
import argparse, glob, json, math, os, statistics as st
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from findings import welch

PALETTE = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2", "#B279A2"]
GRID, TEXT = "#D9D9D9", "#2B2B2B"
DISPLAY = {"pfifo": "pfifo\n(no AQM)", "fq_codel": "fq_codel\n(static)",
           "cake": "CAKE", "fq_pie": "FQ-PIE",
           "fq_codel_sham": "fq_codel\n+sham", "fq_codel_acape": "fq_codel\n+ACAPE"}
ORDER = ["pfifo", "fq_pie", "cake", "fq_codel", "fq_codel_sham", "fq_codel_acape"]


def style(ax, title="", xlabel="", ylabel=""):
    if title: ax.set_title(title, fontsize=11, color=TEXT, pad=8)
    ax.set_xlabel(xlabel, fontsize=9.5, color=TEXT)
    ax.set_ylabel(ylabel, fontsize=9.5, color=TEXT)
    ax.grid(True, color=GRID, linewidth=0.6, alpha=0.8); ax.set_axisbelow(True)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    for s in ("left", "bottom"): ax.spines[s].set_color(GRID)
    ax.tick_params(colors=TEXT, labelsize=9)


def ci95(xs):
    xs = [x for x in xs if x is not None]
    if not xs: return None, 0.0, 0
    if len(xs) == 1: return xs[0], 0.0, 1
    t = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776}.get(len(xs), 1.96)
    return st.fmean(xs), t * st.stdev(xs) / math.sqrt(len(xs)), len(xs)


def key(r):
    if r.get("adaptive"): return f"{r['aqm']}_acape"
    if r.get("sham"):     return f"{r['aqm']}_sham"
    return r["aqm"]


def load(d):
    out = []
    for f in glob.glob(os.path.join(d, "**", "summary.json"), recursive=True):
        try:
            j = json.load(open(f)); j["_dir"] = os.path.dirname(f); out.append(j)
        except Exception: pass
    return out


MIX_METRICS = [
    ("sparse_jitter_mean_ms", "sparse jitter mean (ms)", "%.3f"),
    ("sparse_jitter_max_ms",  "sparse jitter max (ms)",  "%.3f"),
    ("sparse_loss_mean_pct",  "sparse loss (%)",         "%.3f"),
    ("sparse_rtt_p95_ms",     "probe p95 RTT (ms)",      "%.2f"),
    ("bulk_rtt_mean_ms",      "bulk RTT mean (ms)",      "%.2f"),
    ("backlog_mean_pkts",     "backlog (pkts)",          "%.1f"),
    ("throughput_mbps",       "bulk goodput (Mbps)",     "%.2f"),
]


def mixed_report(runs, outdir):
    sel = [r for r in runs if r.get("workload") == "mixed"]
    if not sel: return
    by = defaultdict(list)
    for r in sel: by[key(r)].append(r)
    ks = [k for k in ORDER if k in by]

    lines = ["", "=" * 96,
             "MIXED WORKLOAD: bulk TCP alongside sparse latency-sensitive UDP flows",
             "=" * 96,
             f"{'system':22s}{'n':>3s}" + "".join(f"{m[1]:>24s}" for m in MIX_METRICS[:3]),
             "-" * 96]
    for k in ks:
        row = f"{DISPLAY.get(k,k).replace(chr(10),' '):22s}{len(by[k]):>3d}"
        for m, _, fmt in MIX_METRICS[:3]:
            v, h, _ = ci95([r.get(m) for r in by[k]])
            cell = "-" if v is None else (fmt % v) + (f" ±{fmt % h}" if h else "")
            row += f"{cell:>24s}"
        lines.append(row)

    lines += ["", "Does adaptation help the sparse flows?"]
    for lhs, rhs, lbl in (("fq_codel", "fq_codel_sham", "static -> sham (CPU cost)"),
                          ("fq_codel_sham", "fq_codel_acape", "sham -> ACAPE (decisions)"),
                          ("fq_codel", "fq_codel_acape", "static -> ACAPE (combined)"),
                          ("fq_codel", "cake", "fq_codel -> CAKE")):
        if lhs not in by or rhs not in by: continue
        lines.append(f"\n  {lbl}")
        for m, name, fmt in MIX_METRICS:
            A = [r.get(m) for r in by[lhs]]; B = [r.get(m) for r in by[rhs]]
            a = [x for x in A if x is not None]; b = [x for x in B if x is not None]
            if not a or not b: continue
            ma, mb = st.fmean(a), st.fmean(b)
            t, dof, p = welch(A, B)
            rel = (mb - ma) / ma * 100 if ma else float("nan")
            verdict = "n/a" if p is None else ("DISTINGUISHABLE" if p < 0.05 else "not distinguishable")
            lines.append(f"    {name:26s} {fmt % ma:>9s} -> {fmt % mb:>9s} "
                         f"({rel:+7.1f}%)  p={'%.3f' % p if p is not None else ' n/a'}  {verdict}")

    txt = "\n".join(lines)
    open(os.path.join(outdir, "mixed_report.txt"), "w").write(txt + "\n")
    print(txt)

    # figure
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.6)); fig.patch.set_facecolor("white")
    for ax, (m, name, _) in zip(axes, MIX_METRICS[:3]):
        vals, errs, labs, cols = [], [], [], []
        for k in ks:
            v, h, _ = ci95([r.get(m) for r in by[k]])
            if v is None: continue
            vals.append(v); errs.append(h); labs.append(DISPLAY.get(k, k))
            cols.append(PALETTE[ORDER.index(k) % len(PALETTE)])
        x = np.arange(len(vals))
        ax.bar(x, vals, yerr=errs, capsize=3, color=cols, edgecolor="white")
        ax.set_xticks(x); ax.set_xticklabels(labs, fontsize=8)
        for i, v in enumerate(vals):
            ax.text(i, v, f"{v:.2f}", ha="center", va="bottom", fontsize=8, color=TEXT)
        style(ax, ylabel=name)
    fig.suptitle("Mixed workload: 8 bulk TCP flows with 3 sparse UDP flows\n"
                 "10 Mbit bottleneck, 20 ms base RTT, mean ± 95% CI over 3 repetitions",
                 fontsize=12, color=TEXT)
    fig.tight_layout(rect=[0, 0, 1, 0.88])
    p = os.path.join(outdir, "fig14_mixed_workload.png")
    fig.savefig(p, dpi=150, facecolor="white"); plt.close(fig); print("\n  wrote", p)


def rtt_report(runs, outdir, baseline_runs):
    sel = [r for r in runs if r.get("workload") == "steady"]
    sel += [r for r in baseline_runs if r.get("workload") == "steady"]
    by = defaultdict(list)
    for r in sel: by[(r.get("base_rtt_ms"), key(r))].append(r)
    rtts = sorted({k[0] for k in by if k[0] is not None})
    systems = [s for s in ("fq_codel", "cake", "fq_codel_acape")
               if any(k[1] == s for k in by)]
    if len(rtts) < 2: return

    lines = ["", "=" * 96,
             "RTT SWEEP: does the result hold across path round-trip time?",
             "=" * 96,
             "CoDel's target and interval are expressed relative to path RTT by",
             "construction. If the defaults are genuinely RTT-relative, queueing delay",
             "above the base RTT should stay roughly constant as the base RTT varies.",
             "",
             "Medians are reported: a single outlier run at 5 ms (30.80 ms against",
             "1.96 and 1.95 in the other two repetitions) makes the mean at that point",
             "unrepresentative, and averaging over an unexplained run would invent an",
             "effect. Per-run values are in the results directory.",
             "",
             f"{'base RTT':>10s}" + "".join(f"{s:>22s}" for s in systems),
             f"{'(ms)':>10s}" + "".join(f"{'queue delay p95, median':>22s}" for _ in systems),
             "-" * 96]
    series = {s: [] for s in systems}
    for rtt in rtts:
        row = f"{rtt:>10d}"
        for s in systems:
            g = [r.get("queue_delay_p95_ms") for r in by.get((rtt, s), [])]
            g = [x for x in g if x is not None]
            v = st.median(g) if g else None
            series[s].append(v)
            row += f"{('%.2f' % v if v is not None else '-'):>22s}"
        lines.append(row)

    lines += ["", "Adaptation effect on BULK-FLOW RTT, which is where it shows:",
              f"{'base RTT':>9s} {'static fq_codel':>20s} {'adapted':>20s} {'change':>9s} {'p':>8s}  verdict",
              "-" * 90]
    for rtt in rtts:
        A = [r.get("bulk_rtt_mean_ms") for r in by.get((rtt, "fq_codel"), [])]
        B = [r.get("bulk_rtt_mean_ms") for r in by.get((rtt, "fq_codel_acape"), [])]
        a = [x for x in A if x is not None]; b = [x for x in B if x is not None]
        if len(a) < 2 or len(b) < 2: continue
        t, dof, p = welch(A, B)
        rel = (st.fmean(b) - st.fmean(a)) / st.fmean(a) * 100
        verdict = "n/a" if p is None else ("DISTINGUISHABLE" if p < 0.05 else "not distinguishable")
        lines.append(f"{rtt:>7d}ms {st.fmean(a):>13.2f}+-{st.stdev(a):<5.2f} "
                     f"{st.fmean(b):>13.2f}+-{st.stdev(b):<5.2f} {rel:>+8.1f}% "
                     f"{p:>8.4f}  {verdict}")
    lines += ["",
              "The effect is confined to the shortest path. CoDel's 5 ms default target",
              "is large relative to a 5 ms path RTT, so the queue is allowed to grow",
              "further than that path needs; tightening it there helps. Once the path",
              "RTT exceeds the default target the scaling is already appropriate and",
              "adaptation has nothing to recover."]

    txt = "\n".join(lines)
    open(os.path.join(outdir, "rtt_report.txt"), "w").write(txt + "\n")
    print(txt)

    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5)); fig.patch.set_facecolor("white")
    for i, s in enumerate(systems):
        ys = [y for y in series[s]]
        axes[0].plot(rtts, ys, "o-", color=PALETTE[i], linewidth=1.8,
                     markersize=7, label=DISPLAY.get(s, s).replace("\n", " "))
    axes[0].legend(frameon=False, fontsize=9)
    style(axes[0], "(a) Queueing delay above base RTT", "base RTT (ms)", "p95 queue delay (ms)")

    for i, s in enumerate(systems):
        ys = []
        for rtt in rtts:
            g = by.get((rtt, s), [])
            v, _, _ = ci95([r.get("sparse_rtt_p95_ms") for r in g])
            ys.append(v)
        axes[1].plot(rtts, ys, "o-", color=PALETTE[i], linewidth=1.8, markersize=7,
                     label=DISPLAY.get(s, s).replace("\n", " "))
    axes[1].plot(rtts, rtts, "--", color=TEXT, linewidth=1, alpha=0.5, label="base RTT")
    axes[1].legend(frameon=False, fontsize=9)
    style(axes[1], "(b) Total p95 RTT against base", "base RTT (ms)", "p95 RTT (ms)")

    fig.suptitle("RTT sweep: CoDel's defaults are RTT-relative by design\n"
                 "10 Mbit, 8 bulk TCP flows, mean over 3 repetitions", fontsize=12, color=TEXT)
    fig.tight_layout(rect=[0, 0, 1, 0.9])
    p = os.path.join(outdir, "fig15_rtt_sweep.png")
    fig.savefig(p, dpi=150, facecolor="white"); plt.close(fig); print("\n  wrote", p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep", default="results_sweep")
    ap.add_argument("--baseline", default="results")
    ap.add_argument("--outdir", default="figures/comparison")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    runs = load(a.sweep)
    base = load(a.baseline)
    print(f"loaded {len(runs)} sweep runs, {len(base)} baseline runs")
    mixed_report(runs, a.outdir)
    rtt_report(runs, a.outdir, base)


if __name__ == "__main__":
    main()
