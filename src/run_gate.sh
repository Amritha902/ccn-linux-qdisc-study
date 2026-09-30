#!/usr/bin/env bash
# Does a controller that knows the scaling law beat one that does not?
#
# Two cells, either side of the measured crossover, with three arms each:
# static, ungated adaptive, and self-gating. Thresholds are fixed in
# docs/GATE_PREREG.md, committed before this runs.
#
#   r = 1.00  target 20ms on a 20ms path: gate should OPEN, match the ungated
#             arm's benefit, cost nothing.
#   r = 0.25  target 5ms on a 20ms path: gate should SHUT, match the static
#             arm's retransmissions, while the ungated arm pays ~10% more for
#             a gain that is not significant.
#
# Both cells sit at the same 20ms RTT, so the gate's decision has to come from
# the ratio rather than from the path.
set -uo pipefail

DUR="${DUR:-240}"
SEEDS="${SEEDS:-1 2 3}"
FLOWS="${FLOWS:-8}"
RATE="${RATE:-10}"
OUT="${OUT:-results_gate}"

run() {
    local desc="$1"; shift
    echo "### $desc"
    if python3 src/run_experiment.py "$@" >/dev/null 2>&1; then echo "    ok"
    else echo "    FAILED: $desc"; fi
}
total=0

# target rtt dur   (240s at target 20ms keeps the loop period scaled, per F8)
for cell in "20 20 240" "5 20 60"; do
  set -- $cell; tgt=$1; rtt=$2; dur=$3
  for seed in $SEEDS; do
    for mode in static ungated gated; do
      total=$((total+1))
      case "$mode" in
        static)  extra="" ;;
        ungated) extra="--adapt --ebpf" ;;
        gated)   extra="--gate" ;;
      esac
      run "[$total] r=$(python3 -c "print(f'{$tgt/$rtt:.2f}')") t=${tgt}ms rtt=${rtt}ms $mode" \
          --aqm fq_codel --seed "$seed" --duration "$dur" --flows "$FLOWS" \
          --rate-mbit "$RATE" --rtt-ms "$rtt" --aqm-target-ms "$tgt" \
          --workload steady $extra --outdir "$OUT/t${tgt}_r${rtt}"
    done
  done
done

echo "### gate campaign complete: $total runs -> $OUT"
