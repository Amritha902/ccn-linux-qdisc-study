# CCN Linux Qdisc Study

## Adaptive Characterization of Linux Queue Disciplines under Controlled Congestion

**Author:** Amritha S  
**GitHub:** https://github.com/Amritha902/ccn-linux-qdisc-study  
**Platform:** Ubuntu 24.04 LTS  
**Kernel:** Linux x86_64 GNU/Linux  
**Network Interface:** wlp4s0 (verify yours using `ip a`)  
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

This project presents a **four-part framework** for studying and improving Linux network congestion control:

### **Part 1: Static Queue Discipline Characterization** ✅ COMPLETED
Experimental characterization of legacy (`pfifo_fast`) vs. modern AQM (`fq_codel`) queue disciplines under controlled congestion.

**Completed Phases:**
- **Phase 1:** Baseline throughput analysis without bottleneck
- **Phase 2:** Controlled bottleneck comparison (pfifo_fast vs fq_codel)
- **Phase 3:** Fairness and congestion dynamics under parallel TCP flows

### **Part 2: Controlled Namespace Testbed** ✅ COMPLETED
Development of a deterministic congestion testbed using Linux network namespaces and virtual Ethernet pairs.

### **Part 3: Adaptive Userspace Controller** 🔜 PLANNED
Development of a userspace congestion control framework with dynamic qdisc parameter tuning.

### **Part 4: eBPF-Enhanced In-Kernel Intelligence** 🔜 PLANNED
Integration of eBPF-based in-kernel metrics collection and per-flow adaptive intelligence.

---

## 🔬 Research Motivation

### The Problem

Traditional Linux queue disciplines operate with **static parameters** that cannot adapt to changing network conditions:
- **pfifo_fast:** Legacy FIFO scheduler with tail-drop (reactive, causes bufferbloat)
- **fq_codel:** Modern AQM with controlled delay (proactive, but still static)

### The Solution Framework

1. **Characterize** existing static qdisc behavior (Part 1) ✅
2. **Build** deterministic congestion testbed (Part 2) ✅
3. **Adapt** queue parameters from userspace (Part 3) 🔜
4. **Enhance** with in-kernel eBPF intelligence (Part 4) 🔜

---

## 🖥️ Experimental Platform

### System Configuration

```bash
$ lsb_release -a
$ uname -a
$ ip a
```

**Network Interface:** Replace `<YOUR_INTERFACE>` with your active interface name (e.g., wlp4s0, eth0, enp0s3).  
Check using: `ip a | grep UP`

### Required Tools

```bash
$ sudo apt update
$ sudo apt install -y iperf3 iproute2 git gnuplot python3-pip
```

### Directory Structure

```bash
$ mkdir -p ~/ccn-linux-qdisc-study/logs
$ mkdir -p ~/ccn-linux-qdisc-study/scripts
$ cd ~/ccn-linux-qdisc-study
```

---

# PART 1: Static Queue Discipline Characterization ✅

## Experimental Design

- **Traffic Generator:** iperf3 with 8 parallel TCP flows
- **Test Duration:** 30 seconds per experiment
- **Bottleneck Mechanism:** Token Bucket Filter (TBF) configured to enforce artificial rate limits
- **Monitoring:** Real-time queue statistics via `tc -s`
- **Metrics:** Aggregate throughput, packet drops, queue depth

---

## Phase 1: Baseline Throughput Analysis

### Configuration

```bash
$ sudo tc qdisc del dev <YOUR_INTERFACE> root 2>/dev/null
$ sudo tc qdisc add dev <YOUR_INTERFACE> root pfifo_fast
$ tc qdisc show dev <YOUR_INTERFACE>
```

**Note:** Replace `<YOUR_INTERFACE>` with your actual interface (e.g., wlp4s0, eth0).

### Traffic Generation

**Terminal 1:**
```bash
$ iperf3 -s
```

**Terminal 2:**
```bash
$ iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile logs/phase1_iperf.log
```

**Terminal 3 (Optional):**
```bash
$ watch -n 1 "tc -s qdisc show dev <YOUR_INTERFACE> | tee -a logs/phase1_tc.log"
```

### Data Extraction

```bash
$ grep "^\[SUM\]" logs/phase1_iperf.log | awk '{ t++; print t "," $6 }' > logs/phase1_throughput.csv
```

### Visualization

```bash
$ gnuplot -e "
set terminal png size 800,500;
set output 'logs/phase1_throughput.png';
set title 'Phase 1: Aggregate TCP Throughput (pfifo_fast - No Bottleneck)';
set xlabel 'Time (seconds)';
set ylabel 'Throughput (Gbps)';
set grid;
plot 'logs/phase1_throughput.csv' using 1:2 with lines lw 2 title 'pfifo_fast baseline';
"
```

---

## Phase 2: Bottlenecked Queue Discipline Comparison

### Bottleneck Configuration

```bash
$ sudo tc qdisc del dev <YOUR_INTERFACE> root 2>/dev/null
$ sudo tc qdisc add dev <YOUR_INTERFACE> root handle 1: tbf rate 1gbit burst 32kbit latency 50ms
$ tc qdisc show dev <YOUR_INTERFACE>
```

### Phase 2A: pfifo_fast under Bottleneck

```bash
$ sudo tc qdisc add dev <YOUR_INTERFACE> parent 1:1 pfifo_fast
$ tc qdisc show dev <YOUR_INTERFACE>
```

**Traffic:**
```bash
$ watch -n 1 "tc -s qdisc show dev <YOUR_INTERFACE> | tee -a logs/phase2A_tc.log"
$ iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile logs/phase2A_iperf.log
```

**Data Extraction:**
```bash
$ grep "^\[SUM\]" logs/phase2A_iperf.log | awk '{ t++; print t "," $6 }' > logs/phase2A_throughput.csv
$ awk '/dropped/ { t++; print t "," $4 }' logs/phase2A_tc.log > logs/phase2A_drops.csv
```

**Visualization:**
```bash
$ gnuplot -e "
set terminal png size 800,500;
set output 'logs/phase2A_throughput.png';
set title 'Phase 2A: Throughput under Bottleneck (pfifo_fast)';
set xlabel 'Time (seconds)';
set ylabel 'Throughput (Gbps)';
set grid;
plot 'logs/phase2A_throughput.csv' using 1:2 with lines lw 2 title 'pfifo_fast';
"

$ gnuplot -e "
set terminal png size 800,500;
set output 'logs/phase2A_drops.png';
set title 'Phase 2A: Packet Drops (pfifo_fast)';
set xlabel 'Time (seconds)';
set ylabel 'Dropped Packets';
set grid;
plot 'logs/phase2A_drops.csv' using 1:2 with lines lw 2 lc rgb 'red' title 'pfifo_fast drops';
"
```

### Phase 2B: fq_codel under Bottleneck

```bash
$ sudo tc qdisc del dev <YOUR_INTERFACE> parent 1:1
$ sudo tc qdisc add dev <YOUR_INTERFACE> parent 1:1 fq_codel
$ tc qdisc show dev <YOUR_INTERFACE>
```

**Traffic:**
```bash
$ watch -n 1 "tc -s qdisc show dev <YOUR_INTERFACE> | tee -a logs/phase2B_tc.log"
$ iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile logs/phase2B_iperf.log
```

**Data Extraction:**
```bash
$ grep "^\[SUM\]" logs/phase2B_iperf.log | awk '{ t++; print t "," $6 }' > logs/phase2B_throughput.csv
$ awk '/dropped/ { t++; print t "," $4 }' logs/phase2B_tc.log > logs/phase2B_drops.csv
```

**Visualization:**
```bash
$ gnuplot -e "
set terminal png size 800,500;
set output 'logs/phase2B_throughput.png';
set title 'Phase 2B: Throughput under Bottleneck (fq_codel)';
set xlabel 'Time (seconds)';
set ylabel 'Throughput (Gbps)';
set grid;
plot 'logs/phase2B_throughput.csv' using 1:2 with lines lw 2 lc rgb 'blue' title 'fq_codel';
"

$ gnuplot -e "
set terminal png size 800,500;
set output 'logs/phase2B_drops.png';
set title 'Phase 2B: Packet Drops (fq_codel)';
set xlabel 'Time (seconds)';
set ylabel 'Dropped Packets';
set grid;
plot 'logs/phase2B_drops.csv' using 1:2 with lines lw 2 lc rgb 'blue' title 'fq_codel drops';
"
```

---

## Phase 3: Fairness and Congestion Dynamics

### Phase 3A: pfifo_fast Fairness Test

```bash
$ sudo tc qdisc del dev <YOUR_INTERFACE> root 2>/dev/null
$ sudo tc qdisc add dev <YOUR_INTERFACE> root pfifo_fast
$ tc qdisc show dev <YOUR_INTERFACE>
```

**Traffic:**
```bash
$ watch -n 1 "tc -s qdisc show dev <YOUR_INTERFACE> | tee -a logs/phase3A_tc.log"
$ iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile logs/phase3A_iperf.log
```

**Data Extraction:**
```bash
$ grep "^\[SUM\]" logs/phase3A_iperf.log | awk '{ t++; print t "," $6 }' > logs/phase3A_throughput.csv
$ awk '/dropped/ { t++; print t "," $4 }' logs/phase3A_tc.log > logs/phase3A_drops.csv
```

### Phase 3B: fq_codel Fairness Test

```bash
$ sudo tc qdisc del dev <YOUR_INTERFACE> root
$ sudo tc qdisc add dev <YOUR_INTERFACE> root fq_codel
$ tc qdisc show dev <YOUR_INTERFACE>
```

**Traffic:**
```bash
$ watch -n 1 "tc -s qdisc show dev <YOUR_INTERFACE> | tee -a logs/phase3B_tc.log"
$ iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile logs/phase3B_iperf.log
```

**Data Extraction:**
```bash
$ grep "^\[SUM\]" logs/phase3B_iperf.log | awk '{ t++; print t "," $6 }' > logs/phase3B_throughput.csv
$ awk '/dropped/ { t++; print t "," $4 }' logs/phase3B_tc.log > logs/phase3B_drops.csv
```

### Comparison

```bash
$ gnuplot -e "
set terminal png size 900,500;
set output 'logs/phase3_compare_drops.png';
set title 'Phase 3: Packet Drop Behavior Comparison';
set xlabel 'Time (seconds)';
set ylabel 'Dropped Packets';
set grid;
plot 'logs/phase3A_drops.csv' using 1:2 with lines lw 2 lc rgb 'red' title 'pfifo_fast', \
     'logs/phase3B_drops.csv' using 1:2 with lines lw 2 lc rgb 'blue' title 'fq_codel';
"
```

---

## Part 1 Results Summary

| Phase | Queue Discipline | Key Finding |
|-------|-----------------|-------------|
| **Phase 1** | pfifo_fast | High throughput, high variance, no AQM |
| **Phase 2A** | pfifo_fast | Bursty drops, oscillations, bufferbloat |
| **Phase 2B** | fq_codel | Smoother throughput, controlled drops, low latency |
| **Phase 3A** | pfifo_fast | Unfair flow allocation, synchronized congestion |
| **Phase 3B** | fq_codel | Fair flow distribution, stable performance |

### Key Observations

**pfifo_fast Limitations:**
- Tail-drop only activates after queue saturation (reactive)
- Single queue for all flows (poor fairness)
- No delay control (bufferbloat under congestion)
- Bursty drop pattern (congestion synchronization)

**fq_codel Advantages:**
- Early packet drops prevent bufferbloat (proactive AQM)
- Per-flow queuing with 1024 queues (excellent fairness)
- CoDel algorithm controls delay (low latency)
- Controlled drop pattern (no synchronization)

**Critical Insight:** fq_codel drops MORE packets but performs BETTER because controlled early drops prevent bufferbloat and maintain low latency.

### Research Insight

Part 1 demonstrates that while fq_codel improves congestion stability and fairness, it remains statically configured. This motivates the need for adaptive parameter tuning under dynamic workload conditions, forming the basis for Part 3.

---

# PART 2: Controlled Namespace Testbed ✅

## Architecture

```
       ns1 (10.0.0.1/24)                    ns2 (10.0.0.2/24)
    ┌─────────────────┐                  ┌─────────────────┐
    │  Traffic Sender │                  │ Traffic Receiver│
    │   (iperf3 -c)   │                  │   (iperf3 -s)   │
    └────────┬────────┘                  └────────┬────────┘
             │                                    │
         veth1 ←──────── Virtual Cable ─────────→ veth2
             │
    ┌────────▼────────┐
    │   TBF (10 Mbit) │  ← Bandwidth Limiter
    └────────┬────────┘
             │
    ┌────────▼────────┐
    │    fq_codel     │  ← Active Queue Management
    └─────────────────┘
```

## Step-by-Step Setup

### Step 1: Clean Previous Setup

```bash
$ sudo ip netns del ns1 2>/dev/null
$ sudo ip netns del ns2 2>/dev/null
$ sudo ip link del veth1 2>/dev/null
$ sudo ip link del veth2 2>/dev/null
```

### Step 2: Create Network Namespaces

```bash
$ sudo ip netns add ns1
$ sudo ip netns add ns2
$ ip netns list
```

### Step 3: Create Virtual Ethernet Pair

```bash
$ sudo ip link add veth1 type veth peer name veth2
$ ip link show | grep veth
```

### Step 4: Move Interfaces into Namespaces

```bash
$ sudo ip link set veth1 netns ns1
$ sudo ip link set veth2 netns ns2
$ sudo ip netns exec ns1 ip link show
$ sudo ip netns exec ns2 ip link show
```

### Step 5: Bring Interfaces UP

```bash
$ sudo ip netns exec ns1 ip link set lo up
$ sudo ip netns exec ns2 ip link set lo up
$ sudo ip netns exec ns1 ip link set veth1 up
$ sudo ip netns exec ns2 ip link set veth2 up
```

### Step 6: Assign IP Addresses

```bash
$ sudo ip netns exec ns1 ip addr add 10.0.0.1/24 dev veth1
$ sudo ip netns exec ns2 ip addr add 10.0.0.2/24 dev veth2
$ sudo ip netns exec ns1 ip addr show veth1
$ sudo ip netns exec ns2 ip addr show veth2
```

### Step 7: Verify Connectivity

```bash
$ sudo ip netns exec ns1 ping -c 4 10.0.0.2
```

Expected: 0% packet loss, RTT ~0.04 ms

### Step 8: Add Traffic Control Bottleneck

**8a. Add Token Bucket Filter:**
```bash
$ sudo ip netns exec ns1 tc qdisc add dev veth1 root handle 1: \
    tbf rate 10mbit burst 4kbit latency 50ms
```

**8b. Add fq_codel:**
```bash
$ sudo ip netns exec ns1 tc qdisc add dev veth1 parent 1:1 fq_codel
```

**Verify:**
```bash
$ sudo ip netns exec ns1 tc qdisc show dev veth1
```

### Step 9: Generate Traffic

**Terminal 1 (Server):**
```bash
$ sudo ip netns exec ns2 iperf3 -s
```

**Terminal 2 (Client):**
```bash
$ sudo ip netns exec ns1 iperf3 -c 10.0.0.2 -P 16 -t 30
```

Expected output:
- Sender: ~10.3 Mbits/sec
- Receiver: ~9.16 Mbits/sec
- Retransmissions: ~6,404

### Step 10: Observe Queue Statistics

```bash
$ sudo ip netns exec ns1 tc -s qdisc show dev veth1
```

Expected:
- TBF: dropped ~6,404, overlimits ~74,365
- fq_codel: target 5ms, interval 100ms

## Part 2 Results

**What We Proved:**
1. Traffic demand exceeded bottleneck capacity (74,365 overlimit events)
2. TBF successfully enforced bandwidth limit (~9.16 Mbps actual)
3. fq_codel actively managed queue delay (controlled drops)
4. TCP adapted to congestion (retransmissions)
5. Setup is reproducible and deterministic

---

# PART 3: Adaptive Userspace Controller 🔜

## Architecture

```
Network Traffic → tc (fq_codel with dynamic parameters)
                     ↓ metrics
         Userspace Controller
         ├─ Metrics Collection
         ├─ Congestion Classifier  
         └─ Parameter Optimizer
                     ↓ updates
         tc qdisc change (every 100ms)
```

## Planned Components

### 1. Metrics Collector
- Monitor `tc -s qdisc` every 100ms
- Extract: throughput, drops, backlog, latency

### 2. Congestion Classifier
- **Normal:** Low drop rate, stable throughput
- **Light:** Moderate drops
- **Heavy:** High drops, oscillations

### 3. Parameter Optimizer

Initial implementation uses a heuristic rule-based controller:
- Drop-rate based adjustment
- Backlog threshold control
- Multi-state congestion classification

Future extension may explore PID-based tuning.

### 4. Configuration Manager
- Apply via `tc qdisc change`
- Log updates, rollback on failure

## Implementation Sketch

**metrics_collector.py:**
```python
import subprocess, time

def collect_qdisc_metrics(interface='<YOUR_INTERFACE>'):
    cmd = f"tc -s qdisc show dev {interface}"
    output = subprocess.check_output(cmd, shell=True).decode()
    # Parse and return metrics
    return metrics
```

**congestion_classifier.py:**
```python
def classify_congestion(metrics_history):
    recent_drop_rate = calculate_drop_rate(metrics_history)
    
    if recent_drop_rate < 0.01:
        return "NORMAL"
    elif recent_drop_rate < 0.05:
        return "LIGHT"
    else:
        return "HEAVY"
```

**parameter_tuner.py:**
```python
def optimize_fq_codel_params(congestion_state):
    if congestion_state == "NORMAL":
        return "5ms", "100ms"
    elif congestion_state == "LIGHT":
        return "3ms", "80ms"
    else:  # HEAVY
        return "2ms", "50ms"

def apply_qdisc_change(interface, target, interval):
    cmd = f"sudo tc qdisc change dev {interface} root fq_codel target {target} interval {interval}"
    subprocess.run(cmd, shell=True)
```

---

# PART 4: eBPF-Enhanced In-Kernel Intelligence 🔜

## Architecture

```
Network Packets
    ↓
Linux Kernel Network Stack
    ├─ eBPF Program (XDP/TC hook)
    │  └─ Per-packet processing, flow tracking
    └─ eBPF Map (shared kernel memory)
       └─ Flow state table, metrics counters
    ↓
Userspace Controller
    └─ Reads eBPF maps, updates parameters
```

## Planned Components

### 1. eBPF Metrics Collector
- **XDP hook:** Per-packet metrics at earliest point
- **TC hook:** Queue-aware metrics
- **Per-flow tracking:** RTT, throughput, loss rate

### 2. In-Kernel Intelligence
- Flow classification (elephant vs. mice flows)
- RTT estimation per flow
- Congestion detection
- Per-flow marking (ECN, DSCP, priority)

### 3. Adaptive Flow Scheduling
- Dynamic priority based on flow behavior
- Per-flow fairness
- Congestion-aware routing

## Implementation Sketch

**ebpf_metrics.c:**
```c
#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>

struct flow_metrics {
    __u64 packets;
    __u64 bytes;
    __u64 last_seen;
    __u32 rtt_min;
    __u32 rtt_avg;
    __u16 drop_count;
};

struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __type(key, __u32);
    __type(value, struct flow_metrics);
    __uint(max_entries, 10000);
} flow_table SEC(".maps");

SEC("tc")
int track_flow_metrics(struct __sk_buff *skb) {
    __u32 flow_hash = skb->hash;
    struct flow_metrics *metrics = bpf_map_lookup_elem(&flow_table, &flow_hash);
    
    if (metrics) {
        metrics->packets++;
        metrics->bytes += skb->len;
        metrics->last_seen = bpf_ktime_get_ns();
    }
    
    return TC_ACT_OK;
}
```

**ebpf_reader.py:**
```python
from bcc import BPF

b = BPF(src_file="ebpf_metrics.c")
fn = b.load_func("track_flow_metrics", BPF.SCHED_CLS)
b.attach_ingress("<YOUR_INTERFACE>", fn)

flow_table = b["flow_table"]
for k, v in flow_table.items():
    print(f"Flow {k.value}: {v.packets} packets, {v.bytes} bytes")
```

---

## 🔄 Reproducibility

### Part 1 ✅
```bash
$ git clone https://github.com/Amritha902/ccn-linux-qdisc-study.git
$ cd ccn-linux-qdisc-study
```
Follow phase-by-phase instructions above. All logs/plots stored in `logs/`.

### Part 2 ✅
All commands documented step-by-step. Reproducible on any Linux system with iproute2 and iperf3.

### Part 3 & 4 🔜
Will include Python scripts, eBPF C code, compilation scripts, and test automation.

---

## 📚 References

1. **CoDel Algorithm:** Nichols, K., & Jacobson, V. (2012). "Controlling Queue Delay." *ACM Queue, 10*(5).
2. **Linux Traffic Control:** `man tc`, `man tc-fq_codel`
3. **Active Queue Management:** Braden, B. et al. (1998). RFC 2309.
4. **eBPF:** Gregg, B. (2019). *BPF Performance Tools*. Addison-Wesley.

**Tools:**
- iperf3: https://iperf.fr/
- iproute2: https://wiki.linuxfoundation.org/networking/iproute2
- BCC: https://github.com/iovisor/bcc

---

## 📊 Project Timeline

| Phase | Status | Completion |
|-------|--------|------------|
| Part 1: Phase 1-3 | ✅ Complete | Feb 2026 |
| Part 2: Testbed | ✅ Complete | Feb 2026 |
| Part 3: Controller | 🔜 Planned | Mar-Apr 2026 |
| Part 4: eBPF | 🔜 Planned | May-Jun 2026 |

---

**Author:** Amritha S  
**Platform:** Ubuntu 24.04 LTS  
**GitHub:** https://github.com/Amritha902/ccn-linux-qdisc-study  
**License:** MIT (Educational/Research)

---

**End of README**
