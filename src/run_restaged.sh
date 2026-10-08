#!/usr/bin/env bash
# Re-run the three staged eBPF ACAPE cells whose iperf logs were corrupted by
# an earlier re-run into an existing directory (verification/IPERF_APPEND.md).
# Their directories were removed, so these start clean and the logfile-append
# defect cannot recur now that stale logs are cleared before each run.
set -uo pipefail
DUR="${DUR:-120}"
SEEDS="${SEEDS:-1 2 3}"
OUT="${OUT:-results}"
for seed in $SEEDS; do
    echo "### staged eBPF ACAPE seed=$seed"
    if python3 src/run_experiment.py --aqm fq_codel --seed "$seed" \
        --duration "$DUR" --flows 8 --rate-mbit 10 --rtt-ms 20 \
        --workload staged --adapt --ebpf --outdir "$OUT" >/dev/null 2>&1
    then echo "    ok"; else echo "    FAILED seed=$seed"; fi
done
echo "### staged eBPF re-run complete -> $OUT"
