#!/usr/bin/env python3
"""Check that the scaling-law analysis can report its own refutation.

P2 is the test that is supposed to be able to kill the hypothesis. Until the
ratio-invariance runs finished, no two cells in the corpus shared a ratio, so
the branch that detects inconsistency had never executed even once. An
analysis whose failure path is untested is an analysis that can only report
success, which is worth nothing.

This builds a synthetic corpus with one ratio deliberately consistent and one
deliberately inconsistent, and asserts that the script says so in both cases
and reaches the refuted conclusion. It touches no real data.

Run: python3 src/test_analyse_law.py
"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

# (target_ms, rtt_ms, static_mean, adapted_mean)
# r = 1.0 reached twice and made to agree; r = 0.25 reached twice and made to
# disagree by ~20 percentage points, which is well past the 10-point rule.
SPEC = [(5, 2, 26.0, 21.0), (5, 5, 27.0, 22.0), (20, 20, 40.0, 32.5),
        (5, 20, 36.0, 35.5), (20, 80, 92.0, 72.0), (5, 80, 89.0, 89.5),
        (5, 200, 208.0, 207.5)]


def build(root):
    for tgt, rtt, stat, adap in SPEC:
        for adaptive, mean in ((False, stat), (True, adap)):
            for seed in (1, 2, 3):
                d = os.path.join(root, f"t{tgt}_r{rtt}_{'a' if adaptive else 's'}{seed}")
                os.makedirs(d, exist_ok=True)
                json.dump({"workload": "steady", "aqm": "fq_codel",
                           "adaptive": adaptive, "base_rtt_ms": rtt,
                           "aqm_target_ms": (None if tgt == 5 else tgt),
                           "bulk_rtt_mean_ms": mean + 0.05 * seed, "seed": seed,
                           "drop_rate_mean_per_s": 60 + 10 * adaptive,
                           "retransmits": 6000 + 2000 * adaptive,
                           "throughput_mbps": 9.4,
                           "sojourn_mean_ms": 19.0 - 2 * adaptive,
                           "backlog_mean_pkts": 12.0 - 1.5 * adaptive},
                          open(os.path.join(d, "summary.json"), "w"))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        data, out = os.path.join(tmp, "data"), os.path.join(tmp, "out")
        os.makedirs(data); os.makedirs(out)
        build(data)
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "analyse_law.py"),
             "--law", data, "--sweep", os.path.join(tmp, "none"),
             "--baseline", os.path.join(tmp, "none"), "--outdir", out,
             # Must be redirected. --texdir defaults to paper/generated, so
             # without this the synthetic fixture overwrites the real
             # law_facts.tex and table_law.tex that the papers cite, and the
             # papers would carry invented numbers.
             "--texdir", os.path.join(out, "tex")],
            capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout); print(r.stderr, file=sys.stderr)
            sys.exit("analyse_law.py exited non-zero")
        o = r.stdout

    checks = [
        ("consistent ratio detected", "spread 0.3 percentage points  -> consistent" in o),
        ("inconsistent ratio detected", "INCONSISTENT" in o),
        ("refutation reached", "ratio invariance FAILS" in o),
        ("refutation is the stated conclusion", "is refuted and is reported as such" in o),
        ("both members of a tied ratio appear", o.count("ratio  1.00:") == 1),
        ("hold-out ran", "HOLD-OUT PREDICTION" in o),
        ("cost table ran", "WHAT THE LATENCY IS BOUGHT WITH" in o),
        ("queue estimate labelled by basis", "qest is backlog-derived" in o),
    ]
    bad = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'}  {n}")
    if bad:
        sys.exit(f"\n{len(bad)} check(s) failed: {', '.join(bad)}")
    print("\nall checks passed: the analysis reports refutation when the data refutes it")


if __name__ == "__main__":
    main()
