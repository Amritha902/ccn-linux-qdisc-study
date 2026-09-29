#!/usr/bin/env bash
# Full experiment suite. Runs inside the VM (see src/invm.sh).
#
# Every AQM sees an identical bottleneck: TBF at RATE on the router's egress
# toward the server, with the AQM as TBF's child. TBF is the only shaper, so
# CAKE is configured `besteffort` rather than with its own `bandwidth`.
#
# Two workloads:
#   steady - constant flow count, the original study's condition
#   staged - few flows -> many -> few, so the congestion regime actually
#            changes. Under the original constant overload the classifier sat
#            in HEAVY for 81% of ticks and the controller simply ratcheted
#            target to its floor in every run.
set -uo pipefail

DUR="${DUR:-60}"
SEEDS="${SEEDS:-1 2 3}"
FLOWS="${FLOWS:-8}"
RATE="${RATE:-10}"
RTT="${RTT:-20}"
OUT="${OUT:-results}"
AQMS="${AQMS:-pfifo fq_codel codel pie fq_pie cake red sfq}"
WORKLOADS="${WORKLOADS:-steady staged}"

run() {
    local desc="$1"; shift
    echo "### $desc"
    if python3 src/run_experiment.py "$@" >/dev/null 2>&1; then
        echo "    ok"
    else
        echo "    FAILED: $desc"
    fi
}

total=0
for wl in $WORKLOADS; do
  for seed in $SEEDS; do
    for aqm in $AQMS; do
      total=$((total+1))
      run "[$total] $aqm  $wl  seed=$seed" \
          --aqm "$aqm" --seed "$seed" --duration "$DUR" --flows "$FLOWS" \
          --rate-mbit "$RATE" --rtt-ms "$RTT" --workload "$wl" --outdir "$OUT"
    done
    # ACAPE: fq_codel driven by the adaptive controller
    total=$((total+1))
    run "[$total] fq_codel+ACAPE  $wl  seed=$seed" \
        --aqm fq_codel --seed "$seed" --duration "$DUR" --flows "$FLOWS" \
        --rate-mbit "$RATE" --rtt-ms "$RTT" --workload "$wl" --adapt --outdir "$OUT"

    # Sham control: the controller runs and polls but applies nothing.
    # Without this, "controller CPU cost" and "controller decisions" are
    # confounded in any latency difference against static fq_codel.
    total=$((total+1))
    run "[$total] fq_codel+SHAM  $wl  seed=$seed" \
        --aqm fq_codel --seed "$seed" --duration "$DUR" --flows "$FLOWS" \
        --rate-mbit "$RATE" --rtt-ms "$RTT" --workload "$wl" --sham --outdir "$OUT"
  done
done

# ACAPE with eBPF telemetry attached (contribution C3)
for seed in $SEEDS; do
    total=$((total+1))
    run "[$total] fq_codel+ACAPE+eBPF  staged  seed=$seed" \
        --aqm fq_codel --seed "$seed" --duration "$DUR" --flows "$FLOWS" \
        --rate-mbit "$RATE" --rtt-ms "$RTT" --workload staged --adapt --ebpf \
        --outdir "$OUT"
done

echo "### suite complete: $total runs -> $OUT"
