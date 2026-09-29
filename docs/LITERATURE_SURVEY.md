# Literature Survey: Active Queue Management and Runtime Parameter Adaptation in Linux

Every reference in this survey has been checked against the published record;
venue, year, volume and author list are as the publisher lists them. Where the
project's earlier drafts cited a work incorrectly, the correction is noted in
`verification/CITATION_AUDIT.md`.

---

## 1. Scope

This survey covers the work an adaptive `fq_codel` controller has to be
positioned against. It runs from the identification of bufferbloat, through the
two families of queue-management response (drop-probability schemes and
delay-target schemes), the flow-queueing schedulers that Linux now ships by
default, the recent standards work on low-latency service classes, and finally
the two lines most directly relevant to this project: runtime parameter
adaptation, and programmable in-kernel telemetry via eBPF.

The organising question is narrow and deliberately so: **given a queue
discipline whose parameters are fixed at configuration time, what is known
about changing them while the system runs?**

---

## 2. The problem: bufferbloat

Gettys and Nichols named and characterised bufferbloat: memory became cheap
faster than queue management improved, so network devices acquired buffers far
larger than any control loop needed, and TCP, which infers congestion from
loss, dutifully filled them [1]. The result is queueing delay of hundreds of
milliseconds to seconds on an otherwise healthy link, with throughput
essentially unaffected. Latency degrades while every utilisation metric looks
fine, which is why the problem persisted for years.

Briscoe et al. later surveyed the full space of latency-reduction techniques,
placing queue management alongside transport changes, faster hardware and
topology changes [2]. Their framing is useful here: queue management addresses
*queueing* delay specifically, which is the only component of end-to-end latency
that a qdisc can influence at all.

The IETF's position is RFC 7567, which supersedes RFC 2309 and recommends that
network devices deploy AQM by default, explicitly preferring schemes that
require no per-flow configuration [3]. That recommendation, *no manual tuning*
is the standard against which any adaptive scheme should be judged, and is
worth keeping in view: a controller that adds tuning burden is moving away from
the IETF's stated goal, not towards it.

**Measured in this study.** The bufferbloat effect is not merely cited here but
reproduced: under `pfifo` with a 1000-packet buffer on a 10 Mbit bottleneck, p95
RTT reached 2,288 ms against 25 ms for `fq_codel` on identical traffic, at
statistically indistinguishable goodput.

---

## 3. Drop-probability AQM: RED and its descendants

### 3.1 RED

Floyd and Jacobson's Random Early Detection is the origin of the field [4]. RED
maintains an exponentially weighted moving average of queue length and drops
(or marks) arriving packets with a probability that rises linearly between
`min_th` and `max_th` up to `max_p`. Dropping early and randomly was intended to
signal congestion before the buffer filled and to desynchronise TCP flows that
would otherwise back off in lockstep.

RED's weakness is well documented and was conceded by its authors: its
behaviour depends sharply on `min_th`, `max_th`, `max_p` and `w_q`, and the
correct values depend on link rate, RTT and flow count, none of which the
algorithm observes. A RED configuration tuned for one operating point misbehaves
at another.

### 3.2 Adaptive RED

Adaptive RED [5] is the most direct antecedent of the present work, and the one
whose control law this project borrows. Floyd, Gummadi and Shenker keep RED's
structure but adapt `max_p` at runtime using AIMD: when the average queue sits
above the target band `max_p` is increased multiplicatively (β = 0.9), and when
it sits below, `max_p` is increased additively. The goal is to hold average
queue length near a configured target regardless of load, so the operator sets a
*delay objective* rather than a set of probability constants.

Two points matter for positioning:

- Adaptive RED adapts exactly **one** parameter, and that parameter is a drop
 probability, not a delay target.
- The AIMD constants (β = 0.9, and the additive step) are themselves fixed. The
 scheme removes one layer of manual tuning and introduces a smaller one.

This project applies the same AIMD policy to `fq_codel`'s `target`, `interval`
and `limit`. That is an extension of Adaptive RED's mechanism to a different
qdisc, not a new control law, and this survey's position is that the extension
should be argued and measured on those terms rather than claimed as novel
control theory.

---

## 4. Delay-target AQM: CoDel and PIE

### 4.1 CoDel

Nichols and Jacobson's Controlled Delay algorithm [6], standardised as RFC 8289
[7], changed the controlled variable from queue *length* to queue *sojourn
time*, how long a packet actually waited. CoDel tracks the minimum sojourn time
over a sliding `interval` (default 100 ms) and begins dropping when that minimum
stays above `target` (default 5 ms) for a full interval, with the drop rate
increasing as the inverse square root of the number of drops in the current
dropping state.

CoDel's contribution is that it is *parameterless in practice*: `target` and
`interval` are expressed in units of the path RTT rather than the link rate, so
one setting works across a wide range of link speeds. The authors argue
explicitly that 5 ms/100 ms need not be tuned.

That claim is the central tension for any work proposing to tune them. CoDel's
defaults are not arbitrary constants awaiting optimisation; they encode a
deliberate design position that RTT-relative parameters generalise. A project
adapting them carries the burden of showing that the adaptation beats the
default *in a regime the default was not designed for*, and that it does not
degrade the regimes the default handles well.

### 4.2 PIE

PIE [8], standardised as RFC 8033, reaches a similar objective by explicitly
control-theoretic means. It estimates current queueing delay, then updates a
drop probability using a proportional-integral controller driven by the
deviation from a delay target and the rate of change of that delay. PIE is
lighter than CoDel per packet (no per-packet timestamping) and was designed with
hardware implementation in mind.

Notably, PIE's `target` (default 15 ms in Linux) and `tupdate` are also fixed
constants, and PIE has the same nominal exposure to workload variation as CoDel.

**Measured in this study.** PIE, FQ-PIE, CoDel and CAKE were all run under the
identical bottleneck as `fq_codel`, because a comparison that omits the
obvious alternatives is not a comparison. Results are reported in full,
including where they beat the proposed controller.

---

## 5. Flow queueing and scheduling

### 5.1 Fair queueing foundations

Jain, Chiu and Hawe's fairness index [9] is the standard scalar measure of how
evenly a resource is shared, and is used throughout this study. It is worth
stating plainly what it does and does not show: J ≈ 1 under a flow-queueing
qdisc is a property of the *scheduler*, not of any AQM layered on it, and it is
largely insensitive to the AQM's parameters. A high Jain index is therefore weak
evidence for an AQM contribution.

### 5.2 fq_codel

FlowQueue-CoDel [10], standardised as RFC 8290, combines a Deficit Round Robin
scheduler over a large number of flow queues with an independent CoDel instance
per queue. Hashing to ~1024 queues gives near-perfect isolation between flows;
running CoDel per queue keeps each flow's own sojourn time bounded; and a
new-flow priority heuristic gives latency-sensitive sparse flows preferential
service.

`fq_codel` is the default qdisc on most Linux distributions and is the system
under study in this project. Its exposed parameters are `target`, `interval`,
`limit`, `quantum`, `flows`, `memory_limit` and `ecn`.

### 5.3 FQ-PIE and CAKE

FQ-PIE [11] applies the same flow-queueing structure with PIE as the per-queue
AQM, and is available in Linux as `fq_pie`.

CAKE [12] integrates shaping, flow and host fairness, DiffServ handling, ACK
filtering and link-layer overhead compensation into one qdisc explicitly aimed
at home gateways. Its design philosophy is the opposite of a tunable controller:
it reduces configuration to a single bandwidth parameter and makes every other
decision internally.

### 5.4 Scheduling advances

Sharafzadeh et al.'s Self-Clocked Round-Robin [13] shows that DRR, the
scheduler inside `fq_codel`, performs poorly under certain packet size
distributions and bursty arrivals, and proposes a zero-configuration replacement
with substantially better latency. SCRR is a scheduler, not an AQM, so it is
orthogonal to parameter adaptation; but it is directly relevant because it
suggests that for some workloads the larger gain available in `fq_codel` lies in
replacing the scheduler rather than retuning the AQM.

---

## 6. Low-latency service architectures

The L4S work [14, 15, 16] is the most significant recent development in this
area. Rather than improving a single queue, L4S defines a dual-queue coupled AQM
(RFC 9332) in which scalable congestion controls receive very fine-grained ECN
signalling and achieve sub-millisecond queueing delay, while classic traffic is
served by a conventional AQM, with the two coupled so they compete fairly.

L4S matters to this survey for a structural reason: it achieves its latency goal
by changing the *signalling contract between network and transport*, not by
tuning queue parameters. Any claim that adaptive parameter tuning is the route
to low latency has to be stated against L4S, which reaches a far lower latency
floor by a different mechanism and is now an IETF standard.

---

## 7. Transport-side congestion control

CUBIC [17] is the Linux default and the transport used throughout this study.
Its window growth is a cubic function of time since the last congestion event,
which makes it aggressive at filling large buffers, precisely the behaviour
that makes bufferbloat visible.

BBR [18] models the bottleneck bandwidth and round-trip propagation time
explicitly and paces to that model rather than reacting to loss, keeping queues
short without any network-side support. BBR is complementary to AQM rather than
competing with it, but it is a genuine alternative path to the same objective,
and one that requires no change at the bottleneck at all.

RFC 5681 [19] remains the normative description of the standard loss-based
congestion control that RED and CoDel were designed against.

---

## 8. Programmable in-kernel telemetry: eBPF

eBPF allows verified bytecode to run at kernel hooks without modules or kernel
patches. Vieira et al. survey eBPF and XDP for packet processing [20], covering
the verifier, the JIT, map types and the performance envelope.

For traffic control specifically, programs attached at the `tc` `clsact` hook
observe every packet on ingress or egress and can maintain per-flow state in BPF
maps readable from userspace. This is the mechanism this project uses for flow
classification.

Two practical findings from this study are worth recording, since they are
poorly covered in the literature and each silently invalidated an earlier result
here:

1. **BPF maps are kernel-global.** A program loaded from inside a network
 namespace has maps visible from the host by id, so no namespace-crossing
 machinery is required to read them. An earlier draft of this work attributed
 empty telemetry to "namespace file-descriptor isolation"; that diagnosis was
 wrong, the maps were populated the whole time and the fault was in userspace
 decoding.

2. **`bpf_ktime_get_ns()` is CLOCK_MONOTONIC.** Comparing it against a userspace
 CLOCK_REALTIME timestamp yields ages of decades and silently disables any
 age-based filter. This single line zeroed the flow telemetry across 21,128
 recorded samples.

Reading maps via `bpf(2)` directly rather than by spawning `bpftool` per sample
is also materially faster, in this study, 0.709 s versus 3.17 s per control
tick, which matters whenever the control interval is short.

---

## 9. Learning-based AQM

Toopchinezhad and Ahmadi provide the current comprehensive survey of machine
learning for AQM [21], taxonomising supervised congestion prediction and
reinforcement-learning drop policies, and noting that most proposals are
evaluated only in simulation.

QueuePilot [22] is the strongest deployable result in this line. Dery, Krupnik
and Keslassy train a reinforcement-learning agent offline across many settings
and distil it into a single lightweight policy that tunes ECN marking
probability online with no further learning, enabling small buffers in backbone
routers. QueuePilot is important context because it demonstrates that a learned
policy can be made cheap enough to run inline, the usual objection to RL-based
AQM, and because it adapts a *marking probability*, the same quantity Adaptive
RED adapts.

---

## 10. Runtime parameter adaptation

This is the line the present work sits in.

- **Adaptive RED** [5] adapts `max_p` by AIMD against a queue-length target.
- **Ye and Leung** [23] analyse CoDel's stability and show that a fixed
 `interval` can produce unstable queueing delay in some regimes. They derive
 necessary and sufficient stability conditions for the CoDel control loop and
 propose ACoDel-IT and ACoDel-TIT, which adjust `interval` adaptively. This is
 the closest published work to adapting CoDel's own parameters, and it is an
 analytical result with stability guarantees, a stronger foundation than an
 empirical AIMD heuristic.
- **Borkar** [24] provides the two-timescale stochastic approximation framework
 that justifies separating a fast measurement loop from a slow parameter-update
 loop, provided the timescales are adequately separated.

### The gap, stated honestly

Combining these: AIMD adaptation of a drop probability is established (Adaptive
RED); analytical adaptation of CoDel's `interval` is established (Ye and Leung);
learned adaptation of marking probability is established (QueuePilot). What does
**not** appear in the literature is a published, measured evaluation of AIMD
adaptation applied to `fq_codel`'s `target`/`interval`/`limit`/`quantum`
together, driven by eBPF flow telemetry, on stock Linux with no kernel changes.

That is a genuine gap, but it is a narrow one, and it should be described as
such. Specifically, it is a gap in *what has been tried and measured*, not a
demonstrated deficiency in `fq_codel`. The honest research question is not "no
one has done this, therefore it is valuable" but "does adapting these parameters
actually beat the defaults, and in which regimes?", a question that can only be
answered by measurement including the cases where the answer is no.

Two caveats that the earlier drafts of this project understated:

- CoDel's authors argue its defaults are RTT-relative and need no tuning [6].
 Any gain from adaptation must be demonstrated against that claim, not assumed.
- On the primary latency metric, the relevant baselines are not only static
 `fq_codel` but also PIE, FQ-PIE and CAKE, and L4S where ECN is available.

---

## 11. Summary

| Work | Year | Adapts | Mechanism | Kernel change | Relation to this study |
|---|---|---|---|---|---|
| RED [4] | 1993 | n/a | queue-length EWMA to drop prob. | n/a | ancestor |
| Adaptive RED [5] | 2001 | `max_p` | AIMD to queue target | no | **control law borrowed** |
| CoDel [6,7] | 2012/18 | n/a | sojourn-time target | n/a | AQM inside the system under study |
| PIE [8] | 2017 | n/a | PI controller on delay | n/a | baseline, measured here |
| fq_codel [10] | 2018 | n/a | DRR + per-queue CoDel | n/a | **system under study** |
| FQ-PIE [11] | 2019 | n/a | DRR + per-queue PIE | n/a | baseline, measured here |
| CAKE [12] | 2018 | n/a | integrated shaper + AQM | n/a | baseline, measured here |
| BBR [18] | 2016 | cwnd/pacing | bottleneck model | no (sender) | complementary |
| ACoDel [23] | 2020 | `interval` | stability analysis | yes | **closest prior work** |
| QueuePilot [22] | 2023 | marking prob. | offline RL to fixed policy | no | learned alternative |
| L4S [14-16] | 2023 | n/a | dual-queue + scalable ECN | yes (+transport) | stronger latency floor, different mechanism |
| SCRR [13] | 2025 | n/a | self-clocked round robin | yes | scheduler-side alternative |
| ML-AQM survey [21] | 2025 | n/a | taxonomy | n/a | positions learned AQM |
| **This work** | 2026 | `target`, `interval`, `limit`, `quantum` | AIMD + gradient trajectory + eBPF flow telemetry | **no** | n/a |

---

## References

1. J. Gettys and K. Nichols, "Bufferbloat: Dark Buffers in the Internet," *Communications of the ACM*, vol. 55, no. 1, pp. 57-65, Jan. 2012.
2. B. Briscoe et al., "Reducing Internet Latency: A Survey of Techniques and Their Merits," *IEEE Communications Surveys & Tutorials*, vol. 18, no. 3, pp. 2149-2196, 2016.
3. F. Baker and G. Fairhurst, "IETF Recommendations Regarding Active Queue Management," IETF RFC 7567, Jul. 2015.
4. S. Floyd and V. Jacobson, "Random Early Detection Gateways for Congestion Avoidance," *IEEE/ACM Transactions on Networking*, vol. 1, no. 4, pp. 397-413, Aug. 1993.
5. S. Floyd, R. Gummadi, and S. Shenker, "Adaptive RED: An Algorithm for Increasing the Robustness of RED's Active Queue Management," ICSI Technical Report, Aug. 2001.
6. K. Nichols and V. Jacobson, "Controlling Queue Delay," *ACM Queue*, vol. 10, no. 5, pp. 20-34, May 2012.
7. K. Nichols, V. Jacobson, A. McGregor, and J. Iyengar, "Controlled Delay Active Queue Management," IETF RFC 8289, Jan. 2018.
8. R. Pan, P. Natarajan, F. Baker, and G. White, "Proportional Integral Controller Enhanced (PIE): A Lightweight Control Scheme to Address the Bufferbloat Problem," IETF RFC 8033, Feb. 2017.
9. R. Jain, D.-M. Chiu, and W. Hawe, "A Quantitative Measure of Fairness and Discrimination for Resource Allocation in Shared Computer Systems," DEC Research Report TR-301, Sep. 1984.
10. T. Høiland-Jørgensen, P. McKenney, D. Täht, J. Gettys, and E. Dumazet, "The FlowQueue-CoDel Packet Scheduler and Active Queue Management Algorithm," IETF RFC 8290, Jan. 2018.
11. G. Ramakrishnan, M. Bhasi, V. Saicharan, L. Monis, S. D. Patil, and M. P. Tahiliani, "FQ-PIE Queue Discipline in the Linux Kernel: Design, Implementation and Challenges," in *Proc. IEEE LCN Symposium*, Oct. 2019.
12. T. Høiland-Jørgensen, D. Täht, and J. Morton, "Piece of CAKE: A Comprehensive Queue Management Solution for Home Gateways," in *Proc. IEEE LANMAN*, Washington DC, Jun. 2018. arXiv:1804.07617.
13. E. Sharafzadeh, R. Matson, J. Tourrilhes, P. Sharma, and S. Ghorbani, "Self-Clocked Round-Robin Packet Scheduling," in *Proc. 22nd USENIX Symposium on Networked Systems Design and Implementation (NSDI '25)*, Philadelphia, PA, Apr. 2025.
14. B. Briscoe, K. De Schepper, M. Bagnulo, and G. White, "Low Latency, Low Loss, and Scalable Throughput (L4S) Internet Service: Architecture," IETF RFC 9330, Jan. 2023.
15. K. De Schepper and B. Briscoe, "The Explicit Congestion Notification (ECN) Protocol for Low Latency, Low Loss, and Scalable Throughput (L4S)," IETF RFC 9331, Jan. 2023.
16. K. De Schepper, B. Briscoe, and G. White, "Dual-Queue Coupled Active Queue Management (AQM) for Low Latency, Low Loss, and Scalable Throughput (L4S)," IETF RFC 9332, Jan. 2023.
17. S. Ha, I. Rhee, and L. Xu, "CUBIC: A New TCP-Friendly High-Speed TCP Variant," *ACM SIGOPS Operating Systems Review*, vol. 42, no. 5, pp. 64-74, Jul. 2008.
18. N. Cardwell, Y. Cheng, C. S. Gunn, S. H. Yeganeh, and V. Jacobson, "BBR: Congestion-Based Congestion Control," *ACM Queue*, vol. 14, no. 5, 2016.
19. M. Allman, V. Paxson, and E. Blanton, "TCP Congestion Control," IETF RFC 5681, Sep. 2009.
20. M. A. M. Vieira et al., "Fast Packet Processing with eBPF and XDP: Concepts, Code, Challenges, and Applications," *ACM Computing Surveys*, vol. 53, no. 1, Article 16, 2020.
21. M. P. Toopchinezhad and M. Ahmadi, "Machine Learning Approaches for Active Queue Management: A Survey, Taxonomy, and Future Directions," *Computer Networks*, vol. 262, May 2025. arXiv:2410.02563.
22. M. Dery, O. Krupnik, and I. Keslassy, "QueuePilot: Reviving Small Buffers With a Learned AQM Policy," in *Proc. IEEE INFOCOM*, 2023.
23. J. Ye and K.-C. Leung, "Adaptive and Stable Delay Control for Combating Bufferbloat: Theory and Algorithms," *IEEE Systems Journal*, vol. 14, no. 1, pp. 1285-1296, Mar. 2020.
24. V. S. Borkar, "Stochastic Approximation with Two Time Scales," *Systems & Control Letters*, vol. 29, no. 5, pp. 291-294, 1997.

---

## 12. Recent work (2024, 2026)

The field moved substantially while this project was in progress, and in a
direction that narrows the gap this work claims. The additions below were
checked against the published record in November 2026.

### 12.1 Adaptive target tuning already exists, in programmable data planes

**DESiRED** [25] is the closest published work to this project's core idea, and
it predates it. Fabricio Rodriguez et al. build a P4 AQM (iRED) and then use a
deep reinforcement learning agent fed by In-band Network Telemetry to **tune
the AQM's target delay parameter at runtime**, reporting a 42× improvement in
high-resolution video playback and a 90× reduction in stalling.

This is the same idea, runtime adaptation of an AQM's delay target driven by
live telemetry, realised in P4 rather than Linux `tc`, and with DRL rather
than AIMD. Any claim that "no prior work adapts an AQM's target at runtime" is
therefore wrong. What remains distinct about the present work is narrower and
should be stated as such: **stock Linux, no kernel or data-plane
modification, eBPF rather than INT, and a transparent AIMD rule rather than a
learned policy**. That is a deployment-surface difference, not a conceptual one.

**P4-CoDel** [26] implements CoDel itself in a programmable data plane,
establishing the P4 AQM line that DESiRED builds on.

### 12.2 Large language models reach AQM

**AQM-LLM** [27] distils a large language model into an AQM controller for the
L4S architecture, with a state encoder mapping network telemetry to token
embeddings, a specialised head emitting congestion actions in one inference
step, and LoRA to keep the trainable parameter count small. It was published in
*IEEE Transactions on Networking* in 2026, with an open platform on FreeBSD 14.

Its relevance here is as a marker of where the learned-AQM frontier now sits:
the question is no longer whether a learned policy can run inline, QueuePilot
[22] settled that, but how much context a controller can usefully consume.
Against that, an AIMD rule over four parameters is a deliberately conservative
design, and its merit has to be interpretability and deployability rather than
performance.

### 12.3 AQM and measurement methodology

**Ray et al.** [28] characterise how AQM affects speed-test measurements,
finding that the presence of AQM changes what standard throughput tests report.
This bears directly on the methodology used here: it is a published instance of
the same class of error this project's verification uncovered, where a
measurement instrument interacts with the queue being measured and the
resulting number describes the instrument rather than the network.

**BBR over Wi-Fi 6** [29] examines AQM interaction with BBR on modern wireless,
relevant to the original Part 1 ambition of characterising qdiscs on an 802.11
interface, an experiment this project attempted but did not in fact perform.

### 12.4 Programmable qdiscs in Linux

**eBPF Qdisc** [30] proposes a fully programmable qdisc written in eBPF, using
BPF linked lists, red-black trees and local kernel pointers to let scheduling
and queue-management policy live entirely in BPF. This is the natural successor
to the approach taken here: rather than a userspace controller issuing
`tc qdisc change` on a fixed qdisc, the policy itself becomes a BPF program.
If it lands, it largely subsumes the userspace-controller design pattern.

---

## 13. Assessment of this project against the current field

Stated plainly, because the earlier drafts of this work did not:

**What is genuinely defensible.** A careful, reproducible measurement of nine
Linux queue disciplines under an identical bottleneck with directly measured
latency, multiple seeds and confidence intervals, on stock kernels with a
fully released artefact. Comparative AQM measurements at this level of
methodological care are less common than they should be, and the verification
methodology, checking physical invariants rather than trusting summary
statistics, is transferable.

**What is not novel.** Runtime adaptation of an AQM's delay target is
established (DESiRED, 2024). AIMD adaptation of an AQM parameter is
established (Adaptive RED, 2001). Analytical adaptation of CoDel's interval is
established (Ye and Leung, 2020). Learned AQM policies are established
(QueuePilot 2023, AQM-LLM 2026). eBPF telemetry at the `tc` hook is routine.
The combination, AIMD over four `fq_codel` parameters on stock Linux with eBPF
flow telemetry, appears not to have been published, but a combination is a
weak novelty claim, and it should be framed as an engineering data point rather
than a conceptual contribution.

**Where the field has moved.** Toward programmable data planes (P4, eBPF
qdisc), learned policies (RL, LLM), and changed network-transport contracts
(L4S). All three reach further than parameter tuning on a fixed qdisc. L4S in
particular achieves sub-millisecond queueing delay by changing what the network
signals, which no amount of `target` tuning can match.

**The honest framing for this work.** Not "a novel adaptive AQM" but "a
measured answer to whether tuning `fq_codel`'s parameters is worth doing, with
the apparatus to check." Given that CoDel's authors argue its defaults are
RTT-relative by design, that question was always likely to have a modest
answer, and a modest answer honestly reported is a legitimate contribution.

---

## References (continued)

25. F. Rodriguez et al., "DESiRED, Dynamic, Enhanced, and Smart iRED: A P4-AQM with Deep Reinforcement Learning and In-band Network Telemetry," *Computer Networks*, vol. 244, 2024. arXiv:2310.18159.
26. R. Kundel et al., "P4-CoDel: Active Queue Management in Programmable Data Planes," in *Proc. IEEE NFV-SDN*, 2018.
27. D. Satish et al., "Distilling Large Language Models for Network Active Queue Management," *IEEE Transactions on Networking*, 2026. arXiv:2501.16734.
28. S. Ray, T. Sharma, J. Marques, P. Schmitt, F. Bronzino, and N. Feamster, "Characterizing the Impact of Active Queue Management on Speed Test Measurements," arXiv:2511.19213, Nov. 2025.
29. "TCP BBR Performance over Wi-Fi 6: AQM Impacts and Cross-Layer Insights," arXiv:2512.18259, 2025.
30. C. Hung and P. Wang, "eBPF Qdisc: A Generic Building Block for Traffic Control," Netdevconf 0x17, 2023.
