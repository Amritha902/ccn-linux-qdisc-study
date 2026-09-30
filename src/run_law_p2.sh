#!/usr/bin/env bash
# P2 only, re-run under the F5 fix (bounds scaled to the configured target).
#
# The P1 dense sweep is complete and unaffected: every one of its runs used the
# 5 ms default, where the new relative bounds reproduce the old absolute ones
# exactly. Only these ratio-invariance cells use a non-default target, and only
# they were endangered by the old clamp.
#
# ratio 1.0 is reached at (t=5,rtt=5) already measured, and here at (20,20) and
# (80,80). ratio 0.25 at (t=5,rtt=20) already measured, and here at (20,80).
set -uo pipefail

DUR="${DUR:-60}"
SEEDS="${SEEDS:-1 2 3}"
FLOWS="${FLOWS:-8}"
RATE="${RATE:-10}"
OUT="${OUT:-results_law}"

run() {
    local desc="$1"; shift
    echo "### $desc"
    if python3 src/run_experiment.py "$@" >/dev/null 2>&1; then echo "    ok"
    else echo "    FAILED: $desc"; fi
}
total=0

for pair in "20 20" "80 80" "20 80"; do
  set -- $pair; tgt=$1; rtt=$2
  for seed in $SEEDS; do
    total=$((total+1))
    run "[$total] P2 target=${tgt}ms rtt=${rtt}ms static" \
        --aqm fq_codel --seed "$seed" --duration "$DUR" --flows "$FLOWS" \
        --rate-mbit "$RATE" --rtt-ms "$rtt" --aqm-target-ms "$tgt" \
        --workload steady --outdir "$OUT/ratio_t${tgt}_r${rtt}"
    total=$((total+1))
    run "[$total] P2 target=${tgt}ms rtt=${rtt}ms adapted" \
        --aqm fq_codel --seed "$seed" --duration "$DUR" --flows "$FLOWS" \
        --rate-mbit "$RATE" --rtt-ms "$rtt" --aqm-target-ms "$tgt" \
        --workload steady --adapt --outdir "$OUT/ratio_t${tgt}_r${rtt}"
  done
done

echo "### P2 complete: $total runs -> $OUT"
