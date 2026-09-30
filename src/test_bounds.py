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

    bad = [n for n, ok in checks if not ok]
    for n, ok in checks:
        print(f"  {'ok  ' if ok else 'FAIL'}  {n}")
    if bad:
        sys.exit(f"\n{len(bad)} check(s) failed")
    print("\nall checks passed: no-op at the 5 ms default, so earlier data stands")


if __name__ == "__main__":
    main()
