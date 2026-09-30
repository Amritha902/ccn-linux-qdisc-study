#!/usr/bin/env bash
# Does the ratio law transfer to a different AQM algorithm?
#
# Established on fq_codel: benefit is governed by r = target/RTT, half of it at
# r = 0.50. That is a statement about one qdisc until it is tested on an AQM
# that reaches a delay target by another route.
#
#   codel  same mechanism as fq_codel, no flow queueing. Separates the law
#          from the scheduler.
#   pie    a proportional-integral controller on drop probability. Shares
#          nothing with CoDel but the existence of a target. If the ratio
#          governs PIE too, the law is about delay targets in general.
#
# Each qdisc is swept at its own default target, so the ratios overlap:
#   codel, target 5ms:   RTT 3, 5, 8, 20  -> r = 1.67, 1.00, 0.63, 0.25
#   pie,   target 15ms:  RTT 8, 15, 30, 60 -> r = 1.88, 1.00, 0.50, 0.25
#
# Predictions and thresholds are fixed in docs/CROSS_AQM_PREREG.md, committed
# before this runs.
set -uo pipefail

DUR="${DUR:-60}"
SEEDS="${SEEDS:-1 2 3}"
FLOWS="${FLOWS:-8}"
RATE="${RATE:-10}"
OUT="${OUT:-results_cross}"

run() {
    local desc="$1"; shift
    echo "### $desc"
    if python3 src/run_experiment.py "$@" >/dev/null 2>&1; then echo "    ok"
    else echo "    FAILED: $desc"; fi
}
total=0

sweep() {
    local aqm="$1"; shift
    for rtt in "$@"; do
      for seed in $SEEDS; do
        total=$((total+1))
        run "[$total] $aqm rtt=${rtt}ms static" \
            --aqm "$aqm" --seed "$seed" --duration "$DUR" --flows "$FLOWS" \
            --rate-mbit "$RATE" --rtt-ms "$rtt" --workload steady \
            --outdir "$OUT/${aqm}_rtt${rtt}"
        total=$((total+1))
        run "[$total] $aqm rtt=${rtt}ms adapted" \
            --aqm "$aqm" --seed "$seed" --duration "$DUR" --flows "$FLOWS" \
            --rate-mbit "$RATE" --rtt-ms "$rtt" --workload steady --adapt \
            --outdir "$OUT/${aqm}_rtt${rtt}"
      done
    done
}

sweep codel 3 5 8 20
sweep pie   8 15 30 60

echo "### cross-AQM campaign complete: $total runs -> $OUT"
