#!/usr/bin/env python3
"""Aggregate the experiment suite into tables and figures.

Every number this emits is computed from a summary.json or time series written
by src/run_experiment.py. Nothing is hand-entered. Results are reported as
mean +/- 95% CI across seeds; a single run is reported as a single run.
"""
import argparse, csv, glob, json, math, os, statistics as st
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Brand-neutral, colour-blind-safe categorical palette.
PALETTE = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2",
           "#B279A2", "#EECA3B", "#9D755D", "#BAB0AC"]
GRID = "#D9D9D9"
TEXT = "#2B2B2B"

DISPLAY = {
    "pfifo": "pfifo (no AQM)", "fq_codel": "fq_codel (static)",
    "codel": "CoDel", "pie": "PIE", "fq_pie": "FQ-PIE",
    "cake": "CAKE", "red": "RED (adaptive)", "sfq": "SFQ",
    "fq_codel_acape": "fq_codel + ACAPE",
}
ORDER = ["pfifo", "sfq", "red", "codel", "pie", "fq_pie", "cake",
         "fq_codel", "fq_codel_acape"]


def style(ax, title="", xlabel="", ylabel=""):
    ax.set_title(title, fontsize=11, color=TEXT, pad=10)
    ax.set_xlabel(xlabel, fontsize=9.5, color=TEXT)
    ax.set_ylabel(ylabel, fontsize=9.5, color=TEXT)
    ax.grid(True, color=GRID, linewidth=0.6, alpha=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=TEXT, labelsize=9)


def ci95(xs):
    """Mean and half-width of the 95% CI. Returns (mean, halfwidth, n)."""
    xs = [x for x in xs if x is not None]
    if not xs:
        return None, None, 0
    if len(xs) == 1:
        return xs[0], 0.0, 1
    m = st.fmean(xs)
    sd = st.stdev(xs)
    # t_{0.975} for small samples; falls back to 1.96 for n > 30
    tcrit = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571,
             7: 2.447, 8: 2.365, 9: 2.306, 10: 2.262}.get(len(xs), 1.96)
    return m, tcrit * sd / math.sqrt(len(xs)), len(xs)


def load(resdir):
    runs = []
    for f in sorted(glob.glob(os.path.join(resdir, "*", "summary.json"))):
        try:
            d = json.load(open(f))
            d["_dir"] = os.path.dirname(f)
            runs.append(d)
        except Exception as e:
            print(f"  skipped {f}: {e}")
    return runs


def system_key(r):
    return f"{r['aqm']}_acape" if r.get("adaptive") else r["aqm"]


METRICS = [
    ("throughput_mbps",      "Goodput (Mbps)",              "%.2f"),
    ("jain",                 "Jain's fairness",             "%.4f"),
    ("backlog_mean_pkts",    "Mean backlog (pkts)",         "%.1f"),
    ("backlog_p95_pkts",     "p95 backlog (pkts)",          "%.1f"),
    ("rtt_mean_ms",          "Mean RTT (ms)",               "%.2f"),
    ("rtt_p95_ms",           "p95 RTT (ms)",                "%.2f"),
    ("rtt_p99_ms",           "p99 RTT (ms)",                "%.2f"),
    ("sojourn_p95_ms",       "p95 queue delay (ms)",        "%.2f"),
    ("drop_rate_mean_per_s", "Mean drop rate (/s)",         "%.1f"),
    ("retransmits",          "Retransmits",                 "%.0f"),
]


def build_table(runs, workload):
    sel = [r for r in runs if r.get("workload") == workload]
    by = defaultdict(list)
    for r in sel:
        by[system_key(r)].append(r)
    rows = []
    for k in ORDER:
        if k not in by:
            continue
        group = by[k]
        row = {"system": DISPLAY.get(k, k), "key": k, "n": len(group)}
        for mk, _, _ in METRICS:
            m, h, n = ci95([g.get(mk) for g in group])
            row[mk] = m
            row[mk + "_ci"] = h
        rows.append(row)
    return rows


def write_tables(runs, outdir):
    os.makedirs(outdir, exist_ok=True)
    out = {}
    for wl in ("steady", "staged"):
        rows = build_table(runs, wl)
        if not rows:
            continue
        out[wl] = rows
        path = os.path.join(outdir, f"table_{wl}.csv")
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            hdr = ["system", "n"] + [m[0] for m in METRICS] + \
                  [m[0] + "_ci95" for m in METRICS]
            w.writerow(hdr)
            for r in rows:
                w.writerow([r["system"], r["n"]] +
                           [r.get(m[0]) for m in METRICS] +
                           [r.get(m[0] + "_ci") for m in METRICS])
        # human-readable
        txt = os.path.join(outdir, f"table_{wl}.txt")
        with open(txt, "w") as fh:
            fh.write(f"Workload: {wl}   (mean +/- 95% CI across seeds)\n")
            fh.write("=" * 118 + "\n")
            fh.write(f"{'system':22s}{'n':>3s}")
            for _, lbl, _ in METRICS[:6]:
                fh.write(f"{lbl:>19s}")
            fh.write("\n" + "-" * 118 + "\n")
            for r in rows:
                fh.write(f"{r['system']:22s}{r['n']:>3d}")
                for mk, _, fmt in METRICS[:6]:
                    v, h = r.get(mk), r.get(mk + "_ci")
                    fh.write(f"{(fmt % v) if v is not None else '-':>12s}"
                             f"{('+-' + (fmt % h)) if h else '':>7s}")
                fh.write("\n")
        print(open(txt).read())
    with open(os.path.join(outdir, "tables.json"), "w") as fh:
        json.dump(out, fh, indent=2)
    return out


def bar_with_ci(ax, rows, metric, ylabel, logy=False):
    ks = [r for r in rows if r.get(metric) is not None]
    labels = [r["system"] for r in ks]
    vals = [r[metric] for r in ks]
    errs = [r.get(metric + "_ci") or 0 for r in ks]
    colours = [PALETTE[ORDER.index(r["key"]) % len(PALETTE)] for r in ks]
    x = np.arange(len(ks))
    ax.bar(x, vals, yerr=errs, capsize=3, color=colours,
           edgecolor="white", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8.5)
    if logy:
        ax.set_yscale("log")
    style(ax, ylabel=ylabel)


def fig_comparison(rows, wl, outdir):
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    fig.patch.set_facecolor("white")
    bar_with_ci(axes[0][0], rows, "rtt_p95_ms", "p95 RTT (ms)", logy=True)
    axes[0][0].set_title("(a) Tail latency — log scale", fontsize=11, color=TEXT)
    bar_with_ci(axes[0][1], rows, "throughput_mbps", "Goodput (Mbps)")
    axes[0][1].set_title("(b) Goodput", fontsize=11, color=TEXT)
    bar_with_ci(axes[1][0], rows, "backlog_mean_pkts", "Mean backlog (pkts)", logy=True)
    axes[1][0].set_title("(c) Queue occupancy — log scale", fontsize=11, color=TEXT)
    bar_with_ci(axes[1][1], rows, "jain", "Jain's fairness index")
    axes[1][1].set_ylim(0.9, 1.005)
    axes[1][1].set_title("(d) Flow fairness", fontsize=11, color=TEXT)
    fig.suptitle(f"AQM comparison — {wl} workload, 10 Mbit bottleneck, "
                 f"8 TCP CUBIC flows, 20 ms base RTT\n"
                 f"mean ± 95% CI across seeds",
                 fontsize=12.5, color=TEXT)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    p = os.path.join(outdir, f"fig_comparison_{wl}.png")
    fig.savefig(p, dpi=150, facecolor="white")
    plt.close(fig)
    return p


def fig_latency_throughput(rows, wl, outdir):
    fig, ax = plt.subplots(figsize=(8, 5.5))
    fig.patch.set_facecolor("white")
    for r in rows:
        if r.get("rtt_p95_ms") is None:
            continue
        c = PALETTE[ORDER.index(r["key"]) % len(PALETTE)]
        ax.errorbar(r["throughput_mbps"], r["rtt_p95_ms"],
                    xerr=r.get("throughput_mbps_ci") or 0,
                    yerr=r.get("rtt_p95_ms_ci") or 0,
                    fmt="o", color=c, markersize=9, capsize=3,
                    markeredgecolor="white", markeredgewidth=1.2)
        ax.annotate(r["system"], (r["throughput_mbps"], r["rtt_p95_ms"]),
                    textcoords="offset points", xytext=(8, 5),
                    fontsize=8.5, color=TEXT)
    ax.set_yscale("log")
    style(ax, title=f"Latency–throughput trade-off ({wl} workload)\n"
                    "lower and further right is better",
          xlabel="Goodput (Mbps)", ylabel="p95 RTT (ms, log scale)")
    fig.tight_layout()
    p = os.path.join(outdir, f"fig_tradeoff_{wl}.png")
    fig.savefig(p, dpi=150, facecolor="white")
    plt.close(fig)
    return p


def fig_timeseries(runs, outdir):
    """Backlog over time for one seed of each system: shows the bloat directly."""
    sel = {}
    for r in runs:
        if r.get("workload") != "steady" or r.get("seed") != 1:
            continue
        sel[system_key(r)] = r
    if not sel:
        return None
    fig, ax = plt.subplots(figsize=(10, 5.5))
    fig.patch.set_facecolor("white")
    for k in ORDER:
        if k not in sel:
            continue
        f = os.path.join(sel[k]["_dir"], "qdisc_timeseries.csv")
        if not os.path.exists(f):
            continue
        rows = list(csv.DictReader(open(f)))[1:]
        t = [float(x["t_s"]) for x in rows]
        b = [float(x["backlog_pkts"]) for x in rows]
        ax.plot(t, b, label=DISPLAY.get(k, k), linewidth=1.6,
                color=PALETTE[ORDER.index(k) % len(PALETTE)])
    ax.set_yscale("symlog", linthresh=10)
    ax.legend(frameon=False, fontsize=8.5, ncol=3)
    style(ax, title="Queue occupancy over time (steady workload, seed 1)",
          xlabel="Time (s)", ylabel="Backlog (packets, symlog)")
    fig.tight_layout()
    p = os.path.join(outdir, "fig_backlog_timeseries.png")
    fig.savefig(p, dpi=150, facecolor="white")
    plt.close(fig)
    return p


def fig_acape_behaviour(runs, outdir):
    """What the controller actually did: parameters, regimes, eBPF telemetry."""
    cand = [r for r in runs if r.get("adaptive") and r.get("ebpf")]
    if not cand:
        cand = [r for r in runs if r.get("adaptive")]
    if not cand:
        return None
    r = cand[0]
    mf = os.path.join(r["_dir"], "acape_metrics_ctl.csv")
    if not os.path.exists(mf):
        return None
    rows = list(csv.DictReader(open(mf)))
    t = [float(x["t_s"]) for x in rows]

    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5))
    fig.patch.set_facecolor("white")

    ax = axes[0][0]
    ax.plot(t, [float(x["target_ms"]) for x in rows], color=PALETTE[0],
            linewidth=1.8, label="target (ms)")
    ax.axhline(5.0, color=PALETTE[3], linestyle="--", linewidth=1.2,
               label="static default 5 ms")
    ax.legend(frameon=False, fontsize=8.5)
    style(ax, title="(a) fq_codel target under control",
          xlabel="Time (s)", ylabel="target (ms)")

    ax = axes[0][1]
    ax.plot(t, [float(x["backlog_pkts"]) for x in rows], color=PALETTE[2],
            linewidth=1.5)
    style(ax, title="(b) Queue backlog", xlabel="Time (s)",
          ylabel="Backlog (pkts)")

    ax = axes[1][0]
    ax.plot(t, [int(x["active_flows"]) for x in rows], color=PALETTE[1],
            linewidth=1.5, label="active flows (eBPF)")
    ax.plot(t, [int(x["elephant_flows"]) for x in rows], color=PALETTE[5],
            linewidth=1.5, label="elephant flows")
    ax.legend(frameon=False, fontsize=8.5)
    style(ax, title="(c) eBPF flow telemetry",
          xlabel="Time (s)", ylabel="Flows")

    ax = axes[1][1]
    regs = ["NORMAL", "LIGHT", "MODERATE", "HEAVY"]
    ax.step(t, [regs.index(x["regime"]) for x in rows], where="post",
            color=PALETTE[4], linewidth=1.6)
    ax.set_yticks(range(4))
    ax.set_yticklabels(regs, fontsize=8.5)
    style(ax, title="(d) Congestion regime", xlabel="Time (s)")

    fig.suptitle(f"ACAPE controller behaviour — {r['label']}",
                 fontsize=12.5, color=TEXT)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    p = os.path.join(outdir, "fig_acape_behaviour.png")
    fig.savefig(p, dpi=150, facecolor="white")
    plt.close(fig)
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    ap.add_argument("--outdir", default="figures")
    a = ap.parse_args()
    runs = load(a.results)
    print(f"loaded {len(runs)} runs from {a.results}\n")
    if not runs:
        return
    os.makedirs(a.outdir, exist_ok=True)
    tables = write_tables(runs, a.outdir)
    made = []
    for wl, rows in tables.items():
        made.append(fig_comparison(rows, wl, a.outdir))
        made.append(fig_latency_throughput(rows, wl, a.outdir))
    made.append(fig_timeseries(runs, a.outdir))
    made.append(fig_acape_behaviour(runs, a.outdir))
    for p in made:
        if p:
            print("  wrote", p)


if __name__ == "__main__":
    main()
