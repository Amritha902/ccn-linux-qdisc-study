# Pre-registration: is there a second dimensionless group at the packet floor?

Committed before the campaign runs, as with the scaling law and the cross-AQM
test. The git history is the evidence.

## The gap this addresses

The ratio law says the benefit of adaptation is governed by
`r = target / RTT`. Every measurement supporting it was taken at a 10 Mbit
bottleneck, where one MTU-sized packet serialises in 1.21 ms and the 5 ms
default target is comfortably above one packet time.

That cannot be the whole story, because a delay target below the transmission
time of a single packet is not achievable by any AQM. The queue cannot be
drained below the packet currently in flight. The `tc-codel` documentation says
as much: the target should be at least one MTU serialisation time, and CoDel's
defaults are independently known to behave badly on low-speed links.

So there should be a second dimensionless group,

    s = target / (MTU / rate)

the target measured in units of packet transmission time.

## A convenience worth noting

At `r = 1` the two groups collapse into one statement about the path. Since
`r = 1` means `target = RTT`,

    s = RTT * rate / MTU = BDP / MTU

so `s` is just the bandwidth-delay product measured in packets. `s < 1` is
therefore not an exotic corner: it is the regime where the whole path holds
less than one packet in flight.

## Experimental design

Hold `r = 1.0` fixed and vary only `s`. With `target = RTT = 5 ms` and the MTU
at 1514 bytes:

| rate | MTU serialisation | s | BDP |
|---|---|---|---|
| 2 Mbit | 6.06 ms | 0.83 | under one packet |
| 5 Mbit | 2.42 ms | 2.06 | 2 packets |
| 10 Mbit | 1.21 ms | 4.13 | 4 packets |
| 20 Mbit | 0.61 ms | 8.26 | 8 packets |
| 50 Mbit | 0.24 ms | 20.6 | 21 packets |

This isolates the second group: `r` is constant across every cell, so the
ratio law alone predicts the same benefit everywhere, near the 18.4% measured
at `r = 1.0`. Any systematic variation with rate is the second group.

## Predictions, thresholds fixed here

**S1. The benefit is suppressed at the packet floor.** At `s < 1` the target is
below one packet time and unachievable, so a controller shrinking it further
should recover little or nothing. Decision rule: benefit at `s = 0.83` is at
least 8 percentage points below the mean benefit of the cells at `s >= 4`.

**S2. The benefit recovers above the floor and then plateaus.** For `s >= 4`
the ratio law should hold unmodified. Decision rule: the cells at `s = 4.13`,
`8.26` and `20.6` agree within 8 percentage points of each other, the same
tolerance the invariance test used, scaled to the smaller cell count.

**S3. If S1 and S2 both hold, the law needs two numbers, not one.** The
reportable form becomes `benefit = f(r) * g(s)` with `g` a floor term that
approaches 1 well above `s = 1`. If S1 fails, the packet floor does not
measurably constrain adaptation in this range and the single-group law stands
as published.

## Known confound, stated in advance

Varying the rate at fixed RTT also varies the BDP, and a very small BDP is a
difficult regime for TCP for reasons that have nothing to do with AQM
parameters: at 2 Mbit with a 5 ms path the whole path holds less than one
packet, so congestion control operates at the edge of its own assumptions.
The static arm is subject to the same effect, and the benefit is a difference
between the two arms, so the comparison is still meaningful. But an absent
benefit at `s = 0.83` cannot be attributed to the packet floor alone, and will
be reported as consistent with it rather than as demonstrating it.

Cells where the controller makes no adjustment are excluded, for the reason in
`verification/INERT_CELLS.md`.
