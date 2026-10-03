# Cells where the controller never acted, and why they are excluded

Found when the full-campaign instrument check flagged the ratio 0.25 pair
after it had already been reported as passing on partial data. That report was
wrong and is corrected here.

## What the check found

At ratio 0.25 the two cells did not receive the same control law:

| cell | regime | excursion | adjustments |
|---|---|---|---|
| target 5 ms, RTT 20 ms | HEAVY | 35.3% | 6 |
| target 20 ms, RTT 80 ms | MODERATE | 0.0% | **0, in all three seeds** |

The second cell's controller ran 109, 108 and 108 ticks across its three
seeds and adjusted nothing. Not once.

## Why

The drop rate in that cell averages 7.7 per second. The HEAVY threshold, after
the F7 scaling by `BASE_TARGET/t0` at a 20 ms target, is 7.5 per second. The
operating point sits almost exactly on the boundary, so the classification
oscillates between MODERATE and HEAVY (66/43, 68/40, 77/31 across the seeds),
the gate that requires five consecutive identical classifications never opens,
and no adjustment is ever attempted.

This is not the F7 scaling being wrong. It is a threshold classifier behaving
the way threshold classifiers do when the signal sits on a threshold.

## Why these cells are excluded rather than reported

A cell whose adapted arm never changes a parameter is running the static
configuration twice. Its null is true by construction. Using it as evidence
that a low ratio yields no benefit is circular: it cannot distinguish "no
benefit because the ratio is low" from "no benefit because nothing happened".

Two cells are excluded on this basis, and both sit at RTT 80 ms:

- target 5 ms, RTT 80 ms, r = 0.062, zero adjustments in all three seeds
- target 20 ms, RTT 80 ms, r = 0.250, zero adjustments in all three seeds

The first of those is from the original RTT sweep, where it had been read as
evidence that adaptation does not help on long paths. Part of that null was
the controller not acting at all.

A third cell is borderline and is kept, with its count visible: target 5 ms at
RTT 200 ms made 1, 0 and 0 adjustments. Rather than invent a cutoff, the mean
adjustment count is now a column in the results table, so a reader can see
exactly where the controller was working.

## What survives, and it is the important part

The crossover itself is measured with an active controller at both ends:

| ratio | benefit | adjustments |
|---|---|---|
| 0.625 | 12.4% | 7 |
| 0.417 | 9.5% | 7 |
| 0.250 | 1.4% | 6 |
| 0.125 | 0.0% | 8 |

At r = 0.125 the controller made eight adjustments and still recovered
nothing. That is a genuine null, not an inert instrument, and it is what makes
the crossover a measurement rather than an artefact.

## The correction to the record

An earlier commit reported P2 as passing at both ratios. It does not. The
ratio 0.25 pair is not a valid invariance test because one of its two cells
was inert. P2 is demonstrated at ratio 1.0 across a sixteenfold range of RTT,
on three cells whose control law and excursion were verified equivalent, and
that is what the papers will claim.
