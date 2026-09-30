# F5: absolute parameter bounds invalidated the ratio-invariance test

Caught before the affected runs executed, while checking what could make P2
fail or succeed for the wrong reason. This one would have made it succeed for
the wrong reason, which is worse.

## The defect

`src/acape.py` clamped its parameters against fixed absolute bounds:

```python
T_MIN, T_MAX = 0.2, 20.0      # ms
I_MIN, I_MAX = 20.0, 300.0    # ms
```

The controller does not assume the default target. It reads the real one out
of `tc` at startup:

```python
m = re.search(r"target (\S+?)(?:\s|$)", head)
```

So against a qdisc configured with `target 80ms` the controller began at 80
and the clamp cut it to 20 on the first adjustment. A fourfold reduction,
decided by a constant, before any control logic ran.

## Why this specifically endangered P2

P2 tests ratio invariance by holding `r = target/RTT` fixed while changing
both. Two of its three cells use a non-default target, and the worst is
`target = 80 ms` on an 80 ms path:

- The static arm runs the whole experiment at `target = 80 ms`.
- The adapted arm is clamped to 20 ms within one tick and stays there.

That comparison is `80 ms target` against `20 ms target`. It would have
produced a large, highly significant benefit at nominal `r = 1.0`, matching
the 18 to 20% the hypothesis predicts for that ratio, and it would have been
reported as a clean confirmation of ratio invariance. It would have been an
artefact of a constant.

The clamp also moves the cell off the ratio it is supposed to be testing: an
80 ms target forced to 20 ms on an 80 ms path is running at `r = 0.25`, not
`r = 1.0`.

A test that can only be confirmed is not a test, and this defect could only
have confirmed.

## The fix

The bounds are now a fixed multiple of the configured target, so the
controller explores the same relative range wherever it is deployed:

```python
T_MIN_R, T_MAX_R = 0.04, 4.0      # x configured target
I_MIN_R, I_MAX_R = 4.0, 60.0      # x configured target
```

`set_bounds()` is called once at startup with the target read from `tc`.

## Why the existing data still stands

The multipliers were chosen so that the 5 ms default reproduces the previous
absolute numbers exactly, not approximately:

| bound | multiplier | at target 5 ms | previous |
|---|---|---|---|
| `T_MIN` | 0.04 | 0.2 | 0.2 |
| `T_MAX` | 4 | 20.0 | 20.0 |
| `I_MIN` | 4 | 20.0 | 20.0 |
| `I_MAX` | 60 | 300.0 | 300.0 |

Every run in the first campaign, the sweep, and the 30-run P1 dense sweep used
the 5 ms default, so all of it is bit-identical under this change and none of
it needs re-running. `src/test_bounds.py` asserts that equality, along with
the fact that the old bounds really did clamp 80 ms to 20 ms, so the claim in
this document is checkable rather than asserted.

## What was discarded

The campaign was stopped as soon as the first P2 cell began writing. One
partially written directory, `results_law/ratio_t20_r20`, was removed. No
completed P2 run exists under the old bounds, so no confounded measurement
entered the corpus. The P1 data was untouched and is committed.

## The narrower lesson

A controller whose exploration range is absolute cannot be deployed at an
operating point outside that range, and will silently pretend to control
while doing nothing of the kind. Making the range relative to the operating
point is the correct design independently of this experiment, and it happens
to be the design a paper about a dimensionless ratio ought to have had from
the start.
