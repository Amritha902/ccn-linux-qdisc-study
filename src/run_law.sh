#!/usr/bin/env bash
# Third campaign: is there a scaling law governing when adaptation pays off?
#
# The RTT sweep showed adaptation recovering 18.4% of bulk-flow RTT on a 5 ms
# path and nothing at 20, 80 or 200 ms. The proposed mechanism is that the
# benefit depends on how large the AQM's delay target is relative to the path
# RTT, not on the RTT itself. If that is right, the governing variable is the
# ratio target/RTT, and two predictions follow:
#
#   P1  A crossover exists somewhere between 5 and 20 ms (at the default 5 ms
#       target, ratios 1.0 and 0.25). A dense sweep should locate it.
#
#   P2  RATIO INVARIANCE. Holding target/RTT fixed while changing both should
#       reproduce the same benefit. target=20 ms at RTT=20 ms (ratio 1.0)
#       should behave like target=5 ms at RTT=5 ms (ratio 1.0), despite a
#       fourfold difference in RTT. This is the falsifiable one: if the benefit
#       tracks RTT rather than the ratio, the hypothesis is wrong.
#
#   P3  HOLD-OUT. Fit the benefit curve on a subset of ratios, predict an
#       unseen one, then measure it.
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

# ---- P1: dense sweep across the suspected crossover ---------------------
# Default 5 ms target; RTT from 2 to 40 ms gives ratios 2.5 down to 0.125.
for rtt in 2 3 8 12 40; do
  for seed in $SEEDS; do
    total=$((total+1))
    run "[$total] P1 rtt=${rtt} static" \
        --aqm fq_codel --seed "$seed" --duration "$DUR" --flows "$FLOWS" \
        --rate-mbit "$RATE" --rtt-ms "$rtt" --workload steady \
        --outdir "$OUT/rtt${rtt}"
    total=$((total+1))
    run "[$total] P1 rtt=${rtt} adapted" \
        --aqm fq_codel --seed "$seed" --duration "$DUR" --flows "$FLOWS" \
        --rate-mbit "$RATE" --rtt-ms "$rtt" --workload steady --adapt \
        --outdir "$OUT/rtt${rtt}"
  done
done

# ---- P2: ratio invariance ----------------------------------------------
# ratio 1.0 reached three ways: (t=5,rtt=5) already measured;
# (t=20,rtt=20) and (t=80,rtt=80) here. Plus ratio 0.25 at (t=5,rtt=20),
# already measured, against (t=20,rtt=80) here.
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

echo "### law campaign complete: $total runs -> $OUT"
