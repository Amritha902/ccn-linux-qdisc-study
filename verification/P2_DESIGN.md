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
