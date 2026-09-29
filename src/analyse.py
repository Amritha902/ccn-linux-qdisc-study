#!/usr/bin/env python3
"""Aggregate the experiment suite into tables, LaTeX and fact macros.

Figures are produced by src/plots.py; this module owns only the numbers, so
the two cannot emit conflicting versions of the same output.

Every value here is computed from a summary.json or time series written by
src/run_experiment.py. Nothing is hand-entered. Results are reported as
mean +/- 95% CI across seeds; a single run is reported as a single run.
"""
import argparse, csv, glob, json, math, os, statistics as st
from collections import defaultdict

DISPLAY = {
    "pfifo": "pfifo (no AQM)", "fq_codel": "fq_codel (static)",
    "codel": "CoDel", "pie": "PIE", "fq_pie": "FQ-PIE",
    "cake": "CAKE", "red": "RED (adaptive)", "sfq": "SFQ",
    "fq_codel_sham": "fq_codel + sham ctl",
    "fq_codel_acape": "fq_codel + ACAPE",
}
ORDER = ["pfifo", "sfq", "red", "codel", "pie", "fq_pie", "cake",
         "fq_codel", "fq_codel_sham", "fq_codel_acape"]


def ci95(xs):
    """Mean and half-width of the 95% CI. Returns (mean, halfwidth, n)."""
    xs = [x for x in xs if x is not None]
    if not xs:
        return None, None, 0
    if len(xs) == 1:
        return xs[0], 0.0, 1
    m = st.fmean(xs)
    sd = st.stdev(xs)
    # t_{0.975} for small samples; falls back to 1.96 for n > 30
    tcrit = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571,
             7: 2.447, 8: 2.365, 9: 2.306, 10: 2.262}.get(len(xs), 1.96)
    return m, tcrit * sd / math.sqrt(len(xs)), len(xs)


def load(resdir):
    runs = []
    for f in sorted(glob.glob(os.path.join(resdir, "*", "summary.json"))):
        try:
            d = json.load(open(f))
            d["_dir"] = os.path.dirname(f)
            runs.append(d)
        except Exception as e:
            print(f"  skipped {f}: {e}")
    return runs


def system_key(r):
    if r.get("adaptive"):
        return f"{r['aqm']}_acape"
    if r.get("sham"):
        return f"{r['aqm']}_sham"
    return r["aqm"]


METRICS = [
    ("throughput_mbps",       "Goodput (Mbps)",             "%.2f"),
    ("jain",                  "Jain's fairness",            "%.4f"),
    ("sparse_rtt_mean_ms",    "Probe RTT mean (ms)",        "%.2f"),
    ("sparse_rtt_p95_ms",     "Probe RTT p95 (ms)",         "%.2f"),
    ("sparse_rtt_p99_ms",     "Probe RTT p99 (ms)",         "%.2f"),
    ("sparse_rtt_jitter_ms",  "Probe jitter (ms)",          "%.2f"),
    ("bulk_rtt_mean_ms",      "Bulk RTT mean (ms)",         "%.2f"),
    ("bulk_rtt_p95_ms",       "Bulk RTT p95 (ms)",          "%.2f"),
    ("queue_delay_mean_ms",   "Queue delay mean (ms)",      "%.2f"),
    ("backlog_mean_pkts",     "Mean backlog (pkts)",        "%.1f"),
    ("backlog_p95_pkts",      "p95 backlog (pkts)",         "%.1f"),
    ("drop_rate_mean_per_s",  "Mean drop rate (/s)",        "%.1f"),
    ("retransmits",           "Retransmits",                "%.0f"),
]


def build_table(runs, workload):
    sel = [r for r in runs if r.get("workload") == workload]
    by = defaultdict(list)
    for r in sel:
        by[system_key(r)].append(r)
    rows = []
    for k in ORDER:
        if k not in by:
            continue
        group = by[k]
        row = {"system": DISPLAY.get(k, k), "key": k, "n": len(group)}
        for mk, _, _ in METRICS:
            m, h, n = ci95([g.get(mk) for g in group])
            row[mk] = m
            row[mk + "_ci"] = h
        rows.append(row)
    return rows


def write_tables(runs, outdir):
    os.makedirs(outdir, exist_ok=True)
    out = {}
    for wl in ("steady", "staged"):
        rows = build_table(runs, wl)
        if not rows:
            continue
        out[wl] = rows
        path = os.path.join(outdir, f"table_{wl}.csv")
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            hdr = ["system", "n"] + [m[0] for m in METRICS] + \
                  [m[0] + "_ci95" for m in METRICS]
            w.writerow(hdr)
            for r in rows:
                w.writerow([r["system"], r["n"]] +
                           [r.get(m[0]) for m in METRICS] +
                           [r.get(m[0] + "_ci") for m in METRICS])
        # human-readable
        txt = os.path.join(outdir, f"table_{wl}.txt")
        SHOW = ["throughput_mbps", "sparse_rtt_mean_ms", "sparse_rtt_p95_ms",
                "bulk_rtt_mean_ms", "backlog_mean_pkts", "jain"]
        SHORT = {"throughput_mbps": "goodput Mbps",
                 "sparse_rtt_mean_ms": "probe RTT mean",
                 "sparse_rtt_p95_ms": "probe RTT p95",
                 "bulk_rtt_mean_ms": "bulk RTT mean",
                 "backlog_mean_pkts": "backlog pkt", "jain": "Jain"}
        FMT = dict((m[0], m[2]) for m in METRICS)
        W = 20
        width = 24 + 4 + W * len(SHOW)
        with open(txt, "w") as fh:
            fh.write(f"Workload: {wl}   (mean +/- 95% CI across seeds)\n")
            fh.write("=" * width + "\n")
            fh.write(f"{'system':24s}{'n':>4s}")
            for mk in SHOW:
                fh.write(f"{SHORT[mk]:>{W}s}")
            fh.write("\n" + "-" * width + "\n")
            for r in rows:
                fh.write(f"{r['system']:24s}{r['n']:>4d}")
                for mk in SHOW:
                    v, h = r.get(mk), r.get(mk + "_ci")
                    cell = "-" if v is None else (FMT[mk] % v)
                    if h:
                        cell += " \u00b1" + (FMT[mk] % h)
                    fh.write(f"{cell:>{W}s}")
                fh.write("\n")
        print(open(txt).read())
    with open(os.path.join(outdir, "tables.json"), "w") as fh:
        json.dump(out, fh, indent=2)
    write_latex(out, outdir)
    return out


def write_latex(tables, outdir):
    """Emit \\input-able LaTeX so the paper never contains a hand-typed number."""
    SHOW = [("throughput_mbps", "Goodput", "Mbps", "%.2f"),
            ("sparse_rtt_mean_ms", "Probe RTT", "ms", "%.1f"),
            ("sparse_rtt_p95_ms", "Probe p95", "ms", "%.1f"),
            ("bulk_rtt_mean_ms", "Bulk RTT", "ms", "%.1f"),
            ("backlog_mean_pkts", "Backlog", "pkt", "%.1f"),
            ("jain", "Jain", "", "%.4f")]
    for wl, rows in tables.items():
        lines = [
            "% GENERATED by src/analyse.py -- do not edit by hand.",
            "\\begin{tabular}{l" + "r" * len(SHOW) + "}",
            "\\toprule",
            "\\textbf{System} & " + " & ".join(
                f"\\textbf{{{lbl}}}" + (f" ({u})" if u else "") for _, lbl, u, _ in SHOW)
            + " \\\\",
            "\\midrule",
        ]
        for r in rows:
            cells = []
            for mk, _, _, fmt in SHOW:
                v, h = r.get(mk), r.get(mk + "_ci")
                if v is None:
                    cells.append("--")
                elif h:
                    cells.append(f"{fmt % v}\\,$\\pm$\\,{fmt % h}")
                else:
                    cells.append(fmt % v)
            name = r["system"].replace("_", "\\_")
            lines.append(f"{name} & " + " & ".join(cells) + " \\\\")
        lines += ["\\bottomrule", "\\end{tabular}"]
        path = os.path.join(outdir, f"table_{wl}.tex")
        with open(path, "w") as fh:
            fh.write("\n".join(lines) + "\n")


def write_facts(runs, outdir):
    """Emit every figure the prose quotes as a LaTeX macro, so the text cannot
    drift from the data."""
    facts = {}
    by = defaultdict(list)
    for r in runs:
        by[(system_key(r), r.get("workload"))].append(r)

    def agg(key, wl, metric):
        m, h, n = ci95([g.get(metric) for g in by.get((key, wl), [])])
        return m, h, n

    for wl in ("steady", "staged"):
        for key in ORDER:
            # LaTeX macro names may contain only letters, so no digits here.
            for metric, short in (("sparse_rtt_p95_ms", "ProbeRttPninetyfive"),
                                  ("sparse_rtt_mean_ms", "ProbeRttMean"),
                                  ("bulk_rtt_mean_ms", "BulkRttMean"),
                                  ("bulk_rtt_p95_ms", "BulkRttPninetyfive"),
                                  ("throughput_mbps", "Goodput"),
                                  ("backlog_mean_pkts", "Backlog"),
                                  ("jain", "Jain")):
                m, h, n = agg(key, wl, metric)
                if m is None:
                    continue
                cam = "".join(w.capitalize() for w in key.split("_"))
                name = f"{cam}{short}{wl.capitalize()}"
                facts[name] = m
    path = os.path.join(outdir, "facts.tex")
    with open(path, "w") as fh:
        fh.write("% GENERATED by src/analyse.py -- do not edit by hand.\n")
        for k, v in sorted(facts.items()):
            fh.write(f"\\newcommand{{\\{k}}}{{{v:.4g}}}\n")
    with open(os.path.join(outdir, "facts.json"), "w") as fh:
        json.dump(facts, fh, indent=2, sort_keys=True)
    return facts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    ap.add_argument("--outdir", default="paper/generated")
    a = ap.parse_args()
    runs = load(a.results)
    print(f"loaded {len(runs)} runs from {a.results}\n")
    if not runs:
        return
    os.makedirs(a.outdir, exist_ok=True)
    tables = write_tables(runs, a.outdir)
    write_facts(runs, a.outdir)
    print("\nTables and LaTeX written. Figures are produced by src/plots.py:")
    print("  python3 src/plots.py --results %s --outdir figures/comparison" % a.results)


if __name__ == "__main__":
    main()
