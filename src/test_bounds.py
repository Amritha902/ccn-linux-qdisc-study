#!/usr/bin/env python3
"""Check that scaling the controller bounds changes nothing at the default.

The parameter bounds used to be absolute (target 0.2 to 20 ms). Against a
qdisc configured with target 80 ms the controller read 80 from tc and the
clamp cut it to 20 on the first tick, so the "adapted" arm was not adapting,
it was being clamped. The bounds are now a multiple of the configured target.

Every run in the first two campaigns and in the P1 sweep used the 5 ms
default. Keeping that data is only legitimate if the change is exactly a
no-op there, which is what this asserts. It also checks the clamp really does
open up at larger targets, so the fix does what it claims.

Run: python3 src/test_bounds.py
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import acape

OLD = (0.2, 20.0, 20.0, 300.0)   # T_MIN, T_MAX, I_MIN, I_MAX before the change


def bounds():
    return (acape.T_MIN, acape.T_MAX, acape.I_MIN, acape.I_MAX)


def main():
    checks = []

    checks.append(("module defaults match the old absolute bounds",
                   bounds() == OLD))

    acape.set_bounds(5.0)
    checks.append(("set_bounds(5.0) reproduces the old bounds exactly",
                   bounds() == OLD))

    acape.set_bounds(20.0)
    checks.append(("set_bounds(20.0) scales fourfold",
                   bounds() == (0.8, 80.0, 80.0, 1200.0)))

    acape.set_bounds(80.0)
    b = bounds()
    checks.append(("set_bounds(80.0) leaves the operating point interior",
                   b[0] < 80.0 < b[1]))
    checks.append(("an 80 ms target is no longer clamped down on sight",
                   max(b[0], min(b[1], 80.0)) == 80.0))

    # The old behaviour, for the record: 80 ms clamped straight to 20 ms.
    checks.append(("the old bounds really did clamp 80 ms to 20 ms",
                   max(OLD[0], min(OLD[1], 80.0)) == 20.0))

    for guard in (0, None, -5.0):
        acape.set_bounds(5.0)
        acape.set_bounds(guard)
        checks.append((f"set_bounds({guard!r}) leaves bounds untouched",
                       bounds() == OLD))

    # ---- F6: the additive steps must scale too -------------------------
    # Only the multiplicative decrease was scale-free. A 0.2 ms step is 4% of
    # a 5 ms target and 0.25% of an 80 ms one, so the controller adapted far
    # more slowly in relative terms the larger the target, which would have
    # refuted ratio invariance by an artefact of its own step size.
    acape.set_bounds(5.0)
    checks.append(("STEP_SCALE is 1.0 at the 5 ms default",
                   acape.STEP_SCALE == 1.0))

    def frac(t0, step):
        acape.set_bounds(t0)
        return step * acape.STEP_SCALE / t0

    for step, name in ((0.2, "gentle step"), (acape.ALPHA_T, "alpha step")):
        fracs = [frac(t, step) for t in (5.0, 20.0, 80.0)]
        checks.append((f"{name} is the same fraction of target at 5, 20 and 80 ms",
                       max(fracs) - min(fracs) < 1e-12))

    acape.set_bounds(5.0)
    checks.append(("gentle step is still exactly 0.2 ms at the default",
                   0.2 * acape.STEP_SCALE == 0.2))
    checks.append(("alpha step is still exactly 0.5 ms at the default",
                   acape.ALPHA_T * acape.STEP_SCALE == 0.5))

    acape.set_bounds(80.0)
    checks.append(("an 80 ms target moves 3.2 ms per gentle step, not 0.2",
                   abs(0.2 * acape.STEP_SCALE - 3.2) < 1e-12))

    for guard in (0, None, -5.0):
        acape.set_bounds(5.0)
        acape.set_bounds(guard)
        checks.append((f"set_bounds({guard!r}) leaves STEP_SCALE untouched",
                       acape.STEP_SCALE == 1.0))

    # ---- F7: the regime thresholds must scale too -----------------------
    # Drops per second has units of 1/time. At ratio 1.0 the measured static
    # drop rates are 59.3, 20.2 and 7.1 per second at targets 5, 20 and 80 ms,
    # which against fixed thresholds classify identical relative congestion as
    # HEAVY, MODERATE and LIGHT. Ratio invariance cannot be tested by an
    # instrument that applies a different control law in each compared cell.
    MEASURED = {5.0: 59.3, 20.0: 20.2, 80.0: 7.1}   # drops/s, static arm

    acape.set_bounds(5.0)
    checks.append(("DR_SCALE is 1.0 at the 5 ms default",
                   acape.DR_SCALE == 1.0))
    checks.append(("thresholds are unchanged at the default",
                   acape.DR_HEAVY * acape.DR_SCALE == 30.0))

    regimes = []
    for t0, dr in MEASURED.items():
        acape.set_bounds(t0)
        regimes.append(acape.classify(dr, 12))
    checks.append(("all three ratio-1.0 cells get the same control law",
                   len(set(regimes)) == 1))
    checks.append(("and that law is HEAVY, as at the 5 ms reference",
                   set(regimes) == {"HEAVY"}))

    # Pin the defect itself, so the claim in F7 is checkable, not asserted.
    acape.set_bounds(5.0)
    old = [acape.classify(dr, 12) for dr in MEASURED.values()]
    checks.append(("unscaled thresholds really did split the three cells",
                   old == ["HEAVY", "MODERATE", "LIGHT"]))

    acape.set_bounds(5.0)
    checks.append(("backlog thresholds are left unscaled",
                   acape.BL_HEAVY == 300 and acape.BL_LIGHT == 20))

    for guard in (0, None, -5.0):
        acape.set_bounds(5.0)
        acape.set_bounds(guard)
        checks.append((f"set_bounds({guard!r}) leaves DR_SCALE untouched",
                       acape.DR_SCALE == 1.0))

    # ---- F8: the control loop period must scale too ---------------------
    # CoDel's interval scales with the target. With an absolute 0.5 s loop
    # period, a 16x target meant sampling three times inside one 1.6 s AQM
    # cycle instead of averaging over several, so the regime flickered, the
    # stability gate never opened, and a whole 86-tick run produced zero
    # adjustments with the target unchanged at 80.000 ms.
    acape.set_bounds(5.0)
    checks.append(("loop period is still 0.5 s at the default",
                   acape.T2_INTERVAL == 0.5))

    ratios = []
    for t0 in (5.0, 20.0, 80.0):
        acape.set_bounds(t0)
        aqm_interval_s = t0 * 20 / 1000.0      # configured interval is 20x target
        ratios.append(acape.T2_INTERVAL / aqm_interval_s)
    checks.append(("loop period stays the same multiple of the AQM interval",
                   max(ratios) - min(ratios) < 1e-9))

    acape.set_bounds(80.0)
    checks.append(("an 80 ms target ticks every 8 s, not 0.5 s",
                   abs(acape.T2_INTERVAL - 8.0) < 1e-9))

    for guard in (0, None, -5.0):
        acape.set_bounds(5.0)
        acape.set_bounds(guard)
        checks.append((f"set_bounds({guard!r}) leaves the loop period untouched",
                       acape.T2_INTERVAL == 0.5))

    bad = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'}  {n}")
    if bad:
        sys.exit(f"\n{len(bad)} check(s) failed")
    print("\nall checks passed: no-op at the 5 ms default, so earlier data stands")


if __name__ == "__main__":
    main()
