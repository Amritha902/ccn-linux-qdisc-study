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
