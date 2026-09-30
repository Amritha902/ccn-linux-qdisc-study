# Pre-registration: does a controller that knows the law outperform one that does not?

Committed before the campaign runs.

## What this turns the law into

The scaling law is a measurement. It says the benefit of adapting a
delay-targeting AQM's parameters is governed by `r = target / RTT`, is not
distinguishable from zero below `r = 0.417`, and reaches half its ceiling at
`r = 0.50`.

Below the crossover the controller is not merely useless, it is expensive. At
`r = 0.25` the measured cost is roughly 10% more drops and 10% more
retransmissions for a 1.4% latency gain that is not statistically significant.
An operator running adaptation on a correctly configured box is paying that
for nothing.

So the law implies a mechanism: a controller can estimate its own `r` and
decline to act when acting cannot pay. That is the difference between
publishing a number and publishing something deployable.

## The estimator, and why it is not the usual one

The gate must compute `r` from what the controller observes, not from a value
handed to it, or it is not a contribution. RTT comes from the eBPF flow
telemetry at the `tc` egress hook.

The statistic is the **median** of a sliding window, not the running minimum
that is conventional for base-RTT estimation. On the existing eBPF runs the
median tracked the configured netem delay to 0.7%, 20.13 ms against 20.0 ms,
while the minimum was wrong by a factor of five, 4.15 ms against 20.0 ms, and
would have computed `r = 1.20` where the truth was `0.25`. A gate built on the
minimum would have opened in exactly the regime it exists to avoid.

That evidence comes from three runs at a single RTT, which cannot establish an
estimator. `src/run_rttest.sh` sweeps base RTT and
`src/check_rtt_estimator.py` scores six candidate statistics against the known
delay. The gate is only built on the winner if its worst-case error leaves
margin at the threshold, and the script says so explicitly if it does not.

## Predictions, thresholds fixed here

**G1. Above the crossover the gate opens and costs nothing.** At `r = 1.0` the
gated controller should be indistinguishable from the ungated one. Decision
rule: benefit within 4 percentage points of the ungated arm, and the gate
recorded as open.

**G2. Below the crossover the gate shuts and saves the cost.** At `r = 0.25`
the gated controller should behave like the static configuration, recovering
the drop-rate and retransmission overhead the ungated controller pays.
Decision rule: gate recorded as shut, and retransmissions within 4% of the
static arm while the ungated arm is above it.

**G3. The gate decides correctly without being told.** The estimated `r` should
agree with the configured one. Decision rule: within 25% at every cell tested.
A wider error than that is reported as the gate working by luck.

## What would count as failure

If the gate opens below the crossover, or shuts above it, the estimator is not
good enough and that is the result. If the gated arm at `r = 1.0` loses more
than 4 points of benefit, the gate costs more than it saves. Either outcome is
reported; the mechanism is not assumed to work because the law does.

## Deliberately not claimed

The threshold `GATE_R = 0.4` is taken from this work's own measurements, so the
gate is tuned on the data it is evaluated against. That is a real limitation
and is stated rather than hidden: what is demonstrated is that a gate on this
predicate is implementable and behaves as the law says it should, not that
`0.4` is the correct threshold for deployments unlike this testbed.
