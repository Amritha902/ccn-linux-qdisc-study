# The PIE arm of the cross-AQM test was confounded twice over

Caught by noticing that PIE's controller logged three adjustments where
codel's logged eight, before reading the result as a refutation. Both defects
are mine, in the campaign I designed rather than in inherited code.

## What the numbers looked like

| aqm | RTT | r | benefit | p | adjustments |
|---|---|---|---|---|---|
| `codel` | 8 ms | 0.625 | 7.9% | 0.0101 | 8 |
| `pie` | 8 ms | 1.875 | 4.0% | 0.28 | **3** |
| `pie` | 15 ms | 1.000 | **-4.2%** | 0.44 | **3** |

Read at face value, PIE shows no benefit at either ratio and the ratio law
does not transfer. That reading would have been wrong.

## Defect one: the controller wrote a parameter it never decided to change

PIE has no `interval`. It calls its update period `tupdate`, with a default of
15 ms. `get_params()` searched the qdisc's output for `interval` only, found
nothing, and left the controller's interval state at its hardcoded 100 ms
default. The first adjustment then wrote `tupdate 100ms`.

So the adapted arm did not merely adjust PIE's target. It changed PIE's update
period from 15 ms to 100 ms, a factor of 6.7, as a side effect of a parsing
miss. The controller log shows it plainly: `interval_ms` reads `100.00` on all
34 ticks while the qdisc was configured with 15 ms.

The comparison was therefore not static PIE against adapted PIE. It was PIE
against a differently configured PIE, and the difference in update period is
not something the scaling law says anything about.

## Defect two: the run was three times too short

The controller's loop period scales with the configured target, which F8
established. PIE's default target is 15 ms against \texttt{fq\_codel}'s 5, so
`STEP_SCALE` is 3, the loop period is 1.75 s rather than 0.5 s, and a 60 s run
yields 34 ticks. Adjustments are gated to every tenth tick, so 34 ticks allow
three adjustment opportunities against the eight codel received.

The cross-AQM campaign ran both qdiscs at a flat 60 s. That is exactly the
mistake F8 documented, applied to the ratio-invariance campaign and then not
carried over to this one, where the relevant scale factor comes from each
qdisc's own default target rather than from an overridden one.

## What was kept and what was discarded

The 24 `codel` runs are retained. Its default target is 5 ms, the same as
`fq_codel`, so its scale factor is 1, its 60 s duration is correct, and it
logged eight adjustments per cell, matching `fq_codel`. Neither defect touches
it: `codel` has a real `interval` parameter that parsed correctly.

The 14 `pie` runs are discarded. No confounded PIE measurement enters the
corpus.

## The fixes

`get_params()` now reads the interval state under whichever name the qdisc
uses, taken from the same `PARAM_SETS` table that `apply_params()` writes
through, so a read and a write cannot disagree about what a parameter is
called. `src/test_params.py` asserts the mapping for all four
delay-targeting qdiscs, pins the old behaviour of finding nothing in PIE's
output, checks that no qdisc is written a parameter it does not accept, and
checks that `fq_codel`'s four are unchanged, since every earlier run depends
on that.

`src/run_cross_aqm.sh` now derives each sweep's duration from that qdisc's
default target, giving 60 s for `codel` and 180 s for `pie`.

## What the codel result says, now that it stands alone

`codel` is the only valid cross-AQM arm so far, and it does not straightforwardly
support the law:

| r | codel benefit | p | fq_codel benefit | p |
|---|---|---|---|---|
| 1.667 | 12.6% | 0.0089 | 20.1% | 0.0001 |
| 1.000 | 9.3% | 0.13 | 18.4% | $<$0.0001 |
| 0.625 | 7.9% | 0.0101 | 12.4% | 0.0001 |
| 0.250 | **4.3%** | **0.0003** | 1.4% | 0.38 |

The ceiling is roughly half, which the pre-registration allows, since how much
delay is recoverable depends on how hard each algorithm can be driven. The
shape is the problem. `codel` declines gently rather than crossing over, and
retains a small but significant benefit at $r = 0.25$ where `fq_codel` has
none. A saturating fit to those four points would place the half-benefit ratio
well below `fq_codel`'s 0.50.

Read conservatively, that means the crossover is not purely a property of the
delay target. Flow queueing sharpens it. That is a narrower claim than the
pre-registration hoped for, and it is what the data supports until PIE is
re-run properly.
