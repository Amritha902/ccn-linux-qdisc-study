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

---

# F6: the additive step sizes were absolute too

Found immediately after F5, by reading the target trajectory of the first
re-run adapted cell rather than trusting that the bounds fix had been enough.
It had not been.

## The defect

The multiplicative decrease is scale-free, since `p["target"] *= beta` means
the same thing at any operating point. The additive steps were not:

```python
p["target"] -= 0.2              # additive-decrease
p["target"] += ALPHA_T          # additive-increase, 0.5 ms
p["target"] += 0.2              # gentle-increase
p["interval"] += 5
```

As a fraction of the operating point those steps are:

| configured target | 0.2 ms step | 0.5 ms step |
|---|---|---|
| 5 ms | 4% | 10% |
| 20 ms | 1% | 2.5% |
| 80 ms | 0.25% | 0.6% |

The same controller therefore adapts an order of magnitude more slowly, in
relative terms, the larger the target it is deployed against.

## The evidence

The first re-run adapted cell at `target = 20 ms` moved from 20.0 to 18.4 ms
over 84 ticks, entirely in `-0.2` steps: an 8% total excursion. At the 5 ms
default the identical sequence of control decisions would have moved the
target 32%.

## Why it endangered P2 in the opposite direction to F5

F5 would have manufactured a confirmation. F6 would have manufactured a
refutation. At a large configured target the controller does proportionally
less, so it recovers proportionally less delay, so the cells at `target = 20`
and `target = 80` would have shown a smaller benefit than the `target = 5`
cell at the same ratio. The pre-registered rule would have recorded a spread
greater than 10 percentage points, declared ratio invariance refuted, and the
refutation would have been an artefact of the controller's own step size
rather than a fact about queueing.

Both defects were in the same class, absolute constants inside a controller
whose whole subject is a dimensionless ratio, and the second was only visible
because the first was fixed and the trajectory then read.

## The fix

Time-valued steps are scaled by `STEP_SCALE = configured_target / 5.0`, so
every step is the same fraction of the operating point:

```
t0 =  5.0   gentle 0.200 ms (4.00%)   alpha 0.500 ms (10.00%)
t0 = 20.0   gentle 0.800 ms (4.00%)   alpha 2.000 ms (10.00%)
t0 = 80.0   gentle 3.200 ms (4.00%)   alpha 8.000 ms (10.00%)
```

The scale is fixed per run from the configured target rather than tracking the
drifting current target, which is what keeps the default exactly
bit-identical: at 5 ms `STEP_SCALE` is 1.0 and every step is the constant it
always was. Packet-valued steps (`limit`) are left alone, since a packet count
is not a time and does not scale with the delay target.

`src/test_bounds.py` covers both defects: that the steps are equal fractions
at 5, 20 and 80 ms, that they are still exactly 0.2 and 0.5 ms at the default,
and that an 80 ms target now moves 3.2 ms per gentle step instead of 0.2.

## What was discarded, again

The P2 re-run was stopped after 5 of 18 runs and `results_law/ratio_t20_r20`
removed. No P2 measurement under either defective version has entered the
corpus. The 30 P1 runs remain untouched and committed, since all of them ran
at the 5 ms default where both fixes are no-ops.

---

# F7: the regime thresholds were absolute as well

Third defect of the same class, found by auditing every remaining constant at
once rather than waiting to trip over the next one. The audit was prompted by
noticing that the first re-run cell reached its plateau by a different route
than the cell it is supposed to be compared against.

## The defect

`classify()` decides which control law applies from a drop rate in drops per
second, against fixed thresholds:

```python
DR_LIGHT, DR_MOD, DR_HEAVY = 1.0, 10.0, 30.0    # drops/s
```

Drops per second has units of one over time, so it is not scale-free. Measured
on the static arm at ratio 1.0:

| configured target | drops/s | regime under fixed thresholds | action |
|---|---|---|---|
| 5 ms | 59.3 | HEAVY | multiplicative decrease |
| 20 ms | 20.2 | MODERATE | additive decrease |
| 80 ms | 7.1 | LIGHT | additive **increase** |

The three cells whose whole purpose is to be treated identically each received
a different control law, and the 80 ms cell would have been driven in the
opposite direction to the other two.

This was visible in the trajectories before the numbers were in. At ratio 1.0
the 5 ms cell descends in multiplicative steps of varying size to a 52%
excursion, while the 20 ms cell descends in uniform additive steps to 32%.

## The fix, and two caveats stated plainly

Thresholds are scaled by `BASE_TARGET / t0`. Under that scaling all three
cells classify as HEAVY, with margin: 59.3 against 30, 20.2 against 7.5, and
7.1 against 1.875.

The first caveat is that the measured drop rate falls as roughly `t^-0.78`
rather than the `t^-1` this scaling assumes, so the correction is not exact
and is not claimed to be. The second is that exactness is not what P2 needs.
P2 needs every compared cell to receive the same control law, which is a
weaker condition, and one that can be checked directly from the logged
regimes after the runs rather than argued for in advance. That check is
reported with the P2 result.

## What was not scaled, and why

Backlog thresholds are left alone. Measured at ratio 1.0, mean backlog moves
by only x0.90 and x2.17 across a sixteenfold change in target, so it is close
to invariant already and scaling it would introduce an error rather than
remove one. `composite_gradient()` normalises by the drop threshold, so it
follows the scaling automatically. Packet-valued and byte-valued constants
(`limit` steps, `quantum`) are not times and do not scale with a delay target.

## The pattern

Three defects, one cause: absolute constants inside a controller whose entire
subject is a dimensionless ratio. Each was invisible until the previous one
was fixed, because each was masked by the one before it. F5 would have
manufactured a confirmation, F6 a refutation, and F7 would have applied three
different control laws to the three cells being compared.

The general lesson is worth more than the individual fixes. A controller
intended to work at any operating point must express every threshold, bound
and step in units relative to that operating point, and the only reliable way
to find where it does not is to deploy it far from the point its constants
were tuned at and read what it actually did.

## State of the corpus

No P2 measurement under any of the three defective versions has been kept. The
30 P1 runs are untouched and committed, all having run at the 5 ms default
where every fix is exactly a no-op, which `src/test_bounds.py` asserts across
twenty-six checks.
