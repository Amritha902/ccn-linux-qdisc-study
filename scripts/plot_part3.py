#!/usr/bin/env python3

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import glob
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LD = os.path.join(BASE, "logs")
PD = os.path.join(BASE, "plots")
os.makedirs(PD, exist_ok=True)

SC = {
    "NORMAL": "#00bfa5",
    "LIGHT": "#2979ff",
    "MODERATE": "#ffd600",
    "HEAVY": "#e53935"
}

def lat(pattern):
    files = sorted(glob.glob(os.path.join(LD, pattern)))
    return files[-1] if files else None

def col(df, *keys):
    for k in keys:
        for c in df.columns:
            if k in c:
                return c
    return None

# Load metrics
mf = lat("metrics_*.csv")
if not mf:
    sys.exit("No metrics CSV found")

df = pd.read_csv(mf)
df.columns = [c.strip().lower() for c in df.columns]

# Fix missing time column
if "t" not in df.columns:
    if "t_s" in df.columns:
        df["t"] = df["t_s"]
    elif "timestamp" in df.columns:
        df["t"] = df["timestamp"] - df["timestamp"].iloc[0]
    else:
        df["t"] = range(len(df))
# Load adjustments
af = lat("adjustments_*.csv")
adj = None
if af:
    adj = pd.read_csv(af)
    adj.columns = [c.strip().lower() for c in adj.columns]

# Plot setup
fig, axes = plt.subplots(2, 2, figsize=(14, 9))
fig.patch.set_facecolor("#0d1117")

def shade(ax):
    if "state" not in df.columns:
        return
    prev_state = df["state"].iloc[0]
    prev_t = df["t"].iloc[0]

    for _, row in df.iterrows():
        if row["state"] != prev_state:
            ax.axvspan(prev_t, row["t"], alpha=0.1, color=SC.get(prev_state, "grey"))
            prev_state = row["state"]
            prev_t = row["t"]

    ax.axvspan(prev_t, df["t"].iloc[-1], alpha=0.1, color=SC.get(prev_state, "grey"))

def vadj(ax):
    if adj is None:
        return
    tc = col(adj, "t", "time")
    if tc:
        for v in adj[tc]:
            ax.axvline(v, color="white", linestyle="--", linewidth=0.7, alpha=0.6)

def fmt(ax, title, ylabel):
    ax.set_facecolor("#0d1117")
    ax.set_title(title, color="white")
    ax.set_xlabel("Time (s)", color="white")
    ax.set_ylabel(ylabel, color="white")
    ax.tick_params(colors="white")
    for sp in ax.spines.values():
        sp.set_edgecolor("#444")

# Columns
tc = "throughput_mbps"
bc = col(df, "backlog")
dc = col(df, "drop")
tmc = col(df, "target")
lmc = col(df, "limit")

# (a) Throughput
ax = axes[0, 0]
shade(ax)
vadj(ax)
if tc:
    ax.plot(df["t"], df[tc])
    ax.axhline(10, linestyle="--")
fmt(ax, "Throughput", "Mbps")

# (b) Drop rate
ax = axes[0, 1]
shade(ax)
vadj(ax)
if dc:
    ax.fill_between(df["t"], df[dc])
fmt(ax, "Drop Rate", "drops/sec")

# (c) Backlog
ax = axes[1, 0]
shade(ax)
vadj(ax)
if bc:
    ax.fill_between(df["t"], df[bc])
fmt(ax, "Queue Backlog", "packets")

# (d) Params
ax = axes[1, 1]
vadj(ax)
if tmc:
    ax.plot(df["t"], df[tmc], label="target")
if lmc:
    ax2 = ax.twinx()
    ax2.plot(df["t"], df[lmc], linestyle="--")
fmt(ax, "Parameters", "target (ms)")
ax.legend()

plt.tight_layout()
out = os.path.join(PD, "part3_overview.png")
plt.savefig(out)
print("Saved:", out)
