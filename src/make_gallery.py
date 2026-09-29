#!/usr/bin/env python3
"""Render one labelled figure per experiment run, plus an index.

Produces a complete visual record of the suite: every run gets its own panel
set showing what the queue actually did, captioned with the run's parameters
and measured summary. The index lists every run so none is hidden.
"""
import argparse, csv, glob, json, os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

PALETTE = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2", "#B279A2"]
GRID, TEXT = "#D9D9D9", "#2B2B2B"


def style(ax, title="", xlabel="", ylabel=""):
    ax.set_title(title, fontsize=10, color=TEXT)
    ax.set_xlabel(xlabel, fontsize=9, color=TEXT)
    ax.set_ylabel(ylabel, fontsize=9, color=TEXT)
    ax.grid(True, color=GRID, linewidth=0.6, alpha=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=TEXT, labelsize=8)


def ping_series(path):
    """Extract (seq-ordered) RTT samples from a ping log."""
    import re
    if not os.path.exists(path):
        return []
    return [float(m) for m in re.findall(r"time=([\d.]+) ms", open(path).read())]


def render(d, outdir, step):
    s = json.load(open(os.path.join(d, "summary.json")))
    ts = os.path.join(d, "qdisc_timeseries.csv")
    if not os.path.exists(ts):
        return None
    rows = list(csv.DictReader(open(ts)))[1:]
    if not rows:
        return None
    t = [float(r["t_s"]) for r in rows]

    fig, ax = plt.subplots(1, 4, figsize=(16, 3.6))
    fig.patch.set_facecolor("white")

    ax[0].plot(t, [float(r["backlog_pkts"]) for r in rows],
               color=PALETTE[0], linewidth=1.3)
    style(ax[0], "Queue backlog", "Time (s)", "packets")

    ax[1].plot(t, [float(r["throughput_mbps"]) for r in rows],
               color=PALETTE[2], linewidth=1.3)
    ax[1].axhline(s.get("rate_mbit", 10), color=PALETTE[3], ls="--", lw=1,
                  label=f"{s.get('rate_mbit', 10):.0f} Mbit link")
    ax[1].legend(frameon=False, fontsize=8)
    style(ax[1], "Throughput at the qdisc", "Time (s)", "Mbps")

    ax[2].plot(t, [float(r["drop_rate_per_s"]) for r in rows],
               color=PALETTE[1], linewidth=1.1)
    style(ax[2], "Drop rate", "Time (s)", "drops/s")

    rtts = ping_series(os.path.join(d, "ping.log"))
    if rtts:
        ax[3].plot(range(len(rtts)), rtts, color=PALETTE[5], linewidth=1.0)
        ax[3].set_yscale("log")
        style(ax[3], "Measured RTT (ping)", "sample", "ms (log)")
    else:
        ax[3].text(0.5, 0.5, "no ping data", ha="center", transform=ax[3].transAxes)
        style(ax[3], "Measured RTT (ping)")

    cap = (f"RUN {step}   {s['label']}   |   "
           f"AQM: {s['qdisc_kind']} {s['qdisc_args']}   |   "
           f"{s['flows']} flows, {s['workload']} workload, seed {s['seed']}, "
           f"{s['duration_s']} s, {s['rate_mbit']:.0f} Mbit, "
           f"{s['base_rtt_ms']} ms base RTT"
           + ("   |   ADAPTIVE CONTROLLER ON" if s.get("adaptive") else "")
           + ("  + eBPF" if s.get("ebpf") else ""))
    meas = (f"measured:  goodput {s.get('throughput_mbps', float('nan')):.2f} Mbps   "
            f"mean RTT {s.get('rtt_mean_ms', float('nan')):.1f} ms   "
            f"p95 RTT {s.get('rtt_p95_ms', float('nan')):.1f} ms   "
            f"mean backlog {s.get('backlog_mean_pkts', float('nan')):.1f} pkt   "
            f"Jain {s.get('jain') if s.get('jain') is not None else float('nan')}   "
            f"retransmits {s.get('retransmits')}")
    fig.suptitle(cap + "\n" + meas, fontsize=10, color=TEXT, y=1.02)
    fig.tight_layout()
    path = os.path.join(outdir, f"run{step}_{s['label']}.png")
    fig.savefig(path, dpi=110, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return path, s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    ap.add_argument("--outdir", default="figures/runs")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    dirs = sorted(glob.glob(os.path.join(a.results, "*")))
    index = []
    n = 0
    for d in dirs:
        if not os.path.exists(os.path.join(d, "summary.json")):
            continue
        n += 1
        out = render(d, a.outdir, f"{n:02d}")
        if not out:
            print(f"  skipped {d}")
            continue
        path, s = out
        index.append({"run": f"{n:02d}", "label": s["label"],
                      "image": os.path.basename(path),
                      "aqm": s["qdisc_kind"], "workload": s["workload"],
                      "seed": s["seed"], "adaptive": s.get("adaptive"),
                      "ebpf": s.get("ebpf"),
                      "goodput_mbps": s.get("throughput_mbps"),
                      "rtt_p95_ms": s.get("rtt_p95_ms"),
                      "backlog_mean_pkts": s.get("backlog_mean_pkts")})
        print(f"  RUN {n:02d}  {s['label']}")
    with open(os.path.join(a.outdir, "index.json"), "w") as fh:
        json.dump(index, fh, indent=2)
    with open(os.path.join(a.outdir, "INDEX.md"), "w") as fh:
        fh.write("# Experiment run index\n\n")
        fh.write("Every run in the suite, with its own figure. "
                 "No run is omitted.\n\n")
        fh.write("| Run | System | Workload | Seed | Goodput (Mbps) | "
                 "p95 RTT (ms) | Backlog (pkt) | Figure |\n")
        fh.write("|---|---|---|---|---|---|---|---|\n")
        for r in index:
            name = r["aqm"] + (" + ACAPE" if r["adaptive"] else "") + \
                   (" + eBPF" if r["ebpf"] else "")
            g = f"{r['goodput_mbps']:.2f}" if r["goodput_mbps"] else "-"
            p = f"{r['rtt_p95_ms']:.1f}" if r["rtt_p95_ms"] else "-"
            b = f"{r['backlog_mean_pkts']:.1f}" if r["backlog_mean_pkts"] else "-"
            fh.write(f"| {r['run']} | {name} | {r['workload']} | {r['seed']} | "
                     f"{g} | {p} | {b} | [`{r['image']}`]({r['image']}) |\n")
    print(f"\n{len(index)} run figures -> {a.outdir}")


if __name__ == "__main__":
    main()
