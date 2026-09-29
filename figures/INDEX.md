# Figure Index

Every image in this repository, numbered and captioned.

- **6** methodology evidence captures (STEP)
- **0** per-run result figures (RUN)
- **0** analysis figures (FIG)

## Methodology evidence

Each is a verbatim capture of a command that was actually executed.

| ID | Title | What it shows | Ran on | Image |
|---|---|---|---|---|
| **STEP 01** | Session kernel cannot run the AQMs under study | The cloud container runs a Firecracker kernel with every AQM compiled out and no loadable-module support, so fq_codel cannot be instantiated here at all. This is why the experiments run inside a purpose-built VM rather than directly. | host | [`step01_session_kernel_cannot_run_the_aqms_under_study.png`](steps/step01_session_kernel_cannot_run_the_aqms_under_study.png) |
| **STEP 02** | Kernel built with every AQM compiled in | A 6.12.48 kernel was configured and built with fq_codel, CoDel, CAKE, PIE, FQ-PIE, RED, netem, TBF and HTB all built in (=y), plus BTF for eBPF. This kernel is what the experiments run on. | host | [`step02_kernel_built_with_every_aqm_compiled_in.png`](steps/step02_kernel_built_with_every_aqm_compiled_in.png) |
| **STEP 08** | Regression tests pin all four defects | Seventeen tests, each of which fails against the original implementation's behaviour and passes against the corrected one. They cover the qdisc-selection bug, the three eBPF decode bugs, the integer-millisecond rounding, and the inert prediction. | host | [`step08_regression_tests_pin_all_four_defects.png`](steps/step08_regression_tests_pin_all_four_defects.png) |
| **STEP 09** | Why the eBPF telemetry read zero in every historical run | Three independent defects in read_flows(), each fatal on its own. The immediate cause was a TypeError swallowed by a bare except; behind it sat wrong struct offsets and a comparison of CLOCK_REALTIME against CLOCK_MONOTONIC giving ages of decades. | host | [`step09_why_the_ebpf_telemetry_read_zero_in_every_histor.png`](steps/step09_why_the_ebpf_telemetry_read_zero_in_every_histor.png) |
| **STEP 10** | Throughput overshoot: sum_sent exceeds the link rate | iperf3's sum_sent counts bytes handed to the socket, not bytes delivered. Under pfifo's 1000-packet buffer the sender fills the queue and reports 12.16 Mbps on a 10 Mbit link - physically impossible as a throughput. The excess appears as an 827-packet backlog and 2381 ms p95 RTT, not as delivered data. Every flow-queueing AQM shows no overshoot. This is why goodput is taken from sum_received. | host | [`step10_throughput_overshoot__sum_sent_exceeds_the_link_.png`](steps/step10_throughput_overshoot__sum_sent_exceeds_the_link_.png) |
| **STEP 11** | Drop rates in the original logs exceed the link's packet rate | A 10 Mbit link carrying 1514-byte packets passes at most 826 packets/s, and iperf3 reported ~179 retransmits/s. The original logs record 100,000-138,000 drops/s - up to 155x the physical packet rate. This is the arithmetic that first showed the measurements could not describe the data path. | host | [`step11_drop_rates_in_the_original_logs_exceed_the_link_.png`](steps/step11_drop_rates_in_the_original_logs_exceed_the_link_.png) |

## Analysis figures

| ID | What it shows | Image |
|---|---|---|

## Per-run figures

One figure per experiment run. No run is omitted.

| ID | Run | Measured | Image |
|---|---|---|---|
