#!/usr/bin/env python3
"""
plot_acape.py — ACAPE results visualiser
Amritha S — VIT Chennai 2026
Reads acape_metrics_*.csv, acape_adj_*.csv, acape_state_*.csv
Generates publication-quality figures.
"""
import os, sys, glob, csv, re
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import Patch

LOGDIR  = "../logs"
PLOTDIR = "../plots"
os.makedirs(PLOTDIR, exist_ok=True)

plt.rcParams.update({
    "figure.facecolor":"#1a1a2e","axes.facecolor":"#16213e",
    "axes.edgecolor":"#555","axes.labelcolor":"#ddd",
    "xtick.color":"#aaa","ytick.color":"#aaa","text.color":"#ddd",
    "grid.color":"#2a2a4a","grid.linewidth":0.5,
    "legend.facecolor":"#16213e","legend.edgecolor":"#555",
    "font.family":"monospace","font.size":10,
})

SC  = {"NORMAL":"#00b894","LIGHT":"#74b9ff","MODERATE":"#fdcb6e","HEAVY":"#d63031"}
TC  = {"WORSENING":"#e17055","STABLE":"#636e72","RECOVERING":"#00cec9"}
WC  = {"MICE":"#a29bfe","MIXED":"#fdcb6e","ELEPHANT":"#55efc4"}
SO  = ["NORMAL","LIGHT","MODERATE","HEAVY"]

def latest(pat): f=sorted(glob.glob(pat)); return f[-1] if f else None
def lcsv(path):
    rows=[]
    try:
        with open(path) as f:
            for r in csv.DictReader(f): rows.append(r)
    except: pass
    return rows
def save(fig,name):
    p=os.path.join(PLOTDIR,name)
    fig.savefig(p,dpi=150,bbox_inches="tight",facecolor=fig.get_facecolor())
    print(f"  saved: {p}"); plt.close(fig)

def shade_regime(ax,t,regimes):
    if len(t)<2: return
    ps,pt=regimes[0],t[0]
    for i in range(1,len(regimes)):
        if regimes[i]!=ps or i==len(regimes)-1:
            ax.axvspan(pt,t[i],alpha=0.10,color=SC.get(ps,"#888"),zorder=1)
            ps,pt=regimes[i],t[i]

def vadj(ax,adjs):
    for i,a in enumerate(adjs):
        ax.axvline(float(a.get("t_s",a.get("t",0))),color="white",
                   lw=0.8,alpha=0.5,ls="--",
                   label="adjustment" if i==0 else "")

# ── Load data ─────────────────────────────────────────────────
mf = latest(os.path.join(LOGDIR,"acape_metrics_*.csv"))
af = latest(os.path.join(LOGDIR,"acape_adj_*.csv"))
sf = latest(os.path.join(LOGDIR,"acape_state_*.csv"))
p3m = latest(os.path.join(LOGDIR,"metrics_*.csv"))   # Part 3 for comparison

if not mf: sys.exit(f"No acape_metrics_*.csv in {LOGDIR}/ — run ACAPE first")
print(f"metrics : {mf}")
if af:  print(f"adj     : {af}")
if sf:  print(f"state   : {sf}")
if p3m: print(f"part3   : {p3m}")

rows  = lcsv(mf)
adjs  = lcsv(af) if af else []
srows = lcsv(sf) if sf else []

def g(r,*ks,df=0.0):
    for k in ks:
        if k in r and r[k] not in ("",None): return r[k]
    return str(df)

t       = np.array([float(g(r,"t_s"))               for r in rows])
dr      = np.array([float(g(r,"drop_rate_per_s"))    for r in rows])
bl      = np.array([float(g(r,"backlog_pkts"))        for r in rows])
tp      = np.array([float(g(r,"throughput_mbps"))     for r in rows])
tgt     = np.array([float(g(r,"target_ms"))           for r in rows])
lim     = np.array([float(g(r,"limit_pkts"))          for r in rows])
qnt     = np.array([float(g(r,"quantum_bytes",df=1514)) for r in rows])
rtt     = np.array([float(g(r,"rtt_proxy_ms"))        for r in rows])
flows   = np.array([float(g(r,"active_flows"))        for r in rows])
eleph   = np.array([float(g(r,"elephant_flows"))      for r in rows])
eratio  = np.array([float(g(r,"elephant_ratio"))      for r in rows])
dexp    = np.array([float(g(r,"drops_exp"))           for r in rows])
regimes = [g(r,"regime",df="NORMAL") for r in rows]
trajs   = [g(r,"trajectory",df="STABLE") for r in rows]
preds   = [g(r,"predicted_regime",df="NORMAL") for r in rows]
wklds   = [g(r,"workload_profile",df="MIXED") for r in rows]

if srows:
    st      = np.array([float(g(r,"t_s")) for r in srows])
    dr_grad = np.array([float(g(r,"dr_gradient")) for r in srows])
    bl_grad = np.array([float(g(r,"bl_gradient")) for r in srows])
    rt_grad = np.array([float(g(r,"rtt_gradient")) for r in srows])

# ════════════════════════════════════════════════════════════════
# Figure 1: Main 6-panel overview (ACAPE results)
# ════════════════════════════════════════════════════════════════
print("Plotting Fig 1: ACAPE 6-panel overview...")
fig = plt.figure(figsize=(18,13))
gs  = gridspec.GridSpec(3,3,figure=fig,hspace=0.45,wspace=0.38)
fig.suptitle(
    "ACAPE: Adaptive Condition-Aware Packet Engine — Measured Results\n"
    "Amritha S, VIT Chennai 2026  |  Multi-signal predictive fq_codel controller",
    fontsize=13,fontweight="bold")

def mk(r,c): ax=fig.add_subplot(gs[r,c]); shade_regime(ax,t,regimes); return ax

# (a) Throughput
ax=mk(0,0)
ax.plot(t,tp,color="#4ecdc4",lw=1.2,label="throughput")
ax.axhline(10,color="#888",ls="--",lw=0.8,label="10 Mbit limit")
vadj(ax,adjs)
ax.set(xlabel="Time (s)",ylabel="Mbps",title="(a) Throughput")
ax.legend(fontsize=8); ax.grid(True)

# (b) Drop rate + predicted regime overlay
ax=mk(0,1)
ax.fill_between(t,dr,color="#e94560",alpha=0.7,label="drops/sec")
pred_colors = [SC.get(p,"#888") for p in preds]
ax.scatter(t,[max(dr)*0.95]*len(t),c=pred_colors,s=4,alpha=0.6,label="predicted regime")
vadj(ax,adjs)
ax.set(xlabel="Time (s)",ylabel="drops/sec",
       title="(b) Drop Rate + Predicted Regime\n(coloured strip = next-state prediction)")
ax.legend(fontsize=8); ax.grid(True)

# (c) Queue backlog
ax=mk(0,2)
ax.fill_between(t,bl,color="#f7dc6f",alpha=0.75,label="backlog (pkts)")
vadj(ax,adjs)
ax.set(xlabel="Time (s)",ylabel="packets",title="(c) Queue Backlog")
ax.legend(fontsize=8); ax.grid(True)

# (d) AIMD parameter evolution (target + limit + quantum)
ax=mk(1,0); ax2=ax.twinx(); ax3=ax.twinx()
ax3.spines["right"].set_position(("outward",60))
ax.step(t,tgt,color="#a29bfe",lw=2,where="post",label="target (ms)")
ax2.step(t,lim,color="#fd79a8",lw=1.2,where="post",label="limit (pkts)",alpha=0.8)
ax3.step(t,qnt,color="#55efc4",lw=1,where="post",label="quantum (B)",alpha=0.6,ls="--")
ax2.set_ylabel("limit (pkts)",color="#fd79a8"); ax2.tick_params(colors="#fd79a8")
ax3.set_ylabel("quantum (B)",color="#55efc4");  ax3.tick_params(colors="#55efc4")
l1,n1=ax.get_legend_handles_labels(); l2,n2=ax2.get_legend_handles_labels()
l3,n3=ax3.get_legend_handles_labels()
ax.legend(l1+l2+l3,n1+n2+n3,fontsize=7); ax.grid(True)
ax.set(xlabel="Time (s)",ylabel="target (ms)",
       title="(d) AIMD Parameter Evolution\n(target + limit + quantum)")
vadj(ax,adjs)

# (e) eBPF: flow count + elephant ratio
ax=mk(1,1)
if flows.max()>0:
    ax.fill_between(t,flows,color="#6c5ce7",alpha=0.6,label="active flows")
    ax.fill_between(t,eleph,color="#e17055",alpha=0.6,label="elephant flows")
    ax2=ax.twinx()
    ax2.plot(t,eratio,color="#fdcb6e",lw=1.5,label="elephant ratio",alpha=0.9)
    ax2.set_ylabel("elephant ratio",color="#fdcb6e"); ax2.tick_params(colors="#fdcb6e")
    ax2.set_ylim(0,1)
    l1,n1=ax.get_legend_handles_labels(); l2,n2=ax2.get_legend_handles_labels()
    ax.legend(l1+l2,n1+n2,fontsize=8)
else:
    ax.text(0.5,0.5,"eBPF flow data unavailable\n(tc-only mode)",
            transform=ax.transAxes,ha="center",va="center",fontsize=11,color="#aaa")
ax.set(xlabel="Time (s)",ylabel="flow count",
       title="(e) eBPF Per-Flow Telemetry\nElephant/mice classification")
ax.grid(True)

# (f) Workload profile over time (MICE / MIXED / ELEPHANT)
ax=mk(1,2)
wkld_y = {"MICE":0,"MIXED":1,"ELEPHANT":2}
wkld_colors = [WC.get(w,"#888") for w in wklds]
ax.scatter(t,[wkld_y.get(w,1) for w in wklds],c=wkld_colors,s=8,alpha=0.85)
ax.set(yticks=[0,1,2],yticklabels=["MICE","MIXED","ELEPHANT"],
       xlabel="Time (s)",title="(f) Workload Profile Selection\n(eBPF elephant-ratio driven)")
ax.grid(True,axis="x")
for w,c in WC.items():
    ax.scatter([],[],c=c,label=w,s=40)
ax.legend(fontsize=8)

# (g-i) State timeline with trajectory + gradient signals
ax=fig.add_subplot(gs[2,:])
shade_regime(ax,t,regimes)
sy={"NORMAL":0,"LIGHT":1,"MODERATE":2,"HEAVY":3}
rc=[SC.get(r,"#888") for r in regimes]
pc=[SC.get(p,"#888") for p in preds]
tc_=[TC.get(tr,"#888") for tr in trajs]
ax.scatter(t,[sy.get(r,0) for r in regimes],c=rc,s=12,alpha=0.8,label="current regime",zorder=3)
ax.scatter(t,[sy.get(p,0)+0.3 for p in preds],c=pc,s=6,alpha=0.4,
           label="predicted regime",marker="^",zorder=2)
vadj(ax,adjs)
ax.set(yticks=[0,1,2,3],yticklabels=SO,xlabel="Time (s)",
       title="(g) Regime Timeline: current (circle) + predicted-next (triangle) + AIMD adjustments (dashed)\n"
             "Predictive element: triangles lead circles → controller acts before state transition")
ax.grid(True,axis="x"); ax.legend(fontsize=8,ncol=4)
hs=[Patch(color=SC[s],alpha=0.6,label=s) for s in SO]
ax.legend(handles=hs+ax.get_legend_handles_labels()[0][:2],fontsize=8,ncol=6,loc="upper right")

save(fig,"acape_overview.png")

# ════════════════════════════════════════════════════════════════
# Figure 2: Gradient signals (novel contribution visualisation)
# ════════════════════════════════════════════════════════════════
if srows:
    print("Plotting Fig 2: Gradient signals...")
    fig,(ax1,ax2,ax3)=plt.subplots(3,1,figsize=(14,9),sharex=True)
    fig.suptitle("ACAPE Novel Contribution: Multi-Signal Gradient State Estimator\n"
                 "Predictive regime detection from Δdrop_rate/Δt, Δbacklog/Δt, ΔRTT/Δt",
                 fontsize=12,fontweight="bold")
    for ax in (ax1,ax2,ax3): shade_regime(ax,st,[r for r in [g(rw,"regime",df="NORMAL") for rw in srows]])

    ax1.plot(st,dr_grad,color="#e94560",lw=1.2,label="Δdrop_rate/Δt")
    ax1.axhline(0,color="#888",ls="--",lw=0.8)
    ax1.fill_between(st,dr_grad,where=dr_grad>0,color="#e94560",alpha=0.3,label="worsening")
    ax1.fill_between(st,dr_grad,where=dr_grad<0,color="#00cec9",alpha=0.3,label="recovering")
    ax1.set(ylabel="Δdr/Δt (drops/s²)",title="Drop rate gradient"); ax1.legend(fontsize=8); ax1.grid(True)

    ax2.plot(st,bl_grad,color="#f7dc6f",lw=1.2,label="Δbacklog/Δt")
    ax2.axhline(0,color="#888",ls="--",lw=0.8)
    ax2.fill_between(st,bl_grad,where=bl_grad>0,color="#f7dc6f",alpha=0.3)
    ax2.fill_between(st,bl_grad,where=bl_grad<0,color="#00cec9",alpha=0.3)
    ax2.set(ylabel="Δbl/Δt (pkts/s)",title="Backlog gradient"); ax2.legend(fontsize=8); ax2.grid(True)

    ax3.plot(st,rt_grad,color="#a29bfe",lw=1.2,label="ΔRTT/Δt")
    ax3.axhline(0,color="#888",ls="--",lw=0.8)
    ax3.fill_between(st,rt_grad,where=rt_grad>0,color="#a29bfe",alpha=0.3)
    ax3.fill_between(st,rt_grad,where=rt_grad<0,color="#00cec9",alpha=0.3)
    ax3.set(xlabel="Time (s)",ylabel="ΔRTT/Δt (ms/s)",title="RTT gradient"); ax3.legend(fontsize=8); ax3.grid(True)
    save(fig,"acape_gradients.png")

# ════════════════════════════════════════════════════════════════
# Figure 3: ACAPE vs Static fq_codel vs Part 3 (comparison)
# ════════════════════════════════════════════════════════════════
if p3m:
    print("Plotting Fig 3: ACAPE vs Part 3 comparison...")
    r3   = lcsv(p3m)
    t3   = np.array([float(g(r,"t_s","t")) for r in r3])
    bl3  = np.array([float(g(r,"backlog_pkts","backlog")) for r in r3])
    dr3  = np.array([float(g(r,"drop_rate_per_s","drop_rate")) for r in r3])
    tgt3 = np.array([float(g(r,"target_ms")) for r in r3])
    tp3  = np.array([float(g(r,"throughput_mbps")) for r in r3])

    fig,axes=plt.subplots(2,2,figsize=(15,9))
    fig.suptitle("ACAPE vs Part 3 (Reactive AIMD) — Performance Comparison\n"
                 "Amritha S, VIT Chennai 2026",fontsize=12,fontweight="bold")

    ax=axes[0,0]
    ax.fill_between(t3,bl3,color="#f7dc6f",alpha=0.5,label="Part 3 (reactive AIMD)")
    ax.fill_between(t, bl, color="#a29bfe",alpha=0.6,label="ACAPE (predictive)")
    ax.set(xlabel="Time (s)",ylabel="backlog (pkts)",title="Queue Backlog")
    ax.legend(fontsize=9); ax.grid(True)

    ax=axes[0,1]
    ax.fill_between(t3,dr3,color="#f7dc6f",alpha=0.5,label="Part 3")
    ax.fill_between(t, dr, color="#a29bfe",alpha=0.6,label="ACAPE")
    ax.set(xlabel="Time (s)",ylabel="drops/sec",title="Instantaneous Drop Rate")
    ax.legend(fontsize=9); ax.grid(True)

    ax=axes[1,0]
    ax.step(t3,tgt3,color="#f7dc6f",lw=2,where="post",label="Part 3 target")
    ax.step(t, tgt, color="#a29bfe",lw=2,where="post",label="ACAPE target")
    ax.set(xlabel="Time (s)",ylabel="target (ms)",title="AIMD Target Parameter")
    ax.legend(fontsize=9); ax.grid(True)

    ax=axes[1,1]
    ax.fill_between(t3,tp3,color="#f7dc6f",alpha=0.5,label="Part 3")
    ax.fill_between(t, tp, color="#a29bfe",alpha=0.6,label="ACAPE")
    ax.axhline(10,color="#888",ls="--",lw=0.8,label="10 Mbit limit")
    ax.set(xlabel="Time (s)",ylabel="Mbps",title="Throughput")
    ax.legend(fontsize=9); ax.grid(True)
    save(fig,"acape_vs_part3.png")

# ════════════════════════════════════════════════════════════════
# Figure 4: Adjustment log table
# ════════════════════════════════════════════════════════════════
if adjs:
    print("Plotting Fig 4: Adjustment log...")
    fig,ax=plt.subplots(figsize=(18,max(3,len(adjs)*0.38+1.5)))
    fig.suptitle("ACAPE — AIMD Adjustment Log\n"
                 "[PREDICTIVE] = acted on predicted next state  |  [REACTIVE] = acted on current state",
                 fontsize=11,fontweight="bold")
    ax.axis("off")
    hdrs=["Time (s)","Regime","Trajectory","Predicted",
          "Old target","New target","Old limit","New limit","Workload","Reason"]
    def rv(r): return [
        g(r,"t_s"),g(r,"regime"),g(r,"trajectory"),g(r,"predicted"),
        g(r,"old_target"),g(r,"new_target"),
        g(r,"old_limit"),g(r,"new_limit"),
        g(r,"workload"),g(r,"reason")[:40]]
    data=[rv(r) for r in adjs[:30]]
    if not data: data=[["—"]*len(hdrs)]
    tbl=ax.table(cellText=data,colLabels=hdrs,cellLoc="center",loc="center")
    tbl.auto_set_font_size(False); tbl.set_fontsize(8); tbl.scale(1.0,1.4)
    for (row,col),cell in tbl.get_celld().items():
        cell.set_facecolor("#16213e" if row>0 else "#0f3460")
        cell.set_edgecolor("#0f3460"); cell.set_text_props(color="#e0e0e0")
    save(fig,"acape_adjustments.png")

# ════════════════════════════════════════════════════════════════
# Summary
# ════════════════════════════════════════════════════════════════
sc={s:regimes.count(s) for s in SO}; tot=len(regimes)
tc2={s:trajs.count(s) for s in ["WORSENING","STABLE","RECOVERING"]}
print(f"\n{'═'*60}")
print(f"  ACAPE Results Summary")
print(f"  Duration        : {t[-1]:.1f} s  |  Ticks: {tot}")
print(f"  Adjustments     : {len(adjs)}")
print(f"  Avg drop rate   : {dr.mean():.1f} drops/sec")
print(f"  Avg backlog     : {bl.mean():.1f} pkts")
print(f"  Avg throughput  : {tp.mean():.3f} Mbps")
print(f"  RTT proxy avg   : {rtt[rtt>0].mean():.2f} ms" if rtt.max()>0 else "  RTT proxy: N/A")
print(f"  Regime dist     : {sc}")
print(f"  Trajectory dist : {tc2}")
print(f"  eBPF mode       : {'ON' if flows.max()>0 else 'tc-only'}")
print(f"  Plots → {PLOTDIR}/")
