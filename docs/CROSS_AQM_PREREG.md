# Pre-registration: does the ratio law transfer to a different AQM algorithm?

Committed before the campaign runs, same as `docs/SCALING_LAW.md`. The git
history is the evidence: this file and `src/run_cross_aqm.sh` precede
`results_cross/`.

## Why this is the test worth running next

The ratio law was established on `fq_codel`: the benefit of adapting an AQM's
parameters is governed by `r = target / RTT`, with half the benefit at
`r = 0.50`, invariant across a sixteenfold RTT range at `r = 1.0`.

As it stands that is a statement about one qdisc, and a reviewer is entitled to
read it as a fact about CoDel's sojourn-threshold mechanism rather than about
delay targets in general. The way to settle that is to test an AQM that reaches
a delay target by a completely different route.

PIE is that AQM. It regulates a drop *probability* with a proportional-integral
controller driven by a queue-delay estimate and its derivative. It shares
nothing with CoDel's mechanism except the existence of a delay target. If the
same dimensionless ratio governs PIE, the law is about delay targets. If it
does not, the law is about CoDel, and it should be stated that narrowly.

Plain `codel` is included as the intermediate case: same mechanism as
`fq_codel`, no flow queueing. It separates the law from the scheduler.

## The discriminating prediction

This is the part that can fail, and it is sharp because the two systems are
measured **at the same path RTT**.

At RTT = 20 ms:

| qdisc | default target | r | measured / predicted |
|---|---|---|---|
| `fq_codel` | 5 ms | 0.25 | +1.4%, not significant (already measured) |
| `pie` | 15 ms | 0.75 | **predicted: a large, significant benefit** |

Same path, same rate, same flow count, same load. RTT is identical, so any
explanation in terms of RTT predicts the same outcome for both. The ratio
explains a difference, because 15 ms against a 20 ms path is three times the
budget that 5 ms is.

If PIE at RTT 20 ms shows no benefit, the ratio law does not transfer and the
paper says so.

## Predictions, thresholds fixed here

**X1. A crossover exists for each AQM.** Sweeping RTT at each qdisc's own
default target should produce the same saturating shape, benefit falling away
below `r` of a few tenths.

  - `codel`  at target 5 ms: RTT 3, 5, 8, 20 gives r = 1.67, 1.00, 0.63, 0.25
  - `pie`    at target 15 ms: RTT 8, 15, 30, 60 gives r = 1.88, 1.00, 0.50, 0.25

**X2. The crossover sits at the same ratio.** Fitting each AQM separately, the
half-benefit ratios should agree. Decision rule, fixed now: the fitted `r0`
values agree if they lie within a factor of two of each other, and of the
0.50 already measured for `fq_codel`. Wider than that and the law is
AQM-specific.

**X3. The same-RTT discrimination above.** `pie` at RTT 20 ms (r = 0.75)
should show a significantly larger benefit than `fq_codel` at RTT 20 ms
(r = 0.25). Decision rule: significant at p < 0.05 and at least 5 percentage
points larger.

## What is deliberately not claimed

The ceiling need not match across AQMs. How much delay is recoverable depends
on how aggressively each algorithm can be driven, and PIE's controller is not
CoDel's. The claim under test is about *where* the crossover sits, not how high
the plateau is.

Cells where the controller makes no adjustment are excluded, as in the main
campaign, and for the reason given in `verification/INERT_CELLS.md`: a null
that is true by construction is not evidence.

## Instrument equivalence

Comparisons across AQMs cannot use the excursion check from
`src/check_regimes.py` as a like-for-like test, because the same relative
target excursion means different things to a sojourn threshold and to a PI
controller. What is checked instead, and reported: that the controller
adjusted at all, how many times, and that the regime classification was
stable enough for the stability gate to open. A cell failing that is reported
as inconclusive rather than as a result.
