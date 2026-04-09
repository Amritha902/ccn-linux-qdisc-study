#!/usr/bin/env python3
"""
plot_comparison_final.py
Reads logs/*_recorded.csv and generates one PNG per parameter.
Run: python3 scripts/plot_comparison_final.py --logdir logs --plotdir plots
"""
import argparse, sys
import numpy as np
from pathlib import Path

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "figure.facecolor":"white","axes.facecolor":"#F8FBFD",
        "axes.edgecolor":"#CCCCCC","axes.labelcolor":"#333333",
        "xtick.color":"#555555","ytick.color":"#555555",
        "text.color":"#222222","grid.color":"#DDDDDD",
        "grid.linestyle":"--","grid.alpha":0.7,
        "legend.facecolor":"white","legend.edgecolor":"#CCCCCC",
        "font.family":"DejaVu Sans",
    })
except ImportError:
    sys.exit("pip install matplotlib --break-system-packages")

SYSTEMS = ["static_fqcodel","adaptive_red","pie","acape"]
LABELS  = {
    "static_fqcodel":"Static fq_codel",
    "adaptive_red":  "Adaptive RED",
    "pie":           "PIE",
    "acape":         "ACAPE (ours)",
}
COLORS = {
    "static_fqcodel":"#E63946",
    "adaptive_red":  "#0096C7",
    "pie":           "#FFB703",
    "acape":         "#2DC653",
}
LW = {"acape":3.0,"default":1.8}

def load(logdir, label):
    f = Path(logdir)/(label+"_recorded.csv")
    if not f.exists(): return None
    rows=[]
    with open(f) as fh:
        hdr=[h.strip() for h in fh.readline().split(",")]
        for line in fh:
            v=[x.strip() for x in line.split(",")]
            if len(v)==len(hdr):
                rows.append({k:float(v[i]) for i,k in enumerate(hdr)
                              if v[i].replace(".","").replace("-","").isdigit()})
    return rows if rows else None

def col(rows, key):
    return [r.get(key,0) for r in rows]

def sm(arr, w=5):
    if len(arr)<w: return arr
    return list(np.convolve(arr,np.ones(w)/w,mode="valid"))

def make_plot(datasets, x_key, y_key, title, ylabel, plotdir, fname,
              reference=None, ref_label=None, ref_color="#AAAAAA",
              annotate_winner=True):
    fig, ax = plt.subplots(figsize=(10,5))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#F8FBFD")
    ax.grid(True,color="#DDDDDD",linestyle="--",alpha=0.7)

    avgs = {}
    for label, rows in datasets.items():
        t  = col(rows, x_key)
        y  = col(rows, y_key)
        ys = sm(y)
        tx = t[:len(ys)]
        lw = LW.get(label, LW["default"])
        ax.plot(tx, ys,
                color=COLORS[label], linewidth=lw,
                label=LABELS[label],
                zorder=3 if label=="acape" else 2,
                alpha=0.95)
        avgs[label] = round(np.mean(y),2) if y else 0

    if reference is not None:
        ax.axhline(reference, color=ref_color, linewidth=1.5,
                   linestyle=":", label=ref_label or "Reference")

    ax.set_title(title, fontsize=14, fontweight="bold", pad=10, color="#111111")
    ax.set_xlabel("Time (seconds)", fontsize=11, color="#333333")
    ax.set_ylabel(ylabel, fontsize=11, color="#333333")
    ax.legend(fontsize=10, loc="upper right",
              facecolor="white", edgecolor="#CCCCCC")

    # Avg annotation box
    if annotate_winner:
        best = min(avgs, key=avgs.get) if "backlog" in fname or "sojourn" in fname or "drop" in fname \
               else max(avgs, key=avgs.get)
        ann = "\n".join([f"{LABELS[s]}: {avgs[s]}" for s in avgs])
        ann += f"\n\n★ Best: {LABELS[best]}"
        ax.text(0.02, 0.98, ann, transform=ax.transAxes,
                fontsize=8.5, va="top", ha="left",
                bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                          edgecolor="#CCCCCC", alpha=0.9))

    fig.tight_layout()
    out = Path(plotdir)/fname
    fig.savefig(str(out), dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  Saved: {out}")
    return avgs

def make_bar(datasets, y_key, title, ylabel, plotdir, fname, low_good=True):
    labels=[]; vals=[]; colors=[]
    for label, rows in datasets.items():
        y = col(rows, y_key)
        labels.append(LABELS[label])
        vals.append(round(np.mean(y),2))
        colors.append(COLORS[label])

    fig, ax = plt.subplots(figsize=(9,5))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#F8FBFD")
    ax.grid(axis="y", color="#DDDDDD", linestyle="--", alpha=0.7)

    bars = ax.bar(range(len(labels)), vals, color=colors,
                  edgecolor="#CCCCCC", width=0.55)
    best = vals.index(min(vals) if low_good else max(vals))
    bars[best].set_edgecolor("#111111"); bars[best].set_linewidth(2.5)

    for b, v in zip(bars, vals):
        ax.text(b.get_x()+b.get_width()/2, v + max(vals)*0.01,
                str(v), ha="center", va="bottom", fontsize=11, fontweight="bold")

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_title(title, fontsize=14, fontweight="bold", pad=10)
    ax.set_ylabel(ylabel, fontsize=11)

    winner = labels[best]
    ax.text(0.98, 0.98, f"★ Best: {winner}",
            transform=ax.transAxes, fontsize=10, va="top", ha="right",
            bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                      edgecolor="#CCCCCC", alpha=0.9))

    fig.tight_layout()
    out = Path(plotdir)/fname
    fig.savefig(str(out), dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  Saved: {out}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logdir",  default="logs")
    ap.add_argument("--plotdir", default="plots")
    args = ap.parse_args()
    Path(args.plotdir).mkdir(exist_ok=True)

    print("Loading CSVs...")
    datasets = {}
    for s in SYSTEMS:
        d = load(args.logdir, s)
        if d:
            datasets[s] = d
            print(f"  {s}: {len(d)} rows")
        else:
            print(f"  {s}: MISSING")

    if not datasets:
        print("No data found."); sys.exit(0)

    print("\nGenerating plots...")

    # 1. Backlog over time
    make_plot(datasets,"t_s","backlog_pkts",
              "Queue Backlog Over Time — All Systems",
              "Backlog (packets)",args.plotdir,"cmp_backlog_time.png")

    # 2. Throughput over time
    make_plot(datasets,"t_s","throughput_mbps",
              "Throughput Over Time — All Systems",
              "Throughput (Mbps)",args.plotdir,"cmp_throughput_time.png",
              reference=5.0,ref_label="5 Mbit bottleneck",ref_color="#AAAAAA")

    # 3. Drop rate over time
    make_plot(datasets,"t_s","drop_rate",
              "Drop Rate Over Time — All Systems",
              "Drop Rate (packets/s)",args.plotdir,"cmp_droprate_time.png")

    # 4. Target param over time
    make_plot(datasets,"t_s","target_ms",
              "fq_codel Target Parameter Over Time",
              "Target (ms)",args.plotdir,"cmp_target_time.png",
              annotate_winner=False)

    # 5. Sojourn over time
    make_plot(datasets,"t_s","sojourn_ms",
              "Sojourn Time (Queue Latency) Over Time",
              "Sojourn Time (ms)",args.plotdir,"cmp_sojourn_time.png")

    # 6. Avg backlog bar
    make_bar(datasets,"backlog_pkts",
             "Average Queue Backlog — All Systems",
             "Avg Backlog (packets) ↓ lower is better",
             args.plotdir,"cmp_avg_backlog.png",low_good=True)

    # 7. Avg throughput bar
    make_bar(datasets,"throughput_mbps",
             "Average Throughput — All Systems",
             "Avg Throughput (Mbps) ↑ higher is better",
             args.plotdir,"cmp_avg_throughput.png",low_good=False)

    # 8. Avg drop rate bar
    make_bar(datasets,"drop_rate",
             "Average Drop Rate — All Systems",
             "Avg Drop Rate (pkts/s)",
             args.plotdir,"cmp_avg_droprate.png",low_good=True)

    # 9. Avg sojourn bar
    make_bar(datasets,"sojourn_ms",
             "Average Sojourn Time — All Systems",
             "Avg Sojourn (ms) ↓ lower is better",
             args.plotdir,"cmp_avg_sojourn.png",low_good=True)

    # 10. Min target bar
    for label, rows in datasets.items():
        t = col(rows,"target_ms")
        datasets[label]._min_target = min(t) if t else 5.0

    labels=[]; vals=[]; colors=[]
    for label, rows in datasets.items():
        labels.append(LABELS[label])
        vals.append(round(min(col(rows,"target_ms")),2))
        colors.append(COLORS[label])
    fig, ax = plt.subplots(figsize=(9,5))
    fig.patch.set_facecolor("white"); ax.set_facecolor("#F8FBFD")
    ax.grid(axis="y",color="#DDDDDD",linestyle="--",alpha=0.7)
    bars=ax.bar(range(len(labels)),vals,color=colors,edgecolor="#CCCCCC",width=0.55)
    best=vals.index(min(vals)); bars[best].set_edgecolor("#111111"); bars[best].set_linewidth(2.5)
    for b,v in zip(bars,vals):
        ax.text(b.get_x()+b.get_width()/2,v+0.05,str(v),ha="center",va="bottom",fontsize=11,fontweight="bold")
    ax.set_xticks(range(len(labels))); ax.set_xticklabels(labels,fontsize=11)
    ax.set_title("Minimum fq_codel Target Achieved — Proof of Adaptivity",fontsize=14,fontweight="bold",pad=10)
    ax.set_ylabel("Min Target (ms) ↓ lower = more adaptive",fontsize=11)
    ax.text(0.98,0.98,f"★ Best: {labels[best]}",transform=ax.transAxes,fontsize=10,
            va="top",ha="right",bbox=dict(boxstyle="round,pad=0.4",facecolor="white",edgecolor="#CCCCCC",alpha=0.9))
    fig.tight_layout()
    out=Path(args.plotdir)/"cmp_min_target.png"
    fig.savefig(str(out),dpi=150,bbox_inches="tight",facecolor="white"); plt.close(fig)
    print(f"  Saved: {out}")

    # 11. Big 6-panel summary
    fig, axes = plt.subplots(2,3,figsize=(18,10))
    fig.patch.set_facecolor("white")
    fig.suptitle("Complete Parameter Comparison — All Systems\nStatic fq_codel · Adaptive RED · PIE · ACAPE",
                 fontsize=16, fontweight="bold", y=1.01)

    panels = [
        ("backlog_pkts","Queue Backlog (pkts)"),
        ("throughput_mbps","Throughput (Mbps)"),
        ("drop_rate","Drop Rate (/s)"),
        ("sojourn_ms","Sojourn Time (ms)"),
        ("target_ms","fq_codel Target (ms)"),
        ("limit_pkts","fq_codel Limit (pkts)"),
    ]
    for ax, (col_key, col_title) in zip(axes.flatten(), panels):
        ax.set_facecolor("#F8FBFD")
        ax.grid(True,color="#DDDDDD",linestyle="--",alpha=0.6)
        for label, rows in datasets.items():
            t = col(rows,"t_s"); y = col(rows,col_key)
            ys = sm(y); tx = t[:len(ys)]
            lw = LW.get(label,LW["default"])
            ax.plot(tx,ys,color=COLORS[label],linewidth=lw,
                    label=LABELS[label],
                    zorder=3 if label=="acape" else 2)
        ax.set_title(col_title,fontsize=12,fontweight="bold")
        ax.set_xlabel("Time (s)",fontsize=9)
        ax.legend(fontsize=8,loc="upper right")

    fig.tight_layout()
    out=Path(args.plotdir)/"cmp_all_6panel.png"
    fig.savefig(str(out),dpi=150,bbox_inches="tight",facecolor="white"); plt.close(fig)
    print(f"  Saved: {out}")

    print("\nAll plots done:")
    for f in sorted(Path(args.plotdir).glob("cmp_*.png")):
        print(f"  {f.name}")

if __name__=="__main__": main()
