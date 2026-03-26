#!/bin/bash
# setup_ns.sh — clean veth + TBF + fq_codel testbed
set -e

NS1="ns1"; NS2="ns2"
V1="veth1"; V2="veth2"
IP1="10.0.0.1"; IP2="10.0.0.2"

echo "[1/5] Cleaning previous setup..."
sudo ip netns del $NS1 2>/dev/null || true
sudo ip netns del $NS2 2>/dev/null || true

echo "[2/5] Creating namespaces..."
sudo ip netns add $NS1
sudo ip netns add $NS2

echo "[3/5] Creating veth pair..."
sudo ip link add $V1 type veth peer name $V2
sudo ip link set $V1 netns $NS1
sudo ip link set $V2 netns $NS2

echo "[4/5] Assigning IPs..."
sudo ip netns exec $NS1 ip addr add ${IP1}/24 dev $V1
sudo ip netns exec $NS2 ip addr add ${IP2}/24 dev $V2
sudo ip netns exec $NS1 ip link set $V1 up
sudo ip netns exec $NS2 ip link set $V2 up
sudo ip netns exec $NS1 ip link set lo up
sudo ip netns exec $NS2 ip link set lo up

echo "[5/5] Applying TBF bottleneck + fq_codel on ns1/veth1..."
sudo ip netns exec $NS1 tc qdisc del dev $V1 root 2>/dev/null || true
sudo ip netns exec $NS1 tc qdisc add dev $V1 root handle 1: \
    tbf rate 10mbit burst 32kbit latency 400ms
sudo ip netns exec $NS1 tc qdisc add dev $V1 parent 1:1 handle 10: \
    fq_codel target 5ms interval 100ms limit 1024

echo ""
echo "=== Testbed ready ==="
sudo ip netns exec $NS1 tc qdisc show dev $V1
echo ""
echo "Verify connectivity:"
sudo ip netns exec $NS2 ping -c 2 $IP1
