#!/bin/bash
# run_acape_final.sh
# Enters ns1 via nsenter so BCC attaches eBPF to the RIGHT namespace
# Amritha S — VIT Chennai 2026

NS_PATH="/var/run/netns/ns1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOGDIR="$SCRIPT_DIR/../logs"

if [ ! -f "$NS_PATH" ]; then
    echo "ERROR: ns1 not found. Run setup_ns.sh first."
    exit 1
fi

echo "Entering ns1 via nsenter — BCC will attach to ns1's veth1"
exec sudo nsenter --net="$NS_PATH" -- \
    python3 "$SCRIPT_DIR/acape_controller_ns.py" \
    --iface veth1 \
    --logdir "$LOGDIR" \
    "$@"
