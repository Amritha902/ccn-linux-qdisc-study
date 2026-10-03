# Pre-registration: is the benefit of AQM parameter adaptation governed by target/RTT?

This file is committed *before* the measurement campaign finishes. It states the
hypothesis, the decision rules and the thresholds in advance, so that the
analysis cannot be tuned to the answer. The git history is the evidence: the
commit that adds this file, and the commit that adds `src/analyse_law.py` with
its thresholds already written in, both precede the commit that adds
`results_law/`.

## Where this came from

The RTT sweep in the second campaign produced a result we could not explain at
the time. Adaptation recovered a large, highly significant share of bulk-flow
round-trip time on a short path, and nothing at all on longer ones:

| Base RTT | Static fq_codel | Adapted | Change | p |
|---|---|---|---|---|
| 5 ms | 27.68 +/- 0.14 | 22.58 +/- 0.15 | -18.4% | 0.0000 |
| 20 ms | 36.39 +/- 0.08 | 35.87 +/- 0.80 | -1.4% | 0.38 |
| 80 ms | 89.30 +/- 0.37 | 89.86 +/- 0.70 | +0.6% | 0.31 |
| 200 ms | 208.00 +/- 0.76 | 207.47 +/- 0.74 | -0.3% | 0.43 |

Read as a table this is four separate measurements and a shrug. The obvious
reading, "adaptation helps on short paths", is not a mechanism and does not
predict anything.

## The hypothesis

CoDel's `target` is a delay budget. It is a fixed 5 ms by default, while the
path RTT is whatever the path is. So the quantity that should govern whether
that budget is badly chosen is not the RTT, and not the target, but their
ratio:

    r = target / path RTT

When r is small the standing-queue budget is a minor addition to the path and
there is nothing for a controller to win back. When r is of order 1 the budget
is comparable to the path itself, the queue dominates the delay a flow sees,
and shrinking it is worth a lot. On this reading, RTT never appears on its own;
it appears only through r. That is a stronger claim than the table, and unlike
the table it can be wrong.

## Predictions, fixed in advance

**P1, a crossover exists.** Benefit rises from approximately zero to its
ceiling somewhere between r = 0.25 and r = 1.0. Tested by a dense sweep at base
RTT 2, 3, 8, 12 and 40 ms at the default 5 ms target, giving r from 2.5 down to
0.125.

**P2, ratio invariance. This is the falsifiable one.**

*Amended during the campaign, before any P2 measurement was kept.* The first
attempt varied the target while leaving CoDel's interval at 100 ms, which
moved `target/interval` from 0.05 to 0.80 across the cells and so varied a
second dimensionless group alongside the one under test. The interval is now
scaled with the target. The claim this tests is correspondingly narrower than
the sentence below implies, and is stated as: at fixed `target/interval`, the
benefit is governed by `target/RTT`. Whether it survives changes in
`target/interval` is a separate question this campaign does not answer.
`verification/P2_DESIGN.md` records what was wrong and why the P1 sweep is
unaffected.
 If r is the governing
variable, then two configurations with the same r must show the same benefit
even when their RTTs differ several-fold. `target = 20 ms` on a 20 ms path has
r = 1.0, the same as the default `target = 5 ms` on a 5 ms path, despite four
times the RTT. The hypothesis says they behave alike. The competing
explanation, that short paths are simply special, says the 20 ms case will
show nothing,
because 20 ms was one of the RTTs where we already measured nothing.

The decision rule, fixed here: configurations sharing a ratio are *consistent* if
their benefits lie within 10 percentage points. Any wider and P2 fails and the
scaling law is reported as refuted. We report the refutation if it comes. The
purpose of running the test is that it is able to fail.

**P3, hold-out prediction.** Fit the curve with one interior ratio removed,
predict that point, compare to measurement. Repeated leave-one-out across every
interior point. Endpoints are excluded deliberately: holding out an extreme
ratio asks a saturating curve to extrapolate past the data that fixes its own
ceiling, which tests the fitting procedure rather than the hypothesis.

The decision rule, fixed here: mean absolute prediction error at or below 5
percentage points counts as predictive. Above that, any invariance we find is
still reported, but the fitted functional form is not claimed.

## What the answer would mean either way

The published guidance for CoDel is that `target` should be about 5 to 10
percent of `interval`, and that `interval` should be on the order of the path
RTT. A correctly configured box therefore sits at r of roughly 0.05 to 0.10.

If the crossover lands well above that, near r of a few tenths, then the law
says something sharper than "adaptation sometimes helps". It says adaptation
pays only on boxes already configured several times outside CoDel's own design
envelope, and that on a correctly configured box there is nothing left for a
controller to recover. That would explain the null results in this work and in
the literature as the same effect rather than as separate disappointments, and
it would give an operator a number to check before deploying a controller at
all.

If P2 fails, the ratio is not the governing variable, the short-path result
needs a different mechanism, and this document stands as the record of a
hypothesis that was tested and did not survive.
