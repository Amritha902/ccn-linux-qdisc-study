# Verdicts on three pre-registered campaigns

All thresholds were committed before the data existed. Two predictions passed,
three failed, and one earlier claim of mine turned out to be a coincidence.
Reported in that spirit rather than selectively.

## Cross-AQM transfer (docs/CROSS_AQM_PREREG.md)

| aqm | mechanism | cells | ceiling | r0 | k | R2 |
|---|---|---|---|---|---|---|
| `fq_codel` | flow queueing + sojourn threshold | 7 | 20.5% | 0.49 | 2.8 | 0.986 |
| `codel` | sojourn threshold, no flow queueing | 4 | 13.0% | 0.42 | 2.0 | 0.978 |
| `pie` | proportional-integral on drop probability | 5 | 29.0% | 1.06 | 1.1 | 0.992 |

**X1, a crossover exists for each: PASS.** All three are well described by the
same saturating form.

**X2, the crossovers agree within a factor of two: FAIL.** The spread is
2.52x. The CoDel family agrees tightly, 0.49 against 0.42, but PIE's crossover
sits roughly 2.2 times higher.

**X3, the same-RTT discrimination: PASS.** At a fixed 20 ms path:

| aqm | r | benefit | p |
|---|---|---|---|
| `fq_codel` | 0.250 | +1.4% | 0.38, not significant |
| `codel` | 0.250 | +3.6% | 0.025 |
| `pie` | 0.750 | +11.0% | 0.0089 |

PIE exceeds `fq_codel` by 9.6 percentage points at the same RTT, significant,
clearing the pre-registered rule of 5 points at p below 0.05. Identical path,
rate, flow count and load, so no account in terms of RTT reproduces it.

### Why X2 probably failed, and why the campaign cannot say

PIE's native `target/interval` is 1.0, a 15 ms target against a 15 ms
`tupdate`. CoDel's is 0.05, a 5 ms target against a 100 ms interval. The
scaling law was established holding `target/interval` at 0.05, which is the
scope limit already stated for it.

By sweeping each qdisc at its own defaults, this campaign varied that second
dimensionless group across the very comparison it was meant to isolate. X2
therefore conflates "a different mechanism" with "a different configuration
shape" and cannot separate them. That is a flaw in the design, not a
surprise in the data.

### What the campaign does support

`r = target/RTT` is the governing variable for all three mechanisms, by X1 and
X3. Its critical value is not universal: about 0.45 for the CoDel family and
roughly twice that for PIE, with the difference confounded by
`target/interval`. Flow queueing does not move the crossover at all, 0.49
against 0.42, but raises the ceiling from 13.0% to 20.5% and sharpens the
transition from k of 2.0 to 2.8.

## The packet floor (docs/SERIALIZATION_PREREG.md)

`r` held at 1.0, target and RTT both 5 ms, only the link rate varied.

| rate | MTU serialisation | s | benefit | p |
|---|---|---|---|---|
| 2 Mbit | 6.06 ms | 0.83 | 13.2% | 0.0005 |
| 5 Mbit | 2.42 ms | 2.06 | 18.2% | 0.0001 |
| 10 Mbit | 1.21 ms | 4.13 | 18.0% | 0.0000 |
| 20 Mbit | 0.61 ms | 8.26 | 14.1% | 0.0004 |
| 50 Mbit | 0.24 ms | 20.64 | 7.1% | 0.0172 |

**S1, the benefit is suppressed below s = 1: FAIL.** It is 13.2% and highly
significant there. The floor itself is real, since at 2 Mbit a single packet
takes 6.06 ms against a 5 ms target and CoDel cannot reach it, but the
controller still reduces queue occupancy above that floor. The mechanism
reasoning behind the prediction was wrong.

**S2, the benefit plateaus above s = 4: FAIL.** It declines instead, 18.0 to
14.1 to 7.1 percent.

**S3's conclusion survives in modified form.** There is a real second-group
dependence, so the single-variable law is incomplete, but its shape is a peak
near `s` of 2 to 4 falling away on both sides rather than the floor that was
predicted. The decline at high `s` has a plain reading: static bulk RTT falls
from 42.15 ms at 2 Mbit to 13.19 ms at 50 Mbit, so there is less queueing
delay available to recover.

## The runtime RTT estimator (docs/GATE_PREREG.md)

The self-gating controller needs `r` computed from what it observes. The eBPF
flow telemetry reports an RTT proxy. Scored against the configured delay
across four paths:

| base RTT | min | median |
|---|---|---|
| 3 ms | 8.43 | 14.40 |
| 5 ms | 8.43 | 14.50 |
| 20 ms | 8.67 | 19.42 |
| 80 ms | 17.39 | 21.63 |

**The proxy does not track base RTT.** It saturates between roughly 14 and
22 ms whatever the path. The best of six candidate statistics carries a 96%
mean error and 181% worst case. `src/check_rtt_estimator.py` refuses to
endorse it, as it was written to.

**An earlier claim of mine was a coincidence.** On the three eBPF runs
available at the time, all at a 20 ms path, the median read 20.13 ms against a
configured 20.0 and the minimum read 4.15, and this was reported as the median
being an excellent estimator and the conventional running minimum a poor one.
With four paths measured, the median is the worst of the six. Twenty
milliseconds is simply where the proxy saturates. Insisting on validation
before building the gate was right; being confident from one path was not.

**Consequence for the gate.** Both cells of the gate evaluation sit at a 20 ms
path, the one place the proxy is accidentally accurate, so the gate will
compute `r` of about 1.03 and 0.26, decide correctly in both, and appear to
satisfy every one of G1, G2 and G3. That would be a false validation. The gate
mechanism is implementable and its decisions follow the law, but it is not
validated by this evidence, and a deployable gate needs an RTT estimate this
telemetry does not provide.
