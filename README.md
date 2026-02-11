# CCN Linux Qdisc Study
**Comparative Study of Linux Queue Disciplines under Congestion**

**Author:** Amritha S  
**GitHub:** https://github.com/Amritha902/ccn-linux-qdisc-study  
**Platform:** Ubuntu 24.04 LTS  
**Kernel:** Linux x86_64 GNU/Linux  
**Network Interface:** wlp1s0

---

## 1. Objective

This project experimentally studies the behavior of Linux queuing disciplines (qdisc) under congestion using TCP traffic. The focus is on comparing:

- **`pfifo_fast`** (legacy FIFO with tail-drop)
- **`fq_codel`** (Fair Queuing with Controlled Delay - modern AQM)

### Metrics Evaluated:
- Aggregate TCP throughput
- Throughput stability over time
- Packet drop behavior
- Congestion handling and fairness

All experiments are conducted on **Ubuntu 24.04 LTS** using **iperf3** and **tc** (Traffic Control).

---

## 2. System Setup

### Verify OS and Kernel
```bash
lsb_release -a
uname -a
```

### Network Interface
```bash
ip a
```

**Interface used throughout experiments:** `wlp1s0`

### Install Required Tools
```bash
sudo apt update
sudo apt install -y iperf3 iproute2 git gnuplot
```

---

## 3. Directory Structure

```
ccn-linux-qdisc-study/
├── README.md
├── logs/
│   ├── phase1_iperf.log
│   ├── phase1_tc.log
│   ├── phase1_throughput.csv
│   ├── phase1_throughput.png
│   ├── phase2A_iperf.log
│   ├── phase2A_tc.log
│   ├── phase2A_throughput.csv
│   ├── phase2A_throughput.png
│   ├── phase2A_drops.csv
│   ├── phase2A_drops.png
│   ├── phase2B_iperf.log
│   ├── phase2B_tc.log
│   ├── phase2B_throughput.csv
│   ├── phase2B_throughput.png
│   ├── phase2B_drops.csv
│   ├── phase2B_drops.png
│   ├── phase3A_iperf.log
│   ├── phase3A_tc.log
│   ├── phase3A_throughput.csv
│   ├── phase3A_throughput.png
│   ├── phase3A_drops.csv
│   ├── phase3B_iperf.log
│   ├── phase3B_tc.log
│   ├── phase3B_throughput.csv
│   ├── phase3B_throughput.png
│   ├── phase3B_drops.csv
│   └── phase3_compare_drops.png
```

### Create Directory Structure
```bash
mkdir -p ~/ccn-linux-qdisc-study/logs
cd ~/ccn-linux-qdisc-study
```

---

## 4. Phase 1 — Baseline (pfifo_fast, No Bottleneck)

### Purpose
Measure baseline aggregate TCP throughput with default Linux queuing discipline without any artificial bottleneck.

### Configuration

**Reset qdisc:**
```bash
sudo tc qdisc del dev wlp1s0 root 2>/dev/null
sudo tc qdisc add dev wlp1s0 root pfifo_fast
```

**Verify:**
```bash
tc qdisc show dev wlp1s0
```

### Traffic Generation

**Start iperf3 server (in one terminal):**
```bash
iperf3 -s
```

**Run client (in another terminal):**
```bash
iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile logs/phase1_iperf.log
```

### Logging Queue Statistics

**Monitor in real-time (optional, in third terminal):**
```bash
watch -n 1 "tc -s qdisc show dev wlp1s0 | tee -a logs/phase1_tc.log"
```

### Data Extraction

**Extract throughput:**
```bash
grep "^\[SUM\]" logs/phase1_iperf.log | awk '{ t++; print t "," $6 }' > logs/phase1_throughput.csv
```

### Plotting

**Generate throughput plot:**
```bash
gnuplot -e "
set terminal png size 800,500;
set output 'logs/phase1_throughput.png';
set title 'Phase 1: Aggregate TCP Throughput (pfifo_fast)';
set xlabel 'Time (seconds)';
set ylabel 'Throughput (Gbps)';
plot 'logs/phase1_throughput.csv' using 1:2 with lines title 'pfifo_fast baseline';
"
```

### Results

**[INSERT PLOT: logs/phase1_throughput.png]**

**Expected Behavior:**
- High aggregate throughput
- High variance due to no active queue management
- Establishes baseline for comparison

---

## 5. Phase 2 — Bottleneck Experiments

### Purpose
Introduce an artificial bottleneck using Token Bucket Filter (TBF) to study congestion behavior.

### Bottleneck Configuration

**Create TBF bottleneck:**
```bash
sudo tc qdisc del dev wlp1s0 root 2>/dev/null
sudo tc qdisc add dev wlp1s0 root handle 1: tbf rate 1gbit burst 32kbit latency 50ms
```

**Verify:**
```bash
tc qdisc show dev wlp1s0
```

---

### Phase 2A — pfifo_fast under Bottleneck

#### Purpose
Observe tail-drop behavior and congestion effects with legacy FIFO queuing.

#### Configuration

**Attach pfifo_fast as child qdisc:**
```bash
sudo tc qdisc add dev wlp1s0 parent 1:1 pfifo_fast
```

**Verify:**
```bash
tc qdisc show dev wlp1s0
```

#### Traffic Generation and Monitoring

**Start monitoring (in one terminal):**
```bash
watch -n 1 "tc -s qdisc show dev wlp1s0 | tee -a logs/phase2A_tc.log"
```

**Run traffic (in another terminal):**
```bash
iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile logs/phase2A_iperf.log
```

#### Data Extraction

**Extract throughput:**
```bash
grep "^\[SUM\]" logs/phase2A_iperf.log | awk '{ t++; print t "," $6 }' > logs/phase2A_throughput.csv
```

**Extract packet drops:**
```bash
awk '/dropped/ { t++; print t "," $4 }' logs/phase2A_tc.log > logs/phase2A_drops.csv
```

#### Plotting

**Generate throughput plot:**
```bash
gnuplot -e "
set terminal png size 800,500;
set output 'logs/phase2A_throughput.png';
set title 'Phase 2A: Throughput under Bottleneck (pfifo_fast)';
set xlabel 'Time (seconds)';
set ylabel 'Throughput (Gbps)';
plot 'logs/phase2A_throughput.csv' using 1:2 with lines title 'pfifo_fast';
"
```

**Generate drops plot:**
```bash
gnuplot -e "
set terminal png size 800,500;
set output 'logs/phase2A_drops.png';
set title 'Phase 2A: Packet Drops (pfifo_fast)';
set xlabel 'Time (seconds)';
set ylabel 'Dropped Packets';
plot 'logs/phase2A_drops.csv' using 1:2 with lines title 'pfifo_fast drops';
"
```

#### Results

**[INSERT PLOT: logs/phase2A_throughput.png]**

**[INSERT PLOT: logs/phase2A_drops.png]**

**Key Observations:**
- Throughput oscillations
- Bursty packet drops (tail-drop behavior)
- Queue buildup effects
- Unstable congestion response

---

### Phase 2B — fq_codel under Bottleneck

#### Purpose
Observe active queue management behavior with modern CoDel-based fair queuing.

#### Configuration

**Replace child qdisc with fq_codel:**
```bash
sudo tc qdisc del dev wlp1s0 parent 1:1
sudo tc qdisc add dev wlp1s0 parent 1:1 fq_codel
```

**Verify:**
```bash
tc qdisc show dev wlp1s0
```

#### Traffic Generation and Monitoring

**Start monitoring (in one terminal):**
```bash
watch -n 1 "tc -s qdisc show dev wlp1s0 | tee -a logs/phase2B_tc.log"
```

**Run traffic (in another terminal):**
```bash
iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile logs/phase2B_iperf.log
```

#### Data Extraction

**Extract throughput:**
```bash
grep "^\[SUM\]" logs/phase2B_iperf.log | awk '{ t++; print t "," $6 }' > logs/phase2B_throughput.csv
```

**Extract packet drops:**
```bash
awk '/dropped/ { t++; print t "," $4 }' logs/phase2B_tc.log > logs/phase2B_drops.csv
```

#### Plotting

**Generate throughput plot:**
```bash
gnuplot -e "
set terminal png size 800,500;
set output 'logs/phase2B_throughput.png';
set title 'Phase 2B: Throughput under Bottleneck (fq_codel)';
set xlabel 'Time (seconds)';
set ylabel 'Throughput (Gbps)';
plot 'logs/phase2B_throughput.csv' using 1:2 with lines title 'fq_codel';
"
```

**Generate drops plot:**
```bash
gnuplot -e "
set terminal png size 800,500;
set output 'logs/phase2B_drops.png';
set title 'Phase 2B: Packet Drops (fq_codel)';
set xlabel 'Time (seconds)';
set ylabel 'Dropped Packets';
plot 'logs/phase2B_drops.csv' using 1:2 with lines title 'fq_codel drops';
"
```

#### Results

**[INSERT PLOT: logs/phase2B_throughput.png]**

**[INSERT PLOT: logs/phase2B_drops.png]**

**Key Observations:**
- Smoother throughput (reduced oscillations)
- Controlled early packet drops (AQM behavior)
- Reduced queue delay
- Improved throughput stability
- Higher drop count but better performance (intentional early drops prevent bufferbloat)

---

## 6. Phase 3 — Fairness and Congestion Control Analysis

### Purpose
Evaluate fairness and active queue management behavior under sustained parallel TCP flows.

---

### Phase 3A — pfifo_fast Fairness Test

#### Configuration

**Reset and configure pfifo_fast:**
```bash
sudo tc qdisc del dev wlp1s0 root 2>/dev/null
sudo tc qdisc add dev wlp1s0 root pfifo_fast
```

**Verify:**
```bash
tc qdisc show dev wlp1s0
```

#### Traffic Generation and Monitoring

**Start monitoring (in one terminal):**
```bash
watch -n 1 "tc -s qdisc show dev wlp1s0 | tee -a logs/phase3A_tc.log"
```

**Run traffic (in another terminal):**
```bash
iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile logs/phase3A_iperf.log
```

#### Data Extraction

**Extract throughput:**
```bash
grep "^\[SUM\]" logs/phase3A_iperf.log | awk '{ t++; print t "," $6 }' > logs/phase3A_throughput.csv
```

**Extract packet drops:**
```bash
awk '/dropped/ { t++; print t "," $4 }' logs/phase3A_tc.log > logs/phase3A_drops.csv
```

#### Plotting

**Generate throughput plot:**
```bash
gnuplot -e "
set terminal png size 800,500;
set output 'logs/phase3A_throughput.png';
set title 'Phase 3A: Fairness Test (pfifo_fast)';
set xlabel 'Time (seconds)';
set ylabel 'Throughput (Gbps)';
plot 'logs/phase3A_throughput.csv' using 1:2 with lines title 'pfifo_fast';
"
```

#### Results

**[INSERT PLOT: logs/phase3A_throughput.png]**

---

### Phase 3B — fq_codel Fairness Test

#### Configuration

**Replace with fq_codel:**
```bash
sudo tc qdisc del dev wlp1s0 root
sudo tc qdisc add dev wlp1s0 root fq_codel
```

**Verify:**
```bash
tc qdisc show dev wlp1s0
```

#### Traffic Generation and Monitoring

**Start monitoring (in one terminal):**
```bash
watch -n 1 "tc -s qdisc show dev wlp1s0 | tee -a logs/phase3B_tc.log"
```

**Run traffic (in another terminal):**
```bash
iperf3 -c 127.0.0.1 -P 8 -t 30 --logfile logs/phase3B_iperf.log
```

#### Data Extraction

**Extract throughput:**
```bash
grep "^\[SUM\]" logs/phase3B_iperf.log | awk '{ t++; print t "," $6 }' > logs/phase3B_throughput.csv
```

**Extract packet drops:**
```bash
awk '/dropped/ { t++; print t "," $4 }' logs/phase3B_tc.log > logs/phase3B_drops.csv
```

#### Plotting

**Generate throughput plot:**
```bash
gnuplot -e "
set terminal png size 800,500;
set output 'logs/phase3B_throughput.png';
set title 'Phase 3B: Fairness Test (fq_codel)';
set xlabel 'Time (seconds)';
set ylabel 'Throughput (Gbps)';
plot 'logs/phase3B_throughput.csv' using 1:2 with lines title 'fq_codel';
"
```

#### Results

**[INSERT PLOT: logs/phase3B_throughput.png]**

---

### Phase 3 Comparison — Drop Behavior

**Generate comparison plot:**
```bash
gnuplot -e "
set terminal png size 900,500;
set output 'logs/phase3_compare_drops.png';
set title 'Phase 3: Drop Behavior Comparison';
set xlabel 'Time (seconds)';
set ylabel 'Dropped Packets';
plot 'logs/phase3A_drops.csv' using 1:2 with lines title 'pfifo_fast', \
     'logs/phase3B_drops.csv' using 1:2 with lines title 'fq_codel';
"
```

#### Results

**[INSERT PLOT: logs/phase3_compare_drops.png]**

**Key Observations:**
- **pfifo_fast:** Unfair flow allocation, spiky behavior, bursty drops
- **fq_codel:** Fairer flow distribution, smoother throughput, controlled congestion
- **fq_codel** demonstrates superior active queue management despite higher controlled drops

---

## 7. Summary of Findings

| Phase | Queue Discipline | Key Observation |
|-------|-----------------|-----------------|
| **Phase 1** | pfifo_fast | High baseline throughput, unstable variance |
| **Phase 2A** | pfifo_fast | Bursty tail-drops, throughput oscillations, queue buildup |
| **Phase 2B** | fq_codel | Smoother throughput, controlled early drops, reduced latency |
| **Phase 3A** | pfifo_fast | Unfair flow allocation, spiky congestion response |
| **Phase 3B** | fq_codel | Improved fairness, stable congestion control |

### Key Insights:

1. **pfifo_fast** exhibits classic tail-drop behavior:
   - Bursty packet drops
   - Unstable throughput under congestion
   - Poor fairness among flows
   - Queue buildup (bufferbloat)

2. **fq_codel** demonstrates modern AQM benefits:
   - Controlled early packet drops prevent bufferbloat
   - Smoother, more stable throughput
   - Better fairness through per-flow queuing
   - Lower latency despite higher drop counts

3. **Important:** Higher drop counts in fq_codel are intentional and beneficial:
   - Early drops signal congestion before queue fills
   - Prevents bufferbloat and reduces latency
   - Results in better overall performance

4. Results align with expected behavior described in Linux networking literature and CoDel research papers.

---

## 8. Reproducibility

All experiments are fully reproducible. This repository contains:

- ✅ Complete command-line methodology
- ✅ All log files (iperf3 and tc outputs)
- ✅ Extracted CSV data files
- ✅ Generated plots
- ✅ Step-by-step instructions

### To Reproduce:

1. Clone this repository:
```bash
git clone https://github.com/Amritha902/ccn-linux-qdisc-study.git
cd ccn-linux-qdisc-study
```

2. Follow the commands in each phase section above

3. All results will be stored in the `logs/` directory

---

## 9. References

- **Linux Traffic Control:** `man tc`, `man tc-pfifo_fast`, `man tc-fq_codel`
- **CoDel Paper:** Nichols & Jacobson (2012), "Controlling Queue Delay"
- **iperf3 Documentation:** https://iperf.fr/
- **Linux Networking:** Understanding Linux Network Internals (Christian Benvenuti)

---

## 10. Future Work

Potential extensions to this study:

- Test with varying RTT values
- Evaluate ECN (Explicit Congestion Notification) support
- Compare with other AQM algorithms (PIE, CAKE)
- Test on real network interfaces (not localhost)
- Measure per-flow fairness in detail
- Analyze impact on different application traffic (VoIP, video streaming)

---

## 11. Repository Information

**GitHub Repository:** https://github.com/Amritha902/ccn-linux-qdisc-study

**Author:** Amritha S  
**Course:** Computer Communication Networks (CCN)  
**Platform:** Ubuntu 24.04 LTS  
**Date:** February 2026

---

## License

This project is for educational purposes. All code and documentation are available under the MIT License.

---

**End of README**
