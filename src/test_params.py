#!/usr/bin/env python3
"""Check the controller reads and writes each qdisc's own parameter names.

PIE has no `interval`; it calls its update period `tupdate`. get_params
searched only for `interval`, so against PIE the controller's interval state
stayed at its hardcoded 100 ms default while the qdisc was configured with
15 ms, and the first adjustment wrote `tupdate 100ms`: a 6.7x change to PIE's
update period that no control decision asked for. The whole PIE arm of the
cross-AQM campaign was confounded by it.

Run: python3 src/test_params.py
"""
import os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import acape

HEADS = {
    "fq_codel": "qdisc fq_codel 10: parent 1:1 limit 1024p target 5ms "
                "interval 100ms memory_limit 32Mb ecn quantum 1514",
    "codel":    "qdisc codel 10: parent 1:1 limit 1024p target 5ms "
                "interval 100ms",
    "pie":      "qdisc pie 10: parent 1:1 limit 1000p target 15ms "
                "tupdate 15ms alpha 2 beta 20",
    "fq_pie":   "qdisc fq_pie 10: parent 1:1 limit 1024p flows 1024 "
                "target 15ms tupdate 15ms alpha 2 beta 20",
}
# what the interval state should read, per qdisc, from the heads above
WANT_INTERVAL = {"fq_codel": 100.0, "codel": 100.0, "pie": 15.0, "fq_pie": 15.0}


def read_interval(kind, head):
    names = [tc for tc, st in acape.PARAM_SETS.get(kind, acape.PARAM_SETS["fq_codel"])
             if st == "interval"] or ["interval"]
    for nm in names:
        m = re.search(rf"{nm} (\S+?)(?:\s|$)", head)
        if m:
            return acape.parse_time_to_ms(m.group(1))
    return None


def main():
    checks = []

    for kind, head in HEADS.items():
        got = read_interval(kind, head)
        checks.append((f"{kind}: interval state reads {WANT_INTERVAL[kind]}ms "
                       f"from its own name", got == WANT_INTERVAL[kind]))

    # The old behaviour, pinned so the claim is checkable.
    m = re.search(r"interval (\S+?)(?:\s|$)", HEADS["pie"])
    checks.append(("searching only for 'interval' finds nothing in PIE's head",
                   m is None))

    # A write must use only names the qdisc accepts.
    ACCEPTS = {
        "fq_codel": {"target", "interval", "limit", "quantum"},
        "codel":    {"target", "interval", "limit"},
        "pie":      {"target", "tupdate", "limit"},
        "fq_pie":   {"target", "tupdate", "limit"},
    }
    for kind, ok in ACCEPTS.items():
        emitted = {tc for tc, _ in acape.PARAM_SETS[kind]}
        checks.append((f"{kind}: writes only accepted parameters",
                       emitted <= ok))
        checks.append((f"{kind}: does not write 'quantum' unless accepted",
                       ("quantum" in emitted) == ("quantum" in ok)))

    # fq_codel must be untouched, since every earlier run depends on it.
    checks.append(("fq_codel still writes exactly its original four",
                   [tc for tc, _ in acape.PARAM_SETS["fq_codel"]]
                   == ["target", "interval", "limit", "quantum"]))

    bad = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'}  {n}")
    if bad:
        sys.exit(f"\n{len(bad)} check(s) failed")
    print("\nall checks passed: each qdisc is read and written under its own names")


if __name__ == "__main__":
    main()
