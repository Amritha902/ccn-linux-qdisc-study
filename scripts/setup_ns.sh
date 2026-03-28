#!/bin/bash
# setup_ns.sh — ACAPE namespace testbed
# Amritha S — VIT Chennai 2026
# Run: sudo bash setup_ns.sh

echo "=== Setting up ACAPE namespace testbed ==="

# Clean
ip netns del ns1 2>/dev/null; ip netns del ns2 2>/dev/null
ip link del veth1 2>/dev/null; true
sleep 0.3

# Create namespaces
ip netns add ns1 || { echo "ERROR: ip netns add ns1 failed"; exit 1; }
ip netns add ns2 || { echo "ERROR: ip netns add ns2 failed"; exit 1; }

# Create veth pair
ip link add veth1 type veth peer name veth2
ip link set veth1 netns ns1
ip link set veth2 netns ns2

# Assign IPs
ip netns exec ns1 ip addr add 10.0.0.1/24 dev veth1
ip netns exec ns2 ip addr add 10.0.0.2/24 dev veth2

# Bring up
ip netns exec ns1 ip link set veth1 up
ip netns exec ns2 ip link set veth2 up
ip netns exec ns1 ip link set lo up
ip netns exec ns2 ip link set lo up

# TBF bottleneck (10 Mbit)
ip netns exec ns1 tc qdisc add dev veth1 root handle 1: \
    tbf rate 10mbit burst 32kbit latency 400ms

# fq_codel as child (ACAPE will tune these parameters)
ip netns exec ns1 tc qdisc add dev veth1 parent 1:1 handle 10: \
    fq_codel target 5ms interval 100ms limit 1024 quantum 1514

echo ""
echo "=== Testbed ready ==="
ip netns exec ns1 tc qdisc show dev veth1
echo ""
echo "=== Connectivity test ==="
ip netns exec ns2 ping -c 2 -W 1 10.0.0.1 && echo "✅ OK" || echo "❌ FAILED"
