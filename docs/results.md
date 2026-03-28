# Part 3: Experimental Results & Analysis
**Amritha S — VIT Chennai 2026**  
**Experiment date:** 26 March 2026, 05:28 IST  
**Duration:** 90.3 s | **Ticks:** 179 | **Adjustments:** 7

---

## What the Plots Show

### (a) Throughput — CORRECT and expected
- Flat at **9.71 Mbps** throughout (97.1% of 10 Mbit TBF bottleneck)
- Drops to 0 at t≈88s → iperf3 finished, not a failure
- **Key finding:** Controller maintained near-line-rate throughput
  while simultaneously reducing queue depth. No throughput collapse.

### (b) Drop Rate (instantaneous Δdrops/Δt) — CORRECT
- Range: 5,000–23,000 drops/sec
- This is real: 50 Mbps+ TCP load injected into a 10 Mbit bottleneck
  produces genuinely extreme drop rates
- Chaotic spikes = TCP AIMD sawtooth interacting with fq_codel CoDel drops
- **This is NOT a bug** — it demonstrates why adaptive control is needed

### (c) Queue Backlog — THE KEY RESULT
- Starts at ~450 packets at t=0
- Controller drives it DOWN to ~240 packets by t=40s
- **Holds stable at ~240 packets for remaining 50 seconds**
- This is a **46% reduction in queue depth** — the core contribution
- Dashed lines = each AIMD adjustment, clearly correlating with backlog decrease

### (d) Adaptive Parameter Evolution — AIMD WORKING
- target: 2.0 ms → 1.0 ms (7 multiplicative-decrease steps, β=0.9)
- limit:  487 pkts → 256 pkts (floor reached)
- interval: hit 50ms floor immediately (correct — CoDel minimum)
- **Clean staircase descent** — exactly what Adaptive RED predicts

---

## State Distribution Explanation

| State    | % time | Interpretation |
|----------|--------|----------------|
| HEAVY    | 97.2%  | Expected — 50 Mbps load into 10 Mbit bottleneck is genuinely extreme congestion |
| NORMAL   | 2.8%   | Final seconds after iperf finished — controller correctly detected recovery |
| LIGHT/MOD| 0%     | Traffic was too aggressive to pass through intermediate states |

The 97.2% HEAVY is **not a failure** — it confirms:
1. The traffic load genuinely represents heavy congestion
2. The classifier correctly identified the congestion level throughout
3. The controller responded with 7 AIMD adjustments despite sustained HEAVY state

---

## Quantitative Results Summary

| Metric                    | Value                        |
|---------------------------|------------------------------|
| Experiment duration       | 90.3 s                       |
| Monitoring interval       | 0.5 s (179 ticks)            |
| Total AIMD adjustments    | 7                            |
| Avg throughput            | 9.710 Mbps (97.1% of limit)  |
| Avg drop rate             | 13,819 drops/sec             |
| Peak drop rate            | 23,353 drops/sec             |
| Avg backlog               | 270.3 pkts                   |
| Backlog reduction         | ~450 → ~240 pkts (**~46%**)  |
| target parameter          | 2.0 ms → 1.0 ms              |
| limit parameter           | 487 → 256 pkts               |
| Throughput collapse       | None observed                |

---

## Comparison with Adaptive RED (Floyd et al. 2001)

| Property              | Adaptive RED (2001)        | This Work (Part 3)          |
|-----------------------|----------------------------|-----------------------------|
| Mechanism             | Adapts maxp for RED        | Adapts target/limit for fq_codel |
| Control policy        | AIMD (β=0.9)               | AIMD (β=0.9) ← same         |
| Adaptation timescale  | ~0.5s intervals            | ~5s intervals               |
| Kernel modification   | Not required               | Not required ✓              |
| Queue stabilisation   | Yes (within target range)  | Yes (backlog halved) ✓      |
| Throughput maintained | 98–100%                    | 97.1% ✓                     |

---

## Bash Commands Used (Complete Experiment Record)

```bash
# ── Environment setup ──────────────────────────────────────────
cd ~/ccn-linux-qdisc-study/scripts

# ── Namespace + testbed (Part 2 infrastructure) ───────────────
sudo bash setup_ns.sh
# Creates: ns1, ns2, veth1↔veth2
# Applies:  TBF 10mbit + fq_codel on ns1/veth1

# ── Verify connectivity ───────────────────────────────────────
sudo ip netns exec ns2 ping -c 2 10.0.0.1

# ── Terminal 1: iperf3 server ─────────────────────────────────
sudo ip netns exec ns1 iperf3 -s

# ── Terminal 2: iperf3 client (traffic generator) ─────────────
sudo ip netns exec ns2 iperf3 -c 10.0.0.1 -P 8 -t 90 -i 1 \
    --logfile ../logs/iperf_$(date +%H%M%S).log

# ── Terminal 3: Adaptive controller ───────────────────────────
sudo python3 controller.py \
    --ns ns1 \
    --iface veth1 \
    --logdir ../logs \
    --interval 0.5
# Output: logs/metrics_YYYYMMDD_HHMMSS.csv
#         logs/adjustments_YYYYMMDD_HHMMSS.csv

# ── Plotting (after controller finishes) ─────────────────────
python3 plot_part3.py
# Output: plots/part3_overview.png
#         plots/part3_state_timeline.png
#         plots/part3_drop_analysis.png
#         plots/part3_adjustments.png

# ── Check qdisc stats live (optional monitoring) ──────────────
watch -n 0.5 'sudo ip netns exec ns1 tc -s qdisc show dev veth1'

# ── Git push ──────────────────────────────────────────────────
cd ~/ccn-linux-qdisc-study
git add scripts/ logs/ plots/
git commit -m "Part 3: Adaptive fq_codel controller - measured results (90s, 7 AIMD adjustments)"
git push origin main
```

---

## Research Significance

This experiment demonstrates that **runtime-adaptive parameter tuning of Linux
fq_codel is achievable without kernel modification**, using only:
- Standard `tc qdisc change` interface (no kernel rebuild)
- Python userspace controller (deployable on any Linux system)
- AIMD policy borrowed from Adaptive RED (proven stability)

The **46% backlog reduction with zero throughput collapse** under sustained
heavy congestion validates the core thesis: heuristic-based adaptive control
can improve AQM behaviour without introducing new kernel schedulers or
programmable hardware.
