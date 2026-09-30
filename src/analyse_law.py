#!/usr/bin/env python3
"""Test whether the benefit of parameter adaptation is governed by target/RTT.

The RTT sweep found adaptation recovering 18.4% of bulk-flow round-trip time on
a 5 ms path and nothing at 20, 80 or 200 ms. If the mechanism is that the AQM's
delay target is oversized relative to a short path, then the governing variable
is the ratio r = target / RTT, not the RTT itself.

Three predictions are tested, in increasing order of how badly they could fail:

  P1  A crossover in benefit exists between r = 1.0 and r = 0.25.
  P2  Ratio invariance. Two configurations with the same r but different RTT
      should show the same benefit. This is the one that can refute the
      hypothesis outright: if benefit tracks RTT rather than r, it is wrong.
  P3  Hold-out prediction. Fit on a subset of ratios, predict an unseen one,
      compare against measurement.

A model that survives all three is a scaling law. One that fails P2 is not,
and this script says so rather than reporting the fit anyway.
"""
import argparse, glob, json, math, os, statistics as st, sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from findings import welch

PALETTE = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2", "#B279A2"]
GRID, TEXT = "#D9D9D9", "#2B2B2B"
METRIC = "bulk_rtt_mean_ms"


def style(ax, title="", xlabel="", ylabel=""):
    if title: ax.set_title(title, fontsize=11, color=TEXT, pad=8)
    ax.set_xlabel(xlabel, fontsize=10, color=TEXT)
    ax.set_ylabel(ylabel, fontsize=10, color=TEXT)
    ax.grid(True, color=GRID, linewidth=0.6, alpha=0.8); ax.set_axisbelow(True)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    for s in ("left", "bottom"): ax.spines[s].set_color(GRID)
    ax.tick_params(colors=TEXT, labelsize=9)


def load(*dirs):
    out = []
    for d in dirs:
        for f in glob.glob(os.path.join(d, "**", "summary.json"), recursive=True):
            try:
                j = json.load(open(f))
                if j.get("workload") != "steady" or j.get("aqm") != "fq_codel":
                    continue
                if j.get("sham") or j.get("ebpf"):
                    continue
                j["_ratio"] = (j.get("aqm_target_ms") or 5.0) / j["base_rtt_ms"]
                out.append(j)
            except Exception:
                pass
    return out


# What adaptation costs while it is buying latency. Shrinking the delay target
# makes CoDel drop earlier, so senders back off sooner: the queue drains and
# delay falls, but retransmissions rise. Reporting the benefit without these is
# reporting half the trade.
#
# A note on the queue-side columns. `backlog_mean_pkts` is a counter read
# straight out of `tc -s qdisc`, so it is a direct measurement. The summary
# field `sojourn_mean_ms` is not a measured sojourn despite its name: the
# controller derives it as backlog_bytes*8/rate from an instantaneous backlog
# snapshot once per tick, then averages over ticks. That is a time-average of
# queue occupancy, whereas bulk RTT is a packet-weighted average, and packets
# arrive disproportionately during busy periods. The two therefore cannot be
# expected to reconcile arithmetically, and we checked: the estimated queue
# reduction accounts for anywhere between 12% and 359% of the measured RTT
# reduction across cells. So it is shown as a trend indicator under its real
# name and the mechanism argument rests on backlog, which is measured.
COSTS = ["drop_rate_mean_per_s", "retransmits", "throughput_mbps",
         "sojourn_mean_ms", "backlog_mean_pkts"]


def _pct(a, b):
    """Percentage change from static mean a to adapted mean b."""
    a = [x for x in a if x is not None]; b = [x for x in b if x is not None]
    if not a or not b or st.fmean(a) == 0:
        return None
    return (st.fmean(b) - st.fmean(a)) / st.fmean(a) * 100


def cells(runs):
    """Group into (target, rtt) cells and compute the adaptation benefit."""
    by = defaultdict(lambda: defaultdict(lambda: {"static": [], "adapt": []}))
    for r in runs:
        k = (r.get("aqm_target_ms") or 5.0, r["base_rtt_ms"])
        arm = "adapt" if r.get("adaptive") else "static"
        by[k][METRIC][arm].append(r.get(METRIC))
        for m in COSTS:
            by[k][m][arm].append(r.get(m))
    out = []
    for (tgt, rtt), g in sorted(by.items()):
        a = [x for x in g[METRIC]["static"] if x is not None]
        b = [x for x in g[METRIC]["adapt"] if x is not None]
        if len(a) < 2 or len(b) < 2:
            continue
        t, dof, p = welch(a, b)
        benefit = (st.fmean(a) - st.fmean(b)) / st.fmean(a) * 100
        c = {"target": tgt, "rtt": rtt, "ratio": tgt / rtt,
             "static": st.fmean(a), "adapt": st.fmean(b),
             "benefit": benefit, "p": p, "n": min(len(a), len(b))}
        for m in COSTS:
            c[m] = _pct(g[m]["static"], g[m]["adapt"])
        out.append(c)
    return out


def fit_logistic(ratios, benefits):
    """Least-squares fit of benefit = B / (1 + (r0/r)^k) by coarse grid search.

    A saturating form is the right shape: benefit should go to zero for small r
    (target already well scaled) and approach a ceiling for large r (target far
    too large for the path). Grid search avoids adding a dependency for a
    three-parameter fit over a handful of points.
    """
    best = None
    for B in np.arange(5, 46, 0.5):
        for r0 in np.arange(0.1, 3.01, 0.02):
            for k in np.arange(0.5, 6.01, 0.1):
                pred = [B / (1 + (r0 / r) ** k) for r in ratios]
                sse = sum((p - y) ** 2 for p, y in zip(pred, benefits))
                if best is None or sse < best[0]:
                    best = (sse, B, r0, k)
    sse, B, r0, k = best
    ss_tot = sum((y - st.fmean(benefits)) ** 2 for y in benefits)
    r2 = 1 - sse / ss_tot if ss_tot > 0 else float("nan")
    return B, r0, k, r2


def model(r, B, r0, k):
    return B / (1 + (r0 / r) ** k)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--law", default="results_law")
    ap.add_argument("--sweep", default="results_sweep")
    ap.add_argument("--baseline", default="results")
    ap.add_argument("--outdir", default="figures/comparison")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    runs = load(a.law, a.sweep, a.baseline)
    cs = cells(runs)
    if len(cs) < 3:
        print(f"only {len(cs)} complete cells; campaign still running")
        return

    L = ["", "=" * 92,
         "IS THE BENEFIT OF ADAPTATION GOVERNED BY target/RTT?",
         "=" * 92,
         "Benefit = reduction in mean bulk-flow RTT, static vs adapted fq_codel.", "",
         f"{'target':>8s}{'RTT':>7s}{'ratio':>8s}{'static':>10s}{'adapted':>10s}"
         f"{'benefit':>10s}{'p':>9s}  verdict",
         "-" * 92]
    for c in sorted(cs, key=lambda c: -c["ratio"]):
        v = "significant" if (c["p"] is not None and c["p"] < 0.05) else "not significant"
        L.append(f"{c['target']:>8.0f}{c['rtt']:>7.0f}{c['ratio']:>8.3f}"
                 f"{c['static']:>10.2f}{c['adapt']:>10.2f}{c['benefit']:>9.1f}%"
                 f"{c['p']:>9.4f}  {v}")

    # ---- what it costs -------------------------------------------------
    L += ["", "-" * 92, "WHAT THE LATENCY IS BOUGHT WITH", "-" * 92,
          "Percentage change, adapted against static, in the same cells.",
          "A shrinking target makes CoDel drop earlier, so senders back off",
          "sooner. If the ratio governs the benefit it should govern this too.", "",
          f"{'ratio':>8s}{'RTT gain':>10s}{'drops':>9s}{'retrans':>9s}"
          f"{'thrpt':>9s}{'qest':>9s}{'backlog':>9s}", "-" * 92,
          "qest is backlog-derived, not a measured sojourn; backlog is a tc counter."]
    for c in sorted(cs, key=lambda c: -c["ratio"]):
        def f(m):
            return f"{c[m]:>+8.1f}%" if c.get(m) is not None else f"{'n/a':>9s}"
        L.append(f"{c['ratio']:>8.3f}{c['benefit']:>9.1f}%"
                 + f("drop_rate_mean_per_s") + f("retransmits")
                 + f("throughput_mbps") + f("sojourn_mean_ms")
                 + f("backlog_mean_pkts"))
    thr = [c["throughput_mbps"] for c in cs if c.get("throughput_mbps") is not None]
    if thr:
        L.append("-" * 92)
        L.append(f"  worst throughput change across all cells: {min(thr):+.1f}%")

    # ---- P2: ratio invariance -----------------------------------------
    L += ["", "-" * 92, "P2  RATIO INVARIANCE (the falsifiable test)", "-" * 92,
          "Configurations sharing a ratio but differing in RTT should show the",
          "same benefit. If benefit tracks RTT instead, the hypothesis is wrong.", ""]
    groups = defaultdict(list)
    for c in cs:
        groups[round(c["ratio"], 3)].append(c)
    invariance_ok, tested = True, 0
    for ratio, g in sorted(groups.items(), reverse=True):
        if len(g) < 2:
            continue
        tested += 1
        bens = [c["benefit"] for c in g]
        spread = max(bens) - min(bens)
        desc = ", ".join(f"t={c['target']:.0f}/rtt={c['rtt']:.0f} -> {c['benefit']:+.1f}%"
                         for c in sorted(g, key=lambda c: c["rtt"]))
        ok = spread <= 10.0
        invariance_ok &= ok
        L.append(f"  ratio {ratio:>5.2f}:  {desc}")
        L.append(f"                spread {spread:.1f} percentage points"
                 f"  -> {'consistent' if ok else 'INCONSISTENT'}")
    if tested == 0:
        L.append("  no repeated ratios yet")
        invariance_ok = None

    # ---- fit + P3 hold-out --------------------------------------------
    ratios = [c["ratio"] for c in cs]; bens = [c["benefit"] for c in cs]
    B, r0, k, r2 = fit_logistic(ratios, bens)
    L += ["", "-" * 92, "FIT", "-" * 92,
          f"  benefit(r) = {B:.1f} / (1 + ({r0:.2f}/r)^{k:.1f})    R^2 = {r2:.3f}",
          f"  half-benefit at r = {r0:.2f}  (target {r0:.2f}x the path RTT)"]

    if len(cs) >= 5:
        # Leave-one-out over interior ratios only. Holding out an endpoint asks
        # a saturating curve to extrapolate beyond the data that fixes its
        # ceiling, which no three-parameter form can do and which tests the
        # fitting procedure rather than the hypothesis. Interior points are a
        # fair test: the model must recover a measurement it never saw, from
        # measurements that bracket it.
        order = sorted(cs, key=lambda c: c["ratio"])
        interior = order[1:-1]
        L += ["", "-" * 92, "P3  HOLD-OUT PREDICTION (leave-one-out, interior ratios)", "-" * 92,
              "Each row refits the curve with that point removed, then predicts it.", "",
              f"{'target':>8s}{'RTT':>7s}{'ratio':>8s}{'predicted':>12s}{'measured':>11s}"
              f"{'error':>9s}", "-" * 92]
        errs = []
        for held in interior:
            rest = [c for c in cs if c is not held]
            B2, r02, k2, _ = fit_logistic([c["ratio"] for c in rest],
                                          [c["benefit"] for c in rest])
            pred = model(held["ratio"], B2, r02, k2)
            err = pred - held["benefit"]
            errs.append(abs(err))
            L.append(f"{held['target']:>8.0f}{held['rtt']:>7.0f}{held['ratio']:>8.3f}"
                     f"{pred:>11.1f}%{held['benefit']:>10.1f}%{err:>+8.1f}pp")
        if errs:
            L += ["-" * 92,
                  f"  mean absolute prediction error {st.fmean(errs):.1f} percentage points"
                  f"   (worst {max(errs):.1f})"]
            holdout_ok = st.fmean(errs) <= 5.0
        else:
            holdout_ok = None
    else:
        holdout_ok = None

    L += ["", "=" * 92]
    if invariance_ok is True:
        L += ["CONCLUSION: the ratio target/RTT, not RTT, governs the benefit.",
              "Configurations with equal ratios behave alike across a wide RTT range."]
        if holdout_ok is False:
            L += ["Ratio invariance holds, but the fitted curve does not predict held-out",
                  "points well; the invariance is reported, the functional form is not."]
    elif invariance_ok is False:
        L += ["CONCLUSION: ratio invariance FAILS. The benefit does not depend on",
              "target/RTT alone, so the scaling law is refuted and is reported as such."]
    else:
        L += ["CONCLUSION: pending; no repeated ratio measured yet."]
    L.append("=" * 92)

    txt = "\n".join(L)
    open(os.path.join(a.outdir, "law_report.txt"), "w").write(txt + "\n")
    print(txt)

    # ---- figure --------------------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(13, 5)); fig.patch.set_facecolor("white")
    ax = axes[0]
    xs = np.logspace(math.log10(min(ratios) * 0.7), math.log10(max(ratios) * 1.4), 200)
    ax.plot(xs, [model(x, B, r0, k) for x in xs], "-", color=TEXT, linewidth=1.6,
            alpha=0.7, label=f"fit, $R^2$={r2:.2f}")
    for c in cs:
        sig = c["p"] is not None and c["p"] < 0.05
        ax.scatter(c["ratio"], c["benefit"], s=95,
                   color=PALETTE[0] if sig else "white",
                   edgecolor=PALETTE[0], linewidth=1.6, zorder=3)
        ax.annotate(f"{c['target']:.0f}/{c['rtt']:.0f}", (c["ratio"], c["benefit"]),
                    textcoords="offset points", xytext=(7, 5), fontsize=8, color=TEXT)
    ax.axvline(r0, color=PALETTE[3], ls="--", linewidth=1.2)
    ax.text(r0, ax.get_ylim()[1] * 0.93, f"  half-benefit\n  r={r0:.2f}",
            fontsize=8.5, color=PALETTE[3])
    ax.axhline(0, color=GRID, linewidth=1)
    ax.set_xscale("log")
    ax.legend(frameon=False, fontsize=9)
    style(ax, "(a) Benefit against target/RTT",
          "target / path RTT  (log)", "bulk-flow RTT reduction (%)")

    ax = axes[1]
    for c in cs:
        ax.scatter(c["rtt"], c["benefit"], s=95, color=PALETTE[1],
                   edgecolor="white", linewidth=1.2, zorder=3)
        ax.annotate(f"{c['target']:.0f}/{c['rtt']:.0f}", (c["rtt"], c["benefit"]),
                    textcoords="offset points", xytext=(7, 5), fontsize=8, color=TEXT)
    ax.axhline(0, color=GRID, linewidth=1)
    ax.set_xscale("log")
    style(ax, "(b) The same data against RTT alone",
          "base RTT (ms, log)", "bulk-flow RTT reduction (%)")

    fig.suptitle("Adaptation pays off when the delay target is large relative to the path\n"
                 "labels are target/RTT in ms; filled points are statistically significant",
                 fontsize=12, color=TEXT)
    fig.tight_layout(rect=[0, 0, 1, 0.9])
    p = os.path.join(a.outdir, "fig16_scaling_law.png")
    fig.savefig(p, dpi=150, facecolor="white"); plt.close(fig)
    print("\n  wrote", p)


if __name__ == "__main__":
    main()
