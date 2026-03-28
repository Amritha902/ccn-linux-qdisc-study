#!/bin/bash
# run_part3.sh
# Runs the FULL Part 3 experiment: setup → load → controller → plot
# Usage: sudo bash run_part3.sh
# --------------------------------------------------------------
# This script runs the controller for 90 seconds alongside
# high congestion traffic, then plots everything automatically.
# --------------------------------------------------------------

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOGDIR="$SCRIPT_DIR/../logs"
mkdir -p "$LOGDIR"

echo "============================================="
echo "  Part 3: Adaptive fq_codel Controller"
echo "  Amritha S — VIT Chennai 2026"
echo "============================================="

# Step 1: Setup namespace
echo ""
echo "[Step 1/4] Setting up namespace testbed..."
bash "$SCRIPT_DIR/setup_ns.sh"
sleep 2

# Step 2: Start iperf3 server in ns1
echo ""
echo "[Step 2/4] Starting iperf3 server in ns1..."
sudo ip netns exec ns1 iperf3 -s --daemon \
    --logfile "$LOGDIR/iperf_server.log"
sleep 1

# Step 3: Start iperf3 client (8 flows, 90s) in background
IPERF_LOG="$LOGDIR/iperf_$(date +%Y%m%d_%H%M%S).log"
echo "[Step 3/4] Starting traffic: 8 TCP flows × 90s → $IPERF_LOG"
sudo ip netns exec ns2 iperf3 \
    -c 10.0.0.1 -P 8 -t 90 -i 1 \
    --logfile "$IPERF_LOG" &
IPERF_PID=$!
sleep 2

# Step 4: Run adaptive controller for 85s
echo "[Step 4/4] Starting adaptive controller (85s)..."
echo "  Watch the STATE column change as congestion evolves."
echo ""
sudo timeout 85 python3 "$SCRIPT_DIR/controller.py" \
    --ns ns1 --iface veth1 \
    --logdir "$LOGDIR" \
    --interval 0.5 || true

wait $IPERF_PID 2>/dev/null || true

echo ""
echo "============================================="
echo "  Experiment complete. Generating plots..."
echo "============================================="
cd "$SCRIPT_DIR"
python3 plot_part3.py

echo ""
echo "Done. Plots saved to ../plots/"
ls -lh ../plots/*.png 2>/dev/null
