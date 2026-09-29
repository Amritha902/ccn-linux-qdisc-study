# Novelty Positioning and Comparison with Recent Work (2023, 2026)

This document states exactly what is and is not new in this work, and compares
it with the most recent published AQM research. Every reference has been
checked against the published record.

**A warning on the numbers.** The comparison table reports each paper's own
headline figures. They are **not directly comparable**: the works differ in
link rate, topology, traffic model, hardware and metric definition. A table of
"our 22 ms vs their 42×" would be meaningless. What is comparable is *what each
system adapts, on what platform, at what deployment cost, and with what
evaluation rigour*, and that is what the table is built around.

---

## 1. The closest recent work, and what each does not do

### DESiRED (Computer Networks, vol. 244, 2024)

*Dynamic, Enhanced, and Smart iRED: A P4-AQM with Deep Reinforcement Learning
and In-band Network Telemetry.*

**What it does:** tunes the **target delay** of the iRED AQM at runtime using a
deep reinforcement learning agent fed by In-band Network Telemetry. Evaluated
on a P4 testbed running MPEG-DASH; reports up to **90× reduction in video
stalling** and **42× increase in high-resolution playback**.

**This is the closest prior work, and it must be cited as such.** Any claim
that runtime adaptation of an AQM's delay target is unprecedented is false.

**What it does not do:**
- It requires **programmable data-plane hardware (P4)** and In-band Network
  Telemetry. It cannot run on a stock Linux host.
- It adapts **one parameter** (target delay), not four.
- It tunes **iRED**, a RED derivative, not `fq_codel`, so it has no flow
  queueing, no DRR, and no per-flow CoDel instance to interact with.
- It requires **offline DRL training**; the policy is not interpretable.
- Its evaluation is **application-level** (video QoE). It does not report a
  controlled comparison against the unadapted AQM with confidence intervals,
  and it has no control condition isolating the controller's own cost.

### AQM-LLM (IEEE Transactions on Networking, 2026)

*Distilling Large Language Models for Network Active Queue Management.*

**What it does:** distils an LLM into an L4S AQM controller, a state encoder
mapping telemetry to token embeddings, a specialised head emitting congestion
actions in one inference step, LoRA to limit trainable parameters. Implemented
on FreeBSD 14.

**What it does not do:**
- Targets **L4S/DualPI2**, not `fq_codel`, and therefore presumes ECN-capable
  scalable congestion control at the endpoints.
- Runs on **FreeBSD**, not Linux `tc`.
- Requires **model distillation and training**; the policy is not inspectable.
- Adapts a **congestion action**, not a set of qdisc configuration parameters.

### QueuePilot (IEEE INFOCOM, 2023)

**What it does:** offline RL distilled into a lightweight online policy that
tunes **ECN marking probability**, enabling small buffers in backbone routers.

**What it does not do:** adapts one probability, not qdisc parameters; requires
offline training; targets backbone routers with small buffers, not access links;
no flow queueing.

### ACoDel (IEEE Systems Journal, vol. 14 no. 1, 2020)

**What it does:** derives stability conditions for the CoDel control loop
analytically and adapts CoDel's **`interval`**. Methodologically the strongest
of these on the adaptation itself, it has a **stability proof**, which this
work does not.

**What it does not do:** requires **kernel modification**; adapts one
parameter; single queue, not `fq_codel`.

### Adaptive RED (ICSI, 2001), the base paper

**What it does:** adapts RED's **`max_p`** by AIMD (β = 0.9) against a
queue-length target. This work borrows that control law directly.

**What it does not do:** RED, not `fq_codel`; one parameter; queue length, not
sojourn time; no flow queueing; no telemetry beyond the averaged queue.

### eBPF Qdisc (Netdevconf 0x17, 2023)

**What it does:** proposes a fully programmable qdisc written in eBPF, using
BPF linked lists, red-black trees and local kernel pointers.

**Why it matters here:** this is the natural successor to the approach taken in
this work. If it lands upstream, writing the scheduling policy directly in BPF
largely **subsumes** the userspace-controller pattern used here. It is a
proposal, not a shipped feature, at time of writing.

### L4S, RFC 9330 / 9331 / 9332 (IETF, 2023)

Reaches **sub-millisecond queueing delay** by changing the signalling contract
between network and transport. This is the relevant **upper bound** for the
problem, not a peer: no amount of parameter tuning on a classic AQM can match
it. It requires changes at both the network and the endpoints.

### Ray et al. (arXiv 2511.19213, Nov 2025)

Characterises how AQM presence changes what standard speed tests report, a
published instance of the same failure class this project's verification
uncovered, where the measurement instrument interacts with the queue under
measurement.

---

## 2. Capability comparison

| | Adaptive RED 2001 | ACoDel 2020 | QueuePilot 2023 | **DESiRED 2024** | AQM-LLM 2026 | L4S 2023 | **This work** |
|---|---|---|---|---|---|---|---|
| Adapts at runtime | ✓ | ✓ | ✓ | ✓ | ✓ | n/a | ✓ |
| Parameters adapted | 1 | 1 | 1 | 1 | policy | 0 | **4** |
| Underlying AQM | RED | CoDel | custom | iRED | DualPI2 | DualPI2 | **fq_codel** |
| Flow queueing (DRR) | ✗ | ✗ | ✗ | ✗ | ✗ | partial | **✓** |
| Runs on stock Linux | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | **✓** |
| Kernel / data-plane change | ✗ | **✓** | ✗ | **✓ (P4)** | ✓ | **✓** | **✗ none** |
| Special hardware | ✗ | ✗ | ✗ | **✓ P4 switch** | ✗ | ✗ | **✗** |
| Endpoint changes required | ✗ | ✗ | ✗ | ✗ | ✓ | **✓** | **✗** |
| Telemetry source | queue avg | queue model | queue state | **INT** | telemetry tokens | ECN | **eBPF flow map** |
| Training required | ✗ | ✗ | ✓ | ✓ | ✓ | ✗ | **✗** |
| Interpretable rule | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ | **✓** |
| Stability proof | ✗ | **✓** | ✗ | ✗ | ✗ | ✗ | ✗ |
| Control condition in evaluation | ✗ | ✗ | ✗ | ✗ | ✗ | n/a | **✓ sham controller** |
| Separate sparse/bulk latency reported | ✗ | ✗ | ✗ | ✗ | ✗ | n/a | **✓** |
| Compared against ≥8 alternative qdiscs | ✗ | ✗ | ✗ | ✗ | ✗ | n/a | **✓** |
| Reports a negative result | ✗ | ✗ | ✗ | ✗ | ✗ | n/a | **✓** |

### Reported headline figures (NOT directly comparable)

| Work | Reported figure | Testbed |
|---|---|---|
| Adaptive RED 2001 | queue held near target under varying load | simulation |
| ACoDel 2020 | stability guaranteed under varying load | analysis + simulation |
| QueuePilot 2023 | small buffers made viable at backbone rates | testbed |
| DESiRED 2024 | 90× less video stalling, 42× more HD playback | P4 switch, MPEG-DASH |
| AQM-LLM 2026 | improved L4S congestion control | FreeBSD 14 |
| L4S 2023 | sub-millisecond queueing delay | kernel + transport |
| **This work** | *see `figures/comparison/`, full table with 95% CI* | stock Linux, 10 Mbit, 9 qdiscs, 3 repetitions |

Different link rates, traffic models and metrics. Cross-reading these numbers
as a ranking would be wrong, and the paper does not do so.

---

## 3. What is actually new here

Stated as narrowly as the evidence supports.

### 3.1 The combination (weak claim)

No published work adapts **`fq_codel`'s `target`, `interval`, `limit` and
`quantum` together** at runtime, on **stock Linux with no kernel or data-plane
modification**, driven by **eBPF flow telemetry read through `bpf(2)`**.

Each ingredient exists separately: AIMD adaptation (Adaptive RED 2001),
adaptive delay targets (DESiRED 2024), eBPF at the `tc` hook (routine). The
combination is unpublished, but a combination is a weak novelty claim and
should not be the headline.

### 3.2 The controlled evaluation (the stronger claim)

**No published work reports a controlled evaluation of whether adapting a
flow-queueing AQM's parameters actually helps.**

Every system above reports that its adaptation improved something. None:

- runs a **sham-controller condition** separating the controller's own
  computational cost from its control decisions;
- reports **sparse-probe and bulk-flow latency separately**, despite
  flow-queueing AQMs privileging sparse flows by design;
- compares against **eight alternative queue disciplines** under an identical
  bottleneck;
- reports **confidence intervals across repetitions** with exact
  small-sample statistics;
- publishes a **negative or null result** for the adaptation itself.

This is the genuinely uncontested contribution, and it is stronger than the
combination claim because it is a methodological result rather than an
engineering permutation. The finding that adaptation does *not* measurably help
on stock Linux `fq_codel` is new information, and it is only credible because
of the control condition.

### 3.3 The verification methodology

Seven classes of silent measurement failure, each of which produced confident
and internally consistent wrong results, with the physical invariants that
detect them (bytes per packet on the monitored queue; drop rate against the
link's maximum packet rate; whether a control input changes its output; whether
a threshold is reachable at all). Ray et al. (2025) document one instance of
this class; this work documents seven and releases the detection tooling.

---

## 4. How to state the claim in the paper

**Defensible:**

> We present the first controlled evaluation of runtime parameter adaptation
> for a flow-queueing AQM on stock Linux. Using a sham-controller condition to
> separate the controller's computational cost from its control decisions, and
> reporting sparse-probe and bulk-flow latency separately, we find that
> adapting `fq_codel`'s four parameters does not produce a statistically
> distinguishable improvement over its defaults in the regimes tested.

**Not defensible, and must not appear:**

> - "No prior work adapts an AQM's delay target at runtime", DESiRED, 2024.
> - "The first adaptive AQM requiring no kernel modification", Adaptive RED
>   and QueuePilot both require none.
> - "12× faster stabilisation", never measured; see the verification report.
> - Any comparison of our absolute numbers against DESiRED's or QueuePilot's.

---

## References

See `docs/LITERATURE_SURVEY.md` §12 and `verification/CITATION_AUDIT.md` for
the full verified list. Principal recent works cited here:

- F. Rodriguez et al., "DESiRED, Dynamic, Enhanced, and Smart iRED: A P4-AQM with Deep Reinforcement Learning and In-band Network Telemetry," *Computer Networks*, vol. 244, 2024. arXiv:2310.18159.
- D. Satish et al., "Distilling Large Language Models for Network Active Queue Management," *IEEE Transactions on Networking*, 2026. arXiv:2501.16734.
- M. Dery, O. Krupnik, I. Keslassy, "QueuePilot: Reviving Small Buffers With a Learned AQM Policy," IEEE INFOCOM 2023.
- J. Ye, K.-C. Leung, "Adaptive and Stable Delay Control for Combating Bufferbloat," *IEEE Systems Journal*, vol. 14, no. 1, 2020.
- S. Ray et al., "Characterizing the Impact of Active Queue Management on Speed Test Measurements," arXiv:2511.19213, 2025.
- M. P. Toopchinezhad, M. Ahmadi, "Machine Learning Approaches for Active Queue Management: A Survey, Taxonomy, and Future Directions," *Computer Networks*, vol. 262, 2025.
- C. Hung, P. Wang, "eBPF Qdisc: A Generic Building Block for Traffic Control," Netdevconf 0x17, 2023.
- K. De Schepper, B. Briscoe, G. White, "Dual-Queue Coupled AQM for L4S," IETF RFC 9332, 2023.
