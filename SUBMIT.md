# What to submit, and what is in it

## The files

| file | what it is |
|---|---|
| `paper/acape.pdf` | IEEE two-column, 11 pages. Use for a conference. |
| `paper/scirep/submission.tex` | Single self-contained file for Overleaf, Scientific Reports class. All macros inlined, no `\input` left. |
| `paper/scirep/preview.pdf` | 6-page local render of the above. The real one needs the Overleaf template's `wlscirep.cls`. |
| `paper/ACAPE_2026.pptx` | 17-slide deck with design rationale. |

For Overleaf: start the Scientific Reports template, replace its `main.tex`
with `submission.tex`, upload `refs.bib` and the figures from
`paper/generated/` and `figures/comparison/`. Nothing else is needed.

## The claim

The benefit of adapting a delay-targeting AQM's parameters is governed by the
dimensionless ratio `r = target / RTT`, not by path RTT. It saturates near
20.5% and reaches half of that at `r = 0.50`.

Because published guidance places a correctly configured deployment at `r` of
roughly 0.05 to 0.10, half the available benefit arrives five to ten times
outside that envelope. Adaptation is a remedy for misconfiguration rather than
an improvement on correct configuration, which explains the null results in
this work and in the literature as one effect instead of several.

## Why it should survive review

The hypothesis, its three predictions and their numerical thresholds were
committed to the repository before the campaign that tests them ran. The
commit adding `docs/SCALING_LAW.md` precedes the commit adding the results
directory, and git shows it. Very few measurement papers can show this.

Every number in both papers is generated from the logs by
`src/analyse.py` and `src/analyse_law.py` into `paper/generated/`, and quoted
through LaTeX macros. Prose cannot drift from data.

178 runs, three workloads, eight alternative queue disciplines, path RTTs from
2 to 200 ms, three repetitions per cell, 95% confidence intervals throughout.

## What passed and what failed, all of it in the paper

Passed: the crossover exists (P1); ratio invariance holds to 2.0 percentage
points across a sixteenfold range of RTT while target, interval, control
period and run duration are scaled together (P2); held-out ratios are
predicted to 1.4 points (P3); the saturating form transfers to `codel` and
PIE (X1); and at a fixed 20 ms path, changing only `r` moves the benefit from
1.4% to 11.0% on a different AQM mechanism (X3).

Failed, and reported as failures: the crossover's *location* does not agree
across AQMs within the factor of two we set (2.52, Section on transfer); the
benefit is not suppressed below one packet serialisation time as we predicted,
and the second dimensionless group is a peak rather than a floor (Threats).

## The honest weak points, so you are not surprised by them

- CAKE, which needs no controller at all, outperforms the adapted system at
  every RTT tested. This is stated in the paper. Do not remove it; a reviewer
  who finds it unstated will distrust everything else.
- The eBPF telemetry costs 13.6% of bulk-flow RTT, more than much of the
  adaptation it informs. Also stated, in the pitfalls section, and it is the
  argument for the sham-controller condition.
- The law holds at fixed `target/interval`. Whether it survives changes in
  that second group is not answered.
- Nine measurement defects are documented in `verification/`. Four were
  absolute constants in a controller whose subject is a dimensionless ratio,
  two of which would have manufactured a confirmation and two a refutation.
  They are a strength, not an embarrassment: they are why the result is
  believable.

## Not in the paper, deliberately

The self-gating controller works mechanically but depends on an RTT estimate
the eBPF telemetry does not provide; it is future work, written up in
`verification/CAMPAIGN_VERDICTS.md`. The next research direction, with its
literature check, is in `docs/NOVELTY_MATRIX.md`.
