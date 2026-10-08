#!/usr/bin/env python3
"""Verify that cells compared by P2 received the same control law.

F7 scaled the regime thresholds so that cells at equal target/RTT classify
alike. That scaling assumes the drop rate falls as t^-1 while the measured
exponent is nearer t^-0.78, so it is not exact and is not claimed to be. What
ratio invariance actually requires is weaker: every compared cell must receive
the same control law, and the controller must move through a comparable
relative excursion. Both are recorded in the run logs, so both are checked
here rather than argued for.

If this reports a mismatch, the P2 comparison for that ratio is confounded by
the instrument and must not be read as evidence about queueing.

Run: python3 src/check_regimes.py
"""
import collections, csv, glob, json, os, statistics as st, sys


def cell(d):
    """(target, rtt, dominant regime, excursion %) for one adapted run."""
    s = os.path.join(d, "summary.json")
    m = os.path.join(d, "acape_metrics_ctl.csv")
    if not (os.path.exists(s) and os.path.exists(m)):
        return None
    j = json.load(open(s))
    if not j.get("adaptive") or j.get("sham") or j.get("ebpf"):
        return None
    rows = list(csv.DictReader(open(m)))
    t = [float(r["target_ms"]) for r in rows if r.get("target_ms")]
    rg = [r["regime"] for r in rows if r.get("regime")]
    if not t or not rg:
        return None
    return {"target": j.get("aqm_target_ms") or 5.0, "rtt": j["base_rtt_ms"],
            "regime": collections.Counter(rg).most_common(1)[0][0],
            "exc": (t[0] - min(t)) / t[0] * 100}


def main():
    runs = [c for c in (cell(os.path.dirname(f))
                        for f in glob.glob("results*/**/summary.json", recursive=True))
            if c]
    by = collections.defaultdict(list)
    for c in runs:
        by[round(c["target"] / c["rtt"], 3)].append(c)

    print("Control law and excursion for cells sharing a ratio\n")
    print(f"{'ratio':>7}{'target':>8}{'rtt':>6}{'regime':>11}{'excursion':>12}")
    print("-" * 46)
    bad = []
    for ratio, g in sorted(by.items(), reverse=True):
        cells = collections.defaultdict(list)
        for c in g:
            cells[(c["target"], c["rtt"])].append(c)
        if len(cells) < 2:
            continue
        for (t, r), cs in sorted(cells.items()):
            print(f"{ratio:7.3f}{t:8.0f}{r:6.0f}{cs[0]['regime']:>11}"
                  f"{st.fmean(c['exc'] for c in cs):11.1f}%")
        regimes = {cs[0]["regime"] for cs in cells.values()}
        excs = [st.fmean(c["exc"] for c in cs) for cs in cells.values()]
        spread = max(excs) - min(excs)
        if len(regimes) > 1:
            bad.append(f"ratio {ratio}: control laws differ {sorted(regimes)}")
        elif spread > 15.0:
            bad.append(f"ratio {ratio}: excursions differ by {spread:.1f} points")
        else:
            print(f"        -> same law, excursions within {spread:.1f} points\n")

    if not any(len(set((c['target'], c['rtt']) for c in g)) >= 2
               for g in by.values()):
        print("\nno repeated ratios yet; nothing to check")
        return
    if bad:
        print("\nINSTRUMENT MISMATCH, P2 for these ratios is confounded:")
        for b in bad:
            print("  " + b)
        sys.exit(1)
    print("every compared cell received the same control law and a comparable")
    print("relative excursion, so P2 measures queueing rather than the controller")


if __name__ == "__main__":
    main()
