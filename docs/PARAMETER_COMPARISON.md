# Parameter and Capability Comparison

Three tables:

1. **Table A**, the queue disciplines measured in this study, with the
   parameters each exposes and what each controls.
2. **Table B**, this work against the base paper (Adaptive RED) and the
   related models, on what each adapts and how.
3. **Table C**, measured results across all systems. Generated from the logs;
   see `figures/comparison/table_*.csv` for the machine-readable form.

---

## Table A, Queue disciplines under test, and their parameters

| Discipline | Class | Flow queueing | Delay target | Tunable parameters | Default values used |
|---|---|---|---|---|---|
| `pfifo` | FIFO, no AQM | ✗ | ✗ | `limit` | `limit 1000` |
| `sfq` | Fair queueing, no AQM | ✓ (SFQ hash) | ✗ | `perturb`, `quantum`, `limit`, `divisor` | `perturb 10` |
| `red` (adaptive) | Drop-probability AQM | ✗ | queue length band | `min`, `max`, `limit`, `avpkt`, `burst`, `probability`, `bandwidth`, `adaptive`, `ecn` | `min 30000 max 90000 burst 55 avpkt 1000 bandwidth 10mbit ecn adaptive` |
| `codel` | Delay-target AQM | ✗ | sojourn time | `target`, `interval`, `limit`, `ecn`, `ce_threshold` | `target 5ms interval 100ms limit 1024` |
| `pie` | PI-controller AQM | ✗ | sojourn time | `target`, `tupdate`, `limit`, `alpha`, `beta`, `ecn`, `bytemode` | `target 15ms tupdate 15ms alpha 2 beta 20 limit 1000` |
| `fq_pie` | Flow queueing + PIE | ✓ (DRR) | sojourn time | `limit`, `flows`, `target`, `tupdate`, `alpha`, `beta`, `quantum`, `ecn_prob` | `limit 1024 target 15ms tupdate 15ms` |
| `cake` | Integrated shaper + AQM | ✓ (DRR, 8-way set-associative) | sojourn time (internal) | `bandwidth`, `rtt`, `besteffort`/`diffserv*`, `flows`/`dual*host`, `nat`, `ack-filter`, `overhead` | `besteffort` (TBF is the sole shaper) |
| `fq_codel` | Flow queueing + CoDel | ✓ (DRR) | sojourn time | **`target`**, **`interval`**, **`limit`**, **`quantum`**, `flows`, `memory_limit`, `ecn`, `ce_threshold`, `drop_batch` | `target 5ms interval 100ms limit 1024 quantum 1514` |
| `fq_codel` + ACAPE | Flow queueing + CoDel, adapted | ✓ (DRR) | sojourn time, adapted | the four in bold, adjusted at runtime | initial values as above; bounds set relative to the configured values, `target ∈ [0.04, 4] × target₀`, `interval ∈ [0.2, 3] × interval₀`, `limit ∈ [64, 4096]`, `quantum ∈ {300, 1514, 3000} B` |

All disciplines sit as the child of an identical TBF shaper
(`rate 10mbit burst 32kbit latency 400ms`) on the router's egress toward the
server, with `netem delay 10ms` at each edge for a 20 ms base RTT. CAKE is
configured `besteffort` without its own `bandwidth` so that TBF remains the
only shaper and every discipline sees the same bottleneck.

---

## Table B, This work vs. the base paper and the related models

| | **Adaptive RED**<br>(base paper) | **ACoDel**<br>Ye & Leung | **QueuePilot** | **DESiRED** | **AQM-LLM** | **L4S / DualPI2** | **This work (ACAPE)** |
|---|---|---|---|---|---|---|---|
| Year | 2001 | 2020 | 2023 | 2024 | 2026 | 2023 | 2026 |
| Venue | ICSI TR | IEEE Syst. J. | INFOCOM | Comput. Netw. | IEEE ToN | IETF RFC | n/a |
| **What it adapts** | `max_p` (drop probability) | CoDel `interval` | ECN marking probability | AQM **target delay** | congestion action (ECN/drop) |, (dual queue + coupling) | `target`, `interval`, `limit`, `quantum` |
| **Parameters adapted** | 1 | 1 | 1 | 1 | policy | 0 | 4 |
| **Adaptation method** | AIMD (β = 0.9) | analytical, stability-derived | offline RL → fixed policy | deep RL | distilled LLM + LoRA | n/a | AIMD (β = 0.9) + gradient trajectory |
| **Input signal** | averaged queue length | queue delay model | queue state | In-band Network Telemetry | network telemetry tokens | ECN | tc stats + eBPF flow telemetry |
| **Underlying AQM** | RED | CoDel | custom | iRED (P4) | L4S | DualPI2 | fq_codel |
| **Flow queueing** | ✗ | ✗ | ✗ | ✗ | ✗ | partial (dual queue) | ✓ (DRR) |
| **Platform** | simulation / RED routers | analysis + simulation | testbed | P4 switch | FreeBSD 14 | kernel + transport | stock Linux `tc` |
| **Kernel / data-plane change** | no | **yes** | no | **yes** (P4) | yes | **yes** (+ transport) | **no** |
| **Stability guarantee** | ✗ | **✓ (proved)** | ✗ | ✗ | ✗ | ✗ | ✗ |
| **Interpretable rule** | ✓ | ✓ | ✗ | ✗ | ✗ | ✓ | ✓ |
| **Training required** | ✗ | ✗ | ✓ offline | ✓ | ✓ | ✗ | ✗ |
| **Reported gain** | queue held near target | stability under varying load | small buffers viable | 42× video quality, 90× less stalling | improved L4S control | sub-ms queueing delay | *see Table C* |

### What this positioning means

- **Adaptive RED is the direct ancestor.** This work uses the same AIMD policy
  (β = 0.9) applied to a different qdisc's parameters. The control law is
  borrowed, not new.
- **DESiRED already adapts an AQM's target delay at runtime** using live
  telemetry, in 2024. The concept is therefore not novel. What differs here is
  the deployment surface: stock Linux with no kernel or data-plane change,
  eBPF rather than INT, and a transparent AIMD rule rather than a learned
  policy.
- **ACoDel is methodologically stronger** on the adaptation itself: it derives
  stability conditions analytically. This work's AIMD rule has no stability
  proof, and that is a genuine weakness rather than a presentational one.
- **L4S reaches a lower latency floor than any parameter tuning can**, by
  changing what the network signals to the transport. It is the relevant
  upper bound for the problem, not a peer.
- **The honest claim** is a combination, four `fq_codel` parameters, AIMD,
  eBPF telemetry, stock Linux, measured against eight alternatives. A
  combination is a weak novelty claim, and the value of this work rests mainly
  on the measurement and verification methodology.

---

## Table C, Measured results

Generated from the experiment logs. The authoritative machine-readable forms
are:

- `figures/comparison/table_steady.csv` / `table_staged.csv`, every metric,
  mean and 95% CI
- `figures/comparison/tables.json`, the same, structured
- `figures/comparison/fig08_allparams_<workload>.png`, all metrics × all
  systems as a normalised heatmap with measured values printed
- `figures/comparison/fig09_seeds_<metric>_<workload>.png`, each individual
  seed

Metrics recorded for every run:

| Metric | Source | Meaning |
|---|---|---|
| `throughput_mbps` | iperf3 `sum_received` | goodput actually delivered across the bottleneck |
| `jain` | per-stream iperf3 rates | Jain's fairness index across flows |
| `sparse_rtt_{mean,p50,p90,p95,p99,max,jitter}_ms` | `ping` at 20 Hz | latency seen by a sparse, latency-sensitive flow |
| `bulk_rtt_{mean,p50,p95,p99,max}_ms` | iperf3 per-interval TCP_INFO `rtt` | latency seen by the bulk flows themselves |
| `queue_delay_{mean,p95}_ms` | sparse RTT − configured base RTT | delay attributable to queueing |
| `backlog_{mean,p95,max}_pkts` | `tc -s qdisc show` on the AQM stanza | queue occupancy |
| `drop_rate_mean_per_s` | AQM drop counter delta | packets dropped by the AQM |
| `retransmits` | iperf3 `sum_sent.retransmits` | end-to-end TCP retransmissions |
| `cwnd_mean_bytes` | iperf3 per-interval `snd_cwnd` | sender congestion window |
| `sojourn_{mean,p95}_ms` | backlog bytes ÷ drain rate | instantaneous queue sojourn estimate |

**Why both sparse and bulk RTT are reported.** `fq_codel`'s new-flow heuristic
gives a sparse ICMP probe preferential service, so the probe and the bulk flows
it shares the link with report substantially different latency, in pilot
measurements 22.4 ms versus 36.3 ms mean. Quoting only the probe overstates
the benefit to bulk traffic; quoting only the bulk figure understates the
benefit to interactive traffic. Both belong in a latency claim.
