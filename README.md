# CCN Linux Qdisc Study — ACAPE

## Adaptive Characterization of Linux Queue Disciplines under Controlled Congestion

**Authors:** Amritha S · Yugeshwaran P · Deepti Annuncia  
**Institution:** Dept. of ECE, SENSE — VIT Chennai, India  
**Platform:** Ubuntu 24.04 LTS · Linux 6.8.x · HP Pavilion Laptop 15-eg2xxx  
**Primary Interface (Part 1):** wlp4s0  
**Namespace Interface (Parts 2–4):** veth1 (ns1 ↔ ns2)  
**Monitoring Stack:** Prometheus + Grafana (live eBPF dashboard)  
**Date:** March 2026  
**GitHub:** https://github.com/Amritha902/ccn-linux-qdisc-study

[![Status](https://img.shields.io/badge/Parts%201–4-Complete-brightgreen)]()
[![eBPF](https://img.shields.io/badge/eBPF-clang%2Btc%2Bbpftool-blue)]()
[![Monitoring](https://img.shields.io/badge/Grafana%2BPrometheus-Live-orange)]()
[![License](https://img.shields.io/badge/License-GPL--2.0-red)]()

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Research Motivation](#2-research-motivation)
3. [Repository Structure](#3-repository-structure)
4. [Part 1 — Static Queue Discipline Characterisation](#4-part-1--static-queue-discipline-characterisation)
5. [Part 2 — Deterministic Namespace Testbed](#5-part-2--deterministic-namespace-testbed)
6. [Part 3 — Reactive AIMD Adaptive Controller](#6-part-3--reactive-aimd-adaptive-controller)
7. [Part 4 — ACAPE: Predictive Multi-Signal eBPF Controller](#7-part-4--acape-predictive-multi-signal-ebpf-controller)
8. [Monitoring Stack — Prometheus + Grafana](#8-monitoring-stack--prometheus--grafana)
9. [Complete Results Summary](#9-complete-results-summary)
10. [ACAPE Algorithm Reference](#10-acape-algorithm-reference)
11. [Literature Survey](#11-literature-survey)
12. [Reproducibility](#12-reproducibility)
13. [References](#13-references)

---

## 1. Project Overview

This project presents a **four-part structured research framework** for studying and adaptively improving Linux network congestion control at the Traffic Control (tc) subsystem level.

The progression:

```
Part 1: Static characterisation of pfifo_fast and fq_codel on real interface (wlp4s0)
    ↓   Understanding baseline drop patterns, fairness, throughput under congestion
    
Part 2: Isolated namespace testbed (ns1 ↔ veth ↔ ns2, TBF 10Mbit bottleneck)
    ↓   Eliminates WiFi variability; reproducible controlled congestion environment
    
Part 3: Reactive AIMD adaptive controller (tc stats only, no eBPF)
    ↓   Heuristic congestion state classification + AIMD parameter adjustment
    
Part 4: ACAPE — Adaptive Condition-Aware Packet Engine
        Predictive multi-signal controller + eBPF TC telemetry + Grafana monitoring
```

**This is not theoretical — every part is implemented, measured, and reproducible.**

---

## 2. Research Motivation

### The Core Problem

Linux queue disciplines such as `pfifo_fast` and `fq_codel` use **static parameter configurations**:

```
fq_codel defaults (never change):
  target   = 5ms      ← acceptable queue sojourn time
  interval = 100ms    ← CoDel observation window
  limit    = 10240    ← maximum queue depth (packets)
  quantum  = 1514     ← per-flow service quantum (bytes)
```

These parameters do not adapt to:
- Changing traffic intensity (1 flow vs 8 flows vs 50 flows)
- Flow density distribution (elephant vs mice flows)
- Backlog growth trends (is congestion getting worse or recovering?)
- RTT inflation under sustained load

**Consequence:** Bufferbloat under pfifo_fast; suboptimal latency-throughput trade-offs under static fq_codel; no workload awareness in either.

### The Research Gap

No published work from 2022–2026 proposes:
1. Kernel-free runtime tuning of fq_codel's target/interval/limit/quantum
2. Using gradient-based prediction to act BEFORE congestion state transitions
3. eBPF per-flow telemetry driving fq_codel parameter profile selection
4. All of the above on stock Linux with production monitoring infrastructure

ACAPE fills all four gaps simultaneously.

### Novel Contributions (C1–C5)

| # | Contribution | What no prior work does |
|---|---|---|
| **C1** | Multi-signal gradient vector S(t) = [∇dr, ∇bl, ∇rtt] | All three gradients fused simultaneously |
| **C2** | Predictive regime detection from gradient direction | Acts BEFORE state transition, not after |
| **C3** | eBPF elephant/mice classification → parameter profiles | Live BPF flow data selecting fq_codel profiles |
| **C4** | Three-timescale control (eBPF/100ms/5s) on stock Linux | Zero kernel modification required |
| **C5** | Prometheus + Grafana live monitoring of eBPF metrics | Production-grade monitoring for research AQM |

---

## 3. Repository Structure

```
ccn-linux-qdisc-study/
│
├── scripts/
│   ├── setup_ns.sh              ← Namespace testbed setup (Part 2)
│   ├── controller.py            ← Part 3: Reactive AIMD controller
│   ├── plot_part3.py            ← Part 3: Results plotter
│   ├── acape_v5.py              ← Part 4: ACAPE main controller
│   ├── plot_acape.py            ← Part 4: Results plotter
│   ├── acape_exporter.py        ← Prometheus exporter (BPF maps + tc stats)
│   └── ebpf_dashboard.py        ← Terminal live dashboard
│
├── ebpf/
│   ├── tc_monitor.c             ← eBPF TC hook source (clang -g -target bpf)
│   └── Makefile                 ← Build with BTF (-g required)
│
├── monitoring/
│   └── README.md                ← Prometheus + Grafana setup guide
│
├── logs/                        ← Auto-generated CSV metric logs
│   ├── acape_metrics_*.csv      ← Per-tick: dr, bl, throughput, flows, regime
│   ├── acape_adj_*.csv          ← Per-adjustment: [PREDICTIVE]/[REACTIVE] tags
│   ├── acape_state_*.csv        ← Per-gradient: dr_grad, bl_grad, rtt_grad
│   ├── metrics_20260326_*.csv   ← Part 3 baseline metrics
│   └── archive/                 ← Old experiment runs
│
├── plots/                       ← Auto-generated PNG figures
│   ├── acape_overview.png       ← 6-panel main result figure
│   ├── acape_gradients.png      ← Gradient signals (C1 visualisation)
│   ├── acape_vs_part3.png       ← ACAPE vs reactive baseline comparison
│   ├── acape_adjustments.png    ← AIMD log with [PREDICTIVE]/[REACTIVE] tags
│   ├── part3_overview.png       ← Part 3 baseline plots
│   └── part3_state_timeline.png ← Part 3 state transitions
│
└── README.md
```

---

## 4. Part 1 — Static Queue Discipline Characterisation

**STATUS: ✅ COMPLETE**  
**Interface:** wlp4s0 (real WiFi interface, verified UP with IP)  
**Date:** February 2026

### What we did

Characterised the behaviour of `pfifo_fast` and `fq_codel` under controlled congestion on a real network interface. This established the baseline understanding of how Linux queue disciplines behave without any adaptation.

### Actual commands executed

```bash
# Verify interface
ip a | grep wlp4s0
ip a  # confirmed: state UP, IP assigned

# Install tools
sudo apt update
sudo apt install -y iperf3 iproute2 git python3-pip
pip3 install matplotlib numpy --break-system-packages

# ── Phase 1: pfifo_fast baseline ────────────────────────────
sudo tc qdisc del dev wlp4s0 root 2>/dev/null; true
sudo tc qdisc add dev wlp4s0 root pfifo_fast
tc qdisc show dev wlp4s0

# Traffic generation
iperf3 -s &
iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile logs/phase1_iperf.log

# Real-time monitoring
watch -n 1 "tc -s qdisc show dev wlp4s0 | tee -a logs/phase1_tc.log"

# ── Phase 2: TBF bottleneck at 5 Mbit ───────────────────────
sudo tc qdisc del dev wlp4s0 root 2>/dev/null; true
sudo tc qdisc add dev wlp4s0 root handle 1: \
    tbf rate 5mbit burst 8kbit latency 200ms

# ── Phase 3: fq_codel attached under TBF ────────────────────
sudo tc qdisc add dev wlp4s0 parent 1:1 fq_codel
tc qdisc show dev wlp4s0
# Observed runtime parameters:
# limit 10240p flows 1024 quantum 1514 target 5ms interval 100ms
# memory_limit 32Mb ecn drop_batch 64

# Extract throughput from iperf logs
grep "^\[SUM\]" logs/phase2B_iperf.log | awk '{ t++; print t "," $6 }'

# Extract drop statistics
awk '/dropped/ { t++; print t "," $4 }' logs/phase1_tc.log
```

### Key findings from Part 1

- **pfifo_fast** produced bursty drop clusters under congestion — TCP sawtooth clearly visible
- **fq_codel** distributed drops more evenly — fairer across flows
- fq_codel showed higher absolute drop count but much lower RTT variance
- Throughput stabilised faster under fq_codel than pfifo_fast
- Multi-flow fairness visibly improved under fq_codel
- TBF enforced deterministic rate limits at both 5 Mbit and 10 Mbit tested rates

---

## 5. Part 2 — Deterministic Namespace Testbed

**STATUS: ✅ COMPLETE**  
**Topology:** ns1 (server + bottleneck) ↔ veth pair ↔ ns2 (client)  
**Bottleneck:** TBF 10 Mbit/s + fq_codel child qdisc

### Why namespaces?

The real interface (wlp4s0) introduced external variability:
- WiFi multipath fading
- Background OS traffic
- External network interference

Network namespaces with virtual Ethernet pairs eliminate ALL of this. Every experiment is isolated, reproducible, and controllable.

### Topology

```
┌─────────────────┐                    ┌──────────────────────────────┐
│   ns2 (client)  │                    │      ns1 (server)            │
│                 │                    │                              │
│  iperf3 -c      │──── veth pair ─────│  iperf3 -s                   │
│  10.0.0.2/24    │                    │  10.0.0.1/24                 │
│                 │                    │                              │
└─────────────────┘                    │  TBF: rate 10mbit            │
                                       │  └─ fq_codel: target 5ms    │
                                       │     interval 100ms           │
                                       │     limit 1024               │
                                       └──────────────────────────────┘
```

### Namespace setup commands

```bash
# Create namespaces
sudo ip netns add ns1
sudo ip netns add ns2

# Create virtual Ethernet pair
sudo ip link add veth1 type veth peer name veth2
sudo ip link set veth1 netns ns1
sudo ip link set veth2 netns ns2

# Assign IPs
sudo ip netns exec ns1 ip addr add 10.0.0.1/24 dev veth1
sudo ip netns exec ns2 ip addr add 10.0.0.2/24 dev veth2

# Bring up interfaces
sudo ip netns exec ns1 ip link set veth1 up
sudo ip netns exec ns2 ip link set veth2 up
sudo ip netns exec ns1 ip link set lo up
sudo ip netns exec ns2 ip link set lo up

# Apply TBF bottleneck (10 Mbit) inside ns1
sudo ip netns exec ns1 tc qdisc add dev veth1 root handle 1: \
    tbf rate 10mbit burst 32kbit latency 400ms

# Attach fq_codel as child discipline
sudo ip netns exec ns1 tc qdisc add dev veth1 parent 1:1 handle 10: \
    fq_codel target 5ms interval 100ms limit 1024 quantum 1514

# Verify connectivity
sudo ip netns exec ns2 ping -c 3 10.0.0.1
# Must show 0% packet loss
```

### Experimental results

```bash
# Server in ns1
sudo ip netns exec ns1 iperf3 -s

# Client in ns2 — 8 TCP parallel flows, 20 seconds
sudo ip netns exec ns2 iperf3 -c 10.0.0.1 -P 8 -t 20 -J \
    --logfile logs/part2_iperf.json
```

| Metric | Value |
|--------|-------|
| Topology | ns1 ↔ veth ↔ ns2 |
| Bottleneck | TBF 10 Mbit/s, burst 32kbit |
| Queue discipline | fq_codel |
| Concurrent TCP flows | 8 parallel streams |
| Test duration | 20 seconds |
| **Aggregate throughput** | **≈ 10.1 Mbps (≈ link capacity)** |
| **Jain's Fairness Index** | **0.9997 (near-perfect)** |
| Average RTT | 0.541 ms |
| P95 RTT | 2.200 ms |
| P99 RTT | 2.445 ms |
| Maximum RTT | 5.280 ms |

**Per-flow throughput (all 8 flows):**

| Flow | Throughput (Mbps) |
|------|-------------------|
| 1–4, 6, 8 | 1.206 each |
| 5, 7 | 1.258 each |
| **Aggregate** | **≈ 10.1 Mbps** |

**Jain's Fairness Index:**
```
J = (Σxᵢ)² / (n × Σxᵢ²) = 0.9997
```
Value ≈ 1.0 confirms near-perfect fair sharing across all 8 flows.

### What Part 2 proved

- Correct TBF bottleneck enforcement at 10 Mbit/s
- fq_codel's per-flow fairness (DRR) working correctly
- Effective CoDel queue delay control — sub-millisecond average RTT
- No bufferbloat — P99 RTT < 2.5ms despite 8 concurrent flows
- Deterministic reproducibility — results consistent across repeated runs

---

## 6. Part 3 — Reactive AIMD Adaptive Controller

**STATUS: ✅ COMPLETE**  
**Approach:** tc stats only (no eBPF), heuristic state classification, AIMD parameter adjustment

### What Part 3 adds over Part 2

Part 2 used **static** fq_codel parameters. Part 3 adds a Python userspace controller that:
1. Reads `tc -s qdisc show` every 500ms
2. Classifies congestion state: NORMAL / LIGHT / MODERATE / HEAVY
3. Applies AIMD adjustments: multiplicative decrease (β=0.9) or additive increase (α=0.5ms)
4. Logs all adjustments with timestamps

### Run commands

```bash
# Terminal 1: iperf server
sudo ip netns exec ns1 iperf3 -s

# Terminal 2: traffic generator (8 flows, 90 seconds)
sudo ip netns exec ns2 iperf3 -c 10.0.0.1 -P 8 -t 90 -i 1 \
    --logfile logs/iperf_$(date +%H%M%S).log

# Terminal 3: adaptive controller
sudo python3 scripts/controller.py \
    --ns ns1 --iface veth1 --logdir logs/ --interval 0.5

# After experiment: generate plots
python3 scripts/plot_part3.py
```

### Part 3 results

| Metric | Value |
|--------|-------|
| Experiment duration | 90.3 seconds |
| Monitoring interval | 500ms (179 ticks) |
| AIMD adjustments made | 7–15 |
| **Backlog reduction** | **~46% (450 → 240 pkts)** |
| **Throughput maintained** | **97.1% of 10 Mbit** |
| Throughput collapses | **0** |
| target parameter | 5ms → 1ms (AIMD staircase) |
| limit parameter | 487 → 256 pkts (floor) |
| State distribution | 97.2% HEAVY, 2.8% NORMAL |

### Comparison with Adaptive RED (Floyd et al. 2001)

| Property | Adaptive RED | Part 3 |
|---|---|---|
| Mechanism | Adapts maxp for RED | Adapts target/limit for fq_codel |
| AIMD policy | β=0.9 | β=0.9 (same) |
| Adaptation timescale | ~0.5s | ~5s |
| Kernel modification | Not required | Not required ✓ |
| Queue stabilisation | Yes | Yes (46% reduction) ✓ |
| Throughput maintained | 98–100% | 97.1% ✓ |

---

## 7. Part 4 — ACAPE: Predictive Multi-Signal eBPF Controller

**STATUS: ✅ COMPLETE**  
**Full name:** Adaptive Condition-Aware Packet Engine  
**Key additions over Part 3:**
- Multi-signal gradient state vector (C1)
- Predictive regime detection (C2)  
- eBPF workload-aware profiles (C3)
- Three-timescale architecture (C4)
- Prometheus + Grafana live monitoring (C5)

### Three-timescale architecture

```
T1 (eBPF, ~ns):
  tc_egress_monitor() attached to veth1 egress inside ns1
  Per-packet: parse 5-tuple → update flow_map (packets, bytes, gap_ns, elephant)
  BPF maps: flow_map (LRU_HASH, 65536) | global_map (PERCPU_ARRAY) | size_hist

T2 (Python, 500ms):
  Read tc -s qdisc show → drop_rate, backlog, throughput
  Read bpftool map dump → active_flows, elephant_ratio, rtt_proxy
  Compute gradients: ∇dr, ∇bl, ∇rtt (linear regression over W=10 samples)
  Classify trajectory: WORSENING / STABLE / RECOVERING
  Predict next regime from gradient direction

T3 (Python, ~5s):
  Apply AIMD adjustment based on effective_regime + workload profile
  Issue: tc qdisc change dev veth1 parent 1:1 handle 10: fq_codel target Xms ...
  Log adjustment with [PREDICTIVE] or [REACTIVE] tag
```

### eBPF pipeline

```bash
# Step 1: Compile with BTF (-g required for bpftool formatted output)
cd ebpf/
clang -O2 -g -target bpf \
      -I/usr/include/x86_64-linux-gnu \
      -c tc_monitor.c -o tc_monitor.o
# OR: make clean && make

# Step 2: Attach inside ns1
sudo ip netns exec ns1 tc qdisc add dev veth1 clsact
sudo ip netns exec ns1 tc filter add dev veth1 egress \
    bpf direct-action obj tc_monitor.o sec tc_egress

# Step 3: Verify attachment
sudo ip netns exec ns1 tc filter show dev veth1 egress
# Must show: id N  jited  ← prog_id and JIT compiled

# Step 4: Read maps from HOST (BPF maps are kernel-global)
bpftool prog show id N --json      # get map_ids
bpftool map dump id M --json       # read flow_map entries
```

**Key insight:** BPF programs and maps are kernel-global objects. Even when loaded from inside ns1, their IDs are visible from the host via `bpftool`. This is why ACAPE does not need BCC, nsenter, or pyroute2 for map reads.

### Run ACAPE (4 terminals simultaneously)

```bash
# ── TERMINAL 1 — iperf server (keep open entire experiment) ──
sudo ip netns exec ns1 iperf3 -s -p 5202

# ── TERMINAL 2 — traffic (wait for T1 to show "Server listening") ──
sudo ip netns exec ns2 iperf3 \
    -c 10.0.0.1 -p 5202 \
    -P 8 -t 120 -i 1 \
    --logfile ~/ccn-linux-qdisc-study/logs/iperf_$(date +%H%M%S).log
# MUST show ~9-10 Mbps — NOT Gbps
# If showing Gbps: server isn't in ns1, redo namespace setup

# ── TERMINAL 3 — ACAPE controller (start 5s after T2) ──────
cd ~/ccn-linux-qdisc-study/scripts
sudo python3 acape_v5.py --ns ns1 --iface veth1 --logdir ../logs
# Watch for:
# [eBPF] Layer 1: ✅ Compiled with BTF (-g)
# [eBPF] Layer 2: ✅ Attached  (prog id=527)
# [eBPF] Layer 3: ✅ flow_map id=12
# mode: eBPF (clang+tc+bpftool)

# ── TERMINAL 4 — Prometheus exporter (alongside T3) ────────
sudo python3 ~/ccn-linux-qdisc-study/scripts/acape_exporter.py \
    --ns ns1 --iface veth1
# Exposes: http://localhost:9101/metrics

# After experiment (Ctrl+C on T3), generate plots:
python3 plot_acape.py --logdir ../logs
```

### ACAPE results

| Metric | Value |
|--------|-------|
| Experiment duration | 120 s |
| Total ticks | ~240 ticks (500ms interval) |
| AIMD adjustments | **15** |
| target evolution | **5ms → 1ms** (AIMD staircase) |
| Backlog stabilised at | **~240 pkts (from t=0)** |
| Part 3 needed to stabilise | ~60 seconds |
| **ACAPE stabilises in** | **<5 seconds** |
| Throughput maintained | **97%** |
| Throughput collapses | **0** |
| [PREDICTIVE] mode | **✅ confirmed in adj log** |
| [REACTIVE] mode | **✅ confirmed in adj log** |
| eBPF attached | **✅ prog_id=527, jited** |
| Grafana dashboard | **✅ live, all panels** |
| fq_codel quantum changed | **✅ 1514B → 300B (MICE profile)** |

### What the adjustment log shows

```
Time(s)  Regime  Trajectory   Predicted  Old_tgt  New_tgt  Reason
5.11     HEAVY   STABLE       HEAVY      5.00     4.50     [REACTIVE] mult-decrease β=0.9
10.25    HEAVY   STABLE       HEAVY      4.50     4.05     [REACTIVE] mult-decrease β=0.9
15.38    HEAVY   RECOVERING   MODERATE   4.05     3.65     [PREDICTIVE] mult-decrease β=0.9
20.51    HEAVY   RECOVERING   MODERATE   3.65     3.28     [PREDICTIVE] mult-decrease β=0.9
25.65    HEAVY   STABLE       HEAVY      3.28     2.95     [REACTIVE] mult-decrease β=0.9
...
```

The `[PREDICTIVE]` rows are the novel element: regime is HEAVY but trajectory is RECOVERING, so predicted next = MODERATE. The controller adjusts based on the predicted future state — lighter-touch than full multiplicative decrease.

---

## 8. Monitoring Stack — Prometheus + Grafana

**STATUS: ✅ COMPLETE AND WORKING**  
**Dashboard URL:** `http://localhost:3000/d/acape2026/acape-live-monitor`

### Why Prometheus + Grafana?

These are industry-standard monitoring platforms used in production eBPF deployments at Cloudflare, Meta, and Google. Adding them to ACAPE demonstrates that our telemetry pipeline produces metrics in a format compatible with real production infrastructure — not just a research prototype.

### Architecture

```
eBPF TC hook (kernel)
        ↓  per-packet: packets, bytes, gap_ns, elephant flag
  BPF maps: flow_map | global_map | size_hist
        ↓  bpftool map dump every 2s
  acape_exporter.py → http://localhost:9101/metrics
        ↓  Prometheus scrapes every 2s
  Prometheus (port 9090) — stores time series
        ↓  PromQL queries
  Grafana (port 3000) — ACAPE Live Monitor dashboard
```

### Installation

```bash
# Prometheus
sudo apt install -y prometheus

# Grafana
wget -q -O - https://packages.grafana.com/gpg.key | sudo apt-key add -
echo "deb https://packages.grafana.com/oss/deb stable main" | \
    sudo tee /etc/apt/sources.list.d/grafana.list
sudo apt update && sudo apt install -y grafana
sudo systemctl enable --now prometheus grafana-server

# Python exporter dependency
pip3 install prometheus-client --break-system-packages
```

### Configure Prometheus

```bash
sudo tee /etc/prometheus/prometheus.yml << 'EOF'
global:
  scrape_interval: 2s
scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
  - job_name: 'acape'
    static_configs:
      - targets: ['localhost:9101']
EOF
sudo systemctl restart prometheus
curl http://localhost:9090/-/ready
# Must show: Prometheus Server is Ready.
```

### Grafana dashboard import

```bash
# Get Prometheus datasource UID
curl -s http://admin:admin@localhost:3000/api/datasources

# Patch dashboard JSON and import
python3 -c "
import json, subprocess
uid = json.loads(subprocess.check_output(
    ['curl','-s','http://admin:admin@localhost:3000/api/datasources'],
    text=True))[0]['uid']
d = json.load(open('acape_dashboard_v3.json'))
for p in d['panels']:
    p['datasource'] = {'type':'prometheus','uid':uid}
json.dump({'dashboard':d,'overwrite':True,'folderId':0}, open('/tmp/dash.json','w'))
"
curl -s -X POST http://admin:admin@localhost:3000/api/dashboards/import \
    -H "Content-Type: application/json" -d @/tmp/dash.json

# Open dashboard
# http://localhost:3000/d/acape2026/acape-live-monitor
```

### Dashboard panels

| Panel | Metric | Data source |
|---|---|---|
| eBPF Attached (green/red) | prog_id ≠ 0 | bpftool + tc filter show |
| BPF prog_id | kernel prog ID | tc filter show egress |
| fq_codel target | 5ms → 1ms live | tc qdisc show |
| Queue backlog | pkts in queue | tc -s qdisc show |
| Throughput | Mbps vs 10 Mbit limit | tc byte counter delta |
| Drop rate | drops/sec live | tc drop counter delta |
| Flow classification | elephant vs mice vs active | BPF flow_map |
| fq_codel parameter evolution | target + limit + quantum over time | tc qdisc show |

### Future scope

Grafana Cloud integration for public dashboard URL — expose local Prometheus via ngrok (`ngrok http 9090`) or Grafana Agent pushing to `yourname.grafana.net`. The infrastructure is in place; public hosting is a configuration change only.

---

## 9. Complete Results Summary

### Part 1 — pfifo_fast vs fq_codel

| Metric | pfifo_fast | fq_codel |
|---|---|---|
| Drop pattern | Bursty clusters | Distributed evenly |
| Fairness (Jain) | ~0.89 | **0.9997** |
| RTT variance | High | Low |
| Bufferbloat | Present | Eliminated |

### Part 2 — fq_codel Static Baseline

| Metric | Value |
|---|---|
| Aggregate throughput | 10.1 Mbps |
| Jain's Fairness Index | **0.9997** |
| Average RTT | 0.541 ms |
| P95 RTT | 2.200 ms |
| P99 RTT | 2.445 ms |
| Max RTT | 5.280 ms |

### Parts 3 & 4 Comparison

| Metric | Static fq_codel | Part 3 Reactive | **ACAPE (Part 4)** |
|---|---|---|---|
| Avg backlog | ~450 pkts | ~270 pkts | **~240 pkts** |
| Stabilisation time | never | ~60 seconds | **<5 seconds** |
| AIMD adjustments | 0 | 7–15 | **15** |
| target evolution | fixed 5ms | 5ms → 1ms | **5ms → 1ms** |
| Throughput | 97% | 97.1% | **97%** |
| Throughput collapses | 0 | 0 | **0** |
| Predictive control | ❌ | ❌ | **✅ [PREDICTIVE] tags** |
| eBPF telemetry | ❌ | ❌ | **✅ prog_id=527 jited** |
| Grafana monitoring | ❌ | ❌ | **✅ live dashboard** |
| Kernel modification | ❌ | ❌ | **❌ (none needed)** |

---

## 10. ACAPE Algorithm Reference

### Gradient estimation (Linear Regression, W=10)

```
∇f(t) = Σᵢ(tᵢ − t̄)(f(tᵢ) − f̄) / Σᵢ(tᵢ − t̄)²

f ∈ {drop_rate, backlog, rtt_proxy}
Window W = 10 samples (5 seconds at T2=500ms)
```

### Composite gradient and trajectory

```
G(t) = 0.6 × (∇dr / DR_HEAVY) + 0.4 × (∇bl / BL_HEAVY)
       where DR_HEAVY=30 drops/sec, BL_HEAVY=300 packets

trajectory = WORSENING  if G(t) >  0.5
           = RECOVERING if G(t) < −0.5
           = STABLE     otherwise
```

### Regime classification

```
regime = HEAVY    if drop_rate > 30/s  OR backlog > 300 pkts
       = MODERATE if drop_rate > 10/s  OR backlog > 100 pkts
       = LIGHT    if drop_rate > 1/s   OR backlog > 20 pkts
       = NORMAL   otherwise
```

### Predictive effective regime (core novelty)

```
REGIMES = [NORMAL, LIGHT, MODERATE, HEAVY]
idx     = REGIMES.index(regime)

predicted = REGIMES[idx+1]  if WORSENING  and idx < 3
          = REGIMES[idx-1]  if RECOVERING and idx > 0
          = regime          otherwise

effective = predicted  if trajectory = WORSENING  →  [PREDICTIVE]
          = regime     otherwise                   →  [REACTIVE]
```

### AIMD parameter adjustment (β=0.9, α=0.5ms)

```
HEAVY:    target × 0.9  |  interval × 0.9  |  limit × 0.9
MODERATE: target − 0.2  |  limit − 32
LIGHT:    target + 0.5  |  interval + 5ms  |  limit + 64
NORMAL + RECOVERING: target + 0.2  |  limit + 16

quantum ← WORKLOAD_PROFILES[workload]     ← workload-aware (C3)
```

### Parameter bounds

```
target   ∈ [1ms,   20ms]     interval ≥ target × 10  (CoDel constraint)
interval ∈ [50ms, 300ms]     limit    ∈ [256,    4096] packets
quantum  ∈ {300B, 1514B, 3000B}         (from workload profile)
```

### Workload profiles (from eBPF elephant_ratio)

```
elephant_ratio = |flows: bytes > 10MB, age < 2s| / active_flows

ratio < 0.2  →  MICE     profile: target=2ms,  quantum=300B
ratio > 0.6  →  ELEPHANT profile: target=10ms, quantum=3000B
else         →  MIXED    profile: target=5ms,  quantum=1514B
```

### eBPF RTT proxy (RFC 6298 EWMA, in-kernel)

```
gap_ns = gap_ns == 0 ? Δt : (gap_ns × 7 + Δt) >> 3    (α = 0.125)
rtt_proxy_ms = mean(gap_ns over active flows, age < 2s) / 1e6
```

---

## 11. Literature Survey

| Paper | Venue | What it Does | ACAPE Difference |
|---|---|---|---|
| **Adaptive RED** (Floyd et al. 2001) | ICSI | Adapts RED's max_p via AIMD (β=0.9) | We extend same AIMD to 4 fq_codel params + add gradient prediction + eBPF |
| **fq_codel** (Nichols, Jacobson 2012) | ACM Queue | Fair Queue + CoDel AQM, Linux default | We tune it at runtime without replacing it |
| **QueuePilot** (Dery et al. 2023) | INFOCOM | PPO+LSTM RL + eBPF for new AQM policy | Replaces fq_codel; needs RL training; not stock Linux |
| **ACoDel** (Ye & Leung 2021) | IEEE ToN | Adaptive CoDel formulas: target=RTT/(2√N) | Requires kernel modification; we use tc qdisc change only |
| **SCRR** (Sharafzadeh et al. 2025) | NSDI | O(1) scheduler, 71% latency over DRR | Scheduling only, no AQM; AQM integration is future work |
| **eBPF Qdisc** (Hung, Wang 2023) | Netdevconf | BPF maps for tc state sharing | Validates our TC hook + BPF map architecture |
| **BBR** (Cardwell et al. 2016) | ACM Queue | Model-based proactive TCP CC | Transport layer only; no qdisc control; complements ACAPE |
| **ML-AQM Survey** (2025) | Computer Networks | First comprehensive ML-AQM survey | Directly confirms: no deployable kernel-free adaptive AQM for Linux fq_codel exists |
| **Borkar** (1997) | Sys. Control Lett. | Two-timescale stochastic approximation | Theoretical grounding for our T2/T3 timescale separation |

**Confirmed research gap (from ML-AQM Survey 2025):** No published 2022–2026 work proposes kernel-free runtime tuning of fq_codel's four parameters using gradient-based prediction AND eBPF workload classification AND production monitoring infrastructure.

---

## 12. Reproducibility

### One-time setup

```bash
# Clone
git clone https://github.com/Amritha902/ccn-linux-qdisc-study
cd ccn-linux-qdisc-study

# Dependencies
sudo apt install -y clang llvm libbpf-dev iperf3 iproute2 \
    linux-tools-$(uname -r) bpftool curl prometheus
pip3 install matplotlib numpy prometheus-client --break-system-packages

# Grafana
wget -q -O - https://packages.grafana.com/gpg.key | sudo apt-key add -
echo "deb https://packages.grafana.com/oss/deb stable main" | \
    sudo tee /etc/apt/sources.list.d/grafana.list
sudo apt update && sudo apt install -y grafana
sudo systemctl enable --now prometheus grafana-server

# Build eBPF
cd ebpf && make clean && make && cd ..
```

### Namespace setup (after every reboot)

```bash
sudo ip netns del ns1 2>/dev/null; sudo ip netns del ns2 2>/dev/null; true
sudo ip netns add ns1 && sudo ip netns add ns2
sudo ip link add veth1 type veth peer name veth2
sudo ip link set veth1 netns ns1 && sudo ip link set veth2 netns ns2
sudo ip netns exec ns1 ip addr add 10.0.0.1/24 dev veth1
sudo ip netns exec ns2 ip addr add 10.0.0.2/24 dev veth2
sudo ip netns exec ns1 ip link set veth1 up && sudo ip netns exec ns2 ip link set veth2 up
sudo ip netns exec ns1 ip link set lo up && sudo ip netns exec ns2 ip link set lo up
sudo ip netns exec ns1 tc qdisc add dev veth1 root handle 1: \
    tbf rate 10mbit burst 32kbit latency 400ms
sudo ip netns exec ns1 tc qdisc add dev veth1 parent 1:1 handle 10: \
    fq_codel target 5ms interval 100ms limit 1024 quantum 1514
sudo ip netns exec ns2 ping -c 2 10.0.0.1   # must show 0% loss
```

### Run ACAPE experiment

```bash
# Terminal 1 — server (keep open)
sudo ip netns exec ns1 iperf3 -s -p 5202

# Terminal 2 — traffic (must show ~10 Mbps NOT Gbps)
sudo ip netns exec ns2 iperf3 -c 10.0.0.1 -p 5202 -P 8 -t 120 -i 1 \
    --logfile logs/iperf_$(date +%H%M%S).log

# Terminal 3 — ACAPE controller (5s after T2)
cd scripts && sudo python3 acape_v5.py --ns ns1 --iface veth1 --logdir ../logs

# Terminal 4 — Prometheus exporter (alongside T3)
sudo python3 scripts/acape_exporter.py --ns ns1 --iface veth1

# After experiment (Ctrl+C on T3):
python3 scripts/plot_acape.py --logdir logs/

# Git push
git add logs/ plots/ && git commit -m "ACAPE: $(date +%Y%m%d_%H%M)" && git push
```

### Debug checklist

```bash
# Is eBPF attached?
sudo ip netns exec ns1 tc filter show dev veth1 egress
# Look for: id N  jited

# Are BPF maps visible from host?
bpftool prog show id N --json | python3 -c "import sys,json; print(json.load(sys.stdin)['map_ids'])"

# Is iperf going through the bottleneck?
# Terminal 2 must show ~10 Mbps — if showing Gbps, server is NOT in ns1

# Is Prometheus scraping?
curl http://localhost:9090/api/v1/query?query=acape_backlog_packets

# Is exporter running?
curl http://localhost:9101/metrics | grep acape_
```

---

## 13. References

1. Floyd, Gummadi, Shenker — *Adaptive RED: An Algorithm for Increasing the Robustness of RED's Active Queue Management* (ICSI 2001)
2. Floyd, Jacobson — *Random Early Detection Gateways for Congestion Avoidance* (IEEE/ACM ToN 1993)
3. Nichols, Jacobson — *Controlling Queue Delay* (ACM Queue, May 2012)
4. Dumazet, Taht — *fq_codel Linux Kernel Implementation* (2014)
5. Ramakrishnan et al. — *FQ-PIE Queue Discipline* (IEEE LCN 2019)
6. Cardwell, Cheng, Gunn, Yeganeh, Jacobson — *BBR: Congestion-Based Congestion Control* (ACM Queue 2016)
7. Sharafzadeh, Matson, Tourrilhes, Sharma, Ghorbani — *Self-Clocked Round-Robin Packet Scheduling* (USENIX NSDI 2025)
8. Dery, Krupnik, Keslassy — *QueuePilot: Reviving Small Buffers With a Learned AQM Policy* (IEEE INFOCOM 2023)
9. Ye, Leung — *Analysis and Design of an Adaptive CoDel AQM Algorithm* (IEEE/ACM ToN 2021)
10. Toopchinezhad, Ahmadi — *Machine Learning Approaches for Active Queue Management: A Survey* (Computer Networks, May 2025)
11. Hung, Wang (Bytedance) — *eBPF Qdisc: A Generic Building Block for Traffic Control* (Netdevconf 0x17, 2023)
12. Borkar — *Stochastic Approximation with Two Time Scales* (Systems & Control Letters, 1997)
13. Jain, Chiu, Hawe — *A Quantitative Measure of Fairness and Discrimination for Resource Allocation in Shared Computer Systems* (DEC TR, 1984)

---

**GitHub:** https://github.com/Amritha902/ccn-linux-qdisc-study  
**Authors:** Amritha S · Yugeshwaran P · Deepti Annuncia · VIT Chennai 2026
