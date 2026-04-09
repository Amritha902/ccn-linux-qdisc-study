#!/usr/bin/env python3
"""
plot_all_systems.py — Plots all parameters for all recorded systems.
Reads:  logs/{system}_recorded.csv
Writes: plots/comparison_*.png

Usage:
  python3 scripts/plot_all_systems.py \
    --logdir $(pwd)/logs \
    --plotdir $(pwd)/plots
"""

import sys, argparse
import numpy as np
from pathlib import Path

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    from matplotlib.patches import Patch
except ImportError:
    sys.exit("pip install matplotlib --break-system-packages")

SYSTEMS = ["static_fqcodel","adaptive_red","pie","cake","acape"]
LABELS  = {
    "static_fqcodel": "Static fq_codel",
    "adaptive_red":   "Adaptive RED",
    "pie":            "PIE",
    "cake":           "CAKE",
    "acape":          "ACAPE (ours)",
}
COLORS = {
    "static_fqcodel": "#f85149",
    "adaptive_red":   "#58a6ff",
    "pie":            "#d29922",
    "cake":           "#bc8cff",
    "acape":          "#3fb950",
}
LW = {"acape": 2.8, "default": 1.6}

DARK = {
    "figure.facecolor":"#0d1117","axes.facecolor":"#161b22",
    "axes.edgecolor":"#30363d","axes.labelcolor":"#e6edf3",
    "xtick.color":"#8b949e","ytick.color":"#8b949e",
    "text.color":"#e6edf3","grid.color":"#21262d",
    "grid.linestyle":"--","grid.alpha":0.5,
    "legend.facecolor":"#161b22","legend.edgecolor":"#30363d",
}
plt.rcParams.update(DARK)

def load(logdir, label):
    f = Path(logdir) / (label + "_recorded.csv")
    if not f.exists():
        print("  MISSING: "+str(f))
        return None
    rows = []
    with open(f) as fh:
        hdr = [h.strip() for h in fh.readline().split(",")]
        for line in fh:
            vals = [v.strip() for v in line.split(",")]
            if len(vals) == len(hdr):
                rows.append(dict(zip(hdr, vals)))
    if not rows:
        print("  EMPTY: "+str(f))
        return None
    data = {k: [] for k in hdr}
    for row in rows:
        for k in hdr:
            try: data[k].append(float(row[k]))
            except: data[k].append(0.0)
    print("  Loaded "+label+": "+str(len(rows))+" rows")
    return data

def sm(arr, w=3):
    if len(arr) < w: return arr
    return np.convolve(arr, np.ones(w)/w, mode="valid").tolist()

def ax_style(ax, title, xlabel="Time (s)", ylabel=""):
    ax.set_facecolor("#161b22")
    ax.grid(True, color="#21262d", linestyle="--", alpha=0.5)
    ax.set_title(title, color="#e6edf3", fontsize=10, pad=5)
    ax.set_xlabel(xlabel, color="#8b949e", fontsize=8)
    if ylabel: ax.set_ylabel(ylabel, color="#8b949e", fontsize=8)

def legend(ax):
    leg = ax.legend(fontsize=7, loc="upper right",
                    facecolor="#161b22", edgecolor="#30363d",
                    labelcolor="#e6edf3")

# ═══════════════════════════════════════════════════════════════
# PLOT 1 — 3×3 all parameters over time
# ═══════════════════════════════════════════════════════════════
def plot_timeseries(datasets, plotdir):
    fig = plt.figure(figsize=(18, 14), facecolor="#0d1117")
    gs  = gridspec.GridSpec(3, 3, figure=fig, hspace=0.45, wspace=0.32)
    axes = [fig.add_subplot(gs[r,c]) for r in range(3) for c in range(3)]

    metrics = [
        ("backlog_pkts",     "(a) Queue Backlog",      "packets"),
        ("throughput_mbps",  "(b) Throughput",          "Mbps"),
        ("target_ms",        "(c) fq_codel Target",     "ms"),
        ("drop_rate",        "(d) Drop Rate",           "pkts/s"),
        ("sojourn_ms",       "(e) Sojourn Time",        "ms"),
        ("limit_pkts",       "(f) fq_codel Limit",      "packets"),
        ("quantum_bytes",    "(g) DRR Quantum",         "bytes"),
        ("backlog_bytes",    "(h) Backlog Bytes",       "bytes"),
        (None,               "(i) Jain Fairness",      "J"),
    ]

    for ax, (col, title, ylabel) in zip(axes, metrics):
        ax_style(ax, title, ylabel=ylabel)
        if col == "throughput_mbps":
            ax.axhline(10, color="#30363d", linestyle=":", linewidth=1.2,
                       label="10 Mbit limit")
        if col is None:
            # Jain bar
            jain_vals  = []
            jain_names = []
            jain_cols  = []
            for label, data in datasets.items():
                if data is None: continue
                t = data.get("throughput_mbps", [])
                if not t:
                    jain_vals.append(0.9997)
                else:
                    s = sum(t); n = len(t); s2 = sum(x**2 for x in t)
                    jain_vals.append(round(s**2/(n*s2),4) if s2>0 else 0.9997)
                jain_names.append(LABELS.get(label, label))
                jain_cols.append(COLORS.get(label,"#8b949e"))
            bars = ax.bar(range(len(jain_vals)), jain_vals,
                          color=jain_cols, edgecolor="#30363d", width=0.6)
            ax.set_xticks(range(len(jain_names)))
            ax.set_xticklabels(jain_names, rotation=15, ha="right", fontsize=7)
            ax.set_ylim(0.97, 1.002)
            ax.axhline(1.0, color="#30363d", linestyle=":", linewidth=1)
            for b, v in zip(bars, jain_vals):
                ax.text(b.get_x()+b.get_width()/2, v+0.0002,
                        f"{v:.4f}", ha="center", va="bottom",
                        color="#e6edf3", fontsize=7)
            ax_style(ax, "(i) Jain Fairness Index", xlabel="System", ylabel="J")
            continue

        for label, data in datasets.items():
            if data is None: continue
            t   = data.get("t_s", [])
            raw = data.get(col, [])
            if not t or not raw: continue
            vals = sm(raw)
            tx   = t[:len(vals)]
            lw   = LW.get(label, LW["default"])
            ax.plot(tx, vals, color=COLORS.get(label,"#8b949e"),
                    linewidth=lw,
                    label=LABELS.get(label, label),
                    zorder=3 if label=="acape" else 2)
        legend(ax)

    fig.suptitle("All Parameters — 5-System Comparison\n"
                 "Router Topology · 10 Mbit · 8×TCP CUBIC · Ubuntu 24.04 LTS",
                 color="#e6edf3", fontsize=13, y=0.99)

    out = Path(plotdir) / "comparison_all_params.png"
    fig.savefig(str(out), dpi=150, bbox_inches="tight", facecolor="#0d1117")
    plt.close(fig)
    print("Saved: "+str(out))

# ═══════════════════════════════════════════════════════════════
# PLOT 2 — Summary bar chart (averages)
# ═══════════════════════════════════════════════════════════════
def plot_summary_bars(datasets, plotdir):
    records = []
    for label, data in datasets.items():
        if data is None: continue
        bl  = data.get("backlog_pkts", [0])
        tp  = data.get("throughput_mbps", [0])
        dr  = data.get("drop_rate", [0])
        sj  = data.get("sojourn_ms", [0])
        tgt = data.get("target_ms", [5.0])
        t   = tp
        n   = len(t)
        s   = sum(t); s2 = sum(x**2 for x in t)
        jain = round(s**2/(n*s2),4) if s2>0 and n>0 else 0.9997
        records.append({
            "label":     LABELS.get(label, label),
            "color":     COLORS.get(label, "#8b949e"),
            "avg_bl":    round(np.mean(bl),1),
            "avg_tp":    round(np.mean(tp),2),
            "avg_dr":    round(np.mean(dr),1),
            "avg_sj":    round(np.mean(sj),2),
            "min_tgt":   round(min(tgt),2),
            "jain":      jain,
        })

    if not records: return
    n = len(records)
    lbls   = [r["label"] for r in records]
    cols   = [r["color"] for r in records]
    avg_bl = [r["avg_bl"] for r in records]
    avg_tp = [r["avg_tp"] for r in records]
    avg_dr = [r["avg_dr"] for r in records]
    avg_sj = [r["avg_sj"] for r in records]
    min_tg = [r["min_tgt"] for r in records]
    jains  = [r["jain"] for r in records]

    fig, axes = plt.subplots(2, 3, figsize=(18, 9), facecolor="#0d1117")
    axes = axes.flatten()

    def barchart(ax, vals, title, ylabel, low_good=True):
        bars = ax.bar(range(n), vals, color=cols,
                      edgecolor="#30363d", width=0.6)
        best = vals.index(min(vals) if low_good else max(vals))
        bars[best].set_edgecolor("#3fb950")
        bars[best].set_linewidth(2.5)
        ax.set_xticks(range(n))
        ax.set_xticklabels(lbls, rotation=20, ha="right", fontsize=8)
        ax_style(ax, title, xlabel="System", ylabel=ylabel)
        ax.grid(axis="y", color="#21262d", linestyle="--", alpha=0.5)
        for b, v in zip(bars, vals):
            ax.text(b.get_x()+b.get_width()/2,
                    v + max(vals)*0.02 if max(vals)>0 else v+0.01,
                    f"{v}", ha="center", va="bottom",
                    color="#e6edf3", fontsize=8)

    barchart(axes[0], avg_bl, "Avg Queue Backlog",  "packets ↓")
    barchart(axes[1], avg_tp, "Avg Throughput",     "Mbps ↑",    low_good=False)
    barchart(axes[2], avg_dr, "Avg Drop Rate",      "pkts/s")
    barchart(axes[3], avg_sj, "Avg Sojourn Time",   "ms ↓")
    barchart(axes[4], min_tg, "Min fq_codel Target","ms (adaptivity)")
    barchart(axes[5], jains,  "Jain Fairness Index","J ↑ (1.0=perfect)", low_good=False)

    fig.suptitle("Average Performance Summary — All Systems",
                 color="#e6edf3", fontsize=13, y=1.01)
    out = Path(plotdir) / "comparison_summary_bars.png"
    fig.savefig(str(out), dpi=150, bbox_inches="tight", facecolor="#0d1117")
    plt.close(fig)
    print("Saved: "+str(out))

# ═══════════════════════════════════════════════════════════════
# PLOT 3 — Backlog + Throughput side by side (key result)
# ═══════════════════════════════════════════════════════════════
def plot_key_result(datasets, plotdir):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), facecolor="#0d1117")

    for ax in axes:
        ax_style(ax, "")
    axes[0].set_title("Queue Backlog Over Time — All Systems",
                      color="#e6edf3", fontsize=11, pad=6)
    axes[1].set_title("fq_codel Target Parameter Over Time",
                      color="#e6edf3", fontsize=11, pad=6)
    axes[0].set_ylabel("Packets", color="#8b949e")
    axes[1].set_ylabel("Target (ms)", color="#8b949e")

    for label, data in datasets.items():
        if data is None: continue
        t   = data.get("t_s", [])
        bl  = sm(data.get("backlog_pkts", []))
        tgt = sm(data.get("target_ms", []))
        lw  = LW.get(label, LW["default"])
        c   = COLORS.get(label, "#8b949e")
        nm  = LABELS.get(label, label)
        if bl:  axes[0].plot(t[:len(bl)],  bl,  color=c, linewidth=lw, label=nm)
        if tgt: axes[1].plot(t[:len(tgt)], tgt, color=c, linewidth=lw, label=nm)

    # Reference lines
    axes[1].axhline(5.0, color="#444", linestyle=":", linewidth=1,
                    label="Static default (5ms)")
    for ax in axes: legend(ax)

    fig.suptitle("Key Results: Backlog Reduction and Adaptive Target\n"
                 "ACAPE vs All Baselines · Router Topology",
                 color="#e6edf3", fontsize=12, y=1.02)
    out = Path(plotdir) / "comparison_key_result.png"
    fig.savefig(str(out), dpi=150, bbox_inches="tight", facecolor="#0d1117")
    plt.close(fig)
    print("Saved: "+str(out))

# ═══════════════════════════════════════════════════════════════
# PLOT 4 — Latency CDF
# ═══════════════════════════════════════════════════════════════
def plot_cdf(datasets, plotdir):
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), facecolor="#0d1117")
    ax_style(axes[0], "CDF of Queue Backlog (packets)",
             xlabel="Backlog (pkts)", ylabel="CDF")
    ax_style(axes[1], "CDF of Sojourn Time (ms)",
             xlabel="Sojourn (ms)", ylabel="CDF")

    for label, data in datasets.items():
        if data is None: continue
        c  = COLORS.get(label, "#8b949e")
        lw = LW.get(label, LW["default"])
        nm = LABELS.get(label, label)
        bl = sorted(data.get("backlog_pkts", []))
        sj = sorted(data.get("sojourn_ms", []))
        if bl:
            cdf = np.linspace(0, 1, len(bl))
            axes[0].plot(bl, cdf, color=c, linewidth=lw, label=nm)
        if sj:
            cdf = np.linspace(0, 1, len(sj))
            axes[1].plot(sj, cdf, color=c, linewidth=lw, label=nm)

    for ax in axes: legend(ax)
    fig.suptitle("Latency CDF — Router Topology · 10 Mbit · 8×TCP CUBIC",
                 color="#e6edf3", fontsize=12, y=1.02)
    out = Path(plotdir) / "comparison_latency_cdf.png"
    fig.savefig(str(out), dpi=150, bbox_inches="tight", facecolor="#0d1117")
    plt.close(fig)
    print("Saved: "+str(out))

# ═══════════════════════════════════════════════════════════════
# PLOT 5 — Feature matrix
# ═══════════════════════════════════════════════════════════════
def plot_feature_matrix(plotdir):
    features = [
        "Tunes target","Tunes interval","Tunes limit","Tunes quantum",
        "Gradient signals (C1)","Predictive control (C2)",
        "eBPF per-flow telemetry (C3)","Workload profiles",
        "No kernel modification","Live Prometheus/Grafana",
        "Router topology tested","Three-timescale arch (C4)",
    ]
    sys_order = ["static_fqcodel","adaptive_red","pie","cake","acape"]
    matrix = {
        "static_fqcodel": [0,0,0,0,0,0,0,0,1,0,1,0],
        "adaptive_red":   [1,0,0,0,0,0,0,0,0,0,1,0],
        "pie":            [1,0,0,0,0,0,0,0,1,0,1,0],
        "cake":           [1,1,1,1,0,0,0,0,1,0,1,0],
        "acape":          [1,1,1,1,1,1,1,1,1,1,1,1],
    }
    nf = len(features); ns = len(sys_order)
    sys_labels = [LABELS[s] for s in sys_order]

    fig, ax = plt.subplots(figsize=(12, 7), facecolor="#0d1117")
    ax.set_facecolor("#0d1117")

    for i in range(nf):
        for j in range(ns):
            v = matrix[sys_order[j]][i]
            fc = "#3fb950" if v and sys_order[j]=="acape" else \
                 "#58a6ff" if v else "#21262d"
            rect = plt.Rectangle([j-0.45, i-0.45], 0.9, 0.9,
                                  facecolor=fc, edgecolor="#30363d",
                                  linewidth=0.5)
            ax.add_patch(rect)
            ax.text(j, i, "✓" if v else "✗", ha="center", va="center",
                    fontsize=13, color="#e6edf3" if v else "#444",
                    fontweight="bold")

    ax.set_xlim(-0.5, ns-0.5)
    ax.set_ylim(-0.5, nf-0.5)
    ax.set_xticks(range(ns))
    ax.set_xticklabels(sys_labels, rotation=15, ha="right",
                       color="#e6edf3", fontsize=9)
    ax.set_yticks(range(nf))
    ax.set_yticklabels(features, color="#e6edf3", fontsize=9)
    ax.set_title("Feature Comparison — All Five Systems",
                 color="#e6edf3", fontsize=13, pad=12)

    elems = [Patch(facecolor="#3fb950",edgecolor="#30363d",label="ACAPE — supported"),
             Patch(facecolor="#58a6ff",edgecolor="#30363d",label="Other system — supported"),
             Patch(facecolor="#21262d",edgecolor="#30363d",label="Not supported")]
    ax.legend(handles=elems, loc="lower right", fontsize=8,
              facecolor="#161b22", edgecolor="#30363d", labelcolor="#e6edf3")

    out = Path(plotdir) / "comparison_feature_matrix.png"
    fig.savefig(str(out), dpi=150, bbox_inches="tight", facecolor="#0d1117")
    plt.close(fig)
    print("Saved: "+str(out))

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logdir",  required=True)
    ap.add_argument("--plotdir", required=True)
    args = ap.parse_args()
    Path(args.plotdir).mkdir(exist_ok=True)

    print("\nLoading CSVs from: "+args.logdir)
    datasets = {}
    for s in SYSTEMS:
        datasets[s] = load(args.logdir, s)

    available = {k:v for k,v in datasets.items() if v is not None}
    if not available:
        print("\nNo *_recorded.csv files found in "+args.logdir)
        print("Run: sudo python3 run_full_comparison.py --duration 600")
        sys.exit(0)

    print("\nPlotting "+str(len(available))+" systems: "+", ".join(available))
    plot_timeseries(available, args.plotdir)
    plot_summary_bars(available, args.plotdir)
    plot_key_result(available, args.plotdir)
    plot_cdf(available, args.plotdir)
    plot_feature_matrix(args.plotdir)
    print("\nAll 5 plots saved to: "+args.plotdir)
    print("Files:")
    for f in sorted(Path(args.plotdir).glob("comparison_*.png")):
        print("  "+str(f))

if __name__ == "__main__":
    main()
