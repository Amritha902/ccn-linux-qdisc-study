# Novelty matrix: predict, then act, on a Linux AQM

Built to answer one question before any code is written: for each proposed
direction, what already exists, and does this project's own data support
pursuing it?

Two inputs carry equal weight here. The literature, and the measurements
already in this repository. The second turns out to be more decisive than the
first.

## The measurement that should decide this

Every proposal below involves a controller choosing among actions. So the
first question is how much the available actions are worth. Measured here, at
default configuration, bulk-flow RTT in ms:

| path RTT | `fq_codel` | tuned by ACAPE | `cake` | gain from tuning | gain from switching |
|---|---|---|---|---|---|
| 5 ms | 27.68 | 22.58 | **15.53** | +18.4% | **+43.9%** |
| 20 ms | 36.39 | 35.87 | 33.65 | +1.4%, n.s. | **+7.5%** |
| 80 ms | 89.30 | 89.86 | 92.86 | -0.6% | -4.0% |
| 200 ms | 208.00 | 207.47 | 208.57 | +0.3% | -0.3% |

In the only regime where parameter adaptation does anything, replacing
`fq_codel` with `cake` is worth **2.4 times** as much as tuning
`fq_codel`'s four parameters, and it needs no controller, no telemetry and no
model. At 20 ms it is worth five times as much. Above 40 ms neither action is
worth anything, and switching is mildly harmful.

Two further measured constraints:

- The eBPF flow telemetry costs **13.6% of bulk-flow RTT** and 17.5% of
  probe-RTT p95 on the staged workload. That is larger than most of the
  adaptation effect it exists to inform.
- The telemetry's RTT proxy **does not track path RTT**. It saturates between
  14 and 22 ms whether the path is 3 ms or 80 ms. Anything needing an online
  RTT estimate needs a different signal first.

So the action space in directions 1 and 3 below has a measured ceiling of
about 18%, is worth nothing on a correctly configured box, and the
instrumentation to drive it costs 13.6%. On a correct box the net is negative.

## The matrix

### 1. Predict the effect of an action, then choose

**This is model predictive control, and MPC for AQM is eighteen years old.**

| work | year | what it does |
|---|---|---|
| Predictive functional control for AQM in congested TCP/IP networks | 2008 | predicts queue trajectory, optimises drop probability |
| Design and analysis of a model predictive controller for AQM (ISA Trans.) | 2011 | MPC with explicit constraints on queue length |
| AQM based on data-driven predictive control (Telecommun. Syst.) | 2016 | learns the plant model from data rather than assuming it |
| An Adaptive AQM Based on Model Predictive Control (IEEE) | 2020 | adaptive MPC, Hebbian update of the model |
| RNN inside the MPC horizon (review, Dec 2024) | 2024 | neural state prediction inside the MPC objective |

"Predict the outcome of each candidate action over a horizon, then pick the
best" is the definition of MPC. Calling it counterfactual control renames it.

What is genuinely unexplored is the *action space*: all of the above control a
drop probability or a queue-length setpoint, not a qdisc's configuration
vector. But that is exactly the space the table above shows to be nearly
flat.

**Verdict: the method is standard, and the one part that would be new is
aimed at the action space with the least headroom. Not recommended as the
spine of a paper.**

### 2. Predict time-to-degradation

Congestion prediction is crowded. What is much less common is treating
**warning lead time** as the dependent variable rather than as a means to an
end, and reporting it against a reactive baseline with false-alarm rates.

This project's own data motivates it specifically. Adaptation helped least
under the staged workload, the one designed to exercise it, and the stated
reason was that adjustments lag the transitions they respond to. A controller
that acts before a transition rather than after it addresses the measured
failure, and does not need a rich action space: a crude action applied early
can beat a good action applied late.

The experiment is clean and does not depend on the action space being
valuable: warning time, queue overshoot, recovery time, p95 RTT, drops,
throughput, false alarms, reactive against predictive.

**Verdict: the best-motivated of the four by this project's own evidence.
Recommended as a component.**

### 3. Learn the qdisc's response surface, measure regret against an oracle

The method is standard outside networking: online system identification,
Bayesian optimisation, contextual bandits over a configuration space. RFC
8290 itself notes that `fq_codel`'s parameters relate to link capacity and
RTT, so a response surface is a reasonable object.

The problem is the oracle. The table above is, in effect, a partial oracle
sweep already: the best configuration beats the default by about 18% at
r near 1 and by nothing at r below 0.25. A regret curve would therefore show
convergence toward a near-zero improvement over most of the operating range,
and a reviewer who checks will notice that the oracle itself is beaten by
`cake`.

**Verdict: methodologically sound, aimed at a flat surface. Not
recommended until the action space is widened.**

### 4. Predict which AQM should be running

No prior work for runtime AQM *selection* surfaced in these searches. Plenty
exists for learning within one AQM, for programmable data planes and for
comparing AQMs offline, but nothing choosing between them online. That is
suggestive rather than conclusive, and a systematic search is the first task
if this direction is taken.

This is where the measured headroom is. Switching is worth 2.4 to 5 times
what tuning is worth, and the sign flips with path RTT, which connects
directly to the scaling law already established here: the law says when to
tune, and the obvious extension asks whether a second ratio decides which
AQM to run.

It also has an unmeasured cost that is a contribution in itself. Replacing a
qdisc at runtime flushes its queue and discards its state. Nobody appears to
have measured what that costs, or how long a switch takes to pay for itself.
That is a concrete, bounded, publishable measurement regardless of whether the
controller works.

**Verdict: the most open and the best supported by measurement. Recommended
as the spine.**

### 5. Flow-composition-aware prediction

Closest prior art, and it is close:

| work | year | what it does |
|---|---|---|
| LFQ: Online Learning of Per-flow Queuing Policies using DRL (IEEE LCN) | 2020 | learns each flow's buffer size online from its congestion control, delay and bandwidth |

LFQ adapts per-flow buffer size; predicting harmful *interaction* between
flow types is distinguishable from that, but adjacent enough that it must be
cited and differentiated explicitly rather than treated as open ground.

Two local obstacles. The RTT proxy in the existing telemetry does not work,
and the telemetry already costs 13.6% of bulk RTT. Richer per-flow features
make the instrument more expensive than the effect being measured, unless the
telemetry moves in-kernel first.

**Verdict: blocked on telemetry quality and cost, with near prior art.
Recommended only after direction 6.**

### 6. Move the loop into the kernel with a BPF qdisc

Verified: Linux 6.16 supports implementing `Qdisc_ops` in BPF through
`struct_ops`, with `enqueue`, `dequeue`, `init`, `reset` and `destroy`
registered dynamically (torvalds/linux commit `c8240344956e`). A qdisc can now
be written in BPF rather than as a kernel module.

The motivation here is not novelty, since ML inside eBPF already exists. It is
the 13.6% figure. The present loop is eBPF telemetry into userspace Python
into a `tc` invocation, and that round trip is what costs 13.6% of bulk RTT.
An in-kernel control loop attacks a cost this project has already measured,
which is a far better argument than programmability for its own sake.

Cost: the current kernel is 6.12.48, so this needs a rebuild at 6.16 or later,
and the measurement apparatus validated over the past weeks would need
revalidating against the new kernel.

**Verdict: a real opportunity with a measured justification. Recommended as
the enabling step, with the kernel rebuild costed honestly.**

## Recommendation

Not directions 1 and 3. Both are standard methods pointed at an action space
this repository has already measured to be nearly flat, and the strongest
version of either is beaten by a one-line configuration change.

The combination worth building is **2 plus 4, enabled by 6**:

> Predict how long the current configuration has before it violates a latency
> objective, and use that prediction to choose which queue discipline should
> be running, in-kernel.

That keeps the predictive element, points it at the action space with the
measured headroom, inherits the scaling law as the thing that makes the
decision non-trivial, and justifies the in-kernel move by a cost already
measured rather than by novelty.

And it should be called model predictive control over a discrete action space,
not counterfactual control. The honesty is worth more than the framing, and
this paper's main asset is that its claims survive checking.

## What this matrix does not establish

These are four searches, not a systematic review. Absence of a hit is not
absence of prior art, and the one direction recommended as most open,
direction 4, rests on exactly that kind of absence. Before committing, the
first task is a systematic search over AQM selection, qdisc switching,
scheduler selection and data-plane policy selection, including the venues
where such work would appear rather than only what a general search surfaces.
