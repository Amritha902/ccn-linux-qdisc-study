#!/usr/bin/env python3
"""Build a numbered master index of every figure in the repository.

Three families, each numbered and captioned so any image can be cited later
without opening it:

  STEP nn   methodology evidence - a verbatim capture of a command that ran
  RUN  nn   one experiment run - backlog, throughput, drops, measured RTT
  FIG  nn   analysis figures aggregated across seeds

Writes figures/INDEX.md and figures/index.json.
"""
import argparse, json, os, re, glob

FIG_CAPTIONS = {
    "fig01_latency_tail": "Tail latency (p95 RTT, sparse probe flow) across all systems, log scale",
    "fig02_latency_sparse_vs_bulk": "Sparse probe flow vs bulk TCP flow RTT — why the two differ",
    "fig03_throughput": "Goodput (from iperf3 sum_received), axis zoomed to show it is flat",
    "fig04_backlog": "Mean queue occupancy, log scale",
    "fig05_fairness": "Jain's fairness index, axis zoomed",
    "fig06_droprate": "AQM drop rate and end-to-end TCP retransmissions",
    "fig07_tradeoff": "Latency vs throughput trade-off",
    "fig08_allparams": "All measured parameters × all systems, normalised heatmap with measured values",
    "fig09_seeds": "Per-seed values — every individual run shown, mean marked",
    "fig10_timeseries_backlog": "Queue occupancy over time",
    "fig11_timeseries_rtt": "Measured RTT over time (20 Hz probe)",
    "fig12_controller_behaviour": "What the ACAPE controller actually did: target, backlog, eBPF telemetry, regime",
    "fig13_sham_control": "Sham-controller condition — separates controller CPU cost from control decisions",
}


def caption_for(name):
    base = name.replace(".png", "")
    for k, v in FIG_CAPTIONS.items():
        if base.startswith(k):
            wl = "staged workload" if base.endswith("_staged") else (
                 "steady workload" if base.endswith("_steady") else "")
            metric = ""
            if k == "fig09_seeds":
                m = re.match(r"fig09_seeds_(.+?)_(steady|staged)$", base)
                if m:
                    metric = f" — {m.group(1).replace('_', ' ')}"
            return v + metric + (f" ({wl})" if wl else "")
    return base


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--figures", default="figures")
    a = ap.parse_args()
    F = a.figures
    index = {"steps": [], "runs": [], "figures": []}

    # STEP images
    sp = os.path.join(F, "steps", "index.json")
    if os.path.exists(sp):
        for e in json.load(open(sp)):
            index["steps"].append({
                "id": f"STEP {e['step']}", "title": e["title"],
                "caption": e["explain"], "where": e.get("where", ""),
                "path": os.path.join("steps", e["image"])})
    else:
        for p in sorted(glob.glob(os.path.join(F, "steps", "step*.png"))):
            n = os.path.basename(p)
            index["steps"].append({"id": f"STEP {n[4:6]}", "title": n,
                                   "caption": "", "path": os.path.join("steps", n)})

    # RUN images
    rp = os.path.join(F, "runs", "index.json")
    if os.path.exists(rp):
        for e in json.load(open(rp)):
            sysname = e["aqm"] + (" + ACAPE" if e.get("adaptive") else "") + \
                      (" + eBPF" if e.get("ebpf") else "")
            index["runs"].append({
                "id": f"RUN {e['run']}", "title": e["label"],
                "caption": f"{sysname}, {e['workload']} workload, seed {e['seed']} — "
                           f"goodput {e.get('goodput_mbps')} Mbps, "
                           f"p95 RTT {e.get('rtt_p95_ms')} ms, "
                           f"backlog {e.get('backlog_mean_pkts')} pkt",
                "path": os.path.join("runs", e["image"])})

    # FIG images
    for i, p in enumerate(sorted(glob.glob(os.path.join(F, "comparison", "*.png"))), 1):
        n = os.path.basename(p)
        index["figures"].append({"id": f"FIG {i:02d}", "title": n,
                                 "caption": caption_for(n),
                                 "path": os.path.join("comparison", n)})

    with open(os.path.join(F, "index.json"), "w") as fh:
        json.dump(index, fh, indent=2)

    with open(os.path.join(F, "INDEX.md"), "w") as fh:
        fh.write("# Figure Index\n\n")
        fh.write("Every image in this repository, numbered and captioned.\n\n")
        fh.write(f"- **{len(index['steps'])}** methodology evidence captures (STEP)\n")
        fh.write(f"- **{len(index['runs'])}** per-run result figures (RUN)\n")
        fh.write(f"- **{len(index['figures'])}** analysis figures (FIG)\n\n")

        fh.write("## Methodology evidence\n\n")
        fh.write("Each is a verbatim capture of a command that was actually executed.\n\n")
        fh.write("| ID | Title | What it shows | Ran on | Image |\n|---|---|---|---|---|\n")
        for e in index["steps"]:
            cap = e["caption"].replace("|", "/")
            fh.write(f"| **{e['id']}** | {e['title']} | {cap} | {e.get('where','')} | "
                     f"[`{os.path.basename(e['path'])}`]({e['path']}) |\n")

        fh.write("\n## Analysis figures\n\n")
        fh.write("| ID | What it shows | Image |\n|---|---|---|\n")
        for e in index["figures"]:
            fh.write(f"| **{e['id']}** | {e['caption']} | "
                     f"[`{os.path.basename(e['path'])}`]({e['path']}) |\n")

        fh.write("\n## Per-run figures\n\n")
        fh.write("One figure per experiment run. No run is omitted.\n\n")
        fh.write("| ID | Run | Measured | Image |\n|---|---|---|---|\n")
        for e in index["runs"]:
            fh.write(f"| **{e['id']}** | {e['title']} | {e['caption']} | "
                     f"[`{os.path.basename(e['path'])}`]({e['path']}) |\n")

    total = sum(len(v) for v in index.values())
    print(f"indexed {total} figures -> {os.path.join(F, 'INDEX.md')}")
    for k, v in index.items():
        print(f"  {k}: {len(v)}")


if __name__ == "__main__":
    main()
