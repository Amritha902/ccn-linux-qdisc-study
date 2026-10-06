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
  fig17_main_outputs_<wl>.png              the four main outputs compared

Per-run figures are produced by src/make_gallery.py as
  run<NN>_<label>.png
"""
import argparse, csv, glob, json, math, os, re, statistics as st
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Categorical hues, validated for colour-vision deficiency. The previous set
# put CoDel on #E45756 and RED on #54A24B, which a deuteranope reads as the
# same colour (CVD Delta E 1.2 against a floor of 8), and those two sit next to
# each other in every comparison figure.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
          "#e87ba4", "#008300", "#4a3aa7", "#e34948"]

# The ten-system comparisons do not use those hues at all. Each system is
# already named on the category axis, so colour carrying identity as well is
# redundant, and ten identities cannot be separated under CVD whatever the
# hues. Colour is therefore used only for emphasis: the unmanaged baseline, the
# system under test, and everything else in one neutral ink.
INK      = "#5B6670"   # every system with no special role
BASE_HL  = "#e34948"   # pfifo, the unmanaged baseline
TEST_HL  = "#2a78d6"   # the three fq_codel arms, the systems under test
GRID, TEXT = "#D9D9D9", "#2B2B2B"
# Scientific Reports and most journals require raster figures at 300 dpi or
# better at the size they are printed. 150 is a screen resolution.
FIG_DPI = 300


# Figures are placed at 0.95\linewidth and scaled down again to fit
# 0.4\textheight, so a 9 pt label in the PNG can reach the page at under 6 pt.
# Type is sized here for the printed result rather than for the PNG.
plt.rcParams.update({
    "font.size": 12,
    "axes.titlesize": 13,
    "axes.labelsize": 13,
    "xtick.labelsize": 11.5,
    "ytick.labelsize": 11.5,
    "legend.fontsize": 12,
    "figure.titlesize": 14,
})

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
        ax.set_title(title, fontsize=13, color=TEXT, pad=8)
    ax.set_xlabel(xlabel, fontsize=12.5, color=TEXT)
    ax.set_ylabel(ylabel, fontsize=12.5, color=TEXT)
    ax.grid(True, color=GRID, linewidth=0.6, alpha=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=TEXT, labelsize=11.5)


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
    """Emphasis, not identity. See the note beside INK."""
    if k == "pfifo":
        return BASE_HL
    if k.startswith("fq_codel"):
        return TEST_HL
    return INK


def series(groups, metric):
    out = []
    for k, g in groups:
        m, h, _ = ci95([x.get(metric) for x in g])
        if m is not None:
            out.append((k, DISPLAY.get(k, k), m, h))
    return out


def dots(ax, groups, metric, ylabel, fmt="%.0f", logy=True, clip_hi=None):
    """Position-encoded comparison for a quantity spanning orders of magnitude.

    Bars were used here previously, on a logarithmic axis. A bar states its
    value by its length, and length is only defined from zero, which a log axis
    does not have: the baseline was wherever the axis happened to stop. The
    effect was to understate the result, with pfifo's 102-fold tail latency
    drawn about five times taller than fq_codel's. A dot states its value by
    position alone, which a log axis does support.
    """
    d = series(groups, metric)
    if not d:
        return []
    x = np.arange(len(d))
    vals = [m for _, _, m, _ in d]
    errs = [h for _, _, _, h in d]
    if clip_hi is not None:
        errs = [min(h, clip_hi - m) for _, _, m, h in d]
    for i, (k, _, m, _) in enumerate(d):
        ax.vlines(i, min(vals) * (0.55 if logy else 0), m,
                  color=GRID, linewidth=1.4, zorder=1)
        ax.errorbar(i, m, yerr=[[max(errs[i], 0)], [max(errs[i], 0)]],
                    fmt="o", markersize=11, color=colour(k), ecolor=colour(k),
                    elinewidth=1.8, capsize=5, markeredgecolor="white",
                    markeredgewidth=1.4, zorder=3)
    if logy:
        ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels([lab.replace("\n", " ") for _, lab, _, _ in d],
                       fontsize=11, rotation=28, ha="right",
                       rotation_mode="anchor")
    ax.set_xlim(-0.6, len(d) - 0.4)
    span = (max(vals) / min(vals)) if logy else 1
    for i, (_, _, m, _) in enumerate(d):
        ax.annotate(fmt % m, (i, m), textcoords="offset points",
                    xytext=(0, 15), ha="center", fontsize=11, color=TEXT)
    if logy:
        ax.set_ylim(min(vals) * 0.55, max(vals) * (2.2 if span > 20 else 1.6))
    style(ax, ylabel=ylabel)
    return vals


def bars(ax, groups, metric, ylabel, logy=False, annotate=True, fmt="%.0f",
         clip_hi=None):
    """Zero-based bars. A bar's length is its value, so the axis starts at zero.

    The earlier version cropped the axis to the data range whenever the spread
    was small, which turned a 0.8% difference in goodput into bars of visibly
    different height, and computed that range from the means alone, so the
    error bars were clipped off the top of the panel.
    """
    d = series(groups, metric)
    if not d:
        return []
    labels = [lab for _, lab, _, _ in d]
    vals = [m for _, _, m, _ in d]
    errs = [h for _, _, _, h in d]
    if clip_hi is not None:
        errs = [min(h, clip_hi - m) for _, _, m, h in d]
    cols = [colour(k) for k, _, _, _ in d]
    x = np.arange(len(vals))
    ax.bar(x, vals, yerr=errs, capsize=4, color=cols,
           edgecolor="white", linewidth=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels([l.replace("\n", " ") for l in labels], fontsize=11,
                       rotation=28, ha="right", rotation_mode="anchor")
    if logy:
        ax.set_yscale("log")
    top = max(v + e for v, e in zip(vals, errs))
    if not logy:
        ax.set_ylim(0, top * 1.16)
    if annotate:
        for i, (v, e) in enumerate(zip(vals, errs)):
            ax.text(i, v + e + top * 0.025, fmt % v, ha="center",
                    fontsize=11, color=TEXT)
    style(ax, ylabel=ylabel)
    return vals


def save(fig, outdir, name):
    # Several figures set a two-line suptitle and then let the axes default
    # into it, so panel titles printed on top of the subtitle. Reserve the
    # banner space here rather than per figure, and leave anything that has
    # already laid itself out alone.
    if getattr(fig, "_suptitle", None) is not None and \
            not getattr(fig, "_acape_laid_out", False):
        lines = fig._suptitle.get_text().count("\n") + 1
        top = {1: 0.93, 2: 0.88, 3: 0.84}.get(lines, 0.80)
        try:
            fig.tight_layout(rect=[0, 0, 1, top])
        except Exception:
            pass
    p = os.path.join(outdir, name)
    fig.savefig(p, dpi=FIG_DPI, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"  {name}")
    return p


SUB = "10 Mbit bottleneck · 8 TCP CUBIC flows · 20 ms base RTT · mean ± 95% CI over 3 seeds"


# ── fig01: tail latency ───────────────────────────────────────────────────
def fig01(runs, wl, od):
    g = grouped(runs, wl)
    if not g:
        return
    fig, ax = plt.subplots(figsize=(9.5, 5.6)); fig.patch.set_facecolor("white")
    v = dots(ax, g, "sparse_rtt_p95_ms", "p95 RTT (ms, log scale)",
             fmt="%.0f", logy=True)
    if v:
        ax.text(0.98, 0.95, f"{max(v)/min(v):.0f}x spread",
                transform=ax.transAxes, ha="right", fontsize=13,
                fontweight="bold", color=TEXT)
    fig.suptitle(f"Tail latency (sparse probe flow) — {wl} workload\n{SUB}",
                 fontsize=12, color=TEXT)
    save(fig, od, f"fig01_latency_tail_{wl}.png")


# ── fig02: sparse vs bulk latency ─────────────────────────────────────────
def fig02(runs, wl, od):
    g = grouped(runs, wl)
    if not g:
        return
    fig, ax = plt.subplots(figsize=(10.5, 5.8)); fig.patch.set_facecolor("white")
    labels, sp, spe, bl, ble = [], [], [], [], []
    for k, grp in g:
        a, ae, _ = ci95([x.get("sparse_rtt_mean_ms") for x in grp])
        b, be, _ = ci95([x.get("bulk_rtt_mean_ms") for x in grp])
        if a is None or b is None:
            continue
        labels.append(DISPLAY.get(k, k)); sp.append(a); spe.append(ae)
        bl.append(b); ble.append(be)
    x = np.arange(len(labels))
    # paired dots joined by a rule: the gap between the two is the quantity
    # being argued about, and on a log axis only position can carry it
    for i, (a, b) in enumerate(zip(sp, bl)):
        ax.vlines(i, min(a, b), max(a, b), color=GRID, linewidth=2.4, zorder=1)
        ax.annotate(f"{b/a:.1f}x", (i, math.sqrt(a * b)),
                    textcoords="offset points", xytext=(11, -3), ha="left",
                    fontsize=10.5, color=TEXT, zorder=5,
                    bbox=dict(boxstyle="round,pad=0.12", fc="white",
                              ec="none", alpha=0.9))
    ax.errorbar(x, sp, yerr=spe, fmt="o", markersize=10, color=SERIES[0],
                ecolor=SERIES[0], elinewidth=1.6, capsize=4, linestyle="none",
                markeredgecolor="white", markeredgewidth=1.3, zorder=3,
                label="sparse probe flow (ICMP)")
    ax.errorbar(x, bl, yerr=ble, fmt="s", markersize=10, color=SERIES[1],
                ecolor=SERIES[1], elinewidth=1.6, capsize=4, linestyle="none",
                markeredgecolor="white", markeredgewidth=1.3, zorder=3,
                label="bulk TCP flows (in-band)")
    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels([l.replace("\n", " ") for l in labels], fontsize=11,
                       rotation=28, ha="right", rotation_mode="anchor")
    ax.set_xlim(-0.6, len(labels) - 0.4)
    ax.legend(frameon=False, fontsize=12, loc="upper right")
    style(ax, ylabel="Mean RTT (ms, log scale)")
    fig.suptitle(f"Sparse probe vs bulk flow latency — {wl} workload\n"
                 "fq_codel's new-flow heuristic privileges the probe, so the two differ; "
                 "quoting only the probe overstates the benefit for bulk traffic",
                 fontsize=11.5, color=TEXT)
    save(fig, od, f"fig02_latency_sparse_vs_bulk_{wl}.png")


# ── fig03-06: single-metric panels ────────────────────────────────────────
def _single(runs, wl, od, metric, ylabel, name, title, logy=False, fmt="%.2f",
            zoom=False, clip_hi=None, dot=False):
    g = grouped(runs, wl)
    if not g:
        return
    fig, ax = plt.subplots(figsize=(9.5, 5.4)); fig.patch.set_facecolor("white")
    if dot:
        v = dots(ax, g, metric, ylabel, fmt=fmt, logy=True)
        fig.suptitle(f"{title} — {wl} workload\n{SUB}", fontsize=14, color=TEXT)
        save(fig, od, name)
        return
    v = bars(ax, g, metric, ylabel, logy=logy, fmt=fmt, clip_hi=clip_hi)
    if zoom and v:
        # The axis is NOT cropped to the data any more. The point of these two
        # panels is that the quantity does not vary, and a zero-based axis is
        # what shows that; cropping it manufactured the opposite impression.
        spread = 100 * (max(v) - min(v)) / max(st.fmean(v), 1e-9)
        ax.text(0.5, 0.92, f"full range of all ten systems: {spread:.1f}%",
                transform=ax.transAxes, ha="center", fontsize=12.5,
                color=TEXT)
    fig.suptitle(f"{title} — {wl} workload\n{SUB}", fontsize=12, color=TEXT)
    save(fig, od, name)


def fig03(runs, wl, od):
    _single(runs, wl, od, "throughput_mbps", "Goodput (Mbps)",
            f"fig03_throughput_{wl}.png", "Goodput", fmt="%.2f", zoom=True)


def fig04(runs, wl, od):
    _single(runs, wl, od, "backlog_mean_pkts", "Mean backlog (pkts, log)",
            f"fig04_backlog_{wl}.png", "Queue occupancy", fmt="%.0f", dot=True)


def fig05(runs, wl, od):
    # Jain's index is bounded above by 1. A symmetric interval on three seeds
    # put pfifo's upper limit at 1.0067, which is not a possible value, so the
    # interval is truncated at the bound and the bound is drawn.
    _single(runs, wl, od, "jain", "Jain's fairness index",
            f"fig05_fairness_{wl}.png", "Flow fairness", fmt="%.4f", zoom=True,
            clip_hi=1.0)


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
    # Two faults here previously. The x-axis was cropped to 9.28-9.60 Mbps, a
    # 3% window of noise, under a subtitle reading "down and to the right is
    # better", which invited reading horizontal position as a throughput
    # trade-off when every goodput interval overlaps. And seven of the ten
    # labels landed on each other in the bottom cluster, printing as a solid
    # smear. The axis now runs from zero to the link rate, which is what shows
    # that goodput does not vary, and the labels are placed in a column with a
    # leader line to each point so none can collide.
    pts = []
    for k, grp in g:
        x, xe, _ = ci95([r.get("throughput_mbps") for r in grp])
        y, ye, _ = ci95([r.get("sparse_rtt_p95_ms") for r in grp])
        if x is not None and y is not None:
            pts.append((k, x, xe, y, ye))
    if not pts:
        return
    fig, ax = plt.subplots(figsize=(9.5, 6.2)); fig.patch.set_facecolor("white")
    for k, x, xe, y, ye in pts:
        ax.errorbar(x, y, xerr=xe, yerr=ye, fmt="o", color=colour(k),
                    markersize=11, capsize=4, elinewidth=1.6,
                    markeredgecolor="white", markeredgewidth=1.4, zorder=3)
    ax.set_yscale("log")
    ax.set_xlim(0, 10.4)
    ax.axvline(10.0, color=GRID, linewidth=1.4, zorder=0)
    ax.annotate("link rate", (10.0, min(p[3] for p in pts)),
                textcoords="offset points", xytext=(-7, -2), ha="right",
                va="bottom", fontsize=11, color=TEXT)

    # labels in a column to the right of the cloud, vertical positions pushed
    # apart in display space so that no two can overlap
    fig.canvas.draw()
    order = sorted(pts, key=lambda t: t[3])
    ymin, ymax = ax.get_ylim()
    lo = ax.transData.transform((0, ymin))[1]
    hi = ax.transData.transform((0, ymax))[1]
    need = 17.0
    want = [ax.transData.transform((0, t[3]))[1] for t in order]
    placed, last = [], lo - need
    for wpos in want:
        pos = max(wpos, last + need)
        placed.append(pos); last = pos
    overflow = placed[-1] - (hi - need * 0.5)
    if overflow > 0:
        placed = [q - overflow for q in placed]
    xlab = 10.9
    for (k, x, xe, y, ye), ypix in zip(order, placed):
        ylab = ax.transData.inverted().transform((0, ypix))[1]
        ax.annotate(DISPLAY.get(k, k).replace("\n", " "),
                    xy=(x + xe, y), xycoords="data",
                    xytext=(xlab, ylab), textcoords="data",
                    fontsize=11.5, color=TEXT, va="center", ha="left",
                    arrowprops=dict(arrowstyle="-", color=GRID, linewidth=1.0,
                                    shrinkA=2, shrinkB=2))
    ax.set_xlim(0, 14.6)
    # ticks stop at the link rate; the space to its right holds the label
    # column only, so ticks out there would imply measurements that cannot
    # exist
    ax.set_xticks([0, 2, 4, 6, 8, 10])
    style(ax, xlabel="Goodput (Mbps), axis from zero to the link rate",
          ylabel="p95 RTT (ms, log scale)")
    fig.suptitle(f"Latency against throughput — {wl} workload\n"
                 "Latency spans two orders of magnitude; goodput does not vary, "
                 "so there is no trade-off to read horizontally",
                 fontsize=13, color=TEXT)
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
    # Two changes from the earlier version of this figure.
    #
    # The colour scale was red to green, which a deuteranope cannot read, and
    # it is the pairing reviewers flag most often. Rank here runs in one
    # direction, best to worst, so it is a sequential quantity and takes a
    # single-hue ramp: light is best, dark is worst, and the ordering survives
    # any colour vision and a greyscale print.
    #
    # Colour is still normalised within each row, which is what makes a row
    # readable, but on its own that gave the fairness row, whose ten systems
    # differ by 0.5% and not significantly, the same full light-to-dark range
    # as probe RTT mean, whose systems differ by 78 times. The spread column on
    # the right states each row's actual range, so a row of large colour
    # contrast and no real difference cannot be mistaken for a finding.
    spread = []
    for row in raw:
        vals = [v for v in row if v is not None]
        if not vals or min(vals) <= 0:
            spread.append("")
        else:
            r = max(vals) / min(vals)
            spread.append(f"{r:.0f}x" if r >= 10 else f"{r:.2f}x")
    fig, ax = plt.subplots(figsize=(1.18 * len(names) + 5.0,
                                    0.62 * len(HEAT) + 2.8))
    fig.patch.set_facecolor("white")
    im = ax.imshow(M, cmap="Blues", aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=35, ha="right", fontsize=11)
    ax.set_yticks(range(len(HEAT)))
    ax.set_yticklabels([h[1] for h in HEAT], fontsize=11.5)
    for i in range(len(HEAT)):
        for j in range(len(names)):
            v = raw[i][j]
            if v is None:
                continue
            txt = f"{v:.0f}" if abs(v) >= 100 else f"{v:.3g}"
            ax.text(j, i, txt, ha="center", va="center", fontsize=10,
                    color="white" if M[i, j] > 0.55 else TEXT)
    ax.set_xlim(-0.5, len(names) - 0.5 + 1.9)
    for i, sp in enumerate(spread):
        ax.text(len(names) - 0.5 + 0.95, i, sp, ha="center", va="center",
                fontsize=10.5, color=TEXT)
    ax.text(len(names) - 0.5 + 0.95, -0.85, "spread\n(max/min)", ha="center",
            va="center", fontsize=10.5, color=TEXT)
    cb = fig.colorbar(im, ax=ax, shrink=0.62, pad=0.02)
    cb.set_ticks([0.03, 0.97]); cb.set_ticklabels(["best", "worst"])
    cb.ax.tick_params(labelsize=11)
    ax.set_title(f"All measured parameters — {wl} workload\n"
                 "Colour is each row's rank, light best to dark worst. Cells are "
                 "the measured means.\nThe spread column gives the row's real "
                 "range, so a row with strong colour contrast and no\n"
                 "meaningful difference, such as fairness, cannot be read as one.",
                 fontsize=12.5, color=TEXT, pad=14)
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

            m = st.fmean(ys)
            ax.hlines(m, i - 0.32, i + 0.32, color=TEXT, linewidth=2, zorder=4)
            if len(ys) > 1:
                ax.vlines(i, min(ys), max(ys), color=colour(k),
                          linewidth=1.2, alpha=0.5, zorder=2)
        if not any_pt:
            plt.close(fig); continue
        ax.set_xticks(range(len(g)))
        ax.set_xticklabels([DISPLAY.get(k, k).replace("\n", " ")
                            for k, _ in g], fontsize=11, rotation=28,
                           ha="right", rotation_mode="anchor")
        if logy and metric != "jain":
            ax.set_yscale("log")
        style(ax, ylabel=label)
        fig.suptitle(f"Per-seed values: {label} — {wl} workload\n"
                     "every individual run shown; black bar = mean across seeds",
                     fontsize=14, color=TEXT)
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

    ax[0][0].plot(t, [float(x["target_ms"]) for x in rows], color=SERIES[0], lw=1.8)
    ax[0][0].axhline(5.0, color=SERIES[1], ls="--", lw=1.2, label="static default 5 ms")
    ax[0][0].legend(frameon=False, fontsize=8.5)
    style(ax[0][0], "(a) fq_codel target under control", "Time (s)", "target (ms)")

    ax[0][1].plot(t, [float(x["backlog_pkts"]) for x in rows], color=SERIES[2], lw=1.4)
    style(ax[0][1], "(b) Queue backlog", "Time (s)", "packets")

    ax[1][0].plot(t, [int(x["active_flows"]) for x in rows], color=SERIES[1],
                  lw=1.4, label="active flows")
    ax[1][0].plot(t, [int(x["elephant_flows"]) for x in rows], color=SERIES[4],
                  lw=1.4, label="elephant flows")
    ax[1][0].legend(frameon=False, fontsize=8.5)
    style(ax[1][0], "(c) eBPF flow telemetry", "Time (s)", "flows")

    regs = ["NORMAL", "LIGHT", "MODERATE", "HEAVY"]
    ax[1][1].step(t, [regs.index(x["regime"]) for x in rows], where="post",
                  color=SERIES[6], lw=1.6)
    ax[1][1].set_yticks(range(4)); ax[1][1].set_yticklabels(regs, fontsize=8.5)
    style(ax[1][1], "(d) Congestion regime", "Time (s)")

    fig.suptitle(f"ACAPE controller behaviour — {r['label']}", fontsize=12.5, color=TEXT)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    save(fig, od, "fig12_controller_behaviour.png")


# ── fig13: sham control ─ differences from static, not truncated bars ──
# An earlier version drew four bar charts with the y-axis cropped to the data
# range. A bar encodes its value by length, so cropping the baseline turned
# differences of a fraction of a percent into bars of visibly different
# height, and the axis limit was computed from the means alone, which clipped
# the error bars off the top of the panel. Both faults pushed the same way:
# toward seeing an effect. What the runs actually show is that no arm is
# separable from any other, so the figure now plots each arm's difference from
# static with the confidence interval of that difference, against a zero line.
# An interval covering zero is the result, and it is legible as such.
def fig13(runs, wl, od):
    want = ["fq_codel", "fq_codel_sham", "fq_codel_acape"]
    g = dict((k, grp) for k, grp in grouped(runs, wl) if k in want)
    if "fq_codel" not in g or len(g) < 2:
        return
    metrics = [("sparse_rtt_mean_ms", "probe RTT"),
               ("bulk_rtt_mean_ms", "bulk RTT"),
               ("backlog_mean_pkts", "mean backlog"),
               ("throughput_mbps", "goodput")]
    arms = [k for k in ("fq_codel_sham", "fq_codel_acape") if k in g]

    fig, ax = plt.subplots(figsize=(10.5, 5.0))
    fig.patch.set_facecolor("white")
    offs = {arms[0]: 0.19}
    if len(arms) > 1:
        offs[arms[1]] = -0.19
    seen = set()
    for row, (metric, lbl) in enumerate(metrics):
        base = [x.get(metric) for x in g["fq_codel"] if x.get(metric) is not None]
        bm, bh, bn = ci95(base)
        if bm is None or bm == 0:
            continue
        for k in arms:
            vs = [x.get(metric) for x in g[k] if x.get(metric) is not None]
            m, h, n = ci95(vs)
            if m is None:
                continue
            # difference as a percentage of the static arm, with the two
            # intervals combined in quadrature
            d = (m - bm) / bm * 100.0
            e = math.sqrt(h ** 2 + bh ** 2) / bm * 100.0
            y = row + offs[k]
            covers = abs(d) <= e
            ax.errorbar(d, y, xerr=e, fmt="o", markersize=7,
                        color=colour(k), ecolor=colour(k), elinewidth=1.6,
                        capsize=4, markerfacecolor=colour(k) if not covers
                        else "white", markeredgewidth=1.6,
                        label=DISPLAY.get(k, k).replace("\n", " ")
                        if k not in seen else None)
            seen.add(k)
            # label on the marker's own line, masked so the whisker does
            # not run through it. Placing it past the whisker end strands the
            # number far from its marker when the interval is wide.
            ax.annotate(f"{d:+.2f}%", (d, y), textcoords="offset points",
                        xytext=(9, 0), ha="left", va="center",
                        fontsize=8.5, color=TEXT,
                        bbox=dict(boxstyle="round,pad=0.15", fc="white",
                                  ec="none", alpha=0.92))

    ax.axvline(0, color=TEXT, linewidth=1.2, zorder=0)
    ax.set_yticks(range(len(metrics)))
    ax.set_yticklabels([l for _, l in metrics], fontsize=10)
    ax.set_ylim(-0.75, len(metrics) - 0.25)
    style(ax, xlabel="difference from static fq_codel (%), 95% CI")
    ax.legend(frameon=False, fontsize=9, loc="upper center",
              bbox_to_anchor=(0.5, -0.17), ncol=2)
    lo, hi = ax.get_xlim()
    pad = (hi - lo) * 0.06
    ax.set_xlim(lo - pad, hi + pad)
    fig.suptitle(
        f"Sham-controller control condition ─ {wl} workload\n"
        "The sham arm polls at the controller's cadence and applies nothing, "
        "so static against sham is the controller's cost and sham against "
        "ACAPE is its decisions.\n"
        "Every interval covers zero: on this workload neither the cost nor "
        "the decisions are separable from the static arm. Open markers mark "
        "the intervals that cover zero.",
        fontsize=10.5, color=TEXT)
    fig.tight_layout(rect=[0, 0.02, 1, 0.82])
    fig._acape_laid_out = True
    save(fig, od, f"fig13_sham_control_{wl}.png")



# ── fig17: the main measured outputs, compared ───────────────────────────
# Added because neither of the other comparison figures answers the question
# a reader actually arrives with. fig01 shows one output across the systems;
# fig08 shows every output but encodes rank rather than magnitude, so two
# cells of the same colour can differ by a factor of eighty. This figure puts
# the four outputs the study is about side by side, on their own scales, with
# every value printed, so the comparison between the unmanaged baseline, the
# Linux default, the adapted system and the best alternative can be read off
# directly.
MAIN_OUT = [
    ("sparse_rtt_p95_ms",   "Tail latency, sparse probe\np95 RTT (ms)", True),
    ("bulk_rtt_mean_ms",    "Bulk-flow latency\nmean RTT (ms)",        True),
    ("backlog_mean_pkts",   "Queue occupancy\nmean backlog (packets)", True),
    ("throughput_mbps",     "Goodput\n(Mbit/s)",                       False),
]


def fig17(runs, wl, od):
    g = grouped(runs, wl)
    if not g:
        return
    order = [k for k in ORDER if k in dict(g)]
    gd = dict(g)
    # Two by two rather than one by four. In a single-column journal page a
    # four-panel strip is scaled to about a third of its drawn width and its
    # labels stop being readable; a square grid keeps the type at size.
    fig, axgrid = plt.subplots(2, 2, figsize=(13.0, 9.0))
    fig.patch.set_facecolor("white")
    axes = axgrid.ravel()

    for ax, (metric, label, logx) in zip(axes, MAIN_OUT):
        rows = []
        for k in order:
            m, h, _ = ci95([r.get(metric) for r in gd[k]])
            if m is not None:
                rows.append((k, m, h))
        if not rows:
            continue
        y = np.arange(len(rows))[::-1]
        vals = [m for _, m, _ in rows]
        errs = [h for _, _, h in rows]
        cols = [colour(k) for k, _, _ in rows]
        if logx:
            # Dots, not bars. A bar states its value by its length and length
            # is only defined from zero, which a logarithmic axis does not
            # have; on a log axis the bar would start wherever the axis
            # happened to stop. Only the goodput panel, which is linear and
            # zero-based, is drawn as bars.
            ax.set_xscale("log")
            lo = min(vals) * 0.45
            for yy, (k, m, h) in zip(y, rows):
                ax.hlines(yy, lo, m, color=GRID, linewidth=1.4, zorder=1)
            for yy, (k, m, h) in zip(y, rows):
                ax.errorbar([m], [yy], xerr=[[h], [h]], fmt="o",
                            markersize=10, color=colour(k), ecolor=colour(k),
                            elinewidth=1.5, capsize=4,
                            markeredgecolor="white", markeredgewidth=1.3,
                            zorder=3)
            ax.set_xlim(lo, max(vals) * 3.4)
        else:
            ax.barh(y, vals, xerr=errs, color=cols, edgecolor="white",
                    linewidth=0.8, height=0.72,
                    error_kw=dict(elinewidth=1.4, capsize=3))
            ax.set_xlim(0, max(v + e for v, e in zip(vals, errs)) * 1.30)
        for yy, (k, m, h) in zip(y, rows):
            txt = f"{m:,.0f}" if m >= 100 else (f"{m:.1f}" if m >= 10
                                                else f"{m:.2f}")
            ax.text(m + h + (m * 0.10 if logx else max(vals) * 0.03), yy, txt,
                    va="center", ha="left", fontsize=11, color=TEXT)
        ax.set_yticks(y)
        ax.set_yticklabels([DISPLAY.get(k, k).replace("\n", " ")
                            for k, _, _ in rows], fontsize=11)
        ax.set_title(label, fontsize=12.5, color=TEXT, pad=10)
        ax.grid(True, axis="x", color=GRID, linewidth=0.6, alpha=0.8)
        ax.set_axisbelow(True)
        for sp in ("top", "right", "left"):
            ax.spines[sp].set_visible(False)
        ax.spines["bottom"].set_color(GRID)
        ax.tick_params(colors=TEXT, labelsize=10.5)
        ax.set_xlabel("logarithmic scale" if logx else "linear, from zero",
                      fontsize=10, color=TEXT)

    # Springer Nature style puts the description in the caption, not inside
    # the image, so no title is drawn here.
    fig.tight_layout(h_pad=3.2, w_pad=2.0)
    fig._acape_laid_out = True
    save(fig, od, f"fig17_main_outputs_{wl}.png")


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
                   fig07, fig08, fig09, fig10, fig11, fig13, fig17):
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
