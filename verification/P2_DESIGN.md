# The ratio-invariance experiment was varying two things at once

This one is a flaw in the experiment I designed, not in the code it inherited.
It was caught by the instrument check written for F7, which reported that the
80 ms cell moved through a 10% excursion where the cells it is compared
against moved 55 to 57%.

## What P2 was supposed to do

Hold `r = target / RTT` fixed while changing both, and see whether the benefit
of adaptation follows. `target = 20 ms` on a 20 ms path has the same `r` as
the default `target = 5 ms` on a 5 ms path, so if `r` governs the benefit the
two should behave alike.

## What it actually did

`--aqm-target-ms` rewrote the target and left the interval alone:

```
qdisc_args: "target 80.0ms interval 100ms limit 1024 quantum 1514"
```

CoDel has two time parameters. The target is the standing-queue budget and the
interval is the time it waits before escalating. The shape of the
configuration is set by their ratio, and rewriting one alone changes it:

| cell | target/RTT | target/interval |
|---|---|---|
| 5 ms on a 5 ms path | 1.0 | 0.05 |
| 20 ms on a 20 ms path | 1.0 | 0.20 |
| 80 ms on an 80 ms path | 1.0 | 0.80 |

The published guidance puts target at 5 to 10 percent of interval. The first
cell sits inside that envelope, the second is twice outside it and the third
is an order of magnitude outside, with a standing-queue budget almost as large
as the escalation timer.

So the three cells did not differ only in the quantity the experiment claimed
to be holding fixed. They differed in a second dimensionless group, and any
difference in benefit between them could have been attributed to either. The
test could not have distinguished them.

## The symptom that gave it away

The controller's own trajectory. At `r = 1.0` the 5 ms and 20 ms cells both
descend under the HEAVY law through a 55 to 57% excursion. The 80 ms cell,
under the same law, moved 10%, because the qdisc it was driving was not a
scaled copy of the others. The controller was behaving consistently; the
configuration underneath it was not.

There was a second-order effect too. Once the controller adjusted, the rule
`interval >= target * 10` fired for the first time, jumping the interval from
100 ms to 720 ms mid-run. That rule never binds at the 5 ms default, where the
configured interval is already twenty times the target.

## The fix

`--aqm-target-ms` now scales the interval by the same factor, so the whole
configuration is scaled rather than reshaped:

```
t =  5 ms   target 5.0ms   interval 100ms    target/interval = 0.05
t = 20 ms   target 20.0ms  interval 400ms    target/interval = 0.05
t = 80 ms   target 80.0ms  interval 1600ms   target/interval = 0.05
```

`--no-scale-interval` preserves the old behaviour for anyone who wants to vary
the shape deliberately, which is a different experiment and is now a different
flag rather than the silent default.

## P1 is unaffected

The dense sweep varied RTT alone against the 5 ms target and 100 ms interval,
so `target/interval` was constant at 0.05 across all thirty runs and the only
dimensionless group that moved was `target/RTT`. Those runs stand.

## What this says about the hypothesis

Nothing yet, which is the point. It says the first attempt at testing it was
not a test. A scaling-law claim has to name every dimensionless group it holds
fixed, not only the one it varies, and the honest version of the P2 statement
is narrower than the one written down at pre-registration time: at fixed
`target/interval`, the benefit depends on `target/RTT`. Whether it also
survives changes in `target/interval` is a separate question this campaign
does not answer, and the papers should say so rather than imply a generality
that was never measured.

---

# F8: the control loop period was absolute, and so was the run duration

The interval fix made the qdisc a scaled copy of the reference. It did not
make the controller one, and the 80 ms cell then failed in a way that was
obvious in the logs and would have been invisible in the summary.

## What happened

At target 80 ms the adapted run produced 86 ticks, regimes split 31 MODERATE,
28 HEAVY, 27 LIGHT, a target that read 80.000 ms at every single tick, and an
adjustment log containing nothing but its header. The controller ran for a
full minute and never moved a parameter.

Adjustments are gated on five consecutive identical regime classifications.
The regime never repeated five times because the classification was flickering,
and it was flickering because the controller's loop period is absolute while
CoDel's interval is not:

| target | AQM interval | loop period | samples per AQM cycle |
|---|---|---|---|
| 5 ms | 0.1 s | 0.5 s | averages over 5 cycles |
| 20 ms | 0.4 s | 0.5 s | averages over 1.25 cycles |
| 80 ms | 1.6 s | 0.5 s | three samples inside one cycle |

At the reference the controller sees a drop rate averaged over several AQM
cycles. At 80 ms it sees the inside of a single cycle, which alternates
between bursts and silence, and reads its own aliasing as an unstable system.

## Why the 20 ms result had to be re-run as well

The 20 ms cell did adapt, reached a 53.9% excursion against the reference's
57.2%, and passed the instrument check on regime and excursion. But it ran at
1.25 samples per AQM cycle where the reference runs at 5, and for 60 s where
the scale-equivalent duration is 240 s. The check passing is evidence that the
mismatch did not visibly distort that cell; it is not evidence that the cell
was correctly scaled. Those are different claims and only the second supports
a scale-invariance result, so the cell was re-run properly rather than kept on
the strength of the weaker one.

## The fix

`set_bounds()` scales the loop period so it stays five times the AQM interval
at any operating point: 0.5 s at 5 ms, 2 s at 20 ms, 8 s at 80 ms. The run
duration scales in `src/run_law_p2.sh`, since a controller that ticks sixteen
times more slowly needs sixteen times as long to complete a comparable
trajectory: 60 s, 240 s and 960 s respectively.

At the 5 ms default the scale is 1.0 and the period is the 0.5 s it always
was, so every earlier run is unaffected. `src/test_bounds.py` asserts that,
along with the constant samples-per-cycle ratio and the 8 s period at 80 ms.

## The cost, stated plainly

The properly scaled campaign is 2.4 hours of compute against 45 minutes for
the version that was wrong, almost all of it in the 16x cell. That is the
price of the claim. A scale-invariance result measured on cells whose control
loop was not scaled is not a scale-invariance result, and the 80 ms cell is
the one that makes the claim worth anything, since 4x alone is a narrow range
to generalise from.

## Four defects, one shape

F5 bounds, F6 step sizes, F7 regime thresholds, F8 loop period and duration.
Every one was an absolute constant in a system whose subject is a
dimensionless ratio, and every one was hidden behind the previous until that
was fixed. Two would have manufactured a confirmation, two a refutation. The
only reason any of them surfaced is that the controller was deployed sixteen
times away from the operating point its constants were tuned at, and its logs
were read rather than its summaries.
