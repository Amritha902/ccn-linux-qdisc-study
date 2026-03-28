#!/bin/bash
# setup_ns.sh — ACAPE namespace testbed
# Creates ns1 (server+bottleneck) ↔ ns2 (client)
set -e
echo "=== ACAPE Namespace Testbed Setup ==="
sudo ip netns del ns1 2>/dev/null; sudo ip netns del ns2 2>/dev/null
sudo ip link del veth1 2>/dev/null; true
sudo ip netns add ns1; sudo ip netns add ns2
sudo ip link add veth1 type veth peer name veth2
sudo ip link set veth1 netns ns1; sudo ip link set veth2 netns ns2
sudo ip netns exec ns1 ip addr add 10.0.0.1/24 dev veth1
sudo ip netns exec ns2 ip addr add 10.0.0.2/24 dev veth2
sudo ip netns exec ns1 ip link set veth1 up; sudo ip netns exec ns2 ip link set veth2 up
sudo ip netns exec ns1 ip link set lo up;    sudo ip netns exec ns2 ip link set lo up
sudo ip netns exec ns1 tc qdisc del dev veth1 root 2>/dev/null; true
# TBF bottleneck at 10 Mbit
sudo ip netns exec ns1 tc qdisc add dev veth1 root handle 1: \
    tbf rate 10mbit burst 32kbit latency 400ms
# fq_codel as child — default params (ACAPE will tune these)
sudo ip netns exec ns1 tc qdisc add dev veth1 parent 1:1 handle 10: \
    fq_codel target 5ms interval 100ms limit 1024 quantum 1514
echo "=== Setup complete ==="
sudo ip netns exec ns1 tc qdisc show dev veth1
echo "--- Connectivity test ---"
sudo ip netns exec ns2 ping -c 2 10.0.0.1 && echo "✅ OK" || echo "❌ FAIL"
