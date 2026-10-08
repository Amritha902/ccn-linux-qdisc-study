# Project status

**Branch:** `claude/loving-ptolemy-nc6z3n`, all work committed and pushed.

## What the study concluded

Whether adapting `fq_codel`'s four parameters at runtime is worth doing is
decided by a dimensionless ratio, `r = target/RTT`. Benefit follows a logistic
curve in `r` with half of its ceiling reached at `r = 0.50` (R² = 0.986). The
form holds across a 16-fold change in RTT and transfers to `codel` and PIE.

Published guidance places a correctly configured deployment at `r` between
0.05 and 0.10, five to ten times below the half-benefit point. Adaptation is
therefore a remedy for misconfiguration, not an improvement on correct
configuration. Where `r` is small the larger win is to change discipline:
CAKE needs no controller and beats the adapted system at every RTT tested.

The ratio fixes the shape but not the ceiling. Holding `r = 1` and sweeping
the link rate 25-fold moves the benefit from 7.1% to 18.2%, so the fitted
ceiling of 20.5% belongs to the operating point and not to the mechanism.

## Data

292 runs with a recorded summary. The 210 the manuscript draws on:

| Campaign | Runs | What it establishes |
|---|---|---|
| `results/` | 63 | three workloads, nine configurations plus the sham arm |
| `results_sweep/` | 45 | RTT sweep, 2 to 200 ms |
| `results_law/` | 48 | the law campaign, ten ratio cells |
| `results_cross/` | 54 | transfer to `codel` and PIE |

The remaining 82 belong to two further pre-registered studies, of the runtime
RTT estimator (`results_rttest/`) and of a self-gating variant
(`results_gate/`), reported separately. `results_serial/` (30) supplies the
link-rate sweep above.

## Results, steady workload, three repetitions, exact Welch tests

| Comparison | Effect | Verdict |
|---|---|---|
| pfifo → fq_codel, p95 RTT | 2344 → 24.6 ms (−99.0%) | significant, p<0.001 |
| static → sham (cost alone) | all four outputs within noise | not distinguishable |
| static → ACAPE (decisions) | backlog −9.6%, CI ±1.00 packets | **covers zero** |
| fq_codel → CAKE, p95 RTT | 24.6 → 22.9 ms | significant, p<0.001 |

At three repetitions the design resolves about 3.5%, so the null bounds the
effect rather than disproving it. These runs sit at `r = 0.25`, where the law
predicts 2.9% against a measured 1.4%: the controller was asked to work where
there is little to recover.

Predictive control (C2) never engaged in any run; the stability gate and the
prediction are mutually exclusive by construction. Withdrawn rather than
claimed, see `verification/C2_FINDING.md`.

## Pre-registered outcomes

Four hypotheses on the law, committed before the data existed. Three held: a
crossover exists, the curve is invariant to RTT at fixed ratio (2.0 points
against a 5-point threshold), and leave-one-out predicts held-out cells to 1.4
points. The fourth failed: `r₀` spreads 2.52× across the three mechanisms,
beyond the 2× threshold, driven by PIE and confounded by `target/interval`
differing. A second dimensionless group was also pre-registered and failed,
which is the link-rate finding above.

## Deliverables

| Path | Contents |
|---|---|
| `paper/scirep/overleaf_paper.zip` | **the submission**, Springer Nature layout, 10 pages, 3 figures |
| `paper/scirep/submission.pdf` | what that zip compiles to |
| `paper/overleaf_report.zip` | the technical report, 30 pages, 17 figures |
| `paper/report.pdf` | what that zip compiles to |
| `deck/ACAPE_2026.pptx` | 22 slides, built from `deck/build.js` |
| `src/` | controller, testbed, harness, analysis, plotting |
| `verification/` | defect record, citation audit, C2 finding, style checks |
| `docs/` | literature survey, parameter comparison, pre-registrations |
| `figures/` | numbered figures at 300 dpi + `INDEX.md` |

## Rebuilding everything from the raw data

```bash
python3 src/analyse.py                               # tables and fact macros
python3 src/analyse_law.py  --texdir paper/generated # the scaling law
python3 src/analyse_rate.py --texdir paper/generated # the link-rate sweep
python3 src/analyse_sweep.py                         # the RTT sweep
python3 src/plots.py                                 # analysis figures
python3 src/make_gallery.py                          # per-run figures
python3 src/make_index.py                            # the figure index
python3 paper/scirep/sync_generated.py               # inline numbers into the paper
python3 paper/make_report.py                         # the report
python3 paper/scirep/make_overleaf.py                # the paper bundle
python3 paper/make_overleaf_report.py                # the report bundle
node deck/build.js                                   # the deck
```

Rerunning the analysis reproduces `facts.tex`, `law_facts.tex` and
`rate_facts.tex` byte for byte, so no number in any document can drift from
the logs.

## Remaining work

None outstanding. All three contributors carry their VIT addresses in both
documents, and the corresponding author is Amritha S.
