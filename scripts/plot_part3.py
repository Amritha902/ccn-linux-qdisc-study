#!/usr/bin/env python3
"""
plot_part3.py — Part 3 results plotter
Amritha S — VIT Chennai 2026
Handles column names from both old and new controller.py versions.
"""

import os, sys, glob, csv, re
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

LOGDIR  = "../logs"
PLOTDIR = "../plots"
os.makedirs(PLOTDIR, exist_ok=True)

plt.rcParams.update({
    "figure.facecolor": "#1a1a2e", "axes.facecolor": "#16213e",
    "axes.edgecolor": "#444",      "axes.labelcolor": "#ddd",
    "xtick.color": "#aaa",         "ytick.color": "#aaa",
    "text.color": "#ddd",          "grid.color": "#2a2a4a",
    "grid.linewidth": 0.5,         "legend.facecolor": "#16213e",
    "legend.edgecolor": "#444",    "font.family": "monospace",
    "font.size": 10,
})

STATE_COLORS = {
    "NORMAL":   "#00b894",
    "LIGHT":    "#74b9ff",
    "MODERATE": "#fdcb6e",
    "HEAVY":    "#d63031",
}
STATE_ORDER = ["NORMAL", "LIGHT", "MODERATE", "HEAVY"]


def latest(pattern):
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


def load_csv(path):
    rows = []
    with open(path) as f:
        for r in csv.DictReader(f):
            rows.append(r)
    return rows


def save(fig, name):
    p = os.path.join(PLOTDIR, name)
    fig.savefig(p, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"  Saved: {p}")
    plt.close(fig)


def get(row, *keys, default=0.0):
    """Try multiple column name variants — handles old + new controller output."""
    for k in keys:
        if k in row and row[k] not in ("", None):
            return row[k]
    return str(default)


# ── Load metrics ─────────────────────────────────────────────
metrics_file = latest(os.path.join(LOGDIR, "metrics_*.csv"))
adj_file     = latest(os.path.join(LOGDIR, "adjustments_*.csv"))
iperf_file   = latest(os.path.join(LOGDIR, "iperf_*.log"))

if not metrics_file:
    print(f"ERROR: No metrics_*.csv in {LOGDIR}/")
    print("Run the controller first, then plot.")
    sys.exit(1)

print(f"Loading metrics : {metrics_file}")
rows = load_csv(metrics_file)

# ── Column name aliases (old vs new controller) ───────────────
# old: t, drop_rate, backlog, throughput_mbps, drops_total, state, target_ms, limit
# new: t_s, drop_rate_per_s, backlog_pkts, throughput_mbps, drops_experiment, state, target_ms, limit_pkts

t          = np.array([float(get(r, "t_s", "t"))                         for r in rows])
drop_rate  = np.array([float(get(r, "drop_rate_per_s", "drop_rate"))     for r in rows])
backlog    = np.array([float(get(r, "backlog_pkts", "backlog"))           for r in rows])
throughput = np.array([float(get(r, "throughput_mbps"))                   for r in rows])
target_ms  = np.array([float(get(r, "target_ms"))                         for r in rows])
limit_p    = np.array([float(get(r, "limit_pkts", "limit"))              for r in rows])
drops_exp  = np.array([float(get(r, "drops_experiment", "drops_total"))  for r in rows])
states     = [get(r, "state", default="NORMAL") for r in rows]

# ── Load adjustments ──────────────────────────────────────────
adj_rows = []
if adj_file:
    print(f"Loading adjustments: {adj_file}")
    adj_rows = load_csv(adj_file)

# ── Load iperf time series (text -i 1 format) ─────────────────
iperf_t, iperf_mbps = [], []
if iperf_file:
    with open(iperf_file) as f:
        for line in f:
            m = re.match(
                r'\[SUM\]\s+[\d.]+-\s*([\d.]+)\s+sec.*?([\d.]+)\s+Mbits/sec', line)
            if m:
                iperf_t.append(float(m.group(1)))
                iperf_mbps.append(float(m.group(2)))
    print(f"iperf time series: {len(iperf_mbps)} points")


# ── Helper: shade background by state ────────────────────────
def shade_states(ax, t, states):
    if len(t) < 2:
        return
    prev_s, prev_t = states[0], t[0]
    for i in range(1, len(states)):
        if states[i] != prev_s or i == len(states) - 1:
            ax.axvspan(prev_t, t[i], alpha=0.10,
                       color=STATE_COLORS.get(prev_s, "#888"), zorder=1)
            prev_s, prev_t = states[i], t[i]


def mark_adjustments(ax, adj_rows):
    for i, adj in enumerate(adj_rows):
        ts = float(get(adj, "t_s", "t"))
        ax.axvline(ts, color="white", lw=0.8, alpha=0.55, ls="--",
                   label="adjustment" if i == 0 else "")


# ═════════════════════════════════════════════════════════════
# Figure 1 — 4-panel overview (main result figure)
# ═════════════════════════════════════════════════════════════
print("Plotting Fig 1: 4-panel overview...")
fig = plt.figure(figsize=(14, 10))
gs  = gridspec.GridSpec(2, 2, figure=fig, hspace=0.42, wspace=0.35)
fig.suptitle(
    "Part 3 — Adaptive fq_codel Controller: Measured Results\n"
    "Amritha S, VIT Chennai 2026",
    fontsize=13, fontweight="bold",
)

# ── (a) Throughput ────────────────────────────────────────────
ax = fig.add_subplot(gs[0, 0])
if len(iperf_mbps) > 5:
    ax.plot(iperf_t, iperf_mbps,
            color="#4ecdc4", lw=1.5, label="iperf3 measured")
else:
    ax.plot(t, throughput,
            color="#4ecdc4", lw=1.2, label="throughput (tc byte Δ)")
shade_states(ax, t, states)
ax.axhline(10, color="#888", ls="--", lw=0.8, label="10 Mbit bottleneck")
ax.set(xlabel="Time (s)", ylabel="Mbps", title="(a) Throughput")
ax.legend(fontsize=8)
ax.grid(True)

# ── (b) Instantaneous drop rate ───────────────────────────────
ax = fig.add_subplot(gs[0, 1])
ax.fill_between(t, drop_rate, color="#e94560", alpha=0.75, label="drops/sec (Δdrops/Δt)")
shade_states(ax, t, states)
mark_adjustments(ax, adj_rows)
ax.set(xlabel="Time (s)", ylabel="drops / sec",
       title="(b) Drop Rate — instantaneous\n(Δdrops / Δt per 0.5 s interval)")
ax.legend(fontsize=8)
ax.grid(True)

# ── (c) Queue backlog ─────────────────────────────────────────
ax = fig.add_subplot(gs[1, 0])
ax.fill_between(t, backlog, color="#f7dc6f", alpha=0.75, label="backlog (pkts)")
shade_states(ax, t, states)
mark_adjustments(ax, adj_rows)
ax.set(xlabel="Time (s)", ylabel="packets in queue",
       title="(c) Queue Backlog")
ax.legend(fontsize=8)
ax.grid(True)

# ── (d) Adaptive parameter evolution ─────────────────────────
ax  = fig.add_subplot(gs[1, 1])
ax2 = ax.twinx()
ax.step(t,  target_ms, color="#a29bfe", lw=2.0, where="post", label="target (ms)")
ax2.step(t, limit_p,   color="#fd79a8", lw=1.2, where="post",
         label="limit (pkts)", alpha=0.8)
shade_states(ax, t, states)
mark_adjustments(ax, adj_rows)
ax.set(xlabel="Time (s)", ylabel="target delay (ms)",
       title="(d) Adaptive Parameter Evolution\n(AIMD: β=0.9 decrease, α=0.5 ms increase)")
ax2.set_ylabel("limit (packets)", color="#fd79a8")
ax2.tick_params(colors="#fd79a8")
lines1, lab1 = ax.get_legend_handles_labels()
lines2, lab2 = ax2.get_legend_handles_labels()
ax.legend(lines1 + lines2, lab1 + lab2, fontsize=8)
ax.grid(True)

# ── shared state legend ───────────────────────────────────────
handles = [plt.Rectangle((0, 0), 1, 1,
           color=STATE_COLORS[s], alpha=0.4) for s in STATE_ORDER]
fig.legend(handles, STATE_ORDER,
           title="Congestion state (background shading)",
           loc="upper right", ncol=4, fontsize=8, framealpha=0.3)

save(fig, "part3_overview.png")


# ═════════════════════════════════════════════════════════════
# Figure 2 — State timeline
# ═════════════════════════════════════════════════════════════
print("Plotting Fig 2: State timeline...")
fig, ax = plt.subplots(figsize=(14, 4))
fig.suptitle("Part 3 — Congestion State Timeline", fontsize=12, fontweight="bold")

state_y = {s: i for i, s in enumerate(STATE_ORDER)}
y_vals  = [state_y.get(s, 0) for s in states]
sc_c    = [STATE_COLORS.get(s, "#888") for s in states]

ax.scatter(t, y_vals, c=sc_c, s=10, alpha=0.85, zorder=3)
mark_adjustments(ax, adj_rows)
ax.set(
    yticks=[0, 1, 2, 3], yticklabels=STATE_ORDER,
    xlabel="Time (s)",
    title="Congestion state per 0.5 s interval  |  dashed = AIMD parameter adjustment",
)
ax.grid(True, axis="x")
if adj_rows:
    ax.legend(fontsize=8)
save(fig, "part3_state_timeline.png")


# ═════════════════════════════════════════════════════════════
# Figure 3 — Drop rate: instantaneous vs cumulative (side by side)
# ═════════════════════════════════════════════════════════════
print("Plotting Fig 3: Drop rate analysis...")
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))
fig.suptitle("Part 3 — Drop Rate Analysis", fontsize=12, fontweight="bold")

ax1.fill_between(t, drop_rate, color="#e94560", alpha=0.75)
ax1.set(
    xlabel="Time (s)", ylabel="drops / sec",
    title="Instantaneous drop rate\n(correct: Δdrops / Δt per interval)",
)
ax1.grid(True)
shade_states(ax1, t, states)

ax2.plot(t, drops_exp, color="#e94560", lw=1.5)
ax2.set(
    xlabel="Time (s)", ylabel="cumulative drops (experiment-relative)",
    title="Cumulative drops since experiment start\n(zeroed at t=0, boot offset removed)",
)
ax2.grid(True)
save(fig, "part3_drop_analysis.png")


# ═════════════════════════════════════════════════════════════
# Figure 4 — Adjustments table
# ═════════════════════════════════════════════════════════════
if adj_rows:
    print("Plotting Fig 4: Adjustments table...")
    fig, ax = plt.subplots(figsize=(14, max(3, len(adj_rows) * 0.35 + 1.5)))
    fig.suptitle("Part 3 — AIMD Adjustment Log", fontsize=12, fontweight="bold")
    ax.axis("off")

    headers = ["Time (s)", "State", "Old target", "New target",
               "Old interval", "New interval", "Old limit", "New limit", "Reason"]

    def row_vals(r):
        return [
            get(r, "t_s", "t"),
            get(r, "state"),
            get(r, "old_target_ms", "old_target"),
            get(r, "new_target_ms", "new_target"),
            get(r, "old_interval_ms", "old_interval", default="—"),
            get(r, "new_interval_ms", "new_interval", default="—"),
            get(r, "old_limit_pkts", "old_limit"),
            get(r, "new_limit_pkts", "new_limit"),
            get(r, "reason")[:35],
        ]

    table_data = [row_vals(r) for r in adj_rows[:25]]
    if not table_data:
        table_data = [["—"] * len(headers)]

    tbl = ax.table(cellText=table_data, colLabels=headers,
                   cellLoc="center", loc="center")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8)
    tbl.scale(1.1, 1.45)
    for (row, col), cell in tbl.get_celld().items():
        cell.set_facecolor("#16213e" if row > 0 else "#0f3460")
        cell.set_edgecolor("#0f3460")
        cell.set_text_props(color="#e0e0e0")

    save(fig, "part3_adjustments.png")
else:
    print("  No adjustment log found — skipping table.")


# ═════════════════════════════════════════════════════════════
# Summary stats
# ═════════════════════════════════════════════════════════════
state_counts = {s: states.count(s) for s in STATE_ORDER}
total = len(states)
print("\n══ Summary ══════════════════════════════════")
print(f"  Duration        : {t[-1]:.1f} s")
print(f"  Total ticks     : {total}")
print(f"  Adjustments     : {len(adj_rows)}")
print(f"  Avg drop rate   : {drop_rate.mean():.2f} drops/sec")
print(f"  Max drop rate   : {drop_rate.max():.2f} drops/sec")
print(f"  Avg backlog     : {backlog.mean():.1f} pkts")
print(f"  Avg throughput  : {throughput.mean():.3f} Mbps")
print(f"  State distribution:")
for s in STATE_ORDER:
    pct = 100 * state_counts[s] / total if total else 0
    bar = "█" * int(pct / 3)
    print(f"    {s:>10}: {pct:5.1f}%  {bar}")
print(f"\n  Plots → {PLOTDIR}/")
