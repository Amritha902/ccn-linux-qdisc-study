# Overleaf: exactly what to do

## One upload

`overleaf_upload.zip` contains everything, flat, 14 files:

- `submission.tex` — the whole paper, self-contained
- `refs.bib` — 22 references
- 11 `.png` figures

In Overleaf: **New Project, Upload Project**, pick the zip. Then set
`submission.tex` as the main document (Menu, Main document). Compile.

If your advisor wants the official Scientific Reports class instead, start
from the SR template, replace its `main.tex` with `submission.tex`, and upload
the same 11 PNGs plus `refs.bib` to the project root. `submission.tex` already
carries the preamble it needs and no `\input` remains, so nothing else has to
be wired up.

## The 11 figures, and why each is in the paper

Three establish the implementation. Eight carry results. Nothing is
decorative; each is referenced from the text.

| # | file | what it carries |
|---|---|---|
| 1 | `step04_corrected_three_node_router_topology.png` | the topology as configured, bottleneck on the data path |
| 2 | `step07_ebpf_flow_telemetry_is_live_under_traffic.png` | the telemetry reading non-zero per-flow state under load |
| 3 | `fig12_controller_behaviour.png` | the controller acting: regime, trajectory, queue |
| 4 | `fig16_scaling_law.png` | **the central result.** Benefit against target/RTT collapses onto one curve; against RTT alone it does not |
| 5 | `fig15_rtt_sweep.png` | the RTT sweep that motivated the law |
| 6 | `fig01_latency_tail_steady.png` | tail latency across all nine systems, log scale |
| 7 | `fig08_allparams_steady.png` | **every parameter against every system**, normalised, values printed |
| 8 | `fig02_latency_sparse_vs_bulk_steady.png` | sparse probe against bulk flow RTT, measured separately |
| 9 | `fig09_seeds_bulk_rtt_mean_ms_steady.png` | every individual run, not just the summary |
| 10 | `fig13_sham_control_steady.png` | the sham-controller condition |
| 11 | `run16_fq_codel_acape_steady_s1.png` | one representative run end to end |

## Compile check

The local render builds at 8 pages with no errors, no missing files and no
undefined references. Every number in the text comes from a generated macro
whose definition is inlined in `submission.tex`, so there is nothing to
regenerate on Overleaf.

## If the bibliography comes out empty

Overleaf sometimes needs two passes. Recompile once; if it persists, check
that `refs.bib` is at the project root rather than in a subfolder.
