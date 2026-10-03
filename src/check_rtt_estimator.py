#!/usr/bin/env python3
"""Does a statistic of the eBPF RTT proxy recover the base RTT?

The self-gating controller needs r = target/RTT from what it can observe. It
observes a per-flow RTT proxy through the eBPF map. The question is which
statistic of that proxy tracks the path's base RTT, since the gate's decision
is only as good as the estimate behind it.

Checked here across base RTTs rather than argued for: min, several low
percentiles, and the median, each scored by relative error against the
configured netem delay. Reports the winner and its worst-case error, which is
what the gate's threshold margin has to tolerate.

Run: python3 src/check_rtt_estimator.py
"""
import csv, glob, json, os, statistics as st, sys
from collections import defaultdict


def series(rundir):
    m = os.path.join(rundir, "acape_metrics_ctl.csv")
    if not os.path.exists(m):
        return []
    try:
        rows = list(csv.DictReader(open(m)))
    except Exception:
        return []
    return [float(r["rtt_proxy_ms"]) for r in rows
            if r.get("rtt_proxy_ms") and float(r["rtt_proxy_ms"]) > 0]


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, max(0, int(len(v) * q)))]


ESTIMATORS = {
    "min": min,
    "p05": lambda v: pct(v, 0.05),
    "p10": lambda v: pct(v, 0.10),
    "p25": lambda v: pct(v, 0.25),
    "median": st.median,
    "p75": lambda v: pct(v, 0.75),
}


def main():
    by = defaultdict(list)
    for f in glob.glob("results*/**/summary.json", recursive=True):
        j = json.load(open(f))
        if not j.get("ebpf"):
            continue
        v = series(os.path.dirname(f))
        if len(v) < 20:
            continue
        by[j["base_rtt_ms"]].append(v)

    if len(by) < 2:
        print(f"only {len(by)} base RTT(s) with eBPF telemetry; "
              "run src/run_rttest.sh first")
        return

    print("Recovering base RTT from the eBPF proxy\n")
    hdr = f"{'base':>6}{'n':>4}" + "".join(f"{k:>10}" for k in ESTIMATORS)
    print(hdr); print("-" * len(hdr))
    err = defaultdict(list)
    for base in sorted(by):
        runs = by[base]
        row = f"{base:>6.0f}{len(runs):>4}"
        for k, fn in ESTIMATORS.items():
            vals = [fn(v) for v in runs]
            m = st.fmean(vals)
            row += f"{m:>10.2f}"
            err[k].append(abs(m - base) / base * 100)
        print(row)

    print("\nrelative error against the configured delay (%)\n")
    hdr2 = f"{'estimator':>10}{'mean':>9}{'worst':>9}"
    print(hdr2); print("-" * len(hdr2))
    ranked = sorted(ESTIMATORS, key=lambda k: st.fmean(err[k]))
    for k in ranked:
        print(f"{k:>10}{st.fmean(err[k]):>8.1f}%{max(err[k]):>8.1f}%")

    best = ranked[0]
    print(f"\nbest estimator: {best}, mean error {st.fmean(err[best]):.1f}%, "
          f"worst {max(err[best]):.1f}%")
    if max(err[best]) > 25:
        print("Worst-case error above 25%: too loose for a gate whose threshold")
        print("sits at r = 0.4, since a 25% RTT error moves r by 25%. The gate")
        print("should not be built on this estimator without a wider margin.")
    else:
        print(f"Worst case within 25%, so a gate threshold at r = 0.4 tolerates")
        print(f"it with margin. The gate uses {best}.")


if __name__ == "__main__":
    main()
