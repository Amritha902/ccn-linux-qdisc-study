# The `sojourn_mean_ms` field is an estimate, not a measurement

Found while testing whether the queue-delay reduction accounts arithmetically
for the end-to-end RTT reduction in the scaling-law campaign. It does not, and
the reason is a naming problem rather than a physics problem.

## What the field actually is

`src/acape.py` computes, once per controller tick:

```python
# queue delay estimate: bytes in queue / drain rate
sojourn = (blb * 8 / (args.rate_mbit * 1e6) * 1000) if args.rate_mbit else 0.0
```

and logs it as `sojourn_est_ms`. `src/run_experiment.py` then averages that
column across ticks and writes it into the summary as `sojourn_mean_ms`,
dropping the `est` that the controller was careful to keep.

So the field is a time-average of an instantaneous backlog snapshot divided by
the configured drain rate, sampled at roughly 1 Hz. It is not CoDel's sojourn
time and it is not measured from packets.

## Why it cannot reconcile with bulk RTT

Two independent reasons, both structural:

1. **Different weightings.** The estimate is time-averaged: every tick counts
   once, whether the queue was busy or idle. Bulk RTT is packet-weighted, and
   packets arrive disproportionately while the queue is long. A packet-weighted
   delay therefore exceeds a time-averaged occupancy for any bursty arrival
   process, and the gap grows with burstiness.

2. **Sampling rate.** One snapshot per second cannot see queue excursions that
   build and drain inside a second, which at 10 Mbit/s and a 1024-packet limit
   is most of them.

Measured across the five ratio cells available, the estimated queue reduction
accounts for 71%, 32%, 359%, 12% and 255% of the measured bulk-RTT reduction.
A quantity that lands on both sides of 100% by an order of magnitude is not
tracking the thing it is named after.

## What was done about it

The field was **not** renamed. Over a hundred summaries across three campaigns
already carry this key, and renaming it midway would make early and late runs
incomparable for the sake of cosmetics. This is the same reasoning applied to
the `--seed` semantics earlier in the project.

Instead:

- The papers never used it. It appears in `paper/acape.tex` only in the
  background paragraph describing how CoDel works, which is correct usage and
  refers to CoDel's own sojourn, not to this field.
- `src/analyse_law.py` reports the column as `qest` with its basis stated
  inline, and the mechanism argument in the scaling-law analysis rests on
  `backlog_mean_pkts`, which is a counter read directly from `tc -s qdisc`.

## The part that still stands

The observation this was checking survives without the field. At low
target/RTT the controller demonstrably still acts: backlog, a directly
measured counter, falls by up to 21.8% in cells where end-to-end RTT does not
move at all. The null result at low ratio is therefore not the controller
failing to act. It is the queue it drains being a negligible share of the
delay budget on a long path. That argument needs only backlog and RTT, both
measured.
