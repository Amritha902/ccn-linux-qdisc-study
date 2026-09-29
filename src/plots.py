#!/usr/bin/env python3
"""Full plot set, with explicit and stable file naming.

Naming convention — every file says what it is without opening it:

  fig01_latency_tail_<workload>.png        tail latency, all systems
  fig02_latency_sparse_vs_bulk_<wl>.png    probe flow vs bulk flow RTT
  fig03_throughput_<wl>.png                goodput
  fig04_backlog_<wl>.png                   queue occupancy
  fig05_fairness_<wl>.png                  Jain's index
  fig06_droprate_<wl>.png                  drop rate and retransmissions
  fig07_tradeoff_<wl>.png                  latency vs throughput
  fig08_allparams_<wl>.png                 every metric, normalised heatmap
  fig09_seeds_<metric>_<wl>.png            per-seed scatter (seed variation)
  fig10_timeseries_backlog_<wl>.png        backlog over time
  fig11_timeseries_rtt_<wl>.png            RTT over time
  fig12_controller_behaviour.png           what ACAPE actually did
  fig13_sham_control.png                   controller CPU cost isolated

Per-run figures are produced by src/make_gallery.py as
  run<NN>_<label>.png
"""
import argparse, csv, glob, json, math, os, re, statistics as st
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

PALETTE = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2",
           "#B279A2", "#EECA3B", "#9D755D", "#BAB0AC", "#7F7F7F"]
GRID, TEXT = "#D9D9D9", "#2B2B2B"

DISPLAY = {
    "pfifo": "pfifo\n(no AQM)", "sfq": "SFQ", "red": "RED\n(adaptive)",
    "codel": "CoDel", "pie": "PIE", "fq_pie": "FQ-PIE", "cake": "CAKE",
    "fq_codel": "fq_codel\n(static)", "fq_codel_sham": "fq_codel\n+sham ctl",
    "fq_codel_acape": "fq_codel\n+ACAPE",
}
ORDER = ["pfifo", "sfq", "red", "codel", "pie", "fq_pie", "cake",
         "fq_codel", "fq_codel_sham", "fq_codel_acape"]


def style(ax, title="", xlabel="", ylabel=""):
    if title:
        ax.set_title(title, fontsize=11, color=TEXT, pad=8)
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
    xs = [x for x in xs if x is not None]
    if not xs:
        return None, 0.0, 0
    if len(xs) == 1:
        return xs[0], 0.0, 1
    t = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571,
         7: 2.447, 8: 2.365, 9: 2.306, 10: 2.262}.get(len(xs), 1.96)
    return st.fmean(xs), t * st.stdev(xs) / math.sqrt(len(xs)), len(xs)


def key(r):
    if r.get("adaptive"):
        return f"{r['aqm']}_acape"
    if r.get("sham"):
        return f"{r['aqm']}_sham"
    return r["aqm"]


def load(resdir):
    runs = []
    for f in sorted(glob.glob(os.path.join(resdir, "*", "summary.json"))):
        try:
            d = json.load(open(f))
            d["_dir"] = os.path.dirname(f)
            runs.append(d)
        except Exception:
            pass
    return runs


def grouped(runs, wl):
    by = defaultdict(list)
    for r in runs:
        if r.get("workload") == wl:
            by[key(r)].append(r)
    return [(k, by[k]) for k in ORDER if k in by]


def colour(k):
    return PALETTE[ORDER.index(k) % len(PALETTE)]


def bars(ax, groups, metric, ylabel, logy=False, annotate=True, fmt="%.0f"):
    labels, vals, errs, cols = [], [], [], []
    for k, g in groups:
        m, h, _ = ci95([x.get(metric) for x in g])
        if m is None:
            continue
        labels.append(DISPLAY.get(k, k)); vals.append(m)
        errs.append(h); cols.append(colour(k))
    x = np.arange(len(vals))
    ax.bar(x, vals, yerr=errs, capsize=3, color=cols,
           edgecolor="white", linewidth=0.8)
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8)
    if logy:
        ax.set_yscale("log")
    if annotate:
        for i, v in enumerate(vals):
            ax.text(i, v * (1.18 if logy else 1.0) +
                    (0 if logy else (max(vals) * 0.02)),
                    fmt % v, ha="center", fontsize=8, color=TEXT)
    style(ax, ylabel=ylabel)
    return vals


def save(fig, outdir, name):
    p = os.path.join(outdir, name)
    fig.savefig(p, dpi=150, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"  {name}")
    return p


SUB = "10 Mbit bottleneck · 8 TCP CUBIC flows · 20 ms base RTT · mean ± 95% CI over 3 seeds"


# ── fig01: tail latency ───────────────────────────────────────────────────
def fig01(runs, wl, od):
    g = grouped(runs, wl)
    if not g:
        return
    fig, ax = plt.subplots(figsize=(10, 5.5)); fig.patch.set_facecolor("white")
    v = bars(ax, g, "sparse_rtt_p95_ms", "p95 RTT (ms, log scale)",
             logy=True, fmt="%.0f")
    if v:
        ax.text(0.98, 0.95, f"{max(v)/min(v):.0f}x spread",
                transform=ax.transAxes, ha="right", fontsize=11,
                fontweight="bold", color=TEXT)
    fig.suptitle(f"Tail latency (sparse probe flow) — {wl} workload\n{SUB}",
                 fontsize=12, color=TEXT)
    save(fig, od, f"fig01_latency_tail_{wl}.png")


# ── fig02: sparse vs bulk latency ─────────────────────────────────────────
def fig02(runs, wl, od):
    g = grouped(runs, wl)
    if not g:
        return
    fig, ax = plt.subplots(figsize=(11, 5.8)); fig.patch.set_facecolor("white")
    labels, sp, spe, bl, ble = [], [], [], [], []
    for k, grp in g:
        a, ae, _ = ci95([x.get("sparse_rtt_mean_ms") for x in grp])
        b, be, _ = ci95([x.get("bulk_rtt_mean_ms") for x in grp])
        if a is None or b is None:
            continue
        labels.append(DISPLAY.get(k, k)); sp.append(a); spe.append(ae)
        bl.append(b); ble.append(be)
    x = np.arange(len(labels)); w = 0.38
    ax.bar(x - w/2, sp, w, yerr=spe, capsize=3, color=PALETTE[0],
           label="sparse probe flow (ICMP)", edgecolor="white")
    ax.bar(x + w/2, bl, w, yerr=ble, capsize=3, color=PALETTE[3],
           label="bulk TCP flows (in-band)", edgecolor="white")
    ax.set_yscale("log")
    ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8)
    ax.legend(frameon=False, fontsize=9.5)
    style(ax, ylabel="Mean RTT (ms, log scale)")
    fig.suptitle(f"Sparse probe vs bulk flow latency — {wl} workload\n"
                 "fq_codel's new-flow heuristic privileges the probe, so the two differ; "
                 "quoting only the probe overstates the benefit for bulk traffic",
                 fontsize=11.5, color=TEXT)
    save(fig, od, f"fig02_latency_sparse_vs_bulk_{wl}.png")


# ── fig03-06: single-metric panels ────────────────────────────────────────
def _single(runs, wl, od, metric, ylabel, name, title, logy=False, fmt="%.2f",
            zoom=False):
    g = grouped(runs, wl)
    if not g:
        return
    fig, ax = plt.subplots(figsize=(10, 5.2)); fig.patch.set_facecolor("white")
    v = bars(ax, g, metric, ylabel, logy=logy, fmt=fmt)
    if zoom and v:
        lo, hi = min(v), max(v)
        pad = max((hi - lo) * 2.0, abs(hi) * 0.004)
        ax.set_ylim(lo - pad, hi + pad)
        ax.text(0.5, 0.04, f"axis zoomed — all values within "
                           f"{100*(hi-lo)/max(st.fmean(v),1e-9):.1f}%",
                transform=ax.transAxes, ha="center", fontsize=9, color=TEXT)
    fig.suptitle(f"{title} — {wl} workload\n{SUB}", fontsize=12, color=TEXT)
    save(fig, od, name)


def fig03(runs, wl, od):
    _single(runs, wl, od, "throughput_mbps", "Goodput (Mbps)",
            f"fig03_throughput_{wl}.png", "Goodput", fmt="%.2f", zoom=True)


def fig04(runs, wl, od):
    _single(runs, wl, od, "backlog_mean_pkts", "Mean backlog (pkts, log)",
            f"fig04_backlog_{wl}.png", "Queue occupancy", logy=True, fmt="%.0f")


def fig05(runs, wl, od):
    _single(runs, wl, od, "jain", "Jain's fairness index",
            f"fig05_fairness_{wl}.png", "Flow fairness", fmt="%.4f", zoom=True)


def fig06(runs, wl, od):
    g = grouped(runs, wl)
    if not g:
        return
    fig, axes = plt.subplots(1, 2, figsize=(13, 5)); fig.patch.set_facecolor("white")
    bars(axes[0], g, "drop_rate_mean_per_s", "Mean drop rate (/s)", fmt="%.0f")
    axes[0].set_title("(a) Drops at the qdisc", fontsize=11, color=TEXT)
    bars(axes[1], g, "retransmits", "TCP retransmissions", fmt="%.0f")
    axes[1].set_title("(b) End-to-end retransmissions", fontsize=11, color=TEXT)
    fig.suptitle(f"Loss behaviour — {wl} workload\n{SUB}", fontsize=12, color=TEXT)
    save(fig, od, f"fig06_droprate_{wl}.png")


# ── fig07: trade-off ──────────────────────────────────────────────────────
def fig07(runs, wl, od):
    g = grouped(runs, wl)
    if not g:
        return
    fig, ax = plt.subplots(figsize=(9, 6)); fig.patch.set_facecolor("white")
    for k, grp in g:
        x, xe, _ = ci95([r.get("throughput_mbps") for r in grp])
        y, ye, _ = ci95([r.get("sparse_rtt_p95_ms") for r in grp])
        if x is None or y is None:
            continue
        ax.errorbar(x, y, xerr=xe, yerr=ye, fmt="o", color=colour(k),
                    markersize=10, capsize=3, markeredgecolor="white",
                    markeredgewidth=1.3)
        ax.annotate(DISPLAY.get(k, k).replace("\n", " "), (x, y),
                    textcoords="offset points", xytext=(9, 5),
                    fontsize=8.5, color=TEXT)
    ax.set_yscale("log")
    style(ax, xlabel="Goodput (Mbps)", ylabel="p95 RTT (ms, log scale)")
    fig.suptitle(f"Latency–throughput trade-off — {wl} workload\n"
                 "down and to the right is better", fontsize=12, color=TEXT)
    save(fig, od, f"fig07_tradeoff_{wl}.png")


# ── fig08: all-parameter heatmap ──────────────────────────────────────────
HEAT = [("sparse_rtt_mean_ms", "probe RTT mean", True),
        ("sparse_rtt_p95_ms", "probe RTT p95", True),
        ("sparse_rtt_p99_ms", "probe RTT p99", True),
        ("sparse_rtt_jitter_ms", "probe jitter", True),
        ("bulk_rtt_mean_ms", "bulk RTT mean", True),
        ("bulk_rtt_p95_ms", "bulk RTT p95", True),
        ("queue_delay_mean_ms", "queue delay mean", True),
        ("backlog_mean_pkts", "backlog mean", True),
        ("backlog_p95_pkts", "backlog p95", True),
        ("drop_rate_mean_per_s", "drop rate", True),
        ("retransmits", "retransmissions", True),
        ("throughput_mbps", "goodput", False),
        ("jain", "fairness", False)]


def fig08(runs, wl, od):
    g = grouped(runs, wl)
    if not g:
        return
    names = [DISPLAY.get(k, k).replace("\n", " ") for k, _ in g]
    M, raw = [], []
    for metric, _, lower_better in HEAT:
        row = [ci95([r.get(metric) for r in grp])[0] for _, grp in g]
        raw.append(row)
        vals = [v for v in row if v is not None]
        if not vals:
            M.append([0.5] * len(row)); continue
        lo, hi = min(vals), max(vals)
        rng = (hi - lo) or 1.0
        norm = [0.5 if v is None else (v - lo) / rng for v in row]
        if not lower_better:
            norm = [1 - n for n in norm]
        M.append(norm)
    M = np.array(M)
    fig, ax = plt.subplots(figsize=(1.15 * len(names) + 4, 0.52 * len(HEAT) + 2.4))
    fig.patch.set_facecolor("white")
    im = ax.imshow(M, cmap="RdYlGn_r", aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=35, ha="right", fontsize=8.5)
    ax.set_yticks(range(len(HEAT)))
    ax.set_yticklabels([h[1] for h in HEAT], fontsize=9)
    for i in range(len(HEAT)):
        for j in range(len(names)):
            v = raw[i][j]
            if v is None:
                continue
            txt = f"{v:.3g}" if abs(v) < 1000 else f"{v:.0f}"
            ax.text(j, i, txt, ha="center", va="center", fontsize=7.5,
                    color="black" if 0.25 < M[i, j] < 0.75 else "white")
    cb = fig.colorbar(im, ax=ax, shrink=0.65)
    cb.set_ticks([0.03, 0.97]); cb.set_ticklabels(["best", "worst"])
    ax.set_title(f"All measured parameters — {wl} workload\n"
                 "colour normalised per row (green = best); cell values are the measured means",
                 fontsize=11.5, color=TEXT, pad=12)
    save(fig, od, f"fig08_allparams_{wl}.png")


# ── fig09: per-seed scatter — shows seed-to-seed variation explicitly ─────
SEED_METRICS = [("sparse_rtt_p95_ms", "p95 RTT, probe flow (ms)", True),
                ("bulk_rtt_mean_ms", "mean RTT, bulk flows (ms)", True),
                ("throughput_mbps", "goodput (Mbps)", False),
                ("backlog_mean_pkts", "mean backlog (pkts)", True),
                ("jain", "Jain's fairness index", False),
                ("retransmits", "TCP retransmissions", False)]


def fig09(runs, wl, od):
    """One figure per metric: every individual seed drawn, plus the mean.

    Aggregated bars hide whether a difference is consistent across seeds or
    driven by one outlier. These show each run.
    """
    g = grouped(runs, wl)
    if not g:
        return
    for metric, label, logy in SEED_METRICS:
        fig, ax = plt.subplots(figsize=(10.5, 5.4)); fig.patch.set_facecolor("white")
        any_pt = False
        for i, (k, grp) in enumerate(g):
            pts = [(r.get("seed"), r.get(metric)) for r in grp
                   if r.get(metric) is not None]
            if not pts:
                continue
            any_pt = True
            ys = [p[1] for p in pts]
            jitter = np.linspace(-0.17, 0.17, len(pts)) if len(pts) > 1 else [0]
            for (seed, y), dx in zip(pts, jitter):
                ax.scatter(i + dx, y, s=64, color=colour(k), zorder=3,
                           edgecolor="white", linewidth=1.1)
                ax.annotate(f"s{seed}", (i + dx, y), textcoords="offset points",
                            xytext=(0, 8), ha="center", fontsize=7, color=TEXT)
            m = st.fmean(ys)
            ax.hlines(m, i - 0.32, i + 0.32, color=TEXT, linewidth=2, zorder=4)
            if len(ys) > 1:
                ax.vlines(i, min(ys), max(ys), color=colour(k),
                          linewidth=1.2, alpha=0.5, zorder=2)
        if not any_pt:
            plt.close(fig); continue
        ax.set_xticks(range(len(g)))
        ax.set_xticklabels([DISPLAY.get(k, k) for k, _ in g], fontsize=8)
        if logy and metric != "jain":
            ax.set_yscale("log")
        style(ax, ylabel=label)
        fig.suptitle(f"Per-seed values: {label} — {wl} workload\n"
                     "every individual run shown; black bar = mean across seeds",
                     fontsize=12, color=TEXT)
        save(fig, od, f"fig09_seeds_{metric}_{wl}.png")


# ── fig10/11: time series ─────────────────────────────────────────────────
def fig10(runs, wl, od):
    sel = {}
    for r in runs:
        if r.get("workload") == wl and r.get("seed") == 1:
            sel[key(r)] = r
    if not sel:
        return
    fig, ax = plt.subplots(figsize=(11, 5.6)); fig.patch.set_facecolor("white")
    for k in ORDER:
        if k not in sel:
            continue
        f = os.path.join(sel[k]["_dir"], "qdisc_timeseries.csv")
        if not os.path.exists(f):
            continue
        rows = list(csv.DictReader(open(f)))[1:]
        if not rows:
            continue
        ax.plot([float(x["t_s"]) for x in rows],
                [float(x["backlog_pkts"]) for x in rows],
                label=DISPLAY.get(k, k).replace("\n", " "),
                linewidth=1.5, color=colour(k))
    ax.set_yscale("symlog", linthresh=10)
    ax.legend(frameon=False, fontsize=8.5, ncol=3)
    style(ax, xlabel="Time (s)", ylabel="Backlog (packets, symlog)")
    fig.suptitle(f"Queue occupancy over time — {wl} workload, seed 1",
                 fontsize=12, color=TEXT)
    save(fig, od, f"fig10_timeseries_backlog_{wl}.png")


PING_RE = re.compile(r"time=([\d.]+)\s*ms")


def fig11(runs, wl, od):
    sel = {}
    for r in runs:
        if r.get("workload") == wl and r.get("seed") == 1:
            sel[key(r)] = r
    if not sel:
        return
    fig, ax = plt.subplots(figsize=(11, 5.6)); fig.patch.set_facecolor("white")
    for k in ORDER:
        if k not in sel:
            continue
        f = os.path.join(sel[k]["_dir"], "ping.log")
        if not os.path.exists(f):
            continue
        v = [float(m) for m in PING_RE.findall(open(f).read())]
        if not v:
            continue
        t = np.linspace(0, len(v) * 0.05, len(v))
        ax.plot(t, v, label=DISPLAY.get(k, k).replace("\n", " "),
                linewidth=0.9, color=colour(k), alpha=0.85)
    ax.set_yscale("log")
    ax.legend(frameon=False, fontsize=8.5, ncol=3)
    style(ax, xlabel="Time (s)", ylabel="RTT (ms, log scale)")
    fig.suptitle(f"Measured RTT over time (20 Hz probe) — {wl} workload, seed 1",
                 fontsize=12, color=TEXT)
    save(fig, od, f"fig11_timeseries_rtt_{wl}.png")


# ── fig12: what the controller actually did ───────────────────────────────
def fig12(runs, od):
    cand = [r for r in runs if r.get("adaptive") and r.get("ebpf")] or \
           [r for r in runs if r.get("adaptive")]
    if not cand:
        return
    r = cand[0]
    mf = os.path.join(r["_dir"], "acape_metrics_ctl.csv")
    if not os.path.exists(mf):
        return
    rows = list(csv.DictReader(open(mf)))
    if not rows:
        return
    t = [float(x["t_s"]) for x in rows]
    fig, ax = plt.subplots(2, 2, figsize=(12, 7.5)); fig.patch.set_facecolor("white")

    ax[0][0].plot(t, [float(x["target_ms"]) for x in rows], color=PALETTE[0], lw=1.8)
    ax[0][0].axhline(5.0, color=PALETTE[3], ls="--", lw=1.2, label="static default 5 ms")
    ax[0][0].legend(frameon=False, fontsize=8.5)
    style(ax[0][0], "(a) fq_codel target under control", "Time (s)", "target (ms)")

    ax[0][1].plot(t, [float(x["backlog_pkts"]) for x in rows], color=PALETTE[2], lw=1.4)
    style(ax[0][1], "(b) Queue backlog", "Time (s)", "packets")

    ax[1][0].plot(t, [int(x["active_flows"]) for x in rows], color=PALETTE[1],
                  lw=1.4, label="active flows")
    ax[1][0].plot(t, [int(x["elephant_flows"]) for x in rows], color=PALETTE[5],
                  lw=1.4, label="elephant flows")
    ax[1][0].legend(frameon=False, fontsize=8.5)
    style(ax[1][0], "(c) eBPF flow telemetry", "Time (s)", "flows")

    regs = ["NORMAL", "LIGHT", "MODERATE", "HEAVY"]
    ax[1][1].step(t, [regs.index(x["regime"]) for x in rows], where="post",
                  color=PALETTE[4], lw=1.6)
    ax[1][1].set_yticks(range(4)); ax[1][1].set_yticklabels(regs, fontsize=8.5)
    style(ax[1][1], "(d) Congestion regime", "Time (s)")

    fig.suptitle(f"ACAPE controller behaviour — {r['label']}", fontsize=12.5, color=TEXT)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    save(fig, od, "fig12_controller_behaviour.png")


# ── fig13: sham control — is a difference real or just controller CPU? ────
def fig13(runs, wl, od):
    want = ["fq_codel", "fq_codel_sham", "fq_codel_acape"]
    g = [(k, grp) for k, grp in grouped(runs, wl) if k in want]
    if len(g) < 2:
        return
    metrics = [("sparse_rtt_mean_ms", "probe RTT mean (ms)"),
               ("bulk_rtt_mean_ms", "bulk RTT mean (ms)"),
               ("backlog_mean_pkts", "mean backlog (pkts)"),
               ("throughput_mbps", "goodput (Mbps)")]
    fig, axes = plt.subplots(1, 4, figsize=(16, 4.6)); fig.patch.set_facecolor("white")
    for ax, (metric, lbl) in zip(axes, metrics):
        vals, errs, labels, cols = [], [], [], []
        for k, grp in g:
            m, h, _ = ci95([r.get(metric) for r in grp])
            if m is None:
                continue
            vals.append(m); errs.append(h)
            labels.append(DISPLAY.get(k, k)); cols.append(colour(k))
        x = np.arange(len(vals))
        ax.bar(x, vals, yerr=errs, capsize=3, color=cols, edgecolor="white")
        ax.set_xticks(x); ax.set_xticklabels(labels, fontsize=8)
        if vals:
            lo, hi = min(vals), max(vals)
            pad = max((hi - lo) * 2.2, hi * 0.01)
            ax.set_ylim(max(0, lo - pad), hi + pad)
            for i, v in enumerate(vals):
                ax.text(i, v, f"{v:.2f}", ha="center", va="bottom",
                        fontsize=8, color=TEXT)
        style(ax, ylabel=lbl)
    fig.suptitle(
        f"Sham-controller control condition — {wl} workload\n"
        "'sham' runs the controller at the same polling cadence but applies no change. "
        "static vs sham isolates the controller's CPU cost; sham vs ACAPE isolates its decisions.",
        fontsize=11.5, color=TEXT)
    fig.tight_layout(rect=[0, 0, 1, 0.88])
    save(fig, od, f"fig13_sham_control_{wl}.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    ap.add_argument("--outdir", default="figures/comparison")
    a = ap.parse_args()
    runs = load(a.results)
    os.makedirs(a.outdir, exist_ok=True)
    print(f"loaded {len(runs)} runs -> {a.outdir}")
    for wl in ("steady", "staged"):
        if not grouped(runs, wl):
            continue
        for fn in (fig01, fig02, fig03, fig04, fig05, fig06,
                   fig07, fig08, fig09, fig10, fig11, fig13):
            try:
                fn(runs, wl, a.outdir)
            except Exception as e:
                print(f"  ! {fn.__name__} ({wl}): {e}")
    try:
        fig12(runs, a.outdir)
    except Exception as e:
        print(f"  ! fig12: {e}")


if __name__ == "__main__":
    main()
