# CCN Linux Qdisc Study

## Adaptive Characterization of Linux Queue Disciplines under Controlled Congestion

**Author:** Amritha S  
**GitHub:** https://github.com/Amritha902/ccn-linux-qdisc-study

**Platform:** Ubuntu 24.04 LTS  
**Kernel:** Linux x86_64 GNU/Linux  
**Primary Network Interface Used for Experiments:** wlp4s0  
(Verified using `ip a` → interface state UP with assigned IP address)  
**Date:** February 2026

---

## 📋 Table of Contents

1. [Project Overview](#project-overview)
2. [Research Motivation](#research-motivation)
3. [Experimental Platform](#experimental-platform)
4. [Part 1: Static Queue Discipline Characterization](#part-1-static-queue-discipline-characterization)
5. [Part 2: Controlled Namespace Testbed](#part-2-controlled-namespace-testbed)
6. [Part 3: Adaptive Userspace Controller](#part-3-adaptive-userspace-controller)
7. [Part 4: eBPF-Enhanced In-Kernel Intelligence](#part-4-ebpf-enhanced-in-kernel-intelligence)
8. [Reproducibility](#reproducibility)
9. [References](#references)

---

## 🎯 Project Overview

This project presents a **four-part structured research framework** for studying and improving Linux network congestion control mechanisms within the Traffic Control (tc) subsystem.

This work moves from:

**Static queue characterization**  
→ **Deterministic congestion testbed**  
→ **Heuristic adaptive control**  
→ **eBPF-enhanced multi-timescale intelligence**

### What Has Actually Been Built So Far

✅ **Built and Executed:**

- pfifo_fast baseline characterization
- fq_codel characterization
- TBF bottleneck enforcement
- Drop and throughput time-series extraction
- CSV-based metric logging
- Gnuplot-based visualization
- Fairness comparison experiments
- Network namespace deterministic topology
- 10 Mbit reproducible bottleneck model
- High-concurrency TCP stress tests (8–16 parallel flows)
- Drop rate extraction via:
  ```bash
  tc -s qdisc show dev wlp4s0
  ```
- Throughput extraction via:
  ```bash
  grep "^\[SUM\]"
  ```

**This is not theoretical — this is implemented and reproducible.**

---

## 🔬 Research Motivation

### The Core Problem

Linux queue disciplines such as:
- `pfifo_fast`
- `fq_codel`

operate using **static parameter configurations**.

They do not dynamically adapt to:
- Changing traffic intensity
- Flow density
- Drop evolution
- Backlog growth
- Throughput variance

This leads to:
- Bufferbloat (tail-drop FIFO)
- Reactive-only congestion behavior
- Lack of workload-aware tuning
- Parameter sensitivity

### The Structured Solution Framework

| Part | Goal | Status |
|------|------|--------|
| Part 1 | Static behavioral characterization | ✅ Complete |
| Part 2 | Deterministic congestion testbed | ✅ Complete |
| Part 3 | Heuristic adaptive controller | 🔜 Planned |
| Part 4 | eBPF-enhanced multi-layer adaptation | 🔜 Planned |

---

## 🖥️ Experimental Platform

### System Commands Used

```bash
lsb_release -a
uname -a
ip a
ip route
```

Primary active interface verified:
```bash
ip a | grep wlp4s0
```

**Confirmed:**
- Interface state: UP
- Has IP address
- Used as experiment interface

### Tools Installed

```bash
sudo apt update
sudo apt install -y iperf3 iproute2 git gnuplot python3-pip
```

Additional tools used during stress testing:
```bash
sudo apt install wget bmon net-tools
```

---

# PART 1: Static Queue Discipline Characterization ✅

## Actual Experimental Commands Executed

### Reset Interface

```bash
sudo tc qdisc del dev wlp4s0 root 2>/dev/null
```

### Phase 1 — pfifo_fast Baseline

```bash
sudo tc qdisc add dev wlp4s0 root pfifo_fast
tc qdisc show dev wlp4s0
```

**Traffic:**
```bash
iperf3 -s
iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile logs/phase1_iperf.log
```

**Monitoring:**
```bash
watch -n 1 "tc -s qdisc show dev wlp4s0 | tee -a logs/phase1_tc.log"
```

### Phase 2 — Bottleneck Introduction (TBF)

Artificial bottleneck enforced:
```bash
sudo tc qdisc add dev wlp4s0 root handle 1: \
tbf rate 5mbit burst 8kbit latency 200ms
```

Verified via:
```bash
tc -s qdisc show dev wlp4s0
```

Overlimit counters observed increasing under load.

### fq_codel Attached Under TBF

```bash
sudo tc qdisc add dev wlp4s0 parent 1:1 fq_codel
```

**Verified:**
```bash
tc qdisc show dev wlp4s0
```

### Observed Parameters

```
limit 10240p
flows 1024
quantum 1514
target 5ms
interval 100ms
memory_limit 32Mb
```

These were the actual runtime fq_codel defaults.

### Metrics Extracted

**Throughput:**
```bash
grep "^\[SUM\]" logs/phase2B_iperf.log \
| awk '{ t++; print t "," $6 }'
```

**Drops:**
```bash
awk '/dropped/ { t++; print t "," $4 }'
```

### Actual Observations (Experimentally Seen)

- pfifo_fast produced bursty drop clusters
- fq_codel distributed drops across time
- fq_codel showed higher drop count but lower oscillation
- Throughput stabilized under fq_codel
- Fairness improved under multi-flow TCP load
- TBF enforced deterministic rate limit (5mbit / 10mbit tests)

---

# PART 2: Controlled Namespace Testbed ✅

This removed dependency on WiFi variability.

## Namespaces Created

```bash
sudo ip netns add ns1
sudo ip netns add ns2
```

## veth Pair

```bash
sudo ip link add veth1 type veth peer name veth2
```

## IP Assignment

```bash
sudo ip netns exec ns1 ip addr add 10.0.0.1/24 dev veth1
sudo ip netns exec ns2 ip addr add 10.0.0.2/24 dev veth2
```

## Bottleneck Applied Inside Namespace

```bash
sudo ip netns exec ns1 tc qdisc add dev veth1 root handle 1: \
tbf rate 10mbit burst 4kbit latency 50ms
```

Then:
```bash
sudo ip netns exec ns1 tc qdisc add dev veth1 parent 1:1 fq_codel
```

## What This Proved

- Controlled congestion reproducibility
- Drop-overlimit separation
- Deterministic bottleneck modeling
- Repeatable stress behavior
- Reliable fairness comparison

---

# PART 3: Adaptive Userspace Controller 🔜

This extends your existing system.

## What You Have Designed (Heuristic-Based)

**Closed-loop:**
```
Monitor → Classify → Adjust → Observe → Repeat
```

**Metrics planned:**
- Drop rate D(t)
- Backlog B(t)
- Throughput variance
- Flow density

**Congestion states:**
- NORMAL
- LIGHT
- HEAVY

**Parameter tuning:**
```bash
tc qdisc change dev wlp4s0 root fq_codel target X interval Y
```

---

# PART 4: eBPF-Enhanced Intelligence 🔜

This enhances metric precision.

## Layered Architecture

```
Userspace Controller (100ms loop)
↕
eBPF TC Hook (packet-level metrics)
↕
fq_codel queue discipline
```

**Multi-timescale adaptation.**

---

## Additional What We Have Actually Built

- CSV logging framework
- Drop comparison plots
- Throughput comparison plots
- Phase 3 drop comparison plot
- Reproducible GitHub repository
- Structured experiment documentation
- Full step-by-step test methodology

---

## What Makes This Research-Level

- Empirical characterization under stress
- Controlled bottleneck modeling
- Fairness evaluation
- Time-series congestion analysis
- Heuristic-based adaptive extension
- Roadmap toward in-kernel intelligence
- No kernel modification required

---

## Conclusion

This project is no longer just:

> "Testing qdiscs"

It is:

> **A structured experimental and adaptive congestion control research framework for Linux traffic control.**

**If you want next:**
- I can formalize your heuristic mathematically
- Or strengthen novelty positioning
- Or draft IEEE-ready methodology section

Tell me which direction we refine.
