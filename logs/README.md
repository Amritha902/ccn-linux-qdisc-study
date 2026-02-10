cat << 'EOF' > README.md
# CCN Linux Queue Discipline Study

This project studies Linux queue disciplines (qdisc) under congestion using tc and iperf3.
All experiments were executed on Ubuntu 24.04 LTS.

---

## System Information

- OS: Ubuntu 24.04.2 LTS (Noble)
- Kernel: x86_64 GNU/Linux
- Network Interface: wlp1s0
- Tools: tc, iperf3, git, gnuplot

---

## Phase 1: Baseline Throughput (pfifo_fast)

### Objective
Measure baseline throughput without an artificial bottleneck.

### Commands

Reset qdisc:
```bash
sudo tc qdisc del dev wlp1s0 root 2>/dev/null
sudo tc qdisc add dev wlp1s0 root pfifo_fast
tc qdisc show dev wlp1s0
cd ~/ccn-linux-qdisc-study

✅ STEP 2 — Create / overwrite README.md fully from terminal

This uses a here-document, so no nano typing needed.

cat << 'EOF' > README.md
# CCN Linux Queue Discipline Study

This project studies Linux queue disciplines (qdisc) under congestion using tc and iperf3.
All experiments were executed on Ubuntu 24.04 LTS.

---

## System Information

- OS: Ubuntu 24.04.2 LTS (Noble)
- Kernel: x86_64 GNU/Linux
- Network Interface: wlp1s0
- Tools: tc, iperf3, git, gnuplot

---

## Phase 1: Baseline Throughput (pfifo_fast)

### Objective
Measure baseline throughput without an artificial bottleneck.

### Commands

Reset qdisc:
```bash
sudo tc qdisc del dev wlp1s0 root 2>/dev/null
sudo tc qdisc add dev wlp1s0 root pfifo_fast
tc qdisc show dev wlp1s0

Run iperf:

iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile phase1_iperf.log

Extract throughput:

grep "^\[SUM\]" phase1_iperf.log | awk '{t++; print t "," $6}' > phase1_throughput.csv

Phase 2: Bottleneck Experiments

A bottleneck is introduced using a Token Bucket Filter (TBF) at 1 Gbit/s.
Phase 2A: Bottleneck with pfifo_fast

Configure bottleneck:

sudo tc qdisc del dev wlp1s0 root 2>/dev/null
sudo tc qdisc add dev wlp1s0 root tbf rate 1gbit burst 32k latency 50ms
sudo tc qdisc add dev wlp1s0 parent 1:1 pfifo_fast

Monitor queue:

watch -n 1 "tc -s qdisc show dev wlp1s0 | tee -a phase2A_tc.log"

Run iperf:

iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile phase2A_iperf.log

Extract throughput:

grep "^\[SUM\]" phase2A_iperf.log | awk '{t++; print t "," $6}' > phase2A_throughput.csv

Extract packet drops:

awk '/dropped/ {t++; print t "," $4}' phase2A_tc.log > phase2A_drops.csv

Phase 2B: Bottleneck with fq_codel

Replace queue discipline:

sudo tc qdisc del dev wlp1s0 parent 1:1
sudo tc qdisc add dev wlp1s0 parent 1:1 fq_codel
tc qdisc show dev wlp1s0

Monitor queue:

watch -n 1 "tc -s qdisc show dev wlp1s0 | tee -a phase2B_tc.log"

Run iperf:

iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile phase2B_iperf.log

Extract throughput:

grep "^\[SUM\]" phase2B_iperf.log | awk '{t++; print t "," $6}' > phase2B_throughput.csv

Extract packet drops:

awk '/dropped/ {t++; print t "," $4}' phase2B_tc.log > phase2B_drops.csv

Observations

    A clear bottleneck is formed in Phase 2.

    pfifo_fast shows bursty throughput and queue buildup.

    fq_codel actively controls queue delay using packet drops.

    fq_codel provides more stable congestion control.

Repository Structure

ccn-linux-qdisc-study/
├── logs/
│ ├── phase1_iperf.log
│ ├── phase1_throughput.csv
│ ├── phase2A_iperf.log
│ ├── phase2A_tc.log
│ ├── phase2A_throughput.csv
│ ├── phase2A_drops.csv
│ ├── phase2B_iperf.log
│ ├── phase2B_tc.log
│ ├── phase2B_throughput.csv
│ └── phase2B_drops.csv
└── README.md

Status: Phase 1 and Phase 2 completed.
EOF


---

## ✅ STEP 3 — Git add, commit, push (clean & correct)

```bash
git status
git add README.md
git commit -m "Add complete methodology for Phase 1, Phase 2A and Phase 2B"
git push```

cd ~/ccn-linux-qdisc-study

cat << 'EOF' > README.md
# CCN Linux Queue Discipline Study

This repository documents a systematic experimental study of Linux queue disciplines under baseline and congested conditions using Traffic Control (tc) and iperf3. All experiments were executed on Ubuntu 24.04 LTS using a single-node setup with controlled bottlenecks.

---

## System Configuration

- OS: Ubuntu 24.04.2 LTS (Noble)
- Architecture: x86_64 GNU/Linux
- Network Interface: wlp1s0
- Tools Used:
  - tc (Traffic Control)
  - iperf3
  - gnuplot
  - git

---

## Phase 1: Baseline Throughput (pfifo_fast)

### Objective
Establish baseline throughput behavior without any artificial bottleneck using the default Linux queue discipline.

### Queue Setup
```bash
sudo tc qdisc del dev wlp1s0 root 2>/dev/null
sudo tc qdisc add dev wlp1s0 root pfifo_fast
tc qdisc show dev wlp1s0
Phase 3: Fairness and Congestion Control Analysis

Phase 3 evaluates fairness and active queue management behavior under sustained parallel TCP flows.

Phase 3A: pfifo_fast Fairness Test
Queue Setup
sudo tc qdisc del dev wlp1s0 root 2>/dev/null
sudo tc qdisc add dev wlp1s0 root pfifo_fast
tc qdisc show dev wlp1s0

Queue Monitoring
watch -n 1 "tc -s qdisc show dev wlp1s0 | tee -a phase3A_tc.log"

Traffic Generation
iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile phase3A_iperf.log

Data Extraction
grep "^\[SUM\]" phase3A_iperf.log | awk '{t++; print t "," $6}' > phase3A_throughput.csv
awk '/dropped/ {t++; print t "," $4}' phase3A_tc.log > phase3A_drops.csv

Phase 3B: fq_codel Fairness Test
Queue Replacement
sudo tc qdisc del dev wlp1s0 root
sudo tc qdisc add dev wlp1s0 root fq_codel
tc qdisc show dev wlp1s0

Queue Monitoring
watch -n 1 "tc -s qdisc show dev wlp1s0 | tee -a phase3B_tc.log"

Traffic Generation
iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile phase3B_iperf.log

Data Extraction
grep "^\[SUM\]" phase3B_iperf.log | awk '{t++; print t "," $6}' > phase3B_throughput.csv
awk '/dropped/ {t++; print t "," $4}' phase3B_tc.log > phase3B_drops.csv

Summary

Phase 1 establishes a non-congested baseline.

Phase 2 introduces a controlled bottleneck and compares queue disciplines.

Phase 3 demonstrates fairness and active queue management behavior.

fq_codel consistently exhibits improved congestion control compared to pfifo_fast.

All experiments are reproducible using the documented commands.
EOF


---

## ✅ COMMIT & PUSH README (FINAL)

```bash
git add README.md
git commit -m "Complete README with full Phase 1–3 command-line methodology"
git push
PART 1 — README.md (FULL, FINAL, COPY-PASTABLE)

This is entire content. You can paste it directly into README.md.

# CCN Linux Qdisc Study  
**Comparative Study of Linux Queue Disciplines under Congestion**

Author: Amritha S  
GitHub: https://github.com/Amritha902/ccn-linux-qdisc-study  

---

## 1. Objective

This project experimentally studies the behavior of Linux queuing disciplines (qdisc) under congestion using TCP traffic.  
The focus is on comparing:

- `pfifo_fast` (legacy FIFO, tail-drop)
- `fq_codel` (Fair Queuing with Controlled Delay)

Metrics evaluated:
- Aggregate TCP throughput
- Throughput stability over time
- Packet drop behavior
- Congestion handling and fairness

Experiments are conducted on **Ubuntu 24.04 LTS** using **iperf3** and **tc**.

---

## 2. System Setup

### OS and Kernel
```bash
lsb_release -a
uname -a

Network Interface
ip a


Interface used throughout experiments:

wlp1s0

3. Required Tools

Install required packages:

sudo apt update
sudo apt install -y iperf3 iproute2 git gnuplot

4. Directory Structure
ccn-linux-qdisc-study/
├── README.md
├── logs/
│   ├── phase1_iperf.log
│   ├── phase1_tc.log
│   ├── phase1_throughput.csv
│   ├── phase1_throughput.png
│   ├── phase2A_*
│   ├── phase2B_*
│   ├── phase3A_*
│   ├── phase3B_*
│   └── phase3_compare_drops.png

5. Phase 1 — Baseline (pfifo_fast, No Bottleneck)
Purpose

Measure baseline aggregate TCP throughput with default Linux queuing discipline.

Configuration

Reset qdisc:

sudo tc qdisc del dev wlp1s0 root 2>/dev/null
sudo tc qdisc add dev wlp1s0 root pfifo_fast


Verify:

tc qdisc show dev wlp1s0

Traffic Generation

Start iperf server:

iperf3 -s


Run client:

iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile logs/phase1_iperf.log

Logging Queue Statistics
watch -n 1 "tc -s qdisc show dev wlp1s0 | tee -a logs/phase1_tc.log"

Throughput Extraction
grep "^\[SUM\]" logs/phase1_iperf.log | \
awk '{ t++; print t "," $6 }' > logs/phase1_throughput.csv

Plotting
gnuplot -e "
set terminal png size 800,500;
set output 'logs/phase1_throughput.png';
set title 'Phase 1: Aggregate TCP Throughput (pfifo_fast)';
set xlabel 'Time (seconds)';
set ylabel 'Throughput (Gbps)';
plot 'logs/phase1_throughput.csv' using 1:2 with lines title 'pfifo_fast baseline';
"

6. Phase 2 — Bottleneck Experiments

A bottleneck is introduced using Token Bucket Filter (TBF).

Bottleneck Configuration
sudo tc qdisc del dev wlp1s0 root 2>/dev/null
sudo tc qdisc add dev wlp1s0 root handle 1: tbf rate 100mbit burst 32kbit latency 50ms

Phase 2A — pfifo_fast under Bottleneck
Purpose

Observe tail-drop behavior and congestion effects.

Attach pfifo_fast:

sudo tc qdisc add dev wlp1s0 parent 1:1 pfifo_fast


Run traffic:

iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile logs/phase2A_iperf.log


Log qdisc stats:

watch -n 1 "tc -s qdisc show dev wlp1s0 | tee -a logs/phase2A_tc.log"


Extract metrics:

grep "^\[SUM\]" logs/phase2A_iperf.log | \
awk '{ t++; print t "," $6 }' > logs/phase2A_throughput.csv

awk '/dropped/ { t++; print t "," $4 }' logs/phase2A_tc.log > logs/phase2A_drops.csv

Phase 2B — fq_codel under Bottleneck

Replace child qdisc:

sudo tc qdisc del dev wlp1s0 parent 1:1
sudo tc qdisc add dev wlp1s0 parent 1:1 fq_codel


Run traffic:

iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile logs/phase2B_iperf.log


Extract metrics:

grep "^\[SUM\]" logs/phase2B_iperf.log | \
awk '{ t++; print t "," $6 }' > logs/phase2B_throughput.csv

awk '/dropped/ { t++; print t "," $4 }' logs/phase2B_tc.log > logs/phase2B_drops.csv

7. Phase 3 — Fairness and Congestion Behavior
Phase 3A — pfifo_fast
iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile logs/phase3A_iperf.log

Phase 3B — fq_codel
iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile logs/phase3B_iperf.log

Comparison Plot
gnuplot -e "
set terminal png size 900,500;
set output 'logs/phase3_compare_drops.png';
set title 'Phase 3: Drop Behavior Comparison';
set xlabel 'Time (seconds)';
set ylabel 'Dropped Packets';
plot 'logs/phase3A_drops.csv' using 1:2 with lines title 'pfifo_fast',
     'logs/phase3B_drops.csv' using 1:2 with lines title 'fq_codel';
"

8. Summary of Findings

pfifo_fast exhibits bursty drops and unstable throughput under congestion.

fq_codel introduces early drops to control queue delay.

Despite higher drop counts, fq_codel maintains smoother throughput and better fairness.

Results align with expected AQM behavior described in Linux networking literature.

9. Repository

All logs, CSV files, and plots are available at:
👉 https://github.com/Amritha902/ccn-linux-qdisc-study


---

# ✅ PART 2 — REPORT STRUCTURE (WHAT TO WRITE + WHERE TO ADD PLOTS)

You **do NOT paste commands here**. This is formal academic writing.

---

## Report Sections

### 1. Introduction
- Motivation for studying queuing disciplines
- Why pfifo_fast vs fq_codel
- Brief overview of methodology

---

### 2. Experimental Setup
Include:
- OS version
- Tools used
- Network interface
- Test topology (localhost TCP streams)

---

### 3. Phase 1: Baseline Results
**Add plot:**
- `phase1_throughput.png`

Explain:
- Aggregate throughput behavior
- Variability without congestion
- Why this serves as a baseline

---

### 4. Phase 2: Bottleneck Analysis

#### Phase 2A — pfifo_fast
**Add plots:**
- `phase2A_throughput.png`
- `phase2A_drops.png`

Explain:
- Tail-drop behavior
- Throughput oscillations
- Queue buildup effects

#### Phase 2B — fq_codel
**Add plots:**
- `phase2B_throughput.png`
- `phase2B_drops.png`

Explain:
- Early dropping
- Reduced delay
- Improved throughput stability

---

### 5. Phase 3: Fairness and Congestion Control

**Add plots:**
- `phase3A_throughput.png`
- `phase3B_throughput.png`
- `phase3_compare_drops.png`

Explain:
- Fairness differences
- Congestion responsiveness
- Why fq_codel outperforms pfifo_fast conceptually

---

### 6. Discussion
- Trade-offs between drop rate and latency
- Why more drops ≠ worse performance
- Practical relevance to real networks

---

### 7. Conclusion
- Key findings
- Limitations
- Possible extensions (RTT, ECN, real NIC tests)

---

### 8. Reproducibility
Add GitHub link:
```text
https://github.com/Amritha902/ccn-linux-qdisc-study
