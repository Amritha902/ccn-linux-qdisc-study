#!/usr/bin/env bash
# The X3 discrimination promised in docs/CROSS_AQM_PREREG.md.
#
# The cross-AQM sweep runs PIE at RTT 8, 15, 30 and 60, so it never measures
# RTT 20, which is where the pre-registered same-RTT contrast lives:
#
#   fq_codel, target 5ms,  RTT 20ms -> r = 0.25 -> +1.4%, not significant
#   pie,      target 15ms, RTT 20ms -> r = 0.75 -> predicted substantial
#
# Identical path, rate, flows and load, so any explanation in terms of RTT
# predicts the same outcome for both and only the ratio predicts a difference.
# The sweep's RTT 8 cells give a weaker version of the same contrast, since
# both arms are significant there. This fills the gap rather than leaving a
# pre-registered prediction unmeasured.
set -uo pipefail
SEEDS="${SEEDS:-1 2 3}"
OUT="${OUT:-results_cross}"
DUR="${DUR:-180}"   # PIE's 15ms default gives scale 3, so 60s x 3
total=0
for seed in $SEEDS; do
  for mode in static adapted; do
    total=$((total+1))
    extra=""; [ "$mode" = adapted ] && extra="--adapt"
    echo "### [$total] pie rtt=20ms $mode"
    if python3 src/run_experiment.py --aqm pie --seed "$seed" --duration "$DUR" \
        --flows 8 --rate-mbit 10 --rtt-ms 20 --workload steady $extra \
        --outdir "$OUT/pie_rtt20" >/dev/null 2>&1
    then echo "    ok"; else echo "    FAILED"; fi
  done
done
echo "### pie rtt=20 complete: $total runs"
