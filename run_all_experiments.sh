#!/bin/bash
# =============================================================
# run_all_experiments.sh — Runs all 5 systems on router topology
# Records metrics to CSV, plots everything at the end.
#
# Usage:
#   sudo bash run_all_experiments.sh            # 10 min each (50 min total)
#   sudo bash run_all_experiments.sh --quick    # 5 min each (25 min total)
#   sudo bash run_all_experiments.sh --systems "static_fqcodel acape"
# =============================================================

set -e
REPO="$(cd "$(dirname "$0")"; pwd)"
LOGS="$REPO/logs"
PLOTS="$REPO/plots"
SCRIPTS="$REPO/scripts"
EBPF="$REPO/ebpf"

# ── Defaults ──────────────────────────────────────────────────
DURATION=600
SYSTEMS="static_fqcodel adaptive_red pie cake acape"
PORT=5202
FLOWS=8
RATE="10mbit"

# Parse args
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --quick)    DURATION=300; shift;;
        --duration) DURATION="$2"; shift 2;;
        --systems)  SYSTEMS="$2"; shift 2;;
        *) echo "Unknown: $1"; exit 1;;
    esac
done

G='\033[0;32m'; Y='\033[0;33m'; R='\033[0;31m'
C='\033[0;36m'; Z='\033[0m'; B='\033[1m'
log()  { echo -e "${G}${B}[$(date +%H:%M:%S)]${Z} $1"; }
warn() { echo -e "${Y}[WARN]${Z} $1"; }
sep()  { echo -e "\n${C}${B}$(printf '=%.0s' {1..60})\n  $1\n$(printf '=%.0s' {1..60})${Z}"; }

# ── Preflight ─────────────────────────────────────────────────
if [ "$EUID" -ne 0 ]; then
    echo "Run: sudo bash run_all_experiments.sh"; exit 1
fi
mkdir -p "$LOGS" "$PLOTS"

# Install deps
pip install matplotlib numpy --break-system-packages -q 2>/dev/null || true
modprobe sch_cake 2>/dev/null && log "CAKE module: ok" || warn "CAKE may not be available"
modprobe sch_pie  2>/dev/null && log "PIE module: ok"  || warn "PIE may not be available"

echo ""
echo "============================================================"
echo "  ACAPE 5-System Comparison — Router Topology"
echo "============================================================"
echo "  Systems  : $SYSTEMS"
echo "  Duration : ${DURATION}s each (~$((DURATION/60))m)"
echo "  Total    : ~$(( $(echo $SYSTEMS | wc -w) * DURATION / 60 ))m"
echo "  TCP      : CUBIC, ${FLOWS} parallel flows, ${RATE} bottleneck"
echo "  Platform : Ubuntu 24.04 LTS, Linux $(uname -r)"
echo "============================================================"
echo ""

# ── Cleanup helper ────────────────────────────────────────────
cleanup_procs() {
    pkill -9 -f "iperf3" 2>/dev/null || true
    pkill -9 -f "acape_v5" 2>/dev/null || true
    pkill -9 -f "adaptive_red" 2>/dev/null || true
    pkill -9 -f "record_metrics" 2>/dev/null || true
    sleep 2
}

# ── Topology setup ────────────────────────────────────────────
setup_topology() {
    sep "Setting up router topology"
    cleanup_procs

    # Tear down any existing namespaces
    ip netns del ns2       2>/dev/null || true
    ip netns del ns_router 2>/dev/null || true
    ip netns del ns1       2>/dev/null || true
    ip link del veth_cr    2>/dev/null || true
    ip link del veth_rs    2>/dev/null || true
    sleep 1.5

    # Create namespaces
    ip netns add ns2
    ip netns add ns_router
    ip netns add ns1

    # Client <-> Router
    ip link add veth_cr type veth peer name veth_rc
    ip link set veth_cr netns ns2
    ip link set veth_rc netns ns_router

    # Router <-> Server
    ip link add veth_rs type veth peer name veth_sr
    ip link set veth_rs netns ns_router
    ip link set veth_sr netns ns1

    # IP addresses
    ip netns exec ns2       ip addr add 192.168.1.2/24 dev veth_cr
    ip netns exec ns_router ip addr add 192.168.1.1/24 dev veth_rc
    ip netns exec ns_router ip addr add 192.168.2.1/24 dev veth_rs
    ip netns exec ns1       ip addr add 192.168.2.2/24 dev veth_sr

    # Bring up all interfaces
    for ns_if in "ns2 veth_cr" "ns_router veth_rc" \
                 "ns_router veth_rs" "ns1 veth_sr" \
                 "ns2 lo" "ns_router lo" "ns1 lo"; do
        ns=$(echo $ns_if | awk '{print $1}')
        if=$(echo $ns_if | awk '{print $2}')
        ip netns exec $ns ip link set $if up
    done

    # Enable forwarding
    ip netns exec ns_router sysctl -w net.ipv4.ip_forward=1 -q

    # Static routes
    ip netns exec ns2 ip route add 192.168.2.0/24 via 192.168.1.1
    ip netns exec ns1 ip route add 192.168.1.0/24 via 192.168.2.1

    # TBF bottleneck on router egress
    ip netns exec ns_router tc qdisc add dev veth_rs \
        root handle 1: tbf rate ${RATE} burst 32kbit latency 400ms

    # Test connectivity
    if ip netns exec ns2 ping -c 2 -W 2 192.168.2.2 &>/dev/null; then
        log "Router topology ready: ns2(192.168.1.2) -> ns_router -> ns1(192.168.2.2)"
    else
        echo -e "${R}Ping failed — topology broken${Z}"; exit 1
    fi
}

# ── eBPF attach ───────────────────────────────────────────────
attach_ebpf() {
    sep "Compiling + attaching eBPF"
    cd "$EBPF"
    make clean &>/dev/null
    if make &>/dev/null && [ -f "$EBPF/tc_monitor.o" ]; then
        ip netns exec ns_router tc qdisc add dev veth_rs clsact 2>/dev/null || true
        ip netns exec ns_router tc filter del dev veth_rs egress 2>/dev/null || true
        ip netns exec ns_router tc filter add dev veth_rs egress \
            bpf direct-action obj "$EBPF/tc_monitor.o" sec tc_egress
        OUT=$(ip netns exec ns_router tc filter show dev veth_rs egress)
        PID=$(echo "$OUT" | grep -oP 'id \K[0-9]+' | head -1)
        if echo "$OUT" | grep -q "jited"; then
            log "eBPF attached — prog_id=$PID, JIT compiled"
        else
            warn "eBPF attach unclear"
        fi
    else
        warn "eBPF compile failed — tc-only mode"
    fi
    cd "$REPO"
}

# ── Start monitoring ──────────────────────────────────────────
start_monitoring() {
    local ctrl=$1
    systemctl start prometheus 2>/dev/null || true
    systemctl start grafana-server 2>/dev/null || true
    sleep 1
    if [ -f "$SCRIPTS/acape_exporter_v2.py" ]; then
        python3 "$SCRIPTS/acape_exporter_v2.py" \
            --ns ns_router --iface veth_rs \
            --controller "$ctrl" \
            >> "$LOGS/exporter_${ctrl}.log" 2>&1 &
        log "Exporter started: controller=$ctrl"
        log "Dashboard: http://localhost:3000/d/acape2026/acape-live-monitor"
    fi
    sleep 2
}

# ── Apply qdisc for each system ───────────────────────────────
apply_qdisc() {
    local system=$1
    # Remove existing child qdisc
    ip netns exec ns_router tc qdisc del dev veth_rs parent 1:1 2>/dev/null || true
    sleep 0.5

    case $system in
        static_fqcodel)
            ip netns exec ns_router tc qdisc add dev veth_rs \
                parent 1:1 handle 10: fq_codel \
                target 5ms interval 100ms limit 1024 quantum 1514
            log "Applied: static fq_codel (target=5ms limit=1024 quantum=1514)"
            ;;
        adaptive_red)
            ip netns exec ns_router tc qdisc add dev veth_rs \
                parent 1:1 handle 10: fq_codel \
                target 5ms interval 100ms limit 1024 quantum 1514
            log "Applied: fq_codel for Adaptive RED controller to tune"
            ;;
        pie)
            ip netns exec ns_router tc qdisc add dev veth_rs \
                parent 1:1 handle 10: pie \
                target 15ms limit 1000 tupdate 30ms
            log "Applied: PIE (target=15ms limit=1000)"
            ;;
        cake)
            ip netns exec ns_router tc qdisc add dev veth_rs \
                parent 1:1 handle 10: cake \
                bandwidth ${RATE} diffserv4 flowblind nat wash
            log "Applied: CAKE (bandwidth=${RATE})"
            ;;
        acape)
            ip netns exec ns_router tc qdisc add dev veth_rs \
                parent 1:1 handle 10: fq_codel \
                target 5ms interval 100ms limit 1024 quantum 1514
            log "Applied: fq_codel for ACAPE controller to tune"
            ;;
    esac

    # Show applied qdisc
    log "Queue state:"
    ip netns exec ns_router tc -s qdisc show dev veth_rs | head -8
    sleep 2
}

# ── Run one system ────────────────────────────────────────────
run_system() {
    local system=$1
    sep "RUNNING: ${system^^}  (${DURATION}s)"

    apply_qdisc "$system"

    # Start iperf server
    ip netns exec ns1 iperf3 -s -p $PORT \
        > "$LOGS/${system}_iperf_srv.log" 2>&1 &
    SRV_PID=$!
    sleep 2

    # Start recorder (saves to logs/{system}_recorded.csv)
    python3 "$SCRIPTS/record_metrics.py" \
        --ns ns_router --iface veth_rs \
        --label "$system" \
        --duration $((DURATION + 30)) \
        > "$LOGS/${system}_recorder.log" 2>&1 &
    REC_PID=$!
    sleep 1

    # Start controller if needed
    CTRL_PID=""
    if [ "$system" = "adaptive_red" ] && [ -f "$SCRIPTS/adaptive_red.py" ]; then
        python3 "$SCRIPTS/adaptive_red.py" \
            --ns ns_router --iface veth_rs \
            --logdir "$LOGS" \
            --duration $((DURATION + 30)) \
            > "$LOGS/ared_ctrl.log" 2>&1 &
        CTRL_PID=$!
        log "Adaptive RED controller started (PID=$CTRL_PID)"
        sleep 3
    elif [ "$system" = "acape" ] && [ -f "$SCRIPTS/acape_v5.py" ]; then
        python3 "$SCRIPTS/acape_v5.py" \
            --ns ns_router --iface veth_rs \
            --logdir "$LOGS" \
            > "$LOGS/acape_ctrl.log" 2>&1 &
        CTRL_PID=$!
        log "ACAPE controller started (PID=$CTRL_PID)"
        sleep 3
    fi

    # Start traffic
    TS=$(date +%H%M%S)
    ip netns exec ns2 iperf3 \
        -c 192.168.2.2 -p $PORT \
        -P $FLOWS -t $DURATION -i 1 -J \
        --logfile "$LOGS/${system}_iperf_${TS}.json" \
        > "$LOGS/${system}_iperf.log" 2>&1 &
    TRAF_PID=$!
    log "Traffic started: 8×TCP CUBIC, ${DURATION}s"

    # Wait with live status
    T0=$(date +%s)
    while true; do
        ELAPSED=$(( $(date +%s) - T0 ))
        REMAIN=$(( DURATION - ELAPSED ))
        [ $REMAIN -le 0 ] && break
        kill -0 $TRAF_PID 2>/dev/null || { log "Traffic ended early"; break; }

        # Read live stats
        TC_OUT=$(ip netns exec ns_router tc -s qdisc show dev veth_rs 2>/dev/null)
        BL=$(echo "$TC_OUT" | grep -oP 'backlog \d+b \K\d+(?=p)' | head -1)
        TGT=$(echo "$TC_OUT" | grep -oP 'target \K\d+(?=us|ms)' | head -1)
        printf "\r  [${system}] t=${ELAPSED}s rem=${REMAIN}s  bl=${BL:-?}p  tgt=${TGT:-?}   "
        sleep 5
    done
    echo ""
    log "${system} traffic phase complete"

    # Kill all phase processes
    for pid in $TRAF_PID $CTRL_PID $SRV_PID $REC_PID; do
        [ -n "$pid" ] && kill $pid 2>/dev/null || true
    done
    pkill -9 -f "acape_v5" 2>/dev/null || true
    pkill -9 -f "adaptive_red.py" 2>/dev/null || true
    sleep 3

    # Verify CSV was written
    CSV="$LOGS/${system}_recorded.csv"
    if [ -f "$CSV" ]; then
        ROWS=$(wc -l < "$CSV")
        log "Recorded $((ROWS-1)) ticks -> $CSV"
    else
        warn "No CSV recorded for $system"
    fi
}

# ── Run Jain fairness test ────────────────────────────────────
run_jain_test() {
    local system=$1
    log "Running Jain fairness test for $system (30s)..."
    apply_qdisc "$system"

    ip netns exec ns1 iperf3 -s -p $PORT > "$LOGS/jain_srv.log" 2>&1 &
    SRV=$!; sleep 2

    TS=$(date +%H%M%S)
    ip netns exec ns2 iperf3 \
        -c 192.168.2.2 -p $PORT \
        -P $FLOWS -t 30 -J \
        --logfile "$LOGS/fairness_${system}_${TS}.json" \
        > "$LOGS/jain_${system}.log" 2>&1

    kill $SRV 2>/dev/null || true
    sleep 2

    # Compute Jain index
    JFILE=$(ls -t "$LOGS"/fairness_${system}_*.json 2>/dev/null | head -1)
    if [ -n "$JFILE" ]; then
        python3 - "$JFILE" "$system" << 'EOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    rates = [s["sender"]["bits_per_second"]/1e6 for s in d["end"]["streams"]]
    n = len(rates)
    j = sum(rates)**2 / (n * sum(r**2 for r in rates))
    print(f"  Jain({sys.argv[2]}) = {j:.4f}  total={sum(rates):.2f}Mbps  flows={n}")
except Exception as e:
    print(f"  Could not compute Jain: {e}")
EOF
    fi
}

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
setup_topology
attach_ebpf

# Start monitoring (exporter + grafana)
start_monitoring "static_fqcodel"

# Run each system
for system in $SYSTEMS; do
    run_system "$system"

    # Kill old exporter, start new one with correct label
    pkill -9 -f "acape_exporter" 2>/dev/null || true
    sleep 2
    python3 "$SCRIPTS/acape_exporter_v2.py" \
        --ns ns_router --iface veth_rs \
        --controller "$system" \
        >> "$LOGS/exporter_${system}.log" 2>&1 &
    sleep 1

    echo ""
    log "Pause 15s between systems (visible boundary in Grafana)..."
    sleep 15
done

# Jain fairness tests
sep "Jain Fairness Tests — All Systems"
for system in $SYSTEMS; do
    run_jain_test "$system"
done

# ── Generate plots ─────────────────────────────────────────────
sep "Generating all comparison plots"
python3 "$SCRIPTS/plot_all_systems.py" \
    --logdir "$LOGS" \
    --plotdir "$PLOTS"

# ── Final summary ─────────────────────────────────────────────
sep "ALL DONE"
echo ""
log "Logs:  $LOGS"
log "Plots: $PLOTS"
echo ""
echo "CSV files recorded:"
ls -lh "$LOGS"/*_recorded.csv 2>/dev/null || echo "  (none found)"
echo ""
echo "Plots generated:"
ls -lh "$PLOTS"/comparison_*.png 2>/dev/null || echo "  (none found)"
echo ""
TS=$(date +%Y%m%d_%H%M)
log "Git push:"
echo "  cd $REPO && git add -A && git commit -m 'AllSystems_${TS}' && git push"
echo ""
log "Grafana screenshots to capture:"
echo "  1. comparison_all_params.png    — 9-panel all parameters"
echo "  2. comparison_summary_bars.png  — average metrics bars"
echo "  3. comparison_key_result.png    — backlog + target side by side"
echo "  4. comparison_latency_cdf.png   — latency CDF"
echo "  5. comparison_feature_matrix.png— feature table"
