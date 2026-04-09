#!/bin/bash
# master_run.sh — Full experiment. One command.
# Runs: static_fqcodel → adaptive_red → acape
# Saves CSV per system, plots comparison at end.
#
# Usage:
#   sudo bash master_run.sh              # 30 min each (90 min total)
#   sudo bash master_run.sh --duration 300   # 5 min each (quick test)

DURATION=1800   # 30 min default
FLOWS=8
RATE="10mbit"
PORT=5202

# Parse args
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --duration) DURATION="$2"; shift 2;;
        --quick)    DURATION=300;  shift;;
        *) echo "Unknown: $1"; exit 1;;
    esac
done

REPO="$(cd "$(dirname "$0")"; pwd)"
LOGS="$REPO/logs"
PLOTS="$REPO/plots"
SCRIPTS="$REPO/scripts"
EBPF="$REPO/ebpf"
mkdir -p "$LOGS" "$PLOTS"

G='\033[0;32m'; Y='\033[0;33m'; R='\033[0;31m'
P='\033[0;35m'; Z='\033[0m'; B='\033[1m'
log()  { echo -e "${G}${B}[$(date +%H:%M:%S)]${Z} $1"; }
warn() { echo -e "${Y}[WARN]${Z} $1"; }
sep()  { echo -e "\n${P}${B}$(printf '=%.0s' {1..60})\n  $1\n$(printf '=%.0s' {1..60})${Z}"; }

if [ "$EUID" -ne 0 ]; then echo "Run: sudo bash master_run.sh"; exit 1; fi

echo ""
echo "============================================================"
echo "  ACAPE Master Run — All 3 Systems"
echo "============================================================"
echo "  1. static_fqcodel  (${DURATION}s = $((DURATION/60))m)"
echo "  2. adaptive_red    (${DURATION}s = $((DURATION/60))m)"
echo "  3. acape           (${DURATION}s = $((DURATION/60))m)"
echo "  Total: ~$((DURATION*3/60))m"
echo "  Topology: ns2 → ns_router (TBF+qdisc) → ns1"
echo "  TCP: CUBIC, ${FLOWS} parallel, ${RATE} bottleneck"
echo "============================================================"
echo ""

# ══════════════════════════════════════════════════════════════
# STEP 1 — Setup router topology (done ONCE, reused for all 3)
# ══════════════════════════════════════════════════════════════
sep "Step 1: Router topology setup"

# Kill any leftovers
pkill -9 -f "iperf3"        2>/dev/null || true
pkill -9 -f "acape_v5"      2>/dev/null || true
pkill -9 -f "adaptive_red"  2>/dev/null || true
pkill -9 -f "acape_exporter" 2>/dev/null || true
pkill -9 -f "record_metrics" 2>/dev/null || true
sleep 2

# Tear down old namespaces
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

# Client ↔ Router
ip link add veth_cr type veth peer name veth_rc
ip link set veth_cr netns ns2
ip link set veth_rc netns ns_router

# Router ↔ Server
ip link add veth_rs type veth peer name veth_sr
ip link set veth_rs netns ns_router
ip link set veth_sr netns ns1

# IPs
ip netns exec ns2       ip addr add 192.168.1.2/24 dev veth_cr
ip netns exec ns_router ip addr add 192.168.1.1/24 dev veth_rc
ip netns exec ns_router ip addr add 192.168.2.1/24 dev veth_rs
ip netns exec ns1       ip addr add 192.168.2.2/24 dev veth_sr

# Bring up all
for ns_if in "ns2 veth_cr" "ns_router veth_rc" \
             "ns_router veth_rs" "ns1 veth_sr" \
             "ns2 lo" "ns_router lo" "ns1 lo"; do
    ns=$(echo $ns_if | awk '{print $1}')
    ifc=$(echo $ns_if | awk '{print $2}')
    ip netns exec $ns ip link set $ifc up
done

# Forwarding + routes
ip netns exec ns_router sysctl -w net.ipv4.ip_forward=1 -q
ip netns exec ns2 ip route add 192.168.2.0/24 via 192.168.1.1
ip netns exec ns1 ip route add 192.168.1.0/24 via 192.168.2.1

# TBF bottleneck on router egress
ip netns exec ns_router tc qdisc add dev veth_rs \
    root handle 1: tbf rate ${RATE} burst 32kbit latency 400ms

# Verify
if ip netns exec ns2 ping -c 2 -W 2 192.168.2.2 &>/dev/null; then
    log "Topology ready: ns2(192.168.1.2) → ns_router → ns1(192.168.2.2)"
else
    echo -e "${R}Topology ping failed. Exiting.${Z}"; exit 1
fi

# ══════════════════════════════════════════════════════════════
# STEP 2 — Compile + attach eBPF (done ONCE)
# ══════════════════════════════════════════════════════════════
sep "Step 2: eBPF compile + attach"
cd "$EBPF" && make clean &>/dev/null; make &>/dev/null; cd "$REPO"
if [ -f "$EBPF/tc_monitor.o" ]; then
    ip netns exec ns_router tc qdisc add dev veth_rs clsact 2>/dev/null || true
    ip netns exec ns_router tc filter del dev veth_rs egress 2>/dev/null || true
    ip netns exec ns_router tc filter add dev veth_rs egress \
        bpf direct-action obj "$EBPF/tc_monitor.o" sec tc_egress
    OUT=$(ip netns exec ns_router tc filter show dev veth_rs egress)
    if echo "$OUT" | grep -q "jited"; then
        PID=$(echo "$OUT" | grep -oP 'id \K[0-9]+' | head -1)
        log "eBPF attached — prog_id=$PID JIT compiled"
    fi
else
    warn "eBPF compile failed — tc-only mode"
fi

# ══════════════════════════════════════════════════════════════
# STEP 3 — Start monitoring (Prometheus + Grafana + Exporter)
# ══════════════════════════════════════════════════════════════
sep "Step 3: Start monitoring"

# Wipe old Prometheus data so no old series remain
systemctl stop prometheus 2>/dev/null || true
rm -rf /var/lib/prometheus/* 2>/dev/null || true
systemctl start prometheus
sleep 3

systemctl start grafana-server 2>/dev/null || true
sleep 2

# Start exporter (updates controller label per phase)
pkill -9 -f "acape_exporter" 2>/dev/null || true; sleep 1
python3 "$SCRIPTS/acape_exporter_v2.py" \
    --ns ns_router --iface veth_rs \
    --controller "static_fqcodel" \
    >> "$LOGS/exporter.log" 2>&1 &
EXPORTER_PID=$!
sleep 2

# Verify exporter working
METRICS=$(curl -s http://localhost:9101/metrics 2>/dev/null | grep "^acape_target_ms " | head -1)
if [ -n "$METRICS" ]; then
    log "Exporter OK: $METRICS"
else
    warn "Exporter may not be responding yet — continuing"
fi

log "Grafana: http://localhost:3000/d/acape2026/acape-live-monitor"

# ══════════════════════════════════════════════════════════════
# FUNCTION: run one phase
# ══════════════════════════════════════════════════════════════
run_phase() {
    local SYSTEM=$1
    local LABEL=$2   # for CSV filename

    sep "PHASE: ${SYSTEM^^}  (${DURATION}s = $((DURATION/60))m)"

    # Update exporter label
    pkill -9 -f "acape_exporter" 2>/dev/null || true; sleep 1
    python3 "$SCRIPTS/acape_exporter_v2.py" \
        --ns ns_router --iface veth_rs \
        --controller "$SYSTEM" \
        >> "$LOGS/exporter_${SYSTEM}.log" 2>&1 &
    EXPORTER_PID=$!
    sleep 2

    # Apply qdisc
    ip netns exec ns_router tc qdisc del dev veth_rs parent 1:1 2>/dev/null || true
    sleep 0.5
    case $SYSTEM in
        static_fqcodel)
            ip netns exec ns_router tc qdisc add dev veth_rs \
                parent 1:1 handle 10: fq_codel \
                target 5ms interval 100ms limit 1024 quantum 1514
            log "Applied: static fq_codel (parameters FIXED, never change)"
            ;;
        adaptive_red)
            ip netns exec ns_router tc qdisc add dev veth_rs \
                parent 1:1 handle 10: fq_codel \
                target 5ms interval 100ms limit 1024 quantum 1514
            log "Applied: fq_codel base — Adaptive RED controller will tune target"
            ;;
        acape)
            ip netns exec ns_router tc qdisc add dev veth_rs \
                parent 1:1 handle 10: fq_codel \
                target 5ms interval 100ms limit 1024 quantum 1514
            log "Applied: fq_codel base — ACAPE will tune all 4 parameters"
            ;;
    esac
    sleep 2

    # Show qdisc
    log "Queue state at start:"
    ip netns exec ns_router tc -s qdisc show dev veth_rs | grep -E "fq_codel|tbf|backlog" | head -6

    # Start iperf server
    ip netns exec ns1 iperf3 -s -p $PORT \
        > "$LOGS/${SYSTEM}_iperf_srv.log" 2>&1 &
    SRV_PID=$!
    sleep 2

    # Start recorder
    python3 "$SCRIPTS/record_metrics.py" \
        --ns ns_router --iface veth_rs \
        --label "$SYSTEM" \
        --duration $((DURATION + 30)) \
        > "$LOGS/${SYSTEM}_recorder.log" 2>&1 &
    REC_PID=$!
    log "Recorder started → logs/${SYSTEM}_recorded.csv"

    # Start controller
    CTRL_PID=""
    if [ "$SYSTEM" = "adaptive_red" ] && [ -f "$SCRIPTS/adaptive_red.py" ]; then
        python3 "$SCRIPTS/adaptive_red.py" \
            --ns ns_router --iface veth_rs \
            --logdir "$LOGS" \
            --duration $((DURATION + 60)) \
            > "$LOGS/ared_ctrl.log" 2>&1 &
        CTRL_PID=$!
        log "Adaptive RED controller started (PID=$CTRL_PID)"
        sleep 3
    elif [ "$SYSTEM" = "acape" ] && [ -f "$SCRIPTS/acape_v5.py" ]; then
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
        -P $FLOWS -t $DURATION -i 5 -J \
        --logfile "$LOGS/${SYSTEM}_iperf_${TS}.json" \
        >> "$LOGS/${SYSTEM}_iperf.log" 2>&1 &
    TRAF_PID=$!
    log "Traffic running — ${FLOWS}×TCP CUBIC for ${DURATION}s"
    log ">>> TAKE GRAFANA SCREENSHOT NOW (start of ${SYSTEM}) <<<"

    # Live status
    T0=$(date +%s)
    while true; do
        NOW=$(date +%s); EL=$((NOW-T0)); REM=$((DURATION-EL))
        [ $REM -le 0 ] && break
        kill -0 $TRAF_PID 2>/dev/null || { log "Traffic done early"; break; }
        TC=$(ip netns exec ns_router tc -s qdisc show dev veth_rs 2>/dev/null)
        BL=$(echo "$TC" | grep -oP 'backlog \d+b \K\d+(?=p)' || echo "?")
        TGT_US=$(echo "$TC" | grep -oP 'target \K\d+(?=us)' || echo "")
        if [ -n "$TGT_US" ]; then
            TGT=$(echo "scale=2; $TGT_US/1000" | bc)ms
        else
            TGT=$(echo "$TC" | grep -oP 'target \K\d+(?=ms)' || echo "5")ms
        fi
        printf "\r  [%s] t=%ds rem=%ds | backlog=%sp target=%s     " \
            "$SYSTEM" "$EL" "$REM" "$BL" "$TGT"
        sleep 5
    done
    echo ""

    # Compute average throughput from iperf JSON
    JFILE=$(ls -t "$LOGS/${SYSTEM}_iperf_"*.json 2>/dev/null | head -1)
    if [ -n "$JFILE" ]; then
        python3 << PYEOF
import json, sys
try:
    d = json.load(open("$JFILE"))
    streams = d["end"]["streams"]
    rates = [s["sender"]["bits_per_second"]/1e6 for s in streams]
    total = sum(rates); n = len(rates)
    jain = sum(rates)**2 / (n * sum(r**2 for r in rates))
    retx = sum(s["sender"].get("retransmits",0) for s in streams)
    print(f"\n  ┌─ Results: ${SYSTEM}")
    print(f"  │  Avg throughput : {total:.3f} Mbps")
    print(f"  │  Per-flow avg   : {total/n:.3f} Mbps")
    print(f"  │  Jain fairness  : {jain:.4f}")
    print(f"  │  Retransmits    : {retx}")
    print(f"  └─ Saved: $JFILE")
    import os, json as j2
    summary = {"system":"${SYSTEM}","total_mbps":round(total,3),
               "per_flow_mbps":round(total/n,3),"jain":round(jain,4),
               "retransmits":retx}
    j2.dump(summary, open("$LOGS/summary_${SYSTEM}.json","w"), indent=2)
except Exception as e:
    print(f"  Could not parse iperf JSON: {e}")
PYEOF
    fi

    # Verify CSV
    CSV="$LOGS/${SYSTEM}_recorded.csv"
    if [ -f "$CSV" ]; then
        ROWS=$(wc -l < "$CSV")
        log "CSV saved: $CSV ($((ROWS-1)) data rows)"
    else
        warn "No CSV found at $CSV"
    fi

    # Stop phase processes
    kill $TRAF_PID $SRV_PID $REC_PID 2>/dev/null || true
    [ -n "$CTRL_PID" ] && kill $CTRL_PID 2>/dev/null || true
    pkill -9 -f "acape_v5"      2>/dev/null || true
    pkill -9 -f "adaptive_red"  2>/dev/null || true
    pkill -9 -f "iperf3"        2>/dev/null || true
    sleep 3

    log "Phase ${SYSTEM} complete"
    log ">>> TAKE FINAL GRAFANA SCREENSHOT NOW <<<"
}

# ══════════════════════════════════════════════════════════════
# STEP 4 — Run all 3 phases
# ══════════════════════════════════════════════════════════════
run_phase "static_fqcodel"
echo ""
log "Pausing 20s before next phase (visible gap in Grafana)..."
sleep 20

run_phase "adaptive_red"
echo ""
log "Pausing 20s before next phase..."
sleep 20

run_phase "acape"

# ══════════════════════════════════════════════════════════════
# STEP 5 — Plot all 3 systems
# ══════════════════════════════════════════════════════════════
sep "Step 5: Generating comparison plots"
pip install matplotlib numpy --break-system-packages -q 2>/dev/null || true

if [ -f "$SCRIPTS/plot_all_systems.py" ]; then
    python3 "$SCRIPTS/plot_all_systems.py" \
        --logdir "$LOGS" \
        --plotdir "$PLOTS"
    echo ""
    log "Plots saved:"
    ls -lh "$PLOTS"/comparison_*.png 2>/dev/null || echo "  (check $PLOTS)"
else
    warn "plot_all_systems.py not found in scripts/"
fi

# ══════════════════════════════════════════════════════════════
# DONE
# ══════════════════════════════════════════════════════════════
sep "ALL DONE"
echo ""
log "Logs  : $LOGS"
log "Plots : $PLOTS"
echo ""
echo "  CSV files:"
ls -lh "$LOGS"/*_recorded.csv 2>/dev/null
echo ""
echo "  Summaries:"
for f in "$LOGS"/summary_*.json; do
    [ -f "$f" ] && python3 -c "import json; d=json.load(open('$f')); print('  '+d['system']+': '+str(d['total_mbps'])+'Mbps Jain='+str(d['jain']))"
done
echo ""
TS=$(date +%Y%m%d_%H%M)
log "Git:"
echo "  cd $REPO && git add -A && git commit -m 'Results_$TS' && git push"
