#!/bin/bash

echo "Cleaning old setup..."
sudo ip netns del ns1 2>/dev/null
sudo ip netns del ns2 2>/dev/null
sudo ip link del veth1 2>/dev/null

echo "Creating namespaces..."
sudo ip netns add ns1
sudo ip netns add ns2

sudo ip link add veth1 type veth peer name veth2

sudo ip link set veth1 netns ns1
sudo ip link set veth2 netns ns2

sudo ip netns exec ns1 ip addr add 10.0.0.1/24 dev veth1
sudo ip netns exec ns2 ip addr add 10.0.0.2/24 dev veth2

sudo ip netns exec ns1 ip link set lo up
sudo ip netns exec ns2 ip link set lo up

sudo ip netns exec ns1 ip link set veth1 up
sudo ip netns exec ns2 ip link set veth2 up

echo "Applying bottleneck..."
sudo ip netns exec ns2 tc qdisc add dev veth2 root handle 1: \
tbf rate 10mbit burst 4kbit latency 50ms

sudo ip netns exec ns2 tc qdisc add dev veth2 parent 1:1 fq_codel

echo "Setup complete."

