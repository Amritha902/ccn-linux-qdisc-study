# Experimental Characterization of Linux Queue Disciplines under Controlled Congestion

## Abstract
This report presents an experimental study of Linux queue disciplines under high-concurrency TCP workloads. Using Traffic Control (tc) and iperf3 on Ubuntu 24.04, the behavior of legacy and modern queue disciplines is analyzed under baseline and bottlenecked conditions. The study focuses on throughput, packet drops, and congestion management characteristics.

---

## 1. Introduction
Modern Linux systems rely on queue disciplines (qdiscs) to manage packet scheduling under congestion. While throughput is often used as a primary performance metric, queue-level behavior such as packet drops and congestion signaling plays a crucial role in network stability and fairness. This project experimentally evaluates default FIFO-based scheduling and modern Active Queue Management (AQM) techniques.

---

## 2. Experimental Setup

### 2.1 System Configuration
- Operating System: Ubuntu 24.04.2 LTS
- Architecture: x86_64 GNU/Linux
- Network Interface: wlp1s0
- Tools Used:
  - tc (Traffic Control)
  - iperf3
  - gnuplot

### 2.2 Traffic Model
- Traffic Type: TCP
- Number of parallel flows: 8
- Test duration: 30 seconds
- Traffic generator: iperf3

---

## 3. Phase 1: Baseline Throughput Analysis

### 3.1 Objective
To measure baseline throughput behavior without introducing any artificial bottleneck using the default Linux queue discipline.

### 3.2 Queue Discipline
- pfifo_fast (default)

### 3.3 Observations
Under baseline conditions, the system achieved very high aggregate throughput with negligible packet drops. This confirms unconstrained TCP behavior in the absence of congestion.

---

## 4. Phase 2: Bottlenecked Queue Discipline Analysis

A controlled bottleneck was introduced using a Token Bucket Filter (TBF) configured at 1 Gbit/s.

### 4.1 Phase 2A: pfifo_fast under Bottleneck

#### Observations
- Throughput was capped due to the imposed bottleneck.
- Packet drops increased steadily under sustained load.
- Drop behavior was bursty, indicating tail-drop congestion handling.

### 4.2 Phase 2B: fq_codel under Bottleneck

#### Observations
- Throughput remained stable but slightly lower compared to pfifo_fast.
- Packet drops were higher but controlled.
- fq_codel actively managed congestion through early packet dropping.

---

## 5. Phase 3: Fairness and Active Queue Management

### 5.1 Phase 3A: pfifo_fast Fairness Behavior
pfifo_fast exhibited uneven congestion response, with global synchronization effects and queue buildup under parallel TCP flows.

### 5.2 Phase 3B: fq_codel Fairness Behavior
fq_codel demonstrated improved fairness across flows and prevented persistent queue growth through active queue management.

---

## 6. Discussion
The experiments confirm that legacy FIFO-based queue disciplines are insufficient under high concurrency and bottlenecked conditions. Modern AQM techniques such as fq_codel provide better congestion signaling, improved fairness, and reduced queue buildup.

---

## 7. Conclusion
This study highlights the importance of queue-level analysis in understanding network congestion behavior. The results demonstrate that fq_codel offers significant advantages over pfifo_fast in managing congestion under controlled bottlenecks, making it a suitable choice for modern Linux systems.

---

## 8. Repository
All logs, datasets, and plots are available at:
https://github.com/Amritha902/ccn-linux-qdisc-study
