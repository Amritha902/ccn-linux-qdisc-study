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

# A chain restart used to redo the whole codel sweep, 28 minutes of work whose
# results were already valid, and worse, re-running into an existing directory
# corrupted iperf's log (verification/IPERF_APPEND.md). Cells that already hold
# a complete run are skipped.
# True when a cell already holds the expected number of runs, each with a
# usable bulk_rtt. Defined AND called: an earlier version of this guard was
# written but never invoked, so a restart silently re-ran 24 valid codel cells
# before reaching the one it was restarted for.
cell_done() {
    local dir="$1" want="$2"
    [ -d "$dir" ] || return 1
    python3 - "$dir" "$want" <<'EOP'
import glob, json, os, sys
d, want = sys.argv[1], int(sys.argv[2])
good = 0
for f in glob.glob(os.path.join(d, "*", "summary.json")):
    try:
        if json.load(open(f)).get("bulk_rtt_mean_ms") is not None:
            good += 1
    except Exception:
        pass
sys.exit(0 if good >= want else 1)
EOP
}

run() {
    local desc="$1"; shift
    echo "### $desc"
    if python3 src/run_experiment.py "$@" >/dev/null 2>&1; then echo "    ok"
    else echo "    FAILED: $desc"; fi
}
total=0

# Duration must scale with the qdisc's own default target, for the same reason
# the loop period does (F8): the controller's period scales by target/5ms, so
# at PIE's 15ms default it ticks three times more slowly and needs three times
# as long for a comparable trajectory. Run at a flat 60s, PIE managed 34 ticks
# and 3 adjustments against codel's 8, and showed no benefit -- an under-driven
# instrument, not a refutation.
sweep() {
    local aqm="$1"; local tgt="$2"; shift 2
    local scale dur
    scale=$(python3 -c "print(max(1, round($tgt/5)))")
    dur=$(python3 -c "print(int($DUR*$scale))")
    echo "### $aqm: default target ${tgt}ms, scale x${scale}, duration ${dur}s"
    for rtt in "$@"; do
      local cell="$OUT/${aqm}_rtt${rtt}"
      local want=$(( $(echo $SEEDS | wc -w) * 2 ))
      if cell_done "$cell" "$want"; then
          echo "### $aqm rtt=${rtt}ms: already complete ($want runs), skipping"
          total=$((total+want))
          continue
      fi
      for seed in $SEEDS; do
        total=$((total+1))
        run "[$total] $aqm rtt=${rtt}ms static" \
            --aqm "$aqm" --seed "$seed" --duration "$dur" --flows "$FLOWS" \
            --rate-mbit "$RATE" --rtt-ms "$rtt" --workload steady \
            --outdir "$OUT/${aqm}_rtt${rtt}"
        total=$((total+1))
        run "[$total] $aqm rtt=${rtt}ms adapted" \
            --aqm "$aqm" --seed "$seed" --duration "$dur" --flows "$FLOWS" \
            --rate-mbit "$RATE" --rtt-ms "$rtt" --workload steady --adapt \
            --outdir "$OUT/${aqm}_rtt${rtt}"
      done
    done
}

sweep codel  5 3 5 8 20
sweep pie   15 8 15 30 60

echo "### cross-AQM campaign complete: $total runs -> $OUT"
