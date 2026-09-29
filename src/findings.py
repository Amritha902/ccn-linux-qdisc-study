#!/usr/bin/env python3
"""Decide what the results actually support, before any prose is written.

Runs the specific comparisons the paper's claims depend on and reports, for
each, the effect size and whether it is distinguishable from noise given the
seed-to-seed variation. Welch's t-test is used because group variances are not assumed equal and n is
small; the p-value is computed exactly from Student's t via the incomplete beta
function, not by a normal approximation, which at n=3 would overstate
significance.

The point of this script is to stop the write-up choosing its own conclusion.
"""
import argparse, glob, json, math, os, statistics as st
from collections import defaultdict


def load(resdir):
    runs = []
    for f in sorted(glob.glob(os.path.join(resdir, "*", "summary.json"))):
        try:
            runs.append(json.load(open(f)))
        except Exception:
            pass
    return runs


def key(r):
    return f"{r['aqm']}_acape" if r.get("adaptive") else r["aqm"]


def _betacf(a, b, x, itmax=200, eps=3e-12):
    """Continued fraction for the incomplete beta function (Lentz's method)."""
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < eps:
            break
    return h


def betainc(a, b, x):
    """Regularised incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
             + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(lbeta) * _betacf(a, b, x) / a
    return 1.0 - math.exp(lbeta) * _betacf(b, a, 1.0 - x) / b


def t_sf(t, dof):
    """Two-sided survival function of Student's t.

    Computed exactly via the incomplete beta function rather than by a normal
    approximation. At n=3 per group the normal approximation is markedly
    anti-conservative -- it would report p<0.05 for differences a t-test with
    ~4 degrees of freedom does not support.
    """
    if dof <= 0:
        return float("nan")
    x = dof / (dof + t * t)
    return betainc(0.5 * dof, 0.5, x)


def welch(a, b):
    """Welch's t statistic, degrees of freedom, and exact two-sided p."""
    a = [x for x in a if x is not None]
    b = [x for x in b if x is not None]
    if len(a) < 2 or len(b) < 2:
        return None, None, None
    ma, mb = st.fmean(a), st.fmean(b)
    va, vb = st.variance(a), st.variance(b)
    na, nb = len(a), len(b)
    se2 = va / na + vb / nb
    if se2 <= 0:
        return None, None, None
    t = (ma - mb) / math.sqrt(se2)
    dof = se2 ** 2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    return t, dof, t_sf(abs(t), dof)


def cohen_d(a, b):
    a = [x for x in a if x is not None]
    b = [x for x in b if x is not None]
    if len(a) < 2 or len(b) < 2:
        return None
    na, nb = len(a), len(b)
    sp2 = ((na - 1) * st.variance(a) + (nb - 1) * st.variance(b)) / (na + nb - 2)
    return (st.fmean(a) - st.fmean(b)) / math.sqrt(sp2) if sp2 > 0 else None


METRICS = ["rtt_p95_ms", "rtt_mean_ms", "backlog_mean_pkts",
           "throughput_mbps", "jain", "sojourn_p95_ms"]

COMPARISONS = [
    ("fq_codel", "fq_codel_acape", "Does runtime adaptation beat static fq_codel?"),
    ("pfifo", "fq_codel", "Does fq_codel beat an unmanaged FIFO?"),
    ("fq_codel", "cake", "Does fq_codel differ from CAKE?"),
    ("fq_codel", "fq_pie", "Does fq_codel differ from FQ-PIE?"),
    ("fq_codel", "pie", "Does flow queueing matter (fq_codel vs single-queue PIE)?"),
    ("fq_codel", "codel", "Does flow queueing matter (fq_codel vs single-queue CoDel)?"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    runs = load(a.results)
    out = []

    def emit(s=""):
        print(s)
        out.append(s)

    emit(f"Loaded {len(runs)} runs from {a.results}")
    for wl in ("steady", "staged"):
        sel = [r for r in runs if r.get("workload") == wl]
        if not sel:
            continue
        by = defaultdict(list)
        for r in sel:
            by[key(r)].append(r)
        emit()
        emit("=" * 96)
        emit(f"WORKLOAD: {wl}   systems: {', '.join(sorted(by))}")
        emit("=" * 96)
        for lhs, rhs, question in COMPARISONS:
            if lhs not in by or rhs not in by:
                continue
            emit()
            emit(f"  {question}")
            emit(f"  {lhs} (n={len(by[lhs])})  vs  {rhs} (n={len(by[rhs])})")
            for m in METRICS:
                A = [r.get(m) for r in by[lhs]]
                B = [r.get(m) for r in by[rhs]]
                if not [x for x in A if x is not None] or not [x for x in B if x is not None]:
                    continue
                ma = st.fmean([x for x in A if x is not None])
                mb = st.fmean([x for x in B if x is not None])
                t, dof, p = welch(A, B)
                d = cohen_d(A, B)
                rel = ((mb - ma) / ma * 100) if ma else float("nan")
                verdict = "n/a"
                if p is not None:
                    verdict = "DISTINGUISHABLE" if p < 0.05 else "not distinguishable"
                emit(f"    {m:22s} {ma:9.3f} -> {mb:9.3f}  ({rel:+7.1f}%)  "
                     f"p={'%.3f' % p if p is not None else '  n/a'}  "
                     f"dof={'%.1f' % dof if dof is not None else 'n/a':>5s}  "
                     f"d={'%.2f' % d if d is not None else ' n/a'}   {verdict}")
    if a.out:
        with open(a.out, "w") as fh:
            fh.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
