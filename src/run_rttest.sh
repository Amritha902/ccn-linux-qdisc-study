#!/usr/bin/env bash
# Validate the runtime base-RTT estimator before anything is built on it.
#
# The self-gating controller must compute r = target/RTT from what it can
# observe, not from a number handed to it, or the gate is not a contribution.
# The eBPF flow telemetry reports a per-flow RTT proxy. On the three existing
# eBPF runs, all at a 20ms base RTT, the MEDIAN of that proxy tracked base RTT
# to 0.7% (20.13 against 20.0) while the MINIMUM was wrong by a factor of five
# (4.15 against 20.0). That is the opposite of the usual practice of estimating
# base RTT by a running minimum.
#
# Three runs at one RTT cannot establish an estimator. This sweeps base RTT so
# the estimator can be checked where it will be used, before the gate relies
# on it.
set -uo pipefail

DUR="${DUR:-60}"
SEEDS="${SEEDS:-1 2 3}"
FLOWS="${FLOWS:-8}"
RATE="${RATE:-10}"
OUT="${OUT:-results_rttest}"

run() {
    local desc="$1"; shift
    echo "### $desc"
    if python3 src/run_experiment.py "$@" >/dev/null 2>&1; then echo "    ok"
    else echo "    FAILED: $desc"; fi
}
total=0

for rtt in 3 5 20 80; do
  for seed in $SEEDS; do
    total=$((total+1))
    run "[$total] ebpf telemetry rtt=${rtt}ms" \
        --aqm fq_codel --seed "$seed" --duration "$DUR" --flows "$FLOWS" \
        --rate-mbit "$RATE" --rtt-ms "$rtt" --workload steady \
        --adapt --ebpf --outdir "$OUT/rtt${rtt}"
  done
done

echo "### estimator validation complete: $total runs -> $OUT"
