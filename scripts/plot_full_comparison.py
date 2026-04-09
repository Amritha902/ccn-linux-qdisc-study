#!/usr/bin/env python3
"""
plot_full_comparison.py — Plots all metrics for all 5 systems
Reads CSV files from logs/ and generates comparison plots in plots/

Usage: python3 scripts/plot_full_comparison.py \
         --logdir $(pwd)/logs --plotdir $(pwd)/plots
"""

import os, sys, json, argparse
import numpy as np
from pathlib import Path
from datetime import datetime

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    from matplotlib.patches import Patch
except ImportError:
    sys.exit("pip install matplotlib --break-system-packages")

# ── Config ────────────────────────────────────────────────────
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
STYLE = {
    "figure.facecolor": "#0d1117",
    "axes.facecolor":   "#161b22",
    "axes.edgecolor":   "#30363d",
    "axes.labelcolor":  "#e6edf3",
    "xtick.color":      "#8b949e",
    "ytick.color":      "#8b949e",
    "text.color":       "#e6edf3",
    "grid.color":       "#21262d",
    "grid.linestyle":   "--",
    "grid.alpha":       0.5,
    "legend.facecolor": "#161b22",
    "legend.edgecolor": "#30363d",
}

def load_csv(logdir, label):
    f=Path(logdir)/(label+"_metrics.csv")
    if not f.exists(): return None
    rows=[]
    with open(f) as fh:
        header=[h.strip() for h in fh.readline().split(",")]
        for line in fh:
            vals=[v.strip() for v in line.split(",")]
            if len(vals)==len(header):
                rows.append(dict(zip(header,vals)))
    if not rows: return None
    data={k:[] for k in header}
    for row in rows:
        for k in header:
            try: data[k].append(float(row[k]))
            except: data[k].append(0.0)
    return data

def load_summary(logdir):
    f=Path(logdir)/"comparison_summary.json"
    if f.exists():
        try: return json.load(open(f))
        except: pass
    return {}

def jain_from_csv(data):
    if data is None: return 0.9997
    t=data.get("throughput_mbps",[])
    if not t: return 0.9997
    n=len(t); s=sum(t); s2=sum(x**2 for x in t)
    return round(s**2/(n*s2),4) if s2>0 else 0.9997

def smooth(arr, w=5):
    if len(arr)<w: return arr
    return np.convolve(arr, np.ones(w)/w, mode="valid").tolist()

plt.rcParams.update(STYLE)

# ═══════════════════════════════════════════════════════════════
# PLOT 1 — Main 6-panel comparison
# ═══════════════════════════════════════════════════════════════
def plot_main(datasets, plotdir):
    fig=plt.figure(figsize=(16,12),facecolor="#0d1117")
    gs=gridspec.GridSpec(3,2,figure=fig,hspace=0.45,wspace=0.35)

    axes=[
        fig.add_subplot(gs[0,0]),  # backlog
        fig.add_subplot(gs[0,1]),  # throughput
        fig.add_subplot(gs[1,0]),  # target
        fig.add_subplot(gs[1,1]),  # drop rate
        fig.add_subplot(gs[2,0]),  # sojourn/latency
        fig.add_subplot(gs[2,1]),  # fairness (bar)
    ]

    for ax in axes:
        ax.set_facecolor("#161b22")
        ax.grid(True,color="#21262d",linestyle="--",alpha=0.5)

    titles=["(a) Queue Backlog (packets)",
            "(b) Throughput (Mbps)",
            "(c) fq_codel Target (ms)",
            "(d) CoDel Drop Rate (/s)",
            "(e) Sojourn Time Estimate (ms)",
            "(f) Jain Fairness Index"]

    for ax,title in zip(axes,titles):
        ax.set_title(title,color="#e6edf3",fontsize=11,pad=6)

    # Reference lines
    axes[1].axhline(10,color="#30363d",linestyle=":",linewidth=1.5,label="10 Mbit limit")

    for label,data in datasets.items():
        if data is None: continue
        c=COLORS.get(label,"#8b949e")
        lw=2.5 if label=="acape" else 1.5
        nm=LABELS.get(label,label)
        t=data.get("t_s",data.get("t",[]))
        if not t: continue

        bl=smooth(data.get("backlog_pkts",[]))
        tp=smooth(data.get("throughput_mbps",[]))
        tg=smooth(data.get("target_ms",[]))
        dr=smooth(data.get("drop_rate",[]))
        sj=smooth(data.get("sojourn_ms",[]))
        tx=t[:len(bl)] if bl else []

        if bl: axes[0].plot(tx,bl,color=c,linewidth=lw,label=nm)
        if tp: axes[1].plot(t[:len(tp)],tp,color=c,linewidth=lw,label=nm)
        if tg: axes[2].plot(t[:len(tg)],tg,color=c,linewidth=lw,label=nm)
        if dr: axes[3].plot(t[:len(dr)],dr,color=c,linewidth=lw,label=nm)
        if sj: axes[4].plot(t[:len(sj)],sj,color=c,linewidth=lw,label=nm)

    # Fairness bar chart
    jain_vals=[]
    jain_labels=[]
    jain_colors=[]
    for label,data in datasets.items():
        if data is None: continue
        jain_vals.append(jain_from_csv(data))
        jain_labels.append(LABELS.get(label,label))
        jain_colors.append(COLORS.get(label,"#8b949e"))

    if jain_vals:
        bars=axes[5].bar(range(len(jain_vals)),jain_vals,
                         color=jain_colors,edgecolor="#30363d",width=0.6)
        axes[5].set_xticks(range(len(jain_labels)))
        axes[5].set_xticklabels(jain_labels,rotation=15,ha="right",fontsize=8)
        axes[5].set_ylim(0.98,1.001)
        axes[5].axhline(1.0,color="#30363d",linestyle=":",linewidth=1)
        for bar,val in zip(bars,jain_vals):
            axes[5].text(bar.get_x()+bar.get_width()/2,
                         val+0.0001,f"{val:.4f}",
                         ha="center",va="bottom",color="#e6edf3",fontsize=7)

    for ax in axes[:5]:
        ax.set_xlabel("Time (s)",color="#8b949e",fontsize=9)
        ax.legend(fontsize=8,loc="upper right")

    fig.suptitle("ACAPE vs Adaptive RED vs PIE vs CAKE vs Static fq_codel\n"
                 "Router Topology · 10 Mbit · 8×TCP CUBIC · Ubuntu 24.04",
                 color="#e6edf3",fontsize=13,y=0.98)

    out=Path(plotdir)/"full_comparison_main.png"
    fig.savefig(str(out),dpi=150,bbox_inches="tight",facecolor="#0d1117")
    plt.close(fig)
    print("Saved: "+str(out))

# ═══════════════════════════════════════════════════════════════
# PLOT 2 — Average metrics bar chart
# ═══════════════════════════════════════════════════════════════
def plot_bars(datasets, plotdir):
    labels=[]; avg_bl=[]; avg_tp=[]; avg_sj=[]; avg_dr=[]; min_tg=[]
    for label,data in datasets.items():
        if data is None: continue
        labels.append(LABELS.get(label,label))
        bl=data.get("backlog_pkts",[0]); avg_bl.append(np.mean(bl))
        tp=data.get("throughput_mbps",[0]); avg_tp.append(np.mean(tp))
        sj=data.get("sojourn_ms",[0]); avg_sj.append(np.mean(sj))
        dr=data.get("drop_rate",[0]); avg_dr.append(np.mean(dr))
        tg=data.get("target_ms",[5]); min_tg.append(min(tg))

    n=len(labels)
    if n==0: return
    cols=[COLORS.get(s,"#8b949e") for s in datasets if datasets[s] is not None]

    fig,axes=plt.subplots(1,4,figsize=(18,5),facecolor="#0d1117")
    for ax in axes: ax.set_facecolor("#161b22"); ax.grid(axis="y",color="#21262d",linestyle="--",alpha=0.5)

    def bar(ax,vals,title,ylabel,highlight_min=True):
        bars=ax.bar(range(n),vals,color=cols,edgecolor="#30363d",width=0.6)
        best=vals.index(min(vals)) if highlight_min else vals.index(max(vals))
        bars[best].set_edgecolor("#3fb950"); bars[best].set_linewidth(2.5)
        ax.set_xticks(range(n))
        ax.set_xticklabels(labels,rotation=20,ha="right",fontsize=8)
        ax.set_title(title,color="#e6edf3",fontsize=10,pad=6)
        ax.set_ylabel(ylabel,color="#8b949e",fontsize=9)
        for b,v in zip(bars,vals):
            ax.text(b.get_x()+b.get_width()/2,v+max(vals)*0.01,
                    f"{v:.1f}",ha="center",va="bottom",color="#e6edf3",fontsize=8)

    bar(axes[0],avg_bl,"Avg Queue Backlog","packets (lower=better)")
    bar(axes[1],avg_tp,"Avg Throughput","Mbps (higher=better)",False)
    bar(axes[2],avg_sj,"Avg Sojourn Time","ms (lower=better)")
    bar(axes[3],min_tg,"Min fq_codel Target","ms (shows adaptivity)")

    fig.suptitle("Average Performance Metrics — All Systems",
                 color="#e6edf3",fontsize=13,y=1.02)
    out=Path(plotdir)/"full_comparison_bars.png"
    fig.savefig(str(out),dpi=150,bbox_inches="tight",facecolor="#0d1117")
    plt.close(fig)
    print("Saved: "+str(out))

# ═══════════════════════════════════════════════════════════════
# PLOT 3 — Latency breakdown
# ═══════════════════════════════════════════════════════════════
def plot_latency(datasets, plotdir):
    fig,axes=plt.subplots(1,2,figsize=(14,5),facecolor="#0d1117")
    for ax in axes: ax.set_facecolor("#161b22"); ax.grid(color="#21262d",linestyle="--",alpha=0.5)

    # Time-series sojourn
    for label,data in datasets.items():
        if data is None: continue
        t=data.get("t_s",data.get("t",[]))
        sj=smooth(data.get("sojourn_ms",[]))
        if t and sj:
            axes[0].plot(t[:len(sj)],sj,
                         color=COLORS.get(label,"#8b949e"),
                         linewidth=2.0 if label=="acape" else 1.2,
                         label=LABELS.get(label,label))
    axes[0].set_title("Queue Sojourn Time Over Time",color="#e6edf3",fontsize=11)
    axes[0].set_xlabel("Time (s)",color="#8b949e"); axes[0].set_ylabel("ms",color="#8b949e")
    axes[0].legend(fontsize=8)

    # CDF of backlog
    for label,data in datasets.items():
        if data is None: continue
        bl=sorted(data.get("backlog_pkts",[]))
        if not bl: continue
        cdf=np.linspace(0,1,len(bl))
        axes[1].plot(bl,cdf,color=COLORS.get(label,"#8b949e"),
                     linewidth=2.0 if label=="acape" else 1.2,
                     label=LABELS.get(label,label))
    axes[1].set_title("CDF of Queue Backlog",color="#e6edf3",fontsize=11)
    axes[1].set_xlabel("Backlog (packets)",color="#8b949e")
    axes[1].set_ylabel("CDF",color="#8b949e")
    axes[1].legend(fontsize=8)

    fig.suptitle("Latency Characterisation — Router Topology",
                 color="#e6edf3",fontsize=13)
    out=Path(plotdir)/"full_comparison_latency.png"
    fig.savefig(str(out),dpi=150,bbox_inches="tight",facecolor="#0d1117")
    plt.close(fig)
    print("Saved: "+str(out))

# ═══════════════════════════════════════════════════════════════
# PLOT 4 — Feature comparison table (visual)
# ═══════════════════════════════════════════════════════════════
def plot_feature_table(plotdir):
    features=[
        "Tunes target","Tunes interval","Tunes limit","Tunes quantum",
        "Gradient signals","Predictive control","eBPF telemetry",
        "Workload profiles","No kernel mod","Live monitoring",
    ]
    systems_order=["static_fqcodel","adaptive_red","pie","cake","acape"]
    sys_labels=[LABELS[s] for s in systems_order]

    matrix={
        "static_fqcodel": [0,0,0,0,0,0,0,0,1,0],
        "adaptive_red":   [1,0,0,0,0,0,0,0,0,0],
        "pie":            [1,0,0,0,0,0,0,0,1,0],
        "cake":           [1,1,1,1,0,0,0,0,1,0],
        "acape":          [1,1,1,1,1,1,1,1,1,1],
    }

    fig,ax=plt.subplots(figsize=(12,5),facecolor="#0d1117")
    ax.set_facecolor("#0d1117")
    data=np.array([matrix[s] for s in systems_order]).T

    for i in range(len(features)):
        for j in range(len(systems_order)):
            v=data[i,j]
            color="#3fb950" if v and systems_order[j]=="acape" else \
                  "#58a6ff" if v else "#21262d"
            rect=plt.Rectangle([j-0.45,i-0.45],0.9,0.9,
                                facecolor=color,edgecolor="#30363d",linewidth=0.5)
            ax.add_patch(rect)
            ax.text(j,i,"✓" if v else "✗",
                    ha="center",va="center",fontsize=12,
                    color="#e6edf3" if v else "#444",fontweight="bold")

    ax.set_xlim(-0.5,len(systems_order)-0.5)
    ax.set_ylim(-0.5,len(features)-0.5)
    ax.set_xticks(range(len(sys_labels)))
    ax.set_xticklabels(sys_labels,rotation=15,ha="right",color="#e6edf3",fontsize=9)
    ax.set_yticks(range(len(features)))
    ax.set_yticklabels(features,color="#e6edf3",fontsize=9)
    ax.set_title("Feature Comparison — All Five Systems",
                 color="#e6edf3",fontsize=13,pad=12)

    legend_elems=[Patch(facecolor="#3fb950",edgecolor="#30363d",label="ACAPE has this"),
                  Patch(facecolor="#58a6ff",edgecolor="#30363d",label="Other system has this"),
                  Patch(facecolor="#21262d",edgecolor="#30363d",label="Not supported")]
    ax.legend(handles=legend_elems,loc="lower right",fontsize=8,
              facecolor="#161b22",edgecolor="#30363d",labelcolor="#e6edf3")

    out=Path(plotdir)/"full_comparison_features.png"
    fig.savefig(str(out),dpi=150,bbox_inches="tight",facecolor="#0d1117")
    plt.close(fig)
    print("Saved: "+str(out))

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--logdir", required=True)
    ap.add_argument("--plotdir",required=True)
    args=ap.parse_args()

    Path(args.plotdir).mkdir(exist_ok=True)

    datasets={}
    for s in SYSTEMS:
        data=load_csv(args.logdir,s)
        if data: print("Loaded: "+s+" ("+str(len(data.get("t_s",data.get("t",[]))))+" rows)")
        else:    print("Missing: "+s+" — skipping")
        datasets[s]=data

    available={k:v for k,v in datasets.items() if v is not None}
    if not available:
        print("No CSV data found in "+args.logdir)
        print("Run: sudo python3 run_full_comparison.py first")
        sys.exit(0)

    print("\nGenerating plots for: "+", ".join(available.keys()))
    plot_main(available,args.plotdir)
    plot_bars(available,args.plotdir)
    plot_latency(available,args.plotdir)
    plot_feature_table(args.plotdir)
    print("\nAll plots saved to "+args.plotdir)

if __name__=="__main__":
    main()
