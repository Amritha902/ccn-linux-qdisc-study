#!/usr/bin/env bash
# P2, ratio invariance, with the whole time axis scaled.
#
# Holding target/RTT fixed is not enough. CoDel's interval, the controller's
# loop period and the run duration are all times, so a cell at a 16x target is
# only a scaled copy of the reference if every one of them scales with it.
# Earlier attempts scaled some and not others, and each omission produced an
# artefact rather than a measurement:
#
#   interval left at 100 ms  -> target/interval went 0.05, 0.20, 0.80, so the
#                               cells differed in a second dimensionless group
#                               (verification/P2_DESIGN.md)
#   loop period left at 0.5s -> at a 1.6 s AQM interval the controller sampled
#                               inside a single cycle, the regime flickered,
#                               the stability gate never opened and not one
#                               adjustment fired in 86 ticks (F8)
#   duration left at 60 s    -> fewer adjustment opportunities at large targets,
#                               so a partial trajectory compared against a
#                               complete one
#
# Here interval scales in run_experiment.py, the loop period scales in
# acape.py via set_bounds(), and the duration scales below. The reference cell
# (target 5 ms, RTT 5 ms, 60 s) is already measured in results_sweep.
set -uo pipefail

SEEDS="${SEEDS:-1 2 3}"
FLOWS="${FLOWS:-8}"
RATE="${RATE:-10}"
OUT="${OUT:-results_law}"
BASE_DUR="${BASE_DUR:-60}"

run() {
    local desc="$1"; shift
    echo "### $desc"
    if python3 src/run_experiment.py "$@" >/dev/null 2>&1; then echo "    ok"
    else echo "    FAILED: $desc"; fi
}
total=0

# target rtt   (scale is target/5, the reference target)
for pair in "20 20" "80 80" "20 80"; do
  set -- $pair; tgt=$1; rtt=$2
  scale=$(python3 -c "print(max(1, round($tgt/5)))")
  dur=$(python3 -c "print(int($BASE_DUR*$scale))")
  for seed in $SEEDS; do
    total=$((total+1))
    run "[$total] P2 t=${tgt}ms rtt=${rtt}ms static  (x${scale}, ${dur}s)" \
        --aqm fq_codel --seed "$seed" --duration "$dur" --flows "$FLOWS" \
        --rate-mbit "$RATE" --rtt-ms "$rtt" --aqm-target-ms "$tgt" \
        --workload steady --outdir "$OUT/ratio_t${tgt}_r${rtt}"
    total=$((total+1))
    run "[$total] P2 t=${tgt}ms rtt=${rtt}ms adapted (x${scale}, ${dur}s)" \
        --aqm fq_codel --seed "$seed" --duration "$dur" --flows "$FLOWS" \
        --rate-mbit "$RATE" --rtt-ms "$rtt" --aqm-target-ms "$tgt" \
        --workload steady --adapt --outdir "$OUT/ratio_t${tgt}_r${rtt}"
  done
done

echo "### P2 complete: $total runs -> $OUT"
