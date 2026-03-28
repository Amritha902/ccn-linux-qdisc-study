#!/usr/bin/env python3
import pandas as pd,matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt,glob,os,sys
BASE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LD=os.path.join(BASE,"logs");PD=os.path.join(BASE,"plots");os.makedirs(PD,exist_ok=True)
SC={"NORMAL":"#00bfa5","LIGHT":"#2979ff","MODERATE":"#ffd600","HEAVY":"#e53935"}
def lat(p): f=sorted(glob.glob(os.path.join(LD,p))); return f[-1] if f else None
def col(df,*k):
    for kw in k:
        c=next((x for x in df.columns if kw in x),None)
        if c: return c
    return None
def load(pat):
    f=lat(pat)
    if not f: return None
    df=pd.read_csv(f);df.columns=[c.strip().lower() for c in df.columns]
    if "t" not in df.columns and "timestamp" in df.columns:
        df["t"]=df["timestamp"]-df["timestamp"].iloc[0]
    return df
def fmt(ax,ti,yl):
    ax.set_facecolor("#0d1117");ax.set_title(ti,color="white")
    ax.set_ylabel(yl,color="white");ax.set_xlabel("Time (s)",color="white")
    ax.tick_params(colors="white")
    for sp in ax.spines.values(): sp.set_edgecolor("#444")
p3=load("metrics_*.csv");p4=load("ebpf_metrics_*.csv")
if p4 is None: sys.exit("[P4 plot] no ebpf_metrics CSV")
fig,axes=plt.subplots(2,3,figsize=(18,10))
fig.suptitle("Part 4 — eBPF-Enhanced Adaptive Controller\nAmritha S, VIT Chennai 2026",
             fontsize=13,fontweight="bold",color="white")
fig.patch.set_facecolor("#0d1117")
tc4=col(p4,"throughput");dc4=col(p4,"drop");bc4=col(p4,"backlog")
tmc4=col(p4,"target");lmc4=col(p4,"limit");fc4=col(p4,"active_flow","flow");ec4=col(p4,"elephant")
ax=axes[0,0]
if tc4: ax.plot(p4["t"],p4[tc4],color="#00e5ff",lw=1.2);ax.axhline(10,color="white",ls="--",lw=0.8,alpha=0.5)
fmt(ax,"(a) Throughput","Mbps")
ax=axes[0,1]
if dc4: ax.fill_between(p4["t"],p4[dc4],color="#e53935",alpha=0.75)
fmt(ax,"(b) Drop Rate","drops/sec")
ax=axes[1,0]
if bc4: ax.fill_between(p4["t"],p4[bc4],color="#ffd600",alpha=0.8)
fmt(ax,"(c) Queue Backlog","packets")
ax=axes[1,1]
if tmc4: ax.plot(p4["t"],p4[tmc4],color="#7c4dff",lw=1.5,label="target ms")
if lmc4:
    ax2=ax.twinx();ax2.plot(p4["t"],p4[lmc4],color="#ff4081",lw=1.5,ls="--")
    ax2.set_ylabel("limit",color="#ff4081");ax2.tick_params(colors="#ff4081")
ax.legend(fontsize=8);fmt(ax,"(d) AIMD Parameter Evolution","target (ms)")
ax=axes[0,2]
if fc4 and fc4 in p4.columns: ax.plot(p4["t"],p4[fc4],color="#69f0ae",lw=1.5,label="active flows")
if ec4 and ec4 in p4.columns: ax.plot(p4["t"],p4[ec4],color="#ff6d00",lw=1.5,label="elephant flows")
if not(fc4 and fc4 in p4.columns):
    ax.text(0.5,0.5,"eBPF flow data\nnot available\n(tc-only mode)",ha="center",va="center",
            transform=ax.transAxes,color="#888",fontsize=11)
ax.legend(fontsize=8);fmt(ax,"(e) Per-Flow Visibility (eBPF)","flows")
ax=axes[1,2]
if "state" in p4.columns:
    sm={"NORMAL":0,"LIGHT":1,"MODERATE":2,"HEAVY":3}
    ax.scatter(p4["t"],p4["state"].map(sm),c=[SC.get(s,"grey") for s in p4["state"]],s=12,zorder=3)
    ax.set_yticks([0,1,2,3]);ax.set_yticklabels(["NORMAL","LIGHT","MODERATE","HEAVY"],color="white")
fmt(ax,"(f) Congestion State Timeline","")
plt.tight_layout()
out=os.path.join(PD,"part4_ebpf_overview.png")
plt.savefig(out,dpi=150,facecolor="#0d1117");print(f"[PLOT] {out}")
if p3 is not None:
    fig2,axes2=plt.subplots(1,3,figsize=(18,5))
    fig2.suptitle("Part 3 vs Part 4 — tc-only vs eBPF-Enhanced",fontsize=13,fontweight="bold",color="white")
    fig2.patch.set_facecolor("#0d1117")
    def cmp(ax,kw,yl,ti):
        c3=col(p3,kw);c4=col(p4,kw)
        if c3 and c3 in p3.columns: ax.fill_between(p3["t"],p3[c3],alpha=0.6,color="#ffd600",label="Part3 tc-only")
        if c4 and c4 in p4.columns: ax.fill_between(p4["t"],p4[c4],alpha=0.5,color="#7c4dff",label="Part4 eBPF")
        ax.legend(fontsize=8);fmt(ax,ti,yl)
    cmp(axes2[0],"backlog","pkts","Queue Backlog Comparison")
    cmp(axes2[1],"drop","drops/sec","Drop Rate Comparison")
    ax=axes2[2];tmc3=col(p3,"target")
    if tmc3 and tmc3 in p3.columns: ax.plot(p3["t"],p3[tmc3],color="#ffd600",lw=1.5,label="Part3")
    if tmc4 and tmc4 in p4.columns: ax.plot(p4["t"],p4[tmc4],color="#7c4dff",lw=1.5,label="Part4")
    ax.legend(fontsize=8);fmt(ax,"AIMD Target Evolution","target (ms)")
    plt.tight_layout()
    out2=os.path.join(PD,"part4_vs_part3_comparison.png")
    plt.savefig(out2,dpi=150,facecolor="#0d1117");print(f"[PLOT] {out2}")
