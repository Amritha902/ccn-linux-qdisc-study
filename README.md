# CCN Linux Qdisc Study

Author: Amritha S  
GitHub: https://github.com/Amritha902/ccn-linux-qdisc-study  

---

## Objective
This project experimentally studies Linux queuing disciplines under TCP congestion, comparing pfifo_fast and fq_codel using tc and iperf3.

---

## System Setup
- OS: Ubuntu 24.04 LTS
- Architecture: x86_64
- Network Interface: wlp1s0

---

## Tools Installation
```bash
sudo apt update
sudo apt install -y iperf3 git gnuplot
```

---

## Phase 1 – Baseline (pfifo_fast)
```bash
sudo tc qdisc del dev wlp1s0 root 2>/dev/null
sudo tc qdisc add dev wlp1s0 root pfifo_fast
iperf3 -s
iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile logs/phase1_iperf.log
grep "^\[SUM\]" logs/phase1_iperf.log | awk '{ t++; print t "," $6 }' > logs/phase1_throughput.csv
```

---

## Phase 2 – Bottleneck Experiments
```bash
sudo tc qdisc add dev wlp1s0 root handle 1: tbf rate 1Gbit burst 32k latency 50ms
```

### Phase 2A – pfifo_fast
```bash
sudo tc qdisc add dev wlp1s0 parent 1:1 pfifo_fast
iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile logs/phase2A_iperf.log
```

### Phase 2B – fq_codel
```bash
sudo tc qdisc del dev wlp1s0 parent 1:1
sudo tc qdisc add dev wlp1s0 parent 1:1 fq_codel
iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile logs/phase2B_iperf.log
```

---

## Phase 3 – Fairness Analysis
Parallel TCP flows were used to evaluate fairness and congestion behavior.

---

## Results Summary
- pfifo_fast shows bursty drops and unstable throughput.
- fq_codel provides smoother throughput and better congestion control.

---

## Reproducibility
All logs, CSV files, and plots are available in the GitHub repository.
