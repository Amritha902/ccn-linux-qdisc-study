#!/usr/bin/env bash
# Second experiment campaign, closing the two limitations the first one stated.
#
# 1. MIXED WORKLOAD. The first campaign used bulk TCP only. fq_codel's new-flow
#    heuristic and its `quantum` parameter exist to serve sparse,
#    latency-sensitive flows, and neither is exercised by bulk-only traffic. A
#    null result on bulk-only traffic therefore says nothing about them. Here
#    bulk TCP runs alongside sparse UDP flows that report their own delay
#    variation and loss.
#
# 2. RTT SWEEP. The first campaign used one base RTT (20 ms). CoDel's defaults
#    are expressed relative to path RTT by construction, so a single RTT cannot
#    test the claim that they need no tuning. Sweeping 5, 80 and 200 ms spans
#    a datacentre-like path, a national path and an intercontinental one.
#
# Together these turn "adaptation did not help in our setup" into a statement
# about where it does and does not help.
set -uo pipefail

DUR="${DUR:-60}"
SEEDS="${SEEDS:-1 2 3}"
FLOWS="${FLOWS:-8}"
RATE="${RATE:-10}"
OUT="${OUT:-results_sweep}"
RTTS="${RTTS:-5 80 200}"
MIX_AQMS="${MIX_AQMS:-pfifo fq_codel cake fq_pie}"
RTT_AQMS="${RTT_AQMS:-fq_codel cake}"

run() {
    local desc="$1"; shift
    echo "### $desc"
    if python3 src/run_experiment.py "$@" >/dev/null 2>&1; then echo "    ok"
    else echo "    FAILED: $desc"; fi
}

total=0

# ---- Campaign A: mixed workload at the reference RTT --------------------
for seed in $SEEDS; do
  for aqm in $MIX_AQMS; do
    total=$((total+1))
    run "[$total] mixed  $aqm  seed=$seed" \
        --aqm "$aqm" --seed "$seed" --duration "$DUR" --flows "$FLOWS" \
        --rate-mbit "$RATE" --rtt-ms 20 --workload mixed --outdir "$OUT"
  done
  total=$((total+1))
  run "[$total] mixed  fq_codel+ACAPE  seed=$seed" \
      --aqm fq_codel --seed "$seed" --duration "$DUR" --flows "$FLOWS" \
      --rate-mbit "$RATE" --rtt-ms 20 --workload mixed --adapt --outdir "$OUT"
  total=$((total+1))
  run "[$total] mixed  fq_codel+SHAM  seed=$seed" \
      --aqm fq_codel --seed "$seed" --duration "$DUR" --flows "$FLOWS" \
      --rate-mbit "$RATE" --rtt-ms 20 --workload mixed --sham --outdir "$OUT"
done

# ---- Campaign B: RTT sweep, steady workload ----------------------------
for rtt in $RTTS; do
  for seed in $SEEDS; do
    for aqm in $RTT_AQMS; do
      total=$((total+1))
      run "[$total] rtt=${rtt}ms  $aqm  seed=$seed" \
          --aqm "$aqm" --seed "$seed" --duration "$DUR" --flows "$FLOWS" \
          --rate-mbit "$RATE" --rtt-ms "$rtt" --workload steady \
          --outdir "$OUT/rtt${rtt}"
    done
    total=$((total+1))
    run "[$total] rtt=${rtt}ms  fq_codel+ACAPE  seed=$seed" \
        --aqm fq_codel --seed "$seed" --duration "$DUR" --flows "$FLOWS" \
        --rate-mbit "$RATE" --rtt-ms "$rtt" --workload steady --adapt \
        --outdir "$OUT/rtt${rtt}"
  done
done

echo "### sweep complete: $total runs -> $OUT"
