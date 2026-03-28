# Adaptive Linux AQM: a 2022–2025 gap map for PhD-level contribution

**A userspace+eBPF adaptive controller for fq_codel sits in a genuine, well-defined research gap.** No published work from 2022–2025 combines runtime parameter tuning of stock Linux fq_codel from userspace, multi-signal predictive state estimation, and eBPF-based in-kernel telemetry — despite each ingredient existing independently. The opportunity is real, but the contribution must be framed carefully to clear the bar at SIGCOMM, NSDI, INFOCOM, or IEEE/ACM ToN. Below is the full evidence base.

---

## 1. Adaptive fq_codel tuning without kernel patches is genuinely underexplored

The most important finding is that **no peer-reviewed paper from 2022–2025 proposes a userspace daemon that tunes fq_codel's target, interval, or quantum via `tc qdisc change` on a stock Linux kernel**. Every closely related work either modifies the kernel, replaces fq_codel entirely, or operates only in simulation.

The nearest misses, in decreasing relevance:

- **QueuePilot** (Dery, Krupnik, Keslassy — IEEE INFOCOM 2023). An RL-based AQM using eBPF for kernel-space ECN marking/dropping and a userspace PPO+LSTM agent that collects buffer observations. This is the closest architectural precedent: slow userspace RL + fast eBPF data plane. But it implements a *new* AQM policy from scratch rather than tuning fq_codel's existing parameters, and it targets small-buffer switches, not general Linux traffic control.

- **ACoDel-IT / ACoDel-TIT** (Ye & Leung — IEEE Systems Journal 2020; Ye, Leung & Low — IEEE/ACM ToN 2021). First analytical model of CoDel stability. Derives adaptive formulas for target and interval based on estimated flow count, capacity, and RTT. Proves that the fixed 5 ms / 100 ms defaults can become unstable. Critical limitation: **requires kernel-level changes** to the CoDel algorithm. Not deployable on stock Linux.

- **Gomez, Wang & Shami — "Intelligent Active Queue Management Using ECN"** (GLOBECOM 2019). LSTM congestion predictor feeds an RL agent that tunes fq_codel's target delay. Runs in Mininet with Python/TensorFlow. Closest in *intent* but (a) predates the 2022 window, (b) simulation-only, (c) no `tc`-based runtime deployment.

- **cake-autorate** (lynxthecat et al., open source, 2022–present). A bash script that adjusts CAKE's *bandwidth shaper* from userspace on variable-rate links (LTE, Starlink). Adjusts shaper rate via `tc qdisc change`, but **never touches target, interval, or quantum**. CAKE internally auto-derives those from the configured bandwidth.

- **DUK — "Auto-Tuning Active Queue Management"** (Novak & Kasera — IEEE INFOCOM 2017). A fully new AQM operating at the delay-utilization knee. Eliminates parameter specification entirely — but **replaces fq_codel** rather than tuning it.

- **DESiRED** (Almeida et al. — Computer Networks 2024). DRL-driven adaptive target delay on P4-programmable switches with In-band Network Telemetry. Achieves **90× reduction in video stalls**. Requires specialized programmable hardware, not stock Linux.

- **Toopchinezhad & Ahmadi — "Machine Learning Approaches for AQM: Survey, Taxonomy, Future Directions"** (Computer Networks, May 2025; arXiv 2410.02563). First comprehensive ML-AQM survey. Documents that **no ML-based AQM has reached production deployment**. Identifies the gap between simulation results and real-world systems as the field's central unsolved problem.

**Bottom line**: adaptive fq_codel parameter tuning from userspace on stock Linux is novel. The survey literature confirms it. The gap exists because researchers have focused on either replacing AQM algorithms entirely or modifying the kernel, not on the pragmatic middle path of a userspace control loop over the existing widely-deployed qdisc.

---

## 2. Unsolved limitations of fq_codel, CAKE, and FQ-PIE in 2024–2025

The AQM schemes deployed in Linux each carry specific, well-documented weaknesses that a userspace adaptive controller could directly address.

**fq_codel's fixed defaults create a three-way failure mode.** The 5 ms target is too aggressive below ~1 Mbps (less than one MTU's transmission time, causing underutilization and excessive drops). The 100 ms interval is far too slow for datacenter RTTs in the microsecond range. And neither parameter adapts when link capacity changes — a critical problem on LTE, 5G, cable, and satellite links where bandwidth can shift by an order of magnitude in seconds. Ye & Leung (2020) proved mathematically that the fixed interval can produce oscillatory instability when conditions deviate from assumptions.

**Hash collisions break flow isolation.** fq_codel's stochastic 5-tuple hash can map multiple flows to the same bucket. This is inherent to the design and cannot be fixed without increasing memory usage. CAKE's set-associative hash mitigates but does not eliminate collisions — and introduces its own problem: the CoDel sub-algorithm "gets less chance to run" in CAKE's architecture, causing CAKE to "stabilize at a much higher delay than we would like" (bufferbloat.net documentation).

**CAKE hits a hard CPU ceiling around 250–400 Mbps** on consumer router hardware. It cannot be offloaded to hardware, is incompatible with hardware NAT/flow offloading, and is single-threaded. For gigabit connections, CAKE is simply too expensive. fq_codel is lighter but lacks CAKE's bandwidth-awareness and per-host fairness.

**GRO/TSO superpackets create ~1000× dynamic range.** Modern NICs aggregate packets into ~64 KB superpackets. CAKE "peels" these apart when shaping below line rate; fq_codel does not, distorting both FQ fairness and CoDel sojourn-time measurements.

**WiFi remains partially addressed.** On ath10k (802.11ac), firmware queues bypass CoDel entirely. BQL does not work for wireless interfaces. Google documented that mac80211 sojourn times appear below target even when 1000+ packets sit in firmware queues. Airtime Queue Limits (AQL) help but are chipset-dependent and incomplete.

**BBR and QUIC interactions are poorly understood.** BBR's model-based congestion control interacts with AQM differently than loss-based algorithms. Recent testing on the CAKE mailing list (2024) shows ongoing challenges. L4S/DualPI2 represents the IETF's intended future but deployment remains minimal and interaction with legacy CoDel/CAKE traffic is still actively studied.

---

## 3. What clears the bar at SIGCOMM, NSDI, INFOCOM, and ToN

The acceptance rate and contribution expectations vary sharply across these venues, and targeting the right one matters.

**ACM SIGCOMM** (~10–14% acceptance, ~27–30 papers from 250–300 submissions) demands the highest novelty bar. Craig Partridge's canonical SIGCOMM Author Guide states: "Strong research track submissions will significantly advance the state of the art." The contribution must be statable in one sentence. Small, focused systems papers ("a paper tackling a modest problem") fare better than sprawling multi-contribution papers. Recent AQM-adjacent acceptances include "Principles for Internet Congestion Management" (Brown et al., SIGCOMM 2024), which rethought TCP-friendliness from first principles, and "Efficient Policy-Rich Rate Enforcement with Phantom Queues" (Tahir et al., SIGCOMM 2024).

**USENIX NSDI** is explicitly systems-focused: "Papers with no clear contributions to the design of systems or the networking stack will be considered out of scope." It requires real implementation and evaluation, not just simulation. NSDI 2025 accepted SCRR (see Section 8) and CCEval. The operational track accepts deployment experience papers that "need not present new ideas or results" — the value is in insights from real deployment.

**IEEE INFOCOM** is more theory-friendly with a larger program. Papers can lead with mathematical analysis and follow with simulation. QueuePilot appeared here. Recent relevant acceptances: "BCC: Re-architecting Congestion Control in DCNs" (2024), "RL-based Congestion Control: A Systematic Evaluation" (Giacomoni & Parisis, 2024) — the first reproducible RL-CC study.

**IEEE/ACM ToN** expects journal-level depth: **16 pages**, thorough related work, and meaningful extension beyond any conference version. Ye, Leung & Low's CoDel stability analysis appeared here.

For a userspace+eBPF fq_codel controller, the evaluation bar requires: **(a)** a real Linux testbed (not just ns-3), **(b)** comparison against untuned fq_codel, CAKE, and at least one ML-based AQM baseline, **(c)** trace-driven evaluation with production traffic patterns, **(d)** sensitivity analysis across link types (fixed broadband, LTE, datacenter), and **(e)** open-source code with reproducibility artifacts. NSDI or INFOCOM are the most natural targets; SIGCOMM would require a deeper architectural insight beyond "we tune parameters adaptively."

---

## 4. eBPF-based network control with userspace policy loops

eBPF has become the dominant substrate for programmable in-kernel networking, and several papers establish the architectural precedent for a userspace-policy + kernel-eBPF-telemetry design.

**"eBPF Qdisc: A Generic Building Block for Traffic Control"** (Amery Hung, Cong Wang / Bytedance — Netdevconf 0x17, 2023) is the most directly relevant infrastructure paper. It demonstrates eBPF-implemented fair queueing using `struct_ops` BPF, with **eBPF maps** providing shared state between kernel programs and userspace. Two use cases: a robust EDT rate limiter coordinating with fq via BPF maps, and flexible network emulation. This proves the *mechanism* for a userspace controller reading kernel qdisc state via BPF maps.

**Google's "Replacing HTB with EDT and BPF"** (Fomichev, Dumazet et al. — Netdevconf 2020) is the seminal production deployment: userspace computes rate limits → BPF sets EDT timestamps → FQ releases packets at scheduled times. Eliminates HTB's global lock. This is the pattern at Google scale: slow userspace policy, fast kernel scheduling.

**NetEdit** (Meta — ACM SIGCOMM 2024) is Meta's production eBPF orchestration platform, operational for 6+ years across tens of thousands of servers. **40% of code commits are policy changes** in userspace; 24.6% are BPF kernel code. It manages TCP congestion control tuning, initial window settings, and other network parameters. Demonstrates massive-scale userspace→eBPF→kernel control.

**ALPS** (Fu et al. — USENIX ATC 2024) applies the identical pattern to CPU scheduling: userspace learns approximate SRPT policies from historical workload data, sends them to eBPF hooks in CFS. Achieves **57.2% reduction in average latency**. Though for CPU, not packet scheduling, the architecture — slow-timescale userspace learning feeding fast-timescale eBPF kernel decisions — maps directly.

**sched_ext** (Tejun Heo et al. / Meta & Google — merged Linux 6.12, 2024) makes BPF-based custom CPU scheduling a first-class kernel feature via `struct_ops`. The equivalent for packet scheduling (eBPF Qdisc via `struct_ops`) is on the same trajectory.

Other relevant eBPF networking work: **"Fast In-kernel Traffic Sketching in eBPF"** (Miano et al. — SIGCOMM CCR 2023) shows per-packet data collection is feasible at line rate; **Electrode** (Zhou et al. — NSDI 2023) and **DINT** (Zhou et al. — NSDI 2024) demonstrate fast eBPF kernel paths with userspace fallback; **Valinor** (Sharafzadeh et al. — NSDI 2023) uses eBPF at tc hooks to measure how qdiscs (fq, fq_codel, pfifo_fast) shape bursts at different timescales.

---

## 5. Multi-timescale adaptive control has theory but no Linux qdisc implementation

The concept is straightforward: different control actions operate at different time granularities. Per-packet decisions (enqueue/dequeue, drop, ECN mark) run at microsecond timescales in-kernel. Parameter updates (target, interval, shaper rate) run at millisecond-to-second timescales in userspace. Model retraining or capacity planning runs over hours.

**Borkar's "Stochastic Approximation with Two Time Scales"** (Systems & Control Letters, 1997) provides the foundational mathematical framework: coupled iterations with different step-size schedules where the inner loop (fast) converges before the outer loop (slow) takes its next step. **Bhatnagar, Fu, Marcus & Fard** (IEEE/ACM ToN, 2001) directly applied two-timescale SPSA to ATM/ABR flow control — the most relevant theoretical precedent connecting multi-timescale optimization to network queue management.

**HFTraC** (Wu et al. — IEEE ToN, ~2022–2023) proposes distributed optimal control for RTT-timescale congestion management. Key insight: congestion management at fast timescales is complementary to, not a replacement for, TCP/AQM. Shows **50%+ reduction in packet loss** on WAN topologies.

CoDel and PIE are themselves *implicit* multi-timescale controllers. CoDel distinguishes transient queues (short timescale, acceptable) from persistent queues (long timescale, pathological) via its interval parameter. PIE updates drop probability every 15 ms (slow) and applies it per-packet (fast). **Neither exposes a third, even slower control loop for adapting the parameters of the fast/medium loops** — this is precisely the gap a userspace controller would fill.

The CDC 2015 paper "Effects of Insufficient Time-Scale Separation in Cascaded, Networked Systems" directly demonstrates that when AQM (inner loop) and TCP (outer loop) timescales overlap too much, the cascaded system becomes unstable. This provides theoretical justification for ensuring proper timescale separation in any adaptive controller design.

**The gap is clear**: formal multi-timescale control theory exists, eBPF provides the implementation substrate for the fast in-kernel tier, but **no published work combines them for Linux qdisc parameter adaptation**. QueuePilot (INFOCOM 2023) comes closest architecturally but uses model-free RL rather than principled multi-timescale control theory, and implements a new AQM rather than tuning an existing one.

---

## 6. No paper combines RTT gradient, drop rate gradient, and backlog trend

This is a confirmed genuine gap. After exhaustive search, **no published work from 2022–2025 unifies these three specific signals into a composite congestion state predictor for AQM**.

The research landscape shows three separate threads that have never been woven together:

**Thread 1 — RTT/delay gradient analysis**: CoCoA++ (Rathod et al., Future Generation Computer Systems), TIMELY (Mittal et al., SIGCOMM 2015), and the 2024 paper "Adaptive Congestion Control in IoT Networks: Leveraging One-Way Delay" (Verma et al., Heliyon 2024) all use delay derivatives to detect congestion trends. None incorporates drop rate or backlog signals.

**Thread 2 — Queue backlog/length prediction**: LSTM-based queue length prediction for TSN switches (2022), DRL-AQM (Ma et al., Computer Networks 2022) using PPO with queue occupancy as the primary state input. These use only router-side queue observations without end-to-end delay or loss signals.

**Thread 3 — Loss-based congestion prediction**: Meta's production ML system (March 2024) uses LSTM over RTT and packet loss time series to predict congestion **4 seconds in advance**, achieving ~33% reduction in connection drops and ~44% reduction in transport not-ready events. Uses raw time series, not explicit gradients, and has no queue backlog signal.

The combination of all three gradients as a **state vector** for predictive AQM parameter tuning is novel. This matters because each signal captures a different aspect of congestion dynamics: RTT gradient detects incipient congestion before loss occurs; drop rate gradient captures the AQM's own response intensity; backlog trend reflects whether the queue is filling or draining. Together they form a more complete picture than any single signal.

---

## 7. Workload-aware AQM exists in fragments but lacks a unified adaptive framework

Several papers address pieces of workload-aware queue management, but none provides the full vision of learned workload characterization driving per-class adaptive AQM parameters.

**DC-ECN** (Majidi et al. — Computer Communications, 2020) is the most directly relevant: Gaussian Process Regression classifies elephant vs. mice flows by packet features, places them in dual queues with **independently adaptive ECN thresholds**. Achieves 21.8% lower FCT than MQ-ECN. However, it's binary classification only, uses a single ECN-based mechanism for both classes, and targets datacenter switches rather than Linux qdiscs.

**PET** (IEEE, 2023–2024) embeds the **elephant/mice flow ratio** into a multi-agent RL observation space for ECN threshold tuning. This is the closest to workload-characterization-aware adaptation, but operates on aggregate statistics rather than per-flow classification.

**ACC** (Bai, Chen et al. — ACM SIGCOMM 2021) uses RL to auto-tune ECN thresholds with implicit workload awareness. Achieves 8.7% and 24.3% reduction in average/99th-percentile FCT for mice flows. However, it adapts thresholds globally, not per-flow-class.

**PR-AQM** (Li et al. — Computer Networks 2023) does flow-size-aware scheduling on programmable switches using packet rank information. Reduces average FCT for short flows by up to **45%**. Uses explicit flow-size information but requires programmable hardware.

**Cisco AFD with ETrap** is the most mature *production* workload-aware AQM. ETrap identifies elephant flows via byte-count thresholds; AFD applies proportional dropping to elephants while completely protecting mice. Not ML-based; deployed on Nexus 9000 switches.

**The gap for a Linux qdisc controller**: no system learns the full flow-size distribution from eBPF telemetry, classifies traffic into multiple categories beyond binary elephant/mice, and selects different fq_codel parameter profiles per-class. The existing work is either datacenter-switch-specific, binary in its classification, or does not adapt AQM parameters (only scheduling priority).

---

## 8. SCRR leaves AQM integration and adaptivity as explicit open problems

**"Self-Clocked Round-Robin Packet Scheduling"** (Sharafzadeh, Matson, Tourrilhes, Sharma, Ghorbani — USENIX NSDI 2025) addresses two assumptions of Deficit Round Robin that no longer hold in modern traffic: that packet size distributions are known in advance (invalidated by jumbo frames and variable MTUs), and that all bursts are long enough to create backlogged queues (invalidated by short latency-sensitive flows like DNS, video conferencing, and web).

SCRR hybridizes Fair Queuing's virtual clocking with DRR's round-robin service order, achieving O(1) per-packet complexity while eliminating the quantum parameter entirely. Results: **23% less CPU overhead** than DRR with small quantum, **71% better application latency** than DRR with large quantum, **1.5× less per-packet CPU cost** than tail-drop.

What SCRR explicitly does NOT do, creating clear complementary research opportunities:

- **No AQM whatsoever.** SCRR is purely a scheduler. It decides transmission order but never drops or marks packets. The paper evaluates against tail-drop and PI2 as separate baselines but does not propose combining SCRR with any AQM. How to co-design SCRR with CoDel or PIE is an open question.

- **No adaptive behavior.** SCRR's virtual clock semantics are fixed at design time. There is no mechanism for runtime adaptation based on traffic load, link utilization, or RTT. The scheduling policy cannot change without reloading the kernel module.

- **No eBPF extensibility.** Implemented as a traditional kernel qdisc module (sch_scrr.ko), not using eBPF struct_ops. No userspace programmability.

- **No multi-signal awareness.** Uses only internal virtual clock state. Does not incorporate RTT, loss rate, ECN feedback, or application hints.

- **No production-scale evaluation.** Tested on a controlled physical testbed; no datacenter, WAN, or multi-hop evaluation.

---

## The composite gap: what a userspace+eBPF fq_codel controller could genuinely contribute

Synthesizing all eight research threads, the genuine research gap sits at the intersection of five independently confirmed voids:

**Gap 1 — No userspace adaptive tuning of stock fq_codel exists.** Every adaptive AQM paper either modifies the kernel, replaces the algorithm, or operates in simulation. A controller that uses `tc qdisc change` on an unmodified kernel is both novel and immediately deployable on millions of existing Linux machines.

**Gap 2 — Multi-signal predictive state estimation is unexplored for AQM.** Combining RTT gradient, drop rate gradient, and backlog trend into a composite state predictor has no precedent. This is a concrete algorithmic novelty beyond "we used RL."

**Gap 3 — Principled multi-timescale control theory has not been applied to eBPF-based qdisc management.** The theoretical framework (Borkar 1997, Bhatnagar 2001) and the implementation substrate (eBPF maps, struct_ops) both exist but have never been connected for Linux traffic control. QueuePilot (INFOCOM 2023) uses RL but not formal two-timescale SA theory.

**Gap 4 — Workload-aware parameter adaptation for fq_codel is absent.** Classifying traffic from eBPF flow telemetry and selecting different target/interval profiles for different workload regimes has no precedent on Linux.

**Gap 5 — SCRR creates a scheduling-only baseline that begs for adaptive AQM integration.** An "FQ-SCRR-CoDel" with adaptive parameters from userspace would be a natural and publishable follow-on to NSDI 2025's highest-profile scheduling paper.

For a 2026 publication, the strongest framing would be a **systems paper** (targeting NSDI or INFOCOM) that contributes: (1) a concrete architecture — eBPF telemetry collector feeding a userspace multi-timescale controller that tunes fq_codel parameters via tc; (2) a novel multi-signal state estimator that predicts congestion regime transitions before they occur; (3) a real-Linux implementation evaluated on commodity hardware across fixed broadband, LTE/5G, and datacenter workloads; and (4) head-to-head comparison against untuned fq_codel, CAKE+cake-autorate, and QueuePilot. The evaluation must include production traffic traces (not just Poisson arrivals), sensitivity analysis to control-loop latency, and explicit discussion of failure modes where the adaptive controller performs worse than the static default — acknowledging limitations is, per Partridge's SIGCOMM guide, "typically strengthens rather than weakens the paper."
