# Re-running an experiment corrupted its own measurements

The most consequential defect found in this project, because it was silent, it
affected published numbers, and nothing in a summary file looked wrong.

## The mechanism

`iperf3 --logfile` **appends**. It does not truncate.

`run_experiment.py` creates its output directory with `exist_ok=True` and
passes a fixed path to `--logfile`. Running a cell a second time into the same
directory therefore wrote a second complete JSON document onto the end of the
first. The resulting file has two top-level objects and does not parse:

```
json.decoder.JSONDecodeError: Extra data: line 8236 column 1
```

Every field derived from that file came out `None`: `bulk_rtt_mean_ms`,
`throughput_mbps`, and the whole in-band RTT sample set, which is why
`bulk_rtt.json` read `{"samples": []}`. Every field derived from `ping` or from
`tc` was unaffected and looked entirely normal, so the summary file gave no
sign that half its contents were missing.

## What it damaged

**Three runs in the main corpus.** `results/fq_codel_acape_ebpf_staged_s{1,2,3}`
were re-run earlier in the project, into their existing directories, and so
lost their goodput and bulk-RTT measurements.

**The entire codel arm of the cross-AQM campaign.** The campaign script has no
skip-if-complete guard, so each restart re-ran all 24 codel cells into existing
directories. Twenty-five of its twenty-seven iperf logs were malformed.

A scan of the whole corpus put the rest in the clear: `results_law` 48 of 48
parse, `results_sweep` 45 of 45, and `results` 60 of 60 once the three above
are set aside. The scaling-law result does not depend on any corrupted file.

## The worse, second-order defect this exposed

The three damaged runs did not merely go missing. `analyse.py`'s `system_key()`
ignored the eBPF flag, so an eBPF run and a plain adaptive run were assigned to
the same table row. The staged table therefore read:

```
fq_codel + ACAPE    6    9.18 ±0.10   22.25 ±0.35   24.15 ±0.84 ...
```

with `n = 6` where every other row had 3. Two separate problems in one row:

1. The row merged two configurations that differ by the eBPF polling load,
   which the paper's own pitfalls section argues must be kept apart because
   that load confounds the staged comparison.
2. `ci95()` silently drops `None`, so goodput and bulk RTT were computed from
   three samples and printed beside an `n` of six.

Separating the configurations changes the published staged numbers for
`fq_codel + ACAPE`:

| metric | as published (n=6) | corrected (n=3) |
|---|---|---|
| probe RTT mean | 22.25 ±0.35 | 22.12 ±1.08 |
| probe RTT p95 | 24.15 ±0.84 | 23.47 ±0.38 |
| mean backlog | 11.5 ±1.2 | 11.0 ±3.2 |

Goodput and bulk RTT are unchanged, since they were already being computed
from the three valid runs. But the probe-RTT and backlog columns were genuinely
averaged across both configurations, so those three numbers were contaminated
by exactly the effect the paper warns about.

## The fixes

Stale `iperf_*.json` and `iperf_*.log` files are removed before a run starts,
so a re-run is idempotent rather than destructive.

`system_key()` now appends `_ebpf`, giving `fq_codel + ACAPE + eBPF` its own
row. With the three damaged runs removed pending a clean re-run, that row
correctly shows dashes for the iperf-derived metrics rather than borrowing
another configuration's.

The reported `n` is now the smallest number of samples behind any metric in a
row, with the per-metric counts retained and a warning printed whenever a
row's metrics are not all backed by the same number of runs. The analysis
emitted that warning on its first run after the change, which is how the
remaining gap was confirmed rather than assumed.

## What this says about the method

Three of the five earlier defects were found by reading a parameter
trajectory. This one was found by reading a *file*, after noticing that a
benefit column had gone empty in a cell that had previously produced one. The
general lesson is narrower than the earlier ones and worth as much: a tool
that appends by default will corrupt any experiment that is ever repeated, and
the corruption will present as absent data rather than as an error.
