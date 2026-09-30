# An unexplained outlier in the mixed workload, and what we did about it

## What we saw

Three repetitions of `fq_codel` under the adaptive controller, mixed workload:

| Repetition | sparse jitter mean (ms) | sparse jitter max (ms) | sparse loss (%) |
|---|---|---|---|
| 1 | 2.211 | 2.562 | 0.029 |
| 2 | 1.813 | 2.060 | 0.000 |
| **3** | **5.146** | **10.742** | **6.307** |

Averaged, this reads as the adaptive controller tripling sparse-flow jitter and
raising loss by three orders of magnitude against static `fq_codel`
(2.001 ms, 0.002%). Reported that way it would be a striking result: the
adaptation actively harming the flows it is meant to help.

## Why we do not report it that way

The controller's actions in the outlier run are byte-identical to those in the
run with no loss at all:

```
repetition 3:  t=9.16  target 5.0000 -> 4.5000   limit 1024 -> 921
               t=20.49 target 4.5000 -> 4.0500   limit  921 -> 828
               t=31.94 target 4.0500 -> 3.6400   limit  828 -> 745
               t=43.52 target 3.6400 -> 3.2700   limit  745 -> 670
               t=55.49 target 3.2700 -> 2.9400   limit  670 -> 603

repetition 2:  t=9.49  target 5.0000 -> 4.5000   limit 1024 -> 921
               t=20.09 target 4.5000 -> 4.0500   limit  921 -> 828
               t=31.03 target 4.0500 -> 3.6400   limit  828 -> 745
               t=41.31 target 3.6400 -> 3.2700   limit  745 -> 670
               t=51.34 target 3.2700 -> 2.9400   limit  670 -> 603
```

Same parameter trajectory, same number of adjustments, same final state. The
difference in outcome therefore cannot be attributed to the controller's
decisions. Something else differed between the two runs.

An average over three repetitions, one of which is unexplained, is not a
result. Averaging here would manufacture a finding out of a measurement we do
not understand, which is the failure mode this whole study exists to correct.

## What we did

Added further repetitions of this one condition to establish whether the
outlier recurs:

- If it recurs at roughly one run in three, it is a real intermittent
  behaviour and belongs in the results with its mechanism investigated.
- If it does not recur across additional repetitions, it is run-to-run
  variance in the measurement environment and belongs in the record as such,
  with the median rather than the mean reported for this cell.

Either way the disputed cell gets more data rather than a narrative.

## Robust findings from the same campaign

These hold across all three repetitions and are not in question:

| System | sparse loss (%) | note |
|---|---|---|
| pfifo, no AQM | 8.149, 7.471, 8.306 | consistently around 8% |
| FQ-PIE | 0.000, 0.000, 0.000 | |
| CAKE | 0.000, 0.021, 0.000 | lowest sparse jitter at 1.358 ms mean |
| fq_codel, static | 0.000, 0.007, 0.000 | |

Any flow-queueing discipline with a delay target protects sparse
latency-sensitive flows from bulk traffic almost completely, while an
unmanaged queue loses roughly one packet in twelve. This is a mechanism the
bulk-only campaign could not observe, and it is the clearest argument for
running the mixed workload at all.
