# Project status

**Branch:** `claude/loving-ptolemy-nc6z3n` — all work committed and pushed.

## Data

60 of 63 planned runs completed on the corrected testbed
(`results/`, each with `summary.json`).

| Condition | Repetitions |
|---|---|
| pfifo, SFQ, RED, CoDel, PIE, FQ-PIE, CAKE, fq_codel | 3 each × 2 workloads |
| fq_codel + ACAPE | 3 (steady), **0 (staged)** — see gap below |
| fq_codel + sham controller | 3 each × 2 workloads |
| fq_codel + ACAPE + eBPF | 3 (staged) |

### Known gap

A harness bug omitted `--ebpf` from the run label, so the three
`fq_codel_acape_staged_*` runs were overwritten by the eBPF runs of the same
seed. The bug is fixed (`src/run_experiment.py`) and the surviving runs were
relabelled `fq_codel_acape_ebpf_staged_s*`, which is what they are.

**Consequence:** the staged workload has no plain (non-eBPF) ACAPE condition,
so the staged static → sham → ACAPE decomposition is incomplete. The steady
workload decomposition is complete and is the basis for the reported result.
Re-running three runs (~5 minutes) would close this:

```bash
for s in 1 2 3; do
  bash src/invm.sh "python3 src/run_experiment.py --aqm fq_codel --seed $s \
    --duration 60 --flows 8 --workload staged --adapt --outdir results"
done
```

## Results (steady workload, 3 repetitions, exact t-tests)

| Comparison | Effect | Verdict |
|---|---|---|
| pfifo → fq_codel, p95 RTT | 2344 → 24.6 ms (−99.0%) | significant, p<0.001 |
| static → sham (CPU cost alone) | all metrics within noise | **not** distinguishable |
| sham → ACAPE (decisions alone) | backlog −9.4%, p95 RTT −0.7% | significant, p≈0.04 |
| static → ACAPE (combined) | backlog −9.6%, p95 RTT −0.5% | significant, p≈0.05 |
| fq_codel → CAKE, p95 RTT | 24.6 → 22.9 ms (−6.8%) | significant, p<0.001 |

The sham condition establishes that the controller's computational cost is
negligible, so the ~10% backlog reduction is attributable to its decisions.
CAKE nonetheless outperforms adapted fq_codel by a larger margin than the
adaptation gains.

## Deliverables

| Path | Contents |
|---|---|
| `src/` | corrected controller, testbed, harness, analysis, plotting |
| `tests/test_acape.py` | 17 regression tests, each failing against the original behaviour |
| `verification/` | verification report (7 defects), citation audit, C2 finding, bug demonstrations |
| `docs/` | literature survey (30 refs, through 2026), parameter comparison, novelty positioning |
| `figures/` | 101 numbered figures + `INDEX.md` (6 STEP, 60 RUN, 35 FIG) |
| `paper/` | `acape.tex` + generated tables and fact macros; builds to PDF |
| `deck/` | `ACAPE_2026.pptx` (17 slides) + `build.js` source |
| `results/` | 60 run directories, raw data |
| `results_v1_pilot/` | 23 superseded pilot runs, marked do-not-cite |

## Remaining work

1. Re-run the three staged ACAPE runs (command above) and regenerate analysis.
2. Capture the five VM-dependent evidence figures:
   `python3 src/make_evidence.py --outdir figures/steps`
3. Write the paper's results prose around `paper/generated/findings_digest.txt`
   and finalise the abstract (currently marked PROVISIONAL in `acape.tex`).
4. Regenerate the deck's results slides from the final numbers.
