# Project status

**Branch:** `claude/loving-ptolemy-nc6z3n`, all work committed and pushed.

## Data

All 63 planned runs completed on the corrected testbed
(`results/`, each with `summary.json`).

| Condition | Repetitions |
|---|---|
| pfifo, SFQ, RED, CoDel, PIE, FQ-PIE, CAKE, fq_codel | 3 each × 2 workloads |
| fq_codel + ACAPE | 3 each × 2 workloads |
| fq_codel + sham controller | 3 each × 2 workloads |
| fq_codel + ACAPE + eBPF | 3 (staged) |

## Results (steady workload, 3 repetitions, exact t-tests)

| Comparison | Effect | Verdict |
|---|---|---|
| pfifo → fq_codel, p95 RTT | 2344 → 24.6 ms (−99.0%) | significant, p<0.001 |
| static → sham (CPU cost alone) | all metrics within noise | **not** distinguishable |
| sham → ACAPE (decisions alone) | backlog −9.4%, p95 RTT −0.7% | significant, p≈0.04 |
| static → ACAPE (combined) | backlog −9.6%, p95 RTT −0.5% | significant, p≈0.05 |
| fq_codel → CAKE, p95 RTT | 24.6 → 22.9 ms (−6.8%) | significant, p<0.001 |

Under the **staged** workload (flow count changing twice during the run) the
adaptation produces no improvement on any metric, and mean probe RTT is 1.6%
worse (p=0.050). The workload designed to give the controller something to
respond to is the one in which it helps least.

The sham condition establishes that the controller's computational cost is
negligible in both workloads, so these are its decisions rather than overhead.
CAKE nonetheless outperforms adapted fq_codel by a larger margin than the
adaptation gains.

Predictive control (C2) never engaged in any run; the stability gate and the
prediction are mutually exclusive by construction. Withdrawn rather than
claimed, see `verification/C2_FINDING.md`.

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

None outstanding. To rebuild everything from the raw data:

```bash
python3 src/analyse.py      --results results --outdir paper/generated
python3 src/plots.py        --results results --outdir figures/comparison
python3 src/make_gallery.py --results results --outdir figures/runs
python3 src/gen_results.py  --results results --outdir paper/generated
python3 src/make_index.py   --figures figures
cd paper && make            # builds acape.pdf
node deck/build.js          # builds deck/ACAPE_2026.pptx
```
