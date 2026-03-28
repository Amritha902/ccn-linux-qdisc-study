# ACAPE: Complete Implementation Guide
# Amritha S — VIT Chennai 2026
# ═══════════════════════════════════════════════════════

## STEP 0 — Copy files into your repo
mkdir -p ~/ccn-linux-qdisc-study/ebpf
cp acape_controller.py  ~/ccn-linux-qdisc-study/scripts/
cp plot_acape.py        ~/ccn-linux-qdisc-study/scripts/
cp setup_ns.sh          ~/ccn-linux-qdisc-study/scripts/
cp tc_monitor.c         ~/ccn-linux-qdisc-study/ebpf/
cp Makefile             ~/ccn-linux-qdisc-study/ebpf/
chmod +x ~/ccn-linux-qdisc-study/scripts/setup_ns.sh

## STEP 1 — Install dependencies (once)
sudo apt install -y clang llvm libbpf-dev \
    linux-headers-$(uname -r) \
    python3-bpfcc bpfcc-tools \
    iperf3 iproute2
pip3 install matplotlib numpy --break-system-packages

## STEP 2 — Build eBPF program
cd ~/ccn-linux-qdisc-study/ebpf
make clean
make
# Must print: ✅ Built: tc_monitor.o

## STEP 3 — Setup namespace testbed
cd ~/ccn-linux-qdisc-study/scripts
sudo bash setup_ns.sh
# Must show: ✅ OK (ping succeeds)

## STEP 4 — Attach eBPF to veth1
cd ~/ccn-linux-qdisc-study/ebpf
make attach
# Must show: filter protocol all pref ... bpf ...

## STEP 5 — Run experiment (4 terminals)

### Terminal 1: iperf3 server
sudo ip netns exec ns1 iperf3 -s

### Terminal 2: Traffic generator (wait for server to start)
cd ~/ccn-linux-qdisc-study
sudo ip netns exec ns2 iperf3 \
    -c 10.0.0.1 -P 8 -t 120 -i 1 \
    --logfile logs/iperf_acape_$(date +%H%M%S).log

### Terminal 3: ACAPE controller (start AFTER traffic is running)
cd ~/ccn-linux-qdisc-study/scripts
sudo python3 acape_controller.py \
    --ns ns1 --iface veth1 --logdir ../logs

### Terminal 4: Watch live queue stats (optional)
watch -n 0.5 'sudo ip netns exec ns1 tc -s qdisc show dev veth1'

## STEP 6 — Generate plots (after controller stops with Ctrl+C)
cd ~/ccn-linux-qdisc-study/scripts
python3 plot_acape.py
# Generates:
#   ../plots/acape_overview.png        ← main 6-panel result figure
#   ../plots/acape_gradients.png       ← novel gradient signals
#   ../plots/acape_vs_part3.png        ← comparison with Part 3
#   ../plots/acape_adjustments.png     ← AIMD log table

## STEP 7 — Detach eBPF
cd ~/ccn-linux-qdisc-study/ebpf
make detach

## STEP 8 — Git push
cd ~/ccn-linux-qdisc-study
git add scripts/ ebpf/ logs/ plots/
git commit -m "ACAPE: Predictive multi-signal adaptive fq_codel controller
- Novel 1: Multi-signal gradient state estimator (dr+bl+rtt gradients)
- Novel 2: Predictive regime detection (acts BEFORE state transition)
- Novel 3: eBPF workload-aware parameter profiles (elephant/mice)
- Novel 4: Three-timescale architecture (eBPF/100ms/5s)
- Zero kernel modification — stock Linux only"
git push origin main

## ═══════════════════════════════════════════════════════
## WHAT TO LOOK FOR IN THE TERMINAL OUTPUT
## ═══════════════════════════════════════════════════════
##
## t(s)   regime   trajectory  predicted    dr/s  bl   RTT  flows  eleph  wkld  tgt  lim  adj
## ──────────────────────────────────────────────────────────────────────────────────────────
##  0.5   HEAVY    WORSENING   HEAVY      4500   450  0.5ms     0      0  MIXED  5.0ms 1024   0
##  1.0   HEAVY    WORSENING   HEAVY      5200   460  0.6ms     8      2  MIXED  5.0ms 1024   0
##  5.0   HEAVY    WORSENING   HEAVY      4800   430  0.7ms    16      5  MIXED  4.5ms  921   1  ← adj
## 10.0   HEAVY    STABLE      HEAVY      4200   380  0.8ms    20      8  MIXED  4.0ms  829   2
## 40.0   HEAVY    RECOVERING  MODERATE   2100   180  0.5ms    22      3  MIXED  2.0ms  420   7
## 70.0   NORMAL   RECOVERING  NORMAL        0     0  0.2ms     0      0  MIXED  2.5ms  484   8
##
## KEY THINGS TO SEE:
## 1. trajectory column shows WORSENING → STABLE → RECOVERING
## 2. predicted column sometimes LEADS regime (that's the novel element)
## 3. [PREDICTIVE] tag in adjustment table = acted before state changed
## 4. workload changes MICE/MIXED/ELEPHANT as flows change
## 5. quantum column changes with workload (novel — no prior work does this)

## ═══════════════════════════════════════════════════════
## HOW TO FRAME THIS IN YOUR PAPER
## ═══════════════════════════════════════════════════════
##
## Title: "ACAPE: Adaptive Condition-Aware Packet Scheduling for
##         Linux fq_codel via Multi-Signal Predictive Control"
##
## Contribution 1 (Section III-A):
##   Multi-signal state vector S(t) = [dr(t), ∇dr, bl(t), ∇bl, rtt(t), ∇rtt]
##   Linear regression over sliding window → gradient estimation
##   Predictive regime classification using gradient direction
##   → "We detect imminent congestion BEFORE loss occurs"
##
## Contribution 2 (Section III-B):
##   eBPF TC hook classifies flows into elephant/mice by byte volume
##   elephant_ratio = elephant_flows / active_flows (from BPF maps)
##   Selects one of 3 parameter profiles per workload regime
##   → "First system to select fq_codel profiles based on live flow-size distribution"
##
## Contribution 3 (Section III-C):
##   T1 (eBPF, ~ns): per-packet telemetry in-kernel
##   T2 (100ms): gradient estimation + regime prediction
##   T3 (5s): AIMD parameter adjustment + profile switching
##   → "Principled three-timescale architecture (Borkar 1997)"
##
## Baselines to compare against (Section V):
##   1. Static fq_codel (5ms/100ms defaults) — your Part 2
##   2. Reactive AIMD only (Part 3)
##   3. ACAPE (this, Part 4)
##
## Metrics:
##   - Average backlog (lower = better)
##   - P99 RTT (lower = better)
##   - Throughput (higher = better, must not collapse)
##   - Adjustment count (efficiency)
##   - Time-to-detection of congestion transition
##   - Jain's fairness index
