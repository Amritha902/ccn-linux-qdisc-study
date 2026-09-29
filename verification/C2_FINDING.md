# Why the predictive path still never fires

## What the staged workload showed

With a workload that actually varies (2 → 24 → 2 flows), the corrected
controller behaves as intended in two respects and fails in a third.

**The classifier now works.** Under steady load the regime was HEAVY in 79 of
86 ticks. Under staged load:

```
regimes      : LIGHT 52, HEAVY 29, NORMAL 1
trajectories : STABLE 72, WORSENING 6, RECOVERING 4
```

Both the regime and the gradient-derived trajectory now vary. The original
constant-overload testbed could never have produced this.

**The controller now adapts in both directions.** The original implementation
only ever ratcheted `target` downward to its floor. The corrected one moves it
up under light load and down under heavy load:

```
t= 7.0  LIGHT  target 5.00 -> 5.50
t=14.3  LIGHT  target 5.50 -> 6.00
t=28.3  HEAVY  target 6.00 -> 5.40
t=36.5  HEAVY  target 5.40 -> 4.86
t=50.7  LIGHT  target 4.86 -> 5.36
t=57.8  LIGHT  target 5.36 -> 5.86
```

**But 0 of 6 adjustments are predictive**, and the reason is structural rather
than a coding error.

## The gate and the prediction are mutually exclusive

An adjustment fires only when:

```python
if args.adapt and tick % T3_EVERY_N == 0 and stable_cnt >= STABLE_ROUNDS:
```

`stable_cnt` counts consecutive ticks whose regime is unchanged, and
`STABLE_ROUNDS` is 5. So the controller acts **only after the regime has been
steady for five consecutive samples**.

But the trajectory is derived from the gradient of drop rate and backlog over
the same window. When the regime has been unchanged for five ticks, that
gradient is almost always below the ±0.5 threshold — so the trajectory reads
STABLE, and `pred == regime`, and the adjustment is tagged REACTIVE.

All six adjustments in this run have `trajectory = STABLE`. The ten ticks that
did read WORSENING or RECOVERING never coincided with an adjustment
opportunity, because by construction they cannot.

**The stability gate exists to prevent the controller reacting to noise. The
predictive mechanism exists to let it act before a transition. The two cannot
both apply to the same adjustment.** This is a design contradiction, not a
bug, and it survives the fix to `predict()`.

## Consequence for the paper

C2 (predictive regime detection) has never produced a control action that
differed from the reactive one — not in the original implementation, where an
index guard made it impossible, and not in the corrected one, where the
stability gate makes it unreachable. The contribution should be withdrawn, or
the gate redesigned (for example, allowing an adjustment when the trajectory is
confidently non-STABLE even if the regime has not yet settled) and re-measured.

We report it withdrawn. Redesigning and re-evaluating the gate is future work,
and would need its own controlled comparison.
