#!/usr/bin/env bash
# Is there a second dimensionless group at the packet floor?
#
# s = target / (MTU/rate), the target in units of packet transmission time. A
# target below one packet time cannot be met by any AQM, since the queue cannot
# drain below the packet in flight.
#
# r is held at 1.0 (target = RTT = 5ms) and only the rate varies, so the ratio
# law alone predicts the same benefit in every cell. Any systematic variation
# with rate is the second group. Thresholds fixed in
# docs/SERIALIZATION_PREREG.md, committed before this runs.
#
#   rate    MTU time   s      BDP
#   2Mbit   6.06ms     0.83   under one packet
#   5Mbit   2.42ms     2.06   2 packets
#   10Mbit  1.21ms     4.13   4 packets
#   20Mbit  0.61ms     8.26   8 packets
#   50Mbit  0.24ms     20.6   21 packets
set -uo pipefail

DUR="${DUR:-60}"
SEEDS="${SEEDS:-1 2 3}"
FLOWS="${FLOWS:-8}"
RTT="${RTT:-5}"
OUT="${OUT:-results_serial}"

run() {
    local desc="$1"; shift
    echo "### $desc"
    if python3 src/run_experiment.py "$@" >/dev/null 2>&1; then echo "    ok"
    else echo "    FAILED: $desc"; fi
}
total=0

for rate in 2 5 10 20 50; do
  for seed in $SEEDS; do
    total=$((total+1))
    run "[$total] rate=${rate}Mbit static" \
        --aqm fq_codel --seed "$seed" --duration "$DUR" --flows "$FLOWS" \
        --rate-mbit "$rate" --rtt-ms "$RTT" --aqm-target-ms "$RTT" \
        --workload steady --outdir "$OUT/rate${rate}"
    total=$((total+1))
    run "[$total] rate=${rate}Mbit adapted" \
        --aqm fq_codel --seed "$seed" --duration "$DUR" --flows "$FLOWS" \
        --rate-mbit "$rate" --rtt-ms "$RTT" --aqm-target-ms "$RTT" \
        --workload steady --adapt --outdir "$OUT/rate${rate}"
  done
done

echo "### serialization campaign complete: $total runs -> $OUT"
