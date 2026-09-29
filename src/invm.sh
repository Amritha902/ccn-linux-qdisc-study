#!/usr/bin/env bash
# Run a command inside the AQM-capable VM and return its console output.
#
#   src/invm.sh 'python3 src/run_experiment.py --aqm fq_codel ...'
#
# The command runs as root in the guest with the project directory mounted
# read-write over 9p, so any files it writes land on the host.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJ="$(dirname "$HERE")"
CMD="${1:?usage: invm.sh '<command>'}"
TIMEOUT="${TIMEOUT:-1800}"

printf 'cd %s\n%s\n' "$PROJ" "$CMD" > "$PROJ/.runcmd"

INIT="$HERE/guest_init.sh" MEM="${MEM:-4096}" CPUS="${CPUS:-2}" \
    timeout "$TIMEOUT" bash "$HERE/vm.sh" 2>&1 \
  | sed -e 's/\r$//' \
  | awk '/=====GUEST_UP=====/{on=1} on{print} /=====GUEST_DONE=====/{exit}'

rm -f "$PROJ/.runcmd"
