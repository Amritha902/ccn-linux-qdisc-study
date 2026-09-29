#!/usr/bin/env bash
# ACAPE testbed — three-node router topology (corrected).
#
# WHY THIS REPLACES THE TWO-NODE SETUP
# ------------------------------------
# The original README (Parts 2-4) attached the bottleneck to veth1 root INSIDE
# ns1 and then ran `iperf3 -c 10.0.0.1` FROM ns2. Data therefore flowed
# ns2 -> ns1, but an egress qdisc on veth1 shapes only ns1 -> ns2 -- the
# ACKNOWLEDGEMENT direction. Measured on that topology:
#
#     ns2 -> ns1, 8 flows : 9,777 Mbps        (unshaped)
#     tc on veth1         : 284,379 pkt @ 66 bytes/pkt  (pure TCP ACKs)
#     eBPF size histogram : 341,243 pkts <128B vs 2 pkts in 512-1500B
#
# Every backlog/drop figure from that topology is a measurement of ACK
# queueing, which is why drop rates of 100,000-138,000/s were logged on a link
# whose physical packet rate is 826/s.
#
# Here the AQM sits on the ROUTER's egress toward the server, so the bottleneck
# is on the data path:
#
#     ns_client ---- veth_cr/veth_rc ---- ns_router ---- veth_rs/veth_sr ---- ns_server
#      192.168.1.2                      .1.1     .2.1                     192.168.2.2
#                                                 |
#                                        [ TBF shaper + AQM ]  <-- data path
#
set -euo pipefail

RATE_MBIT="${RATE_MBIT:-10}"
AQM="${AQM:-fq_codel}"
AQM_ARGS="${AQM_ARGS:-target 5ms interval 100ms limit 1024 quantum 1514}"
BASE_RTT_MS="${BASE_RTT_MS:-20}"     # one-way netem delay on each side
BURST="${BURST:-32kbit}"
LATENCY="${LATENCY:-400ms}"

say() { printf '  %s\n' "$*"; }

teardown() {
    for ns in ns_client ns_router ns_server; do
        ip netns del "$ns" 2>/dev/null || true
    done
    ip link del veth_cr 2>/dev/null || true
    ip link del veth_rs 2>/dev/null || true
}

setup() {
    teardown
    ip netns add ns_client
    ip netns add ns_router
    ip netns add ns_server

    ip link add veth_cr type veth peer name veth_rc
    ip link set veth_cr netns ns_client
    ip link set veth_rc netns ns_router

    ip link add veth_rs type veth peer name veth_sr
    ip link set veth_rs netns ns_router
    ip link set veth_sr netns ns_server

    ip netns exec ns_client ip addr add 192.168.1.2/24 dev veth_cr
    ip netns exec ns_router ip addr add 192.168.1.1/24 dev veth_rc
    ip netns exec ns_router ip addr add 192.168.2.1/24 dev veth_rs
    ip netns exec ns_server ip addr add 192.168.2.2/24 dev veth_sr

    ip netns exec ns_client ip link set veth_cr up
    ip netns exec ns_router ip link set veth_rc up
    ip netns exec ns_router ip link set veth_rs up
    ip netns exec ns_server ip link set veth_sr up
    for ns in ns_client ns_router ns_server; do
        ip netns exec "$ns" ip link set lo up
    done

    ip netns exec ns_router sysctl -qw net.ipv4.ip_forward=1
    ip netns exec ns_client ip route add 192.168.2.0/24 via 192.168.1.1
    ip netns exec ns_server ip route add 192.168.1.0/24 via 192.168.2.1

    # Propagation delay, split across the two hops, so RTT is realistic.
    local half=$(( BASE_RTT_MS / 2 ))
    if [ "$half" -gt 0 ]; then
        ip netns exec ns_client tc qdisc add dev veth_cr root netem delay "${half}ms"
        ip netns exec ns_server tc qdisc add dev veth_sr root netem delay "${half}ms"
    fi

    apply_aqm
}

apply_aqm() {
    ip netns exec ns_router tc qdisc del dev veth_rs root 2>/dev/null || true
    # TBF shaper as root: enforces the bottleneck rate deterministically.
    ip netns exec ns_router tc qdisc add dev veth_rs root handle 1: \
        tbf rate "${RATE_MBIT}mbit" burst "$BURST" latency "$LATENCY"
    # AQM as the child: this is the discipline under study.
    # shellcheck disable=SC2086
    ip netns exec ns_router tc qdisc add dev veth_rs parent 1:1 handle 10: \
        "$AQM" $AQM_ARGS
}

verify() {
    say "kernel: $(uname -r)"
    say "AQM under test: $AQM $AQM_ARGS"
    echo
    say "--- router egress qdisc (the bottleneck, on the DATA path) ---"
    ip netns exec ns_router tc -s qdisc show dev veth_rs
    echo
    say "--- connectivity client -> server ---"
    ip netns exec ns_client ping -c 3 -q 192.168.2.2
}

case "${1:-setup}" in
    setup)    setup; verify ;;
    verify)   verify ;;
    aqm)      apply_aqm ;;
    teardown) teardown; say "testbed removed" ;;
    *) echo "usage: $0 {setup|verify|aqm|teardown}" >&2; exit 2 ;;
esac
