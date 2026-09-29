# Definitive experiment suite

Raw per-run data from the corrected testbed. **This directory is written
incrementally while the suite runs**, so a commit may capture a partial state;
the run count is complete at 63.

Each run directory contains:

| File | Contents |
|---|---|
| `summary.json` | every computed metric for the run, plus its configuration |
| `qdisc_timeseries.csv` | 500 ms samples of the AQM's own queue statistics |
| `iperf_client.json` | iperf3 JSON, per-flow goodput, retransmits, in-band RTT |
| `iperf_stage*.json` | per-stage JSON for the staged workload |
| `ping.log` | 20 Hz sparse-flow RTT probe |
| `bulk_rtt.json` | in-band bulk-flow RTT samples (from iperf3 TCP_INFO) |
| `00_setup.txt` | the testbed as built, including `tc -s qdisc show` |
| `acape_*.csv` | controller metrics, adjustments and gradients (adaptive/sham runs) |
| `controller.log` | controller console output |

Run labels are `<aqm>[_acape|_sham]_<workload>_s<repetition>`.

`_sham` runs the controller at the same polling cadence but apply no parameter
change, so the controller's CPU cost can be separated from its control
decisions.

`s<N>` indexes an independent repetition, not a PRNG seed, iperf3 exposes no
seed, so repetitions differ only through real timing variation. Confidence
intervals describe run-to-run variance.

Regenerate all analysis from this directory with:

```bash
python3 src/analyse.py    --results results --outdir paper/generated
python3 src/plots.py      --results results --outdir figures/comparison
python3 src/make_gallery.py --results results --outdir figures/runs
python3 src/findings.py   --results results
```
