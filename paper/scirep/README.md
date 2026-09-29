# Scientific Reports submission

Manuscript restructured for *Scientific Reports* (Nature Portfolio).

## Files

| File | Purpose |
|------|---------|
| `main.tex` | The submission file. Uses `\documentclass{wlscirep}` |
| `body.tex` | Manuscript body, shared by both builds |
| `refs.bib` | 22 references, all verified against the published record |
| `preview.tex` | Local preview using the standard `article` class |
| `preview.pdf` | Compiled preview, 5 pages |

## Getting it into Overleaf

1. On Overleaf: **New Project, Templates**, search **"Scientific Reports"**, create from it.
2. Replace that project's `main.tex` with the `main.tex` here.
3. Upload `body.tex` and `refs.bib`.
4. Upload `paper/results_prose.tex` and the `paper/generated/` directory (the
   generated tables and the `facts.tex` macro file), keeping the relative paths
   that `body.tex` expects, or run `make flatten` below to inline them.
5. Upload the figures you intend to include from `figures/comparison/`.

Do **not** upload a copy of `wlscirep.cls`; the Overleaf template supplies it.

```bash
make flatten     # produces submission.tex with all \input files inlined
```

## Structural changes from the conference version

*Scientific Reports* requires **Introduction, Results, Discussion, Methods** in
that order, with Methods after Discussion. The conference version
(`../acape.tex`) places the testbed and controller design before the results.
Content is otherwise the same, with these adjustments:

- Abstract rewritten to 198 words, unstructured, no citations, per journal style.
- Testbed and controller description moved into **Methods**.
- Measurement pitfalls and threats to validity folded into **Discussion**.
- Added the sections the journal requires: Data availability, Author
  contributions, Competing interests.
- Notation expanded on first use (eBPF, AQM, AIMD, L4S) for a general readership.

## Recent references cited in the Introduction and Discussion

Requested addition of recent work. The following are cited in the text, not
merely listed:

| Reference | Year | Where cited |
|---|---|---|
| DESiRED (P4-AQM, deep RL + in-band telemetry) | 2024 | Introduction, Discussion |
| AQM-LLM (distilled LLM controller for L4S) | 2026 | Introduction |
| ML-AQM survey | 2025 | Introduction |
| Ray et al., AQM effects on speed-test measurement | 2025 | Discussion |
| Self-clocked round robin (NSDI) | 2025 | Discussion |
| eBPF qdisc proposal | 2023 | Discussion |
| L4S, RFC 9330 and RFC 9332 | 2023 | Introduction, Discussion |

DESiRED is cited as the closest prior work and as the reason we do **not**
claim runtime target adaptation as novel. That framing is deliberate: the claim
we defend is the controlled evaluation, which none of these works performs.
