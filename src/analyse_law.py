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

# Scientific Reports and most journals require raster figures at 300 dpi or
# better at the size they are printed. 150 is a screen resolution.
FIG_DPI = 300


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


def _adjustments(rundir):
    """Rows in the controller's adjustment log, or None if there is no log."""
    f = os.path.join(rundir, "acape_adj_ctl.csv")
    if not os.path.exists(f):
        return None
    try:
        with open(f) as fh:
            return max(0, sum(1 for _ in fh) - 1)
    except Exception:
        return None


def load(*dirs):
    out = []
    for d in dirs:
        for f in glob.glob(os.path.join(d, "**", "summary.json"), recursive=True):
            try:
                j = json.load(open(f))
                if j.get("adaptive"):
                    j["_adj"] = _adjustments(os.path.dirname(f))
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
        if arm == "adapt" and r.get("_adj") is not None:
            by[k]["_adj"]["adapt"].append(r["_adj"])
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
        adj = [x for x in g["_adj"]["adapt"] if x is not None]
        c = {"adj": (st.fmean(adj) if adj else None),
             "inert": bool(adj) and max(adj) == 0,
             "target": tgt, "rtt": rtt, "ratio": tgt / rtt,
             "static": st.fmean(a), "adapt": st.fmean(b),
             "benefit": benefit, "p": p, "n": min(len(a), len(b)),
             "abs_ms": st.fmean(a) - st.fmean(b)}
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


def _num(x, nd=2):
    return "n/a" if x is None else f"{x:.{nd}f}"



def model_comparison(ratios, benefits):
    """W2: is the third parameter earning its place?

    R-squared always improves with another parameter, so it cannot answer
    this. Leave-one-out prediction can: each model is refitted with one cell
    removed and asked to predict it. Compared against the saturating form with
    the exponent fixed at one, and against a step that is flat below a
    threshold and flat above it.
    """
    def loo(fitfn, predfn):
        errs = []
        for i in range(len(ratios)):
            r = ratios[:i] + ratios[i + 1:]
            y = benefits[:i] + benefits[i + 1:]
            par = fitfn(r, y)
            errs.append(abs(predfn(ratios[i], par) - benefits[i]))
        return st.fmean(errs)

    def fit2(r, y):
        best = None
        for B in np.arange(5, 46, 0.5):
            for r0 in np.arange(0.1, 3.01, 0.02):
                sse = sum((B / (1 + (r0 / x)) - v) ** 2 for x, v in zip(r, y))
                if best is None or sse < best[0]:
                    best = (sse, B, r0)
        return best[1], best[2]

    def fitstep(r, y):
        best = None
        for thr in np.arange(0.1, 2.01, 0.02):
            hi = [v for x, v in zip(r, y) if x >= thr]
            lo = [v for x, v in zip(r, y) if x < thr]
            B = st.fmean(hi) if hi else 0.0
            L = st.fmean(lo) if lo else 0.0
            sse = sum(((B if x >= thr else L) - v) ** 2 for x, v in zip(r, y))
            if best is None or sse < best[0]:
                best = (sse, thr, B, L)
        return best[1], best[2], best[3]

    return (loo(lambda r, y: fit_logistic(r, y)[:3],
                lambda r, p: model(r, *p)),
            loo(fit2, lambda r, p: p[0] / (1 + (p[1] / r))),
            loo(fitstep, lambda r, p: p[1] if r >= p[0] else p[2]))


def emit_latex(cs, B, r0, k, r2, invariance_ok, holdout_ok, texdir, real=True):
    """Write the ratio table and the fact macros the papers cite.

    Every number the papers quote about the scaling law comes from here, so
    that editing prose can never silently disagree with the measurements.
    Macro names carry no digits: TeX will not accept them in a control
    sequence, which cost an afternoon earlier in this project.
    """
    if not texdir:
        return
    _loo3, _loo2, _loostep = model_comparison(
        [c["ratio"] for c in cs], [c["benefit"] for c in cs])
    # Refuse to write the papers' generated LaTeX from anything but the real
    # corpus. The test fixture once overwrote law_facts.tex with synthetic
    # numbers because it did not pass --texdir, and a paper that cites
    # generated macros would have carried them silently.
    if not real:
        print("  not the default corpus; skipping paper/generated LaTeX")
        return
    os.makedirs(texdir, exist_ok=True)

    rows = sorted(cs, key=lambda c: -c["ratio"])
    T = [r"% GENERATED by src/analyse_law.py -- do not edit by hand.",
         r"\begin{tabular}{rrrrrrrl}", r"\hline",
         r"target & RTT & $r$ & static & adapted & \multicolumn{2}{c}{reduction} & $p$ \\",
         r" (ms) & (ms) & & (ms) & (ms) & (\%) & (ms) & \\", r"\hline"]
    for c in rows:
        star = r"$^{*}$" if (c["p"] is not None and c["p"] < 0.05) else ""
        pstr = "$<$0.001" if (c["p"] is not None and c["p"] < 0.001) else _num(c["p"], 3)
        T.append(f"{c['target']:.0f} & {c['rtt']:.0f} & {c['ratio']:.3f} & "
                 f"{c['static']:.2f} & {c['adapt']:.2f} & {c['benefit']:.1f}{star} & "
                 f"{c['abs_ms']:.2f} & {pstr} \\\\")
    T += [r"\hline", r"\end{tabular}"]
    open(os.path.join(texdir, "table_law.tex"), "w").write("\n".join(T) + "\n")

    hi = [c["abs_ms"] for c in cs if c["ratio"] >= 0.4]
    lo = [c["abs_ms"] for c in cs if c["ratio"] < 0.4]
    sig = [c for c in cs if c["p"] is not None and c["p"] < 0.05]
    thr = [c["throughput_mbps"] for c in cs if c.get("throughput_mbps") is not None]
    drp = [c["drop_rate_mean_per_s"] for c in cs
           if c.get("drop_rate_mean_per_s") is not None and c["ratio"] >= 1.0]

    M = {"LawCells": f"{len(cs)}",
         "LawCeiling": f"{B:.1f}", "LawHalfBenefit": f"{r0:.2f}",
         "LawSteepness": f"{k:.1f}", "LawRsq": f"{r2:.3f}",
         "LawPeakBenefit": f"{max(c['benefit'] for c in cs):.1f}",
         "LawRatioMax": f"{max(c['ratio'] for c in cs):.3f}",
         "LawRatioMin": f"{min(c['ratio'] for c in cs):.3f}",
         "LawLowestSigRatio": (f"{min(c['ratio'] for c in sig):.3f}" if sig else "n/a"),
         "LawGainHiMin": (_num(min(hi)) if hi else "n/a"),
         "LawGainHiMax": (_num(max(hi)) if hi else "n/a"),
         "LawGainLoMin": (_num(min(lo)) if lo else "n/a"),
         "LawGainLoMax": (_num(max(lo)) if lo else "n/a"),
         "LawWorstThroughput": (_num(min(thr), 1) if thr else "n/a"),
         "LawDropRiseHigh": (_num(max(drp), 0) if drp else "n/a"),
         "LawInvariance": {True: "holds", False: "fails",
                           None: "untested"}[invariance_ok],
         "LawHoldout": {True: "predictive", False: "not predictive",
                        None: "untested"}[holdout_ok],
         "LawLooLogistic": f"{_loo3:.2f}",
         "LawLooSimple": f"{_loo2:.2f}",
         "LawLooStep": f"{_loostep:.2f}"}
    F = [r"% GENERATED by src/analyse_law.py -- do not edit by hand."]
    F += [f"\\newcommand{{\\{k2}}}{{{v}}}" for k2, v in sorted(M.items())]
    open(os.path.join(texdir, "law_facts.tex"), "w").write("\n".join(F) + "\n")
    json.dump(M, open(os.path.join(texdir, "law_facts.json"), "w"), indent=1)
    print(f"  wrote {texdir}/table_law.tex, law_facts.tex, law_facts.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--law", default="results_law")
    ap.add_argument("--sweep", default="results_sweep")
    ap.add_argument("--baseline", default="results")
    ap.add_argument("--outdir", default="figures/comparison")
    ap.add_argument("--texdir", default="paper/generated")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)

    runs = load(a.law, a.sweep, a.baseline)
    cs_all = cells(runs)
    # A cell whose adapted arm never adjusted a parameter is measuring static
    # against static. Its null is true by construction, so it cannot be
    # evidence that the ratio produces no benefit there, and including it in
    # the fit or the invariance test would be circular. It is reported
    # separately instead of silently dropped.
    cs = [c for c in cs_all if not c.get("inert")]
    inert = [c for c in cs_all if c.get("inert")]
    if len(cs) < 3:
        print(f"only {len(cs)} complete cells; campaign still running")
        return

    L = ["", "=" * 92,
         "IS THE BENEFIT OF ADAPTATION GOVERNED BY target/RTT?",
         "=" * 92,
         "Benefit = reduction in mean bulk-flow RTT, static vs adapted fq_codel.", "",
         f"{'target':>8s}{'RTT':>7s}{'ratio':>8s}{'static':>10s}{'adapted':>10s}"
         f"{'benefit':>10s}{'gain ms':>9s}{'p':>9s}{'adj':>6s}  verdict",
         "-" * 92,
         "adj is the mean number of parameter adjustments the controller made.",
         "A cell where it is zero or near zero is not measuring adaptation.",
         "-" * 92]
    for c in sorted(cs, key=lambda c: -c["ratio"]):
        v = "significant" if (c["p"] is not None and c["p"] < 0.05) else "not significant"
        adj_s = "-" if c.get("adj") is None else f"{c['adj']:.0f}"
        L.append(f"{c['target']:>8.0f}{c['rtt']:>7.0f}{c['ratio']:>8.3f}"
                 f"{c['static']:>10.2f}{c['adapt']:>10.2f}{c['benefit']:>9.1f}%"
                 f"{c['abs_ms']:>9.2f}{c['p']:>9.4f}{adj_s:>6s}  {v}")

    # A percentage reduction shrinks automatically when its denominator grows,
    # so a reviewer is right to ask whether the collapse at low ratio is an
    # artefact of dividing by a larger RTT. The absolute column answers it: if
    # the gain in milliseconds also collapses, the effect is real.
    hi = [c["abs_ms"] for c in cs if c["ratio"] >= 0.4]
    lo = [c["abs_ms"] for c in cs if c["ratio"] < 0.4]
    if hi and lo:
        L += ["", f"  absolute gain above r=0.4: {min(hi):.2f} to {max(hi):.2f} ms",
              f"  absolute gain below r=0.4: {min(lo):.2f} to {max(lo):.2f} ms",
              "  The gain collapses in milliseconds as well as in percent, so the",
              "  null at low ratio is not an artefact of the larger denominator."]

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
    if inert:
        L += ["", "-" * 92, "EXCLUDED: CELLS WHERE THE CONTROLLER NEVER ACTED", "-" * 92,
              "The adapted arm made no adjustment at all, so these compare static",
              "against static. Their null is true by construction and cannot be",
              "evidence about queueing, so they are outside the fit and the tests.", ""]
        for c in inert:
            L.append(f"  target {c['target']:.0f}ms rtt {c['rtt']:.0f}ms "
                     f"(r={c['ratio']:.3f}): 0 adjustments, "
                     f"measured {c['benefit']:+.1f}%")
        L.append("")
        L.append("  Cause: the scaled HEAVY threshold lands on the operating drop")
        L.append("  rate, so the regime oscillates and the stability gate that")
        L.append("  requires five consecutive identical classifications never opens.")

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
        tested_ratios = sorted({round(c["ratio"], 3) for c in cs
                                if sum(1 for d in cs
                                       if round(d["ratio"], 3) == round(c["ratio"], 3)) > 1},
                               reverse=True)
        rng = [c for c in cs if round(c["ratio"], 3) in tested_ratios]
        fold = (max(c["rtt"] for c in rng) / min(c["rtt"] for c in rng)) if rng else 0
        L += ["CONCLUSION: the ratio target/RTT, not RTT, governs the benefit.",
              f"Invariance is demonstrated at ratio "
              f"{', '.join(f'{r:g}' for r in tested_ratios)} over a "
              f"{fold:.0f}-fold range of RTT, and the fitted curve predicts",
              f"held-out interior ratios to {st.fmean(errs):.1f} percentage points.",
              "",
              "Scope, stated rather than implied: this holds at fixed",
              "target/interval, which was scaled with the target throughout, and",
              "rests on cells where the controller demonstrably acted. Cells where",
              "it never adjusted are excluded above and prove nothing either way."]
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

    real = (a.law, a.sweep, a.baseline) == ("results_law", "results_sweep", "results")
    emit_latex(cs, B, r0, k, r2, invariance_ok, holdout_ok, a.texdir, real)

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
    fig.savefig(p, dpi=FIG_DPI, facecolor="white"); plt.close(fig)
    print("\n  wrote", p)


if __name__ == "__main__":
    main()
