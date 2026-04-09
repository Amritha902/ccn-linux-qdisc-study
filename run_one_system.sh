#!/bin/bash
# run_one_system.sh — Run ONE algorithm for 30 min, save everything
# Usage: sudo bash run_one_system.sh <system> [duration]
# system: static_fqcodel | adaptive_red | pie | cake | acape
#
# Example:
#   sudo bash run_one_system.sh static_fqcodel 1800
#   sudo bash run_one_system.sh adaptive_red 1800
#   sudo bash run_one_system.sh pie 1800
#   sudo bash run_one_system.sh cake 1800
#   sudo bash run_one_system.sh acape 1800

SYSTEM=${1:-acape}
DURATION=${2:-1800}  # 30 min default
FLOWS=8
RATE="10mbit"        # tight bottleneck
PORT=5202

REPO="$(cd "$(dirname "$0")"; pwd)"
LOGS="$REPO/logs"
PLOTS="$REPO/plots"
SCRIPTS="$REPO/scripts"
EBPF="$REPO/ebpf"
mkdir -p "$LOGS" "$PLOTS"

G='\033[0;32m'; Y='\033[0;33m'; R='\033[0;31m'
C='\033[0;36m'; Z='\033[0m'; B='\033[1m'
log()  { echo -e "${G}${B}[$(date +%H:%M:%S)]${Z} $1"; }
warn() { echo -e "${Y}[WARN]${Z} $1"; }
sep()  { echo -e "\n${C}${B}$(printf '=%.0s' {1..58})\n  $1\n$(printf '=%.0s' {1..58})${Z}"; }

if [ "$EUID" -ne 0 ]; then echo "Need sudo"; exit 1; fi

# ── Cleanup ───────────────────────────────────────────────────
cleanup() {
    log "Stopping all processes..." 
    kill $TRAF_PID $SRV_PID $REC_PID $CTRL_PID $EXP_PID 2>/dev/null || true
    pkill -9 -f "iperf3"         2>/dev/null || true
    pkill -9 -f "acape_v5"       2>/dev/null || true
    pkill -9 -f "adaptive_red.py" 2>/dev/null || true
    pkill -9 -f "record_metrics" 2>/dev/null || true
    sleep 2
}
trap cleanup EXIT

echo ""
sep "ACAPE Experiment: ${SYSTEM^^}  (${DURATION}s = $((DURATION/60))m)"
echo "  Flows     : ${FLOWS} parallel TCP CUBIC"
echo "  Rate      : ${RATE} bottleneck (very tight)"
echo "  Topology  : ns2 -> ns_router (TBF+qdisc) -> ns1"
echo ""

# ── Topology ──────────────────────────────────────────────────
sep "Setting up router topology"
pkill -9 -f "iperf3" 2>/dev/null || true
pkill -9 -f "acape_v5" 2>/dev/null || true
pkill -9 -f "adaptive_red" 2>/dev/null || true
sleep 2

ip netns del ns2       2>/dev/null || true
ip netns del ns_router 2>/dev/null || true
ip netns del ns1       2>/dev/null || true
ip link del veth_cr    2>/dev/null || true
ip link del veth_rs    2>/dev/null || true
sleep 1.5

ip netns add ns2; ip netns add ns_router; ip netns add ns1

ip link add veth_cr type veth peer name veth_rc
ip link set veth_cr netns ns2
ip link set veth_rc netns ns_router

ip link add veth_rs type veth peer name veth_sr
ip link set veth_rs netns ns_router
ip link set veth_sr netns ns1

ip netns exec ns2       ip addr add 192.168.1.2/24 dev veth_cr
ip netns exec ns_router ip addr add 192.168.1.1/24 dev veth_rc
ip netns exec ns_router ip addr add 192.168.2.1/24 dev veth_rs
ip netns exec ns1       ip addr add 192.168.2.2/24 dev veth_sr

for ns_if in "ns2 veth_cr" "ns_router veth_rc" \
             "ns_router veth_rs" "ns1 veth_sr" \
             "ns2 lo" "ns_router lo" "ns1 lo"; do
    ns=$(echo $ns_if | awk '{print $1}')
    ifc=$(echo $ns_if | awk '{print $2}')
    ip netns exec $ns ip link set $ifc up
done

ip netns exec ns_router sysctl -w net.ipv4.ip_forward=1 -q
ip netns exec ns2 ip route add 192.168.2.0/24 via 192.168.1.1
ip netns exec ns1 ip route add 192.168.1.0/24 via 192.168.2.1

# TBF bottleneck — tight 10mbit
ip netns exec ns_router tc qdisc add dev veth_rs \
    root handle 1: tbf rate ${RATE} burst 32kbit latency 400ms

if ip netns exec ns2 ping -c 2 -W 2 192.168.2.2 &>/dev/null; then
    log "Router topology ready: 192.168.1.2 -> ns_router -> 192.168.2.2"
else
    echo -e "${R}Ping failed${Z}"; exit 1
fi

# ── eBPF ─────────────────────────────────────────────────────
sep "Compiling + attaching eBPF"
cd "$EBPF" && make clean &>/dev/null; make &>/dev/null; cd "$REPO"
if [ -f "$EBPF/tc_monitor.o" ]; then
    ip netns exec ns_router tc qdisc add dev veth_rs clsact 2>/dev/null || true
    ip netns exec ns_router tc filter del dev veth_rs egress 2>/dev/null || true
    ip netns exec ns_router tc filter add dev veth_rs egress \
        bpf direct-action obj "$EBPF/tc_monitor.o" sec tc_egress
    OUT=$(ip netns exec ns_router tc filter show dev veth_rs egress)
    PID=$(echo "$OUT" | grep -oP 'id \K[0-9]+' | head -1)
    if echo "$OUT" | grep -q "jited"; then
        log "eBPF attached — prog_id=$PID JIT compiled"
    fi
fi

# ── Apply qdisc ───────────────────────────────────────────────
sep "Applying qdisc: $SYSTEM"
ip netns exec ns_router tc qdisc del dev veth_rs parent 1:1 2>/dev/null || true
sleep 0.5

case $SYSTEM in
    static_fqcodel)
        ip netns exec ns_router tc qdisc add dev veth_rs \
            parent 1:1 handle 10: fq_codel \
            target 5ms interval 100ms limit 1024 quantum 1514
        log "Static fq_codel: target=5ms limit=1024 quantum=1514 (FIXED — never changes)"
        ;;
    adaptive_red)
        ip netns exec ns_router tc qdisc add dev veth_rs \
            parent 1:1 handle 10: fq_codel \
            target 5ms interval 100ms limit 1024 quantum 1514
        log "fq_codel base ready for Adaptive RED controller"
        ;;
    pie)
        modprobe sch_pie 2>/dev/null || true
        ip netns exec ns_router tc qdisc add dev veth_rs \
            parent 1:1 handle 10: pie \
            target 15ms limit 1000 tupdate 30ms
        log "PIE: target=15ms limit=1000 tupdate=30ms"
        ;;
    cake)
        modprobe sch_cake 2>/dev/null || true
        ip netns exec ns_router tc qdisc add dev veth_rs \
            parent 1:1 handle 10: cake \
            bandwidth ${RATE} diffserv4 flowblind nat wash
        log "CAKE: bandwidth=${RATE} diffserv4 flowblind"
        ;;
    acape)
        ip netns exec ns_router tc qdisc add dev veth_rs \
            parent 1:1 handle 10: fq_codel \
            target 5ms interval 100ms limit 1024 quantum 1514
        log "fq_codel base ready for ACAPE controller"
        ;;
esac
sleep 2
ip netns exec ns_router tc -s qdisc show dev veth_rs

# ── Start exporter (Prometheus/Grafana) ───────────────────────
sep "Starting monitoring"
systemctl start prometheus 2>/dev/null || true
systemctl start grafana-server 2>/dev/null || true
sleep 1
pkill -9 -f "acape_exporter" 2>/dev/null || true
sleep 1
if [ -f "$SCRIPTS/acape_exporter_v2.py" ]; then
    python3 "$SCRIPTS/acape_exporter_v2.py" \
        --ns ns_router --iface veth_rs \
        --controller "$SYSTEM" \
        >> "$LOGS/exporter_${SYSTEM}.log" 2>&1 &
    EXP_PID=$!
    log "Exporter PID=$EXP_PID controller=$SYSTEM"
fi
sleep 2
log "Grafana: http://localhost:3000/d/acape2026/acape-live-monitor"
log "Metrics: curl -s http://localhost:9101/metrics | grep acape_backlog"

# ── Start iperf server ────────────────────────────────────────
sep "Starting traffic: ${FLOWS} TCP CUBIC flows"
ip netns exec ns1 iperf3 -s -p $PORT \
    > "$LOGS/${SYSTEM}_iperf_srv.log" 2>&1 &
SRV_PID=$!
sleep 2

# ── Start recorder (every 1 second to CSV) ───────────────────
python3 "$SCRIPTS/record_metrics.py" \
    --ns ns_router --iface veth_rs \
    --label "$SYSTEM" \
    --duration $((DURATION + 60)) \
    > "$LOGS/${SYSTEM}_recorder.log" 2>&1 &
REC_PID=$!
log "Recorder PID=$REC_PID -> logs/${SYSTEM}_recorded.csv"
sleep 1

# ── Start controller if needed ────────────────────────────────
CTRL_PID=""
if [ "$SYSTEM" = "adaptive_red" ] && [ -f "$SCRIPTS/adaptive_red.py" ]; then
    python3 "$SCRIPTS/adaptive_red.py" \
        --ns ns_router --iface veth_rs \
        --logdir "$LOGS" \
        --duration $((DURATION + 60)) \
        > "$LOGS/ared_ctrl.log" 2>&1 &
    CTRL_PID=$!
    log "Adaptive RED controller PID=$CTRL_PID"
    sleep 3
elif [ "$SYSTEM" = "acape" ] && [ -f "$SCRIPTS/acape_v5.py" ]; then
    python3 "$SCRIPTS/acape_v5.py" \
        --ns ns_router --iface veth_rs \
        --logdir "$LOGS" \
        > "$LOGS/acape_ctrl.log" 2>&1 &
    CTRL_PID=$!
    log "ACAPE controller PID=$CTRL_PID"
    sleep 3
fi

# ── Start traffic ─────────────────────────────────────────────
TS=$(date +%H%M%S)
ip netns exec ns2 iperf3 \
    -c 192.168.2.2 -p $PORT \
    -P $FLOWS -t $DURATION -i 5 -J \
    --logfile "$LOGS/${SYSTEM}_iperf_${TS}.json" \
    >> "$LOGS/${SYSTEM}_iperf.log" 2>&1 &
TRAF_PID=$!
log "Traffic started PID=$TRAF_PID — ${FLOWS}×TCP CUBIC for ${DURATION}s"
log "TAKE GRAFANA SCREENSHOT NOW at start of run!"

# ── Live status loop ──────────────────────────────────────────
sep "Running — status every 10s"
T0=$(date +%s)
PREV_DROPS=0
TOTAL_TP=0
TP_COUNT=0
while true; do
    NOW=$(date +%s)
    ELAPSED=$(( NOW - T0 ))
    REMAIN=$(( DURATION - ELAPSED ))
    [ $REMAIN -le 0 ] && break
    kill -0 $TRAF_PID 2>/dev/null || { log "Traffic done"; break; }

    TC=$(ip netns exec ns_router tc -s qdisc show dev veth_rs 2>/dev/null)
    BL=$(echo  "$TC" | grep -oP 'backlog \d+b \K\d+(?=p)' | head -1 || echo "?")
    TGT=$(echo "$TC" | grep -oP 'target \K\d+(?=us)' | head -1)
    DR=$(echo  "$TC" | grep -oP 'dropped \K\d+' | head -1 || echo "?")
    SNT=$(echo "$TC" | grep -oP 'Sent \K\d+ bytes' | head -1 | awk '{print $1}' || echo "0")

    [ -n "$TGT" ] && TGT_MS=$(echo "scale=2; $TGT/1000" | bc) || TGT_MS="5.00"

    printf "\r  [%s] t=%ds rem=%ds | bl=%sp tgt=%sms drops=%s" \
        "$SYSTEM" "$ELAPSED" "$REMAIN" "$BL" "$TGT_MS" "$DR"
    sleep 10
done
echo ""

# ── Compute average throughput ────────────────────────────────
sep "Computing average throughput"
JFILE=$(ls -t "$LOGS/${SYSTEM}_iperf_"*.json 2>/dev/null | head -1)
if [ -n "$JFILE" ]; then
    python3 - "$JFILE" "$SYSTEM" << 'PYEOF'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    streams = d["end"]["streams"]
    total = sum(s["sender"]["bits_per_second"] for s in streams) / 1e6
    rates = [s["sender"]["bits_per_second"]/1e6 for s in streams]
    n = len(rates)
    jain = sum(rates)**2 / (n * sum(r**2 for r in rates))
    retrans = sum(s["sender"].get("retransmits",0) for s in streams)
    print(f"\n  System          : {sys.argv[2]}")
    print(f"  Total throughput: {total:.3f} Mbps")
    print(f"  Per-flow avg    : {total/n:.3f} Mbps")
    print(f"  Jain fairness   : {jain:.4f}")
    print(f"  Retransmits     : {retrans}")
    print(f"  Flows           : {n}")
    # Save summary
    import os
    logdir = os.path.dirname(sys.argv[1])
    summary = {"system":sys.argv[2],"total_mbps":round(total,3),
                "per_flow_mbps":round(total/n,3),"jain":round(jain,4),
                "retransmits":retrans,"n_flows":n}
    with open(os.path.join(logdir, f"summary_{sys.argv[2]}.json"),"w") as f:
        import json; json.dump(summary,f,indent=2)
    print(f"  Saved: logs/summary_{sys.argv[2]}.json")
except Exception as e:
    print(f"  Could not parse: {e}")
PYEOF
fi

# ── Check CSV ─────────────────────────────────────────────────
CSV="$LOGS/${SYSTEM}_recorded.csv"
if [ -f "$CSV" ]; then
    ROWS=$(wc -l < "$CSV")
    log "CSV: $CSV ($((ROWS-1)) rows)"
    log "Columns: $(head -1 "$CSV")"
    log "Last row: $(tail -1 "$CSV")"
else
    warn "No CSV found at $CSV"
fi

sep "DONE: $SYSTEM"
log "Now run the next system OR plot results:"
echo "  Next: sudo bash run_one_system.sh adaptive_red 1800"
echo "  Plot: python3 scripts/plot_all_systems.py --logdir \$(pwd)/logs --plotdir \$(pwd)/plots"
