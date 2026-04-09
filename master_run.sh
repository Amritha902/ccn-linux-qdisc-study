#!/bin/bash
# master_run.sh — Heavy traffic, tight bottleneck, all 4 systems
# Topology matches Adaptive RED base paper (Floyd et al. 2001):
#   - Single bottleneck link
#   - Multiple TCP sources
#   - Controlled oversubscription
#
# Usage:
#   sudo bash master_run.sh                  # 1 hour each (4 hours total)
#   sudo bash master_run.sh --duration 3600  # same
#   sudo bash master_run.sh --quick          # 10 min each (test)

DURATION=3600   # 1 hour default per system
FLOWS=20        # 20 parallel TCP CUBIC flows (heavy load)
RATE="5mbit"    # 5 Mbit bottleneck (very tight — forces heavy congestion)
BURST="16kbit"
PORT=5202

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --duration) DURATION="$2"; shift 2;;
        --quick)    DURATION=600; shift;;
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
echo "  ACAPE Extended Experiment — 4 Systems"
echo "  Topology: Floyd et al. 2001 (Adaptive RED base paper)"
echo "============================================================"
echo "  Systems  : static_fqcodel | adaptive_red | pie | acape"
echo "  Duration : ${DURATION}s = $((DURATION/60))m each"
echo "  Total    : ~$((DURATION*4/60))m = $((DURATION*4/3600))h $((DURATION*4%3600/60))m"
echo "  Flows    : ${FLOWS} parallel TCP CUBIC"
echo "  Rate     : ${RATE} bottleneck (tight — forces congestion)"
echo "  Topology : ns2(client) → ns_router(TBF+qdisc) → ns1(server)"
echo "  Base paper: Floyd, Gummadi, Shenker 2001 — single bottleneck,"
echo "              multiple TCP sources, oversubscribed link"
echo "============================================================"
echo ""

# ── Kill everything ───────────────────────────────────────────
pkill -9 -f "iperf3"         2>/dev/null || true
pkill -9 -f "acape_v5"       2>/dev/null || true
pkill -9 -f "adaptive_red"   2>/dev/null || true
pkill -9 -f "acape_exporter" 2>/dev/null || true
pkill -9 -f "record_metrics" 2>/dev/null || true
sleep 2

# ── Router topology ───────────────────────────────────────────
sep "Router topology (Floyd 2001 single-bottleneck)"

ip netns del ns2       2>/dev/null || true
ip netns del ns_router 2>/dev/null || true
ip netns del ns1       2>/dev/null || true
ip link del veth_cr    2>/dev/null || true
ip link del veth_rs    2>/dev/null || true
sleep 1.5

ip netns add ns2
ip netns add ns_router
ip netns add ns1

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

# TBF: 5Mbit tight bottleneck
# 20 flows × average ~1Mbit each = 20Mbit injected into 5Mbit = 4:1 oversubscription
# Matches Floyd 2001 experiment design
ip netns exec ns_router tc qdisc add dev veth_rs \
    root handle 1: tbf rate ${RATE} burst ${BURST} latency 400ms

if ip netns exec ns2 ping -c 2 -W 2 192.168.2.2 &>/dev/null; then
    log "Topology ready — ${FLOWS} flows into ${RATE} = $((FLOWS))x oversubscription"
    log "Matches Floyd 2001: single bottleneck, N TCP sources"
else
    echo -e "${R}Ping failed${Z}"; exit 1
fi

# ── eBPF ─────────────────────────────────────────────────────
sep "eBPF compile + attach"
cd "$EBPF" && make clean &>/dev/null; make &>/dev/null; cd "$REPO"
if [ -f "$EBPF/tc_monitor.o" ]; then
    ip netns exec ns_router tc qdisc add dev veth_rs clsact 2>/dev/null || true
    ip netns exec ns_router tc filter del dev veth_rs egress 2>/dev/null || true
    ip netns exec ns_router tc filter add dev veth_rs egress \
        bpf direct-action obj "$EBPF/tc_monitor.o" sec tc_egress
    OUT=$(ip netns exec ns_router tc filter show dev veth_rs egress)
    PID=$(echo "$OUT" | grep -oP 'id \K[0-9]+' | head -1)
    echo "$OUT" | grep -q "jited" && log "eBPF attached prog_id=$PID JIT" || warn "eBPF attach unclear"
fi

# ── Prometheus + Grafana ──────────────────────────────────────
sep "Monitoring stack"
systemctl stop prometheus 2>/dev/null || true
rm -rf /var/lib/prometheus/* 2>/dev/null || true
systemctl start prometheus; sleep 3
systemctl start grafana-server 2>/dev/null || true; sleep 2
log "Grafana: http://localhost:3000/d/acape2026/acape-live-monitor"

# ── Phase runner ──────────────────────────────────────────────
run_phase() {
    local SYSTEM=$1
    sep "PHASE: ${SYSTEM^^}  ($((DURATION/60))m)"

    # Start exporter with correct label
    pkill -9 -f "acape_exporter" 2>/dev/null || true; sleep 1
    python3 "$SCRIPTS/acape_exporter_v2.py" \
        --ns ns_router --iface veth_rs \
        --controller "$SYSTEM" \
        >> "$LOGS/exporter_${SYSTEM}.log" 2>&1 &
    sleep 2

    # Apply qdisc
    ip netns exec ns_router tc qdisc del dev veth_rs parent 1:1 2>/dev/null || true
    sleep 0.5
    case $SYSTEM in
        static_fqcodel)
            ip netns exec ns_router tc qdisc add dev veth_rs \
                parent 1:1 handle 10: fq_codel \
                target 5ms interval 100ms limit 1024 quantum 1514
            log "static fq_codel: ALL params fixed (no adaptation)"
            ;;
        adaptive_red)
            ip netns exec ns_router tc qdisc add dev veth_rs \
                parent 1:1 handle 10: fq_codel \
                target 5ms interval 100ms limit 1024 quantum 1514
            log "Adaptive RED: tunes target only (like Floyd 2001 tunes max_p)"
            ;;
        pie)
            modprobe sch_pie 2>/dev/null || true
            ip netns exec ns_router tc qdisc add dev veth_rs \
                parent 1:1 handle 10: pie \
                target 15ms limit 1000 tupdate 30ms
            log "PIE: control-theoretic AQM, target=15ms"
            ;;
        acape)
            ip netns exec ns_router tc qdisc add dev veth_rs \
                parent 1:1 handle 10: fq_codel \
                target 5ms interval 100ms limit 1024 quantum 1514
            log "ACAPE: will tune all 4 params via gradient+AIMD"
            ;;
    esac
    sleep 2

    log "Queue at start:"
    ip netns exec ns_router tc -s qdisc show dev veth_rs | grep -E "fq_codel|pie|backlog" | head -4

    # Start iperf server
    ip netns exec ns1 iperf3 -s -p $PORT \
        > "$LOGS/${SYSTEM}_iperf_srv.log" 2>&1 &
    SRV_PID=$!
    sleep 2

    # Start recorder → CSV
    python3 "$SCRIPTS/record_metrics.py" \
        --ns ns_router --iface veth_rs \
        --label "$SYSTEM" \
        --duration $((DURATION + 60)) \
        > "$LOGS/${SYSTEM}_recorder.log" 2>&1 &
    REC_PID=$!
    log "Recording → logs/${SYSTEM}_recorded.csv"

    # Start controller
    CTRL_PID=""
    if [ "$SYSTEM" = "adaptive_red" ] && [ -f "$SCRIPTS/adaptive_red.py" ]; then
        python3 "$SCRIPTS/adaptive_red.py" \
            --ns ns_router --iface veth_rs \
            --logdir "$LOGS" \
            --duration $((DURATION+60)) \
            > "$LOGS/ared_ctrl.log" 2>&1 &
        CTRL_PID=$!; sleep 3
        log "Adaptive RED controller running"
    elif [ "$SYSTEM" = "acape" ] && [ -f "$SCRIPTS/acape_v5.py" ]; then
        python3 "$SCRIPTS/acape_v5.py" \
            --ns ns_router --iface veth_rs \
            --logdir "$LOGS" \
            > "$LOGS/acape_ctrl.log" 2>&1 &
        CTRL_PID=$!; sleep 3
        log "ACAPE controller running"
    fi

    # Start traffic — 20 TCP CUBIC flows
    TS=$(date +%H%M%S)
    ip netns exec ns2 iperf3 \
        -c 192.168.2.2 -p $PORT \
        -P $FLOWS -t $DURATION -i 10 -J \
        --logfile "$LOGS/${SYSTEM}_iperf_${TS}.json" \
        >> "$LOGS/${SYSTEM}_iperf.log" 2>&1 &
    TRAF_PID=$!
    log "${FLOWS}x TCP CUBIC running for $((DURATION/60))m"
    log ">>> SCREENSHOT GRAFANA NOW — ${SYSTEM} start <<<"

    # Status every 30s
    T0=$(date +%s)
    while true; do
        NOW=$(date +%s); EL=$((NOW-T0)); REM=$((DURATION-EL))
        [ $REM -le 0 ] && break
        kill -0 $TRAF_PID 2>/dev/null || { log "Traffic done"; break; }
        TC=$(ip netns exec ns_router tc -s qdisc show dev veth_rs 2>/dev/null)
        BL=$(echo "$TC" | grep -oP 'backlog \d+b \K\d+(?=p)' || echo "?")
        TGT_US=$(echo "$TC" | grep -oP 'target \K\d+(?=us)' || echo "")
        [ -n "$TGT_US" ] && TGT="$(echo "scale=2;$TGT_US/1000"|bc)ms" || TGT="5ms"
        CSV_ROWS=$(wc -l < "$LOGS/${SYSTEM}_recorded.csv" 2>/dev/null || echo 0)
        printf "\r  [%s] %dm%ds rem=%dm | bl=%sp tgt=%s rows=%s     " \
            "$SYSTEM" "$((EL/60))" "$((EL%60))" "$((REM/60))" "$BL" "$TGT" "$CSV_ROWS"
        sleep 30
    done
    echo ""

    # Compute results
    JFILE=$(ls -t "$LOGS/${SYSTEM}_iperf_"*.json 2>/dev/null | head -1)
    [ -n "$JFILE" ] && python3 << PYEOF
import json, os
try:
    d = json.load(open("$JFILE"))
    streams = d["end"]["streams"]
    rates = [s["sender"]["bits_per_second"]/1e6 for s in streams]
    total = sum(rates); n = len(rates)
    jain = sum(rates)**2 / (n * sum(r**2 for r in rates))
    retx = sum(s["sender"].get("retransmits",0) for s in streams)
    print(f"\n  Results: ${SYSTEM}")
    print(f"    Total throughput : {total:.2f} Mbps")
    print(f"    Per-flow average : {total/n:.3f} Mbps")
    print(f"    Jain fairness    : {jain:.4f}")
    print(f"    Retransmits      : {retx}")
    summary = {"system":"${SYSTEM}","total_mbps":round(total,2),
               "per_flow_mbps":round(total/n,3),
               "jain":round(jain,4),"retransmits":retx,"flows":n}
    json.dump(summary, open("$LOGS/summary_${SYSTEM}.json","w"), indent=2)
except Exception as e: print(f"  Parse error: {e}")
PYEOF

    CSV="$LOGS/${SYSTEM}_recorded.csv"
    [ -f "$CSV" ] && log "CSV: $(wc -l < "$CSV") rows → $CSV" || warn "No CSV"

    # Stop phase
    kill $TRAF_PID $SRV_PID $REC_PID 2>/dev/null || true
    [ -n "$CTRL_PID" ] && kill $CTRL_PID 2>/dev/null || true
    pkill -9 -f "acape_v5"     2>/dev/null || true
    pkill -9 -f "adaptive_red" 2>/dev/null || true
    pkill -9 -f "iperf3"       2>/dev/null || true
    sleep 5

    log ">>> SCREENSHOT GRAFANA NOW — ${SYSTEM} end <<<"
    log "Phase ${SYSTEM} complete"
}

# ══════════════════════════════════════════════════════════════
# RUN ALL 4 SYSTEMS
# ══════════════════════════════════════════════════════════════
run_phase "static_fqcodel"
log "30s gap between systems..."; sleep 30

run_phase "adaptive_red"
log "30s gap..."; sleep 30

run_phase "pie"
log "30s gap..."; sleep 30

run_phase "acape"

# ══════════════════════════════════════════════════════════════
# PLOT
# ══════════════════════════════════════════════════════════════
sep "Generating all comparison plots"
pip install matplotlib numpy --break-system-packages -q 2>/dev/null || true
chown -R $(logname):$(logname) "$LOGS" "$PLOTS" 2>/dev/null || true

if [ -f "$SCRIPTS/plot_all_systems.py" ]; then
    python3 "$SCRIPTS/plot_all_systems.py" \
        --logdir "$LOGS" \
        --plotdir "$PLOTS"
fi

sep "ALL DONE"
echo ""
echo "  CSV files saved:"
ls -lh "$LOGS"/*_recorded.csv 2>/dev/null
echo ""
echo "  Throughput summary:"
for f in "$LOGS"/summary_*.json; do
    [ -f "$f" ] && python3 -c "
import json; d=json.load(open('$f'))
print('  '+d['system']+': '+str(d['total_mbps'])+'Mbps Jain='+str(d['jain']))
"
done
echo ""
echo "  Plots: $PLOTS/"
ls "$PLOTS"/comparison_*.png 2>/dev/null | xargs -I{} basename {}
echo ""
TS=$(date +%Y%m%d_%H%M)
log "Push results:"
echo "  cd $REPO && git add -A && git commit -m 'Extended_$TS' && git push"
