# Figure Index

Every image in this repository, numbered and captioned.

- **11** methodology evidence captures (STEP)
- **63** per-run result figures (RUN)
- **35** analysis figures (FIG)

## Methodology evidence

Each is a verbatim capture of a command that was actually executed.

| ID | Title | What it shows | Ran on | Image |
|---|---|---|---|---|
| **STEP 01** | Session kernel cannot run the AQMs under study | The cloud container runs a Firecracker kernel with every AQM compiled out and no loadable-module support, so fq_codel cannot be instantiated here at all. This is why the experiments run inside a purpose-built VM rather than directly. | host | [`step01_session_kernel_cannot_run_the_aqms_under_study.png`](steps/step01_session_kernel_cannot_run_the_aqms_under_study.png) |
| **STEP 02** | Kernel built with every AQM compiled in | A 6.12.48 kernel was configured and built with fq_codel, CoDel, CAKE, PIE, FQ-PIE, RED, netem, TBF and HTB all built in (=y), plus BTF for eBPF. This kernel is what the experiments run on. | host | [`step02_kernel_built_with_every_aqm_compiled_in.png`](steps/step02_kernel_built_with_every_aqm_compiled_in.png) |
| **STEP 03** | AQM availability confirmed inside the VM | Each queue discipline is instantiated on a real veth device in the guest. Availability is demonstrated, not assumed. | vm | [`step03_aqm_availability_confirmed_inside_the_vm.png`](steps/step03_aqm_availability_confirmed_inside_the_vm.png) |
| **STEP 04** | Corrected three-node router topology | The bottleneck now sits on the router's egress toward the server, so it is on the data path. TBF is the shaper and the AQM under study is its child. | vm | [`step04_corrected_three_node_router_topology.png`](steps/step04_corrected_three_node_router_topology.png) |
| **STEP 05** | The original two-node testbed shaped ACKs, not data | README Parts 2-4 put the bottleneck on veth1 inside ns1 but ran iperf3 FROM ns2, so data flowed ns2 -> ns1 while the egress qdisc on veth1 shaped only ns1 -> ns2: the acknowledgement path. Left panel: data passes unshaped at multi-Gbit and the queue carries 66-byte ACKs. Right panel: the corrected topology shapes the data path, and the queue carries full-size packets. Every backlog and drop figure in the original Parts 2-4 was a measurement of ACK queueing. | comparison | [`step05_the_original_two_node_testbed_shaped_acks__not_d.png`](steps/step05_the_original_two_node_testbed_shaped_acks__not_d.png) |
| **STEP 06** | eBPF telemetry program compiles, attaches and JITs | tc_monitor.c is compiled with BTF, attached at the clsact egress hook on the router, and verified JIT-compiled. Its maps are then located through the bpf(2) syscall. | vm | [`step06_ebpf_telemetry_program_compiles__attaches_and_ji.png`](steps/step06_ebpf_telemetry_program_compiles__attaches_and_ji.png) |
| **STEP 07** | eBPF flow telemetry is live under traffic | With traffic running, the flow_map is read through bpf(2) and reports real per-flow state. In all 21,128 samples of the original study this read returned zero. | vm | [`step07_ebpf_flow_telemetry_is_live_under_traffic.png`](steps/step07_ebpf_flow_telemetry_is_live_under_traffic.png) |
| **STEP 08** | Regression tests pin all four defects | Seventeen tests, each of which fails against the original implementation's behaviour and passes against the corrected one. They cover the qdisc-selection bug, the three eBPF decode bugs, the integer-millisecond rounding, and the inert prediction. | host | [`step08_regression_tests_pin_all_four_defects.png`](steps/step08_regression_tests_pin_all_four_defects.png) |
| **STEP 09** | Why the eBPF telemetry read zero in every historical run | Three independent defects in read_flows(), each fatal on its own. The immediate cause was a TypeError swallowed by a bare except; behind it sat wrong struct offsets and a comparison of CLOCK_REALTIME against CLOCK_MONOTONIC giving ages of decades. | host | [`step09_why_the_ebpf_telemetry_read_zero_in_every_histor.png`](steps/step09_why_the_ebpf_telemetry_read_zero_in_every_histor.png) |
| **STEP 10** | Throughput overshoot: sum_sent exceeds the link rate | iperf3's sum_sent counts bytes handed to the socket, not bytes delivered. Under pfifo's 1000-packet buffer the sender fills the queue and reports 12.16 Mbps on a 10 Mbit link - physically impossible as a throughput. The excess appears as an 827-packet backlog and 2381 ms p95 RTT, not as delivered data. Every flow-queueing AQM shows no overshoot. This is why goodput is taken from sum_received. | host | [`step10_throughput_overshoot__sum_sent_exceeds_the_link_.png`](steps/step10_throughput_overshoot__sum_sent_exceeds_the_link_.png) |
| **STEP 11** | Drop rates in the original logs exceed the link's packet rate | A 10 Mbit link carrying 1514-byte packets passes at most 826 packets/s, and iperf3 reported ~179 retransmits/s. The original logs record 100,000-138,000 drops/s - up to 155x the physical packet rate. This is the arithmetic that first showed the measurements could not describe the data path. | host | [`step11_drop_rates_in_the_original_logs_exceed_the_link_.png`](steps/step11_drop_rates_in_the_original_logs_exceed_the_link_.png) |

## Analysis figures

| ID | What it shows | Image |
|---|---|---|
| **FIG 01** | Tail latency (p95 RTT, sparse probe flow) across all systems, log scale (staged workload) | [`fig01_latency_tail_staged.png`](comparison/fig01_latency_tail_staged.png) |
| **FIG 02** | Tail latency (p95 RTT, sparse probe flow) across all systems, log scale (steady workload) | [`fig01_latency_tail_steady.png`](comparison/fig01_latency_tail_steady.png) |
| **FIG 03** | Sparse probe flow vs bulk TCP flow RTT — why the two differ (staged workload) | [`fig02_latency_sparse_vs_bulk_staged.png`](comparison/fig02_latency_sparse_vs_bulk_staged.png) |
| **FIG 04** | Sparse probe flow vs bulk TCP flow RTT — why the two differ (steady workload) | [`fig02_latency_sparse_vs_bulk_steady.png`](comparison/fig02_latency_sparse_vs_bulk_steady.png) |
| **FIG 05** | Goodput (from iperf3 sum_received), axis zoomed to show it is flat (staged workload) | [`fig03_throughput_staged.png`](comparison/fig03_throughput_staged.png) |
| **FIG 06** | Goodput (from iperf3 sum_received), axis zoomed to show it is flat (steady workload) | [`fig03_throughput_steady.png`](comparison/fig03_throughput_steady.png) |
| **FIG 07** | Mean queue occupancy, log scale (staged workload) | [`fig04_backlog_staged.png`](comparison/fig04_backlog_staged.png) |
| **FIG 08** | Mean queue occupancy, log scale (steady workload) | [`fig04_backlog_steady.png`](comparison/fig04_backlog_steady.png) |
| **FIG 09** | Jain's fairness index, axis zoomed (staged workload) | [`fig05_fairness_staged.png`](comparison/fig05_fairness_staged.png) |
| **FIG 10** | Jain's fairness index, axis zoomed (steady workload) | [`fig05_fairness_steady.png`](comparison/fig05_fairness_steady.png) |
| **FIG 11** | AQM drop rate and end-to-end TCP retransmissions (staged workload) | [`fig06_droprate_staged.png`](comparison/fig06_droprate_staged.png) |
| **FIG 12** | AQM drop rate and end-to-end TCP retransmissions (steady workload) | [`fig06_droprate_steady.png`](comparison/fig06_droprate_steady.png) |
| **FIG 13** | Latency vs throughput trade-off (staged workload) | [`fig07_tradeoff_staged.png`](comparison/fig07_tradeoff_staged.png) |
| **FIG 14** | Latency vs throughput trade-off (steady workload) | [`fig07_tradeoff_steady.png`](comparison/fig07_tradeoff_steady.png) |
| **FIG 15** | All measured parameters × all systems, normalised heatmap with measured values (staged workload) | [`fig08_allparams_staged.png`](comparison/fig08_allparams_staged.png) |
| **FIG 16** | All measured parameters × all systems, normalised heatmap with measured values (steady workload) | [`fig08_allparams_steady.png`](comparison/fig08_allparams_steady.png) |
| **FIG 17** | Per-seed values — every individual run shown, mean marked — backlog mean pkts (staged workload) | [`fig09_seeds_backlog_mean_pkts_staged.png`](comparison/fig09_seeds_backlog_mean_pkts_staged.png) |
| **FIG 18** | Per-seed values — every individual run shown, mean marked — backlog mean pkts (steady workload) | [`fig09_seeds_backlog_mean_pkts_steady.png`](comparison/fig09_seeds_backlog_mean_pkts_steady.png) |
| **FIG 19** | Per-seed values — every individual run shown, mean marked — bulk rtt mean ms (staged workload) | [`fig09_seeds_bulk_rtt_mean_ms_staged.png`](comparison/fig09_seeds_bulk_rtt_mean_ms_staged.png) |
| **FIG 20** | Per-seed values — every individual run shown, mean marked — bulk rtt mean ms (steady workload) | [`fig09_seeds_bulk_rtt_mean_ms_steady.png`](comparison/fig09_seeds_bulk_rtt_mean_ms_steady.png) |
| **FIG 21** | Per-seed values — every individual run shown, mean marked — jain (staged workload) | [`fig09_seeds_jain_staged.png`](comparison/fig09_seeds_jain_staged.png) |
| **FIG 22** | Per-seed values — every individual run shown, mean marked — jain (steady workload) | [`fig09_seeds_jain_steady.png`](comparison/fig09_seeds_jain_steady.png) |
| **FIG 23** | Per-seed values — every individual run shown, mean marked — retransmits (staged workload) | [`fig09_seeds_retransmits_staged.png`](comparison/fig09_seeds_retransmits_staged.png) |
| **FIG 24** | Per-seed values — every individual run shown, mean marked — retransmits (steady workload) | [`fig09_seeds_retransmits_steady.png`](comparison/fig09_seeds_retransmits_steady.png) |
| **FIG 25** | Per-seed values — every individual run shown, mean marked — sparse rtt p95 ms (staged workload) | [`fig09_seeds_sparse_rtt_p95_ms_staged.png`](comparison/fig09_seeds_sparse_rtt_p95_ms_staged.png) |
| **FIG 26** | Per-seed values — every individual run shown, mean marked — sparse rtt p95 ms (steady workload) | [`fig09_seeds_sparse_rtt_p95_ms_steady.png`](comparison/fig09_seeds_sparse_rtt_p95_ms_steady.png) |
| **FIG 27** | Per-seed values — every individual run shown, mean marked — throughput mbps (staged workload) | [`fig09_seeds_throughput_mbps_staged.png`](comparison/fig09_seeds_throughput_mbps_staged.png) |
| **FIG 28** | Per-seed values — every individual run shown, mean marked — throughput mbps (steady workload) | [`fig09_seeds_throughput_mbps_steady.png`](comparison/fig09_seeds_throughput_mbps_steady.png) |
| **FIG 29** | Queue occupancy over time (staged workload) | [`fig10_timeseries_backlog_staged.png`](comparison/fig10_timeseries_backlog_staged.png) |
| **FIG 30** | Queue occupancy over time (steady workload) | [`fig10_timeseries_backlog_steady.png`](comparison/fig10_timeseries_backlog_steady.png) |
| **FIG 31** | Measured RTT over time (20 Hz probe) (staged workload) | [`fig11_timeseries_rtt_staged.png`](comparison/fig11_timeseries_rtt_staged.png) |
| **FIG 32** | Measured RTT over time (20 Hz probe) (steady workload) | [`fig11_timeseries_rtt_steady.png`](comparison/fig11_timeseries_rtt_steady.png) |
| **FIG 33** | What the ACAPE controller actually did: target, backlog, eBPF telemetry, regime | [`fig12_controller_behaviour.png`](comparison/fig12_controller_behaviour.png) |
| **FIG 34** | Sham-controller condition — separates controller CPU cost from control decisions (staged workload) | [`fig13_sham_control_staged.png`](comparison/fig13_sham_control_staged.png) |
| **FIG 35** | Sham-controller condition — separates controller CPU cost from control decisions (steady workload) | [`fig13_sham_control_steady.png`](comparison/fig13_sham_control_steady.png) |

## Per-run figures

One figure per experiment run. No run is omitted.

| ID | Run | Measured | Image |
|---|---|---|---|
| **RUN 01** | cake_staged_s1 | cake, staged workload, seed 1 — goodput 9.1985 Mbps, p95 RTT 22.2 ms, backlog 8.92 pkt | [`run01_cake_staged_s1.png`](runs/run01_cake_staged_s1.png) |
| **RUN 02** | cake_staged_s2 | cake, staged workload, seed 2 — goodput 9.2728 Mbps, p95 RTT 22.3 ms, backlog 11.2 pkt | [`run02_cake_staged_s2.png`](runs/run02_cake_staged_s2.png) |
| **RUN 03** | cake_staged_s3 | cake, staged workload, seed 3 — goodput 9.25 Mbps, p95 RTT 22.3 ms, backlog 11.28 pkt | [`run03_cake_staged_s3.png`](runs/run03_cake_staged_s3.png) |
| **RUN 04** | cake_steady_s1 | cake, steady workload, seed 1 — goodput 9.4098 Mbps, p95 RTT 22.8 ms, backlog 6.89 pkt | [`run04_cake_steady_s1.png`](runs/run04_cake_steady_s1.png) |
| **RUN 05** | cake_steady_s2 | cake, steady workload, seed 2 — goodput 9.4085 Mbps, p95 RTT 23.0 ms, backlog 6.55 pkt | [`run05_cake_steady_s2.png`](runs/run05_cake_steady_s2.png) |
| **RUN 06** | cake_steady_s3 | cake, steady workload, seed 3 — goodput 9.4236 Mbps, p95 RTT 22.9 ms, backlog 6.58 pkt | [`run06_cake_steady_s3.png`](runs/run06_cake_steady_s3.png) |
| **RUN 07** | codel_staged_s1 | codel, staged workload, seed 1 — goodput 9.2517 Mbps, p95 RTT 193.0 ms, backlog 23.58 pkt | [`run07_codel_staged_s1.png`](runs/run07_codel_staged_s1.png) |
| **RUN 08** | codel_staged_s2 | codel, staged workload, seed 2 — goodput 9.2975 Mbps, p95 RTT 126.0 ms, backlog 23.71 pkt | [`run08_codel_staged_s2.png`](runs/run08_codel_staged_s2.png) |
| **RUN 09** | codel_staged_s3 | codel, staged workload, seed 3 — goodput 9.2825 Mbps, p95 RTT 197.0 ms, backlog 25.09 pkt | [`run09_codel_staged_s3.png`](runs/run09_codel_staged_s3.png) |
| **RUN 10** | codel_steady_s1 | codel, steady workload, seed 1 — goodput 9.4456 Mbps, p95 RTT 43.7 ms, backlog 8.98 pkt | [`run10_codel_steady_s1.png`](runs/run10_codel_steady_s1.png) |
| **RUN 11** | codel_steady_s2 | codel, steady workload, seed 2 — goodput 9.445 Mbps, p95 RTT 46.7 ms, backlog 8.63 pkt | [`run11_codel_steady_s2.png`](runs/run11_codel_steady_s2.png) |
| **RUN 12** | codel_steady_s3 | codel, steady workload, seed 3 — goodput 9.4614 Mbps, p95 RTT 44.9 ms, backlog 8.04 pkt | [`run12_codel_steady_s3.png`](runs/run12_codel_steady_s3.png) |
| **RUN 13** | fq_codel_acape_ebpf_staged_s1 | fq_codel + ACAPE + eBPF, staged workload, seed 1 — goodput None Mbps, p95 RTT 24.7 ms, backlog 11.19 pkt | [`run13_fq_codel_acape_ebpf_staged_s1.png`](runs/run13_fq_codel_acape_ebpf_staged_s1.png) |
| **RUN 14** | fq_codel_acape_ebpf_staged_s2 | fq_codel + ACAPE + eBPF, staged workload, seed 2 — goodput None Mbps, p95 RTT 25.3 ms, backlog 11.93 pkt | [`run14_fq_codel_acape_ebpf_staged_s2.png`](runs/run14_fq_codel_acape_ebpf_staged_s2.png) |
| **RUN 15** | fq_codel_acape_ebpf_staged_s3 | fq_codel + ACAPE + eBPF, staged workload, seed 3 — goodput None Mbps, p95 RTT 24.5 ms, backlog 12.96 pkt | [`run15_fq_codel_acape_ebpf_staged_s3.png`](runs/run15_fq_codel_acape_ebpf_staged_s3.png) |
| **RUN 16** | fq_codel_acape_staged_s1 | fq_codel + ACAPE, staged workload, seed 1 — goodput 9.1339 Mbps, p95 RTT 23.5 ms, backlog 12.5 pkt | [`run16_fq_codel_acape_staged_s1.png`](runs/run16_fq_codel_acape_staged_s1.png) |
| **RUN 17** | fq_codel_acape_staged_s2 | fq_codel + ACAPE, staged workload, seed 2 — goodput 9.1986 Mbps, p95 RTT 23.3 ms, backlog 10.4 pkt | [`run17_fq_codel_acape_staged_s2.png`](runs/run17_fq_codel_acape_staged_s2.png) |
| **RUN 18** | fq_codel_acape_staged_s3 | fq_codel + ACAPE, staged workload, seed 3 — goodput 9.2051 Mbps, p95 RTT 23.6 ms, backlog 10.16 pkt | [`run18_fq_codel_acape_staged_s3.png`](runs/run18_fq_codel_acape_staged_s3.png) |
| **RUN 19** | fq_codel_acape_steady_s1 | fq_codel + ACAPE, steady workload, seed 1 — goodput 9.3894 Mbps, p95 RTT 24.5 ms, backlog 6.34 pkt | [`run19_fq_codel_acape_steady_s1.png`](runs/run19_fq_codel_acape_steady_s1.png) |
| **RUN 20** | fq_codel_acape_steady_s2 | fq_codel + ACAPE, steady workload, seed 2 — goodput 9.4088 Mbps, p95 RTT 24.4 ms, backlog 5.84 pkt | [`run20_fq_codel_acape_steady_s2.png`](runs/run20_fq_codel_acape_steady_s2.png) |
| **RUN 21** | fq_codel_acape_steady_s3 | fq_codel + ACAPE, steady workload, seed 3 — goodput 9.4093 Mbps, p95 RTT 24.4 ms, backlog 6.24 pkt | [`run21_fq_codel_acape_steady_s3.png`](runs/run21_fq_codel_acape_steady_s3.png) |
| **RUN 22** | fq_codel_sham_staged_s1 | fq_codel, staged workload, seed 1 — goodput 9.1858 Mbps, p95 RTT 23.6 ms, backlog 11.93 pkt | [`run22_fq_codel_sham_staged_s1.png`](runs/run22_fq_codel_sham_staged_s1.png) |
| **RUN 23** | fq_codel_sham_staged_s2 | fq_codel, staged workload, seed 2 — goodput 9.2323 Mbps, p95 RTT 23.5 ms, backlog 10.3 pkt | [`run23_fq_codel_sham_staged_s2.png`](runs/run23_fq_codel_sham_staged_s2.png) |
| **RUN 24** | fq_codel_sham_staged_s3 | fq_codel, staged workload, seed 3 — goodput 9.1657 Mbps, p95 RTT 23.4 ms, backlog 12.26 pkt | [`run24_fq_codel_sham_staged_s3.png`](runs/run24_fq_codel_sham_staged_s3.png) |
| **RUN 25** | fq_codel_sham_steady_s1 | fq_codel, steady workload, seed 1 — goodput 9.4098 Mbps, p95 RTT 24.6 ms, backlog 6.82 pkt | [`run25_fq_codel_sham_steady_s1.png`](runs/run25_fq_codel_sham_steady_s1.png) |
| **RUN 26** | fq_codel_sham_steady_s2 | fq_codel, steady workload, seed 2 — goodput 9.3923 Mbps, p95 RTT 24.6 ms, backlog 6.73 pkt | [`run26_fq_codel_sham_steady_s2.png`](runs/run26_fq_codel_sham_steady_s2.png) |
| **RUN 27** | fq_codel_sham_steady_s3 | fq_codel, steady workload, seed 3 — goodput 9.392 Mbps, p95 RTT 24.5 ms, backlog 6.79 pkt | [`run27_fq_codel_sham_steady_s3.png`](runs/run27_fq_codel_sham_steady_s3.png) |
| **RUN 28** | fq_codel_staged_s1 | fq_codel, staged workload, seed 1 — goodput 9.232 Mbps, p95 RTT 23.3 ms, backlog 11.15 pkt | [`run28_fq_codel_staged_s1.png`](runs/run28_fq_codel_staged_s1.png) |
| **RUN 29** | fq_codel_staged_s2 | fq_codel, staged workload, seed 2 — goodput 9.2362 Mbps, p95 RTT 23.4 ms, backlog 11.8 pkt | [`run29_fq_codel_staged_s2.png`](runs/run29_fq_codel_staged_s2.png) |
| **RUN 30** | fq_codel_staged_s3 | fq_codel, staged workload, seed 3 — goodput 9.2382 Mbps, p95 RTT 23.5 ms, backlog 10.88 pkt | [`run30_fq_codel_staged_s3.png`](runs/run30_fq_codel_staged_s3.png) |
| **RUN 31** | fq_codel_steady_s1 | fq_codel, steady workload, seed 1 — goodput 9.3904 Mbps, p95 RTT 24.6 ms, backlog 6.47 pkt | [`run31_fq_codel_steady_s1.png`](runs/run31_fq_codel_steady_s1.png) |
| **RUN 32** | fq_codel_steady_s2 | fq_codel, steady workload, seed 2 — goodput 9.4243 Mbps, p95 RTT 24.6 ms, backlog 6.83 pkt | [`run32_fq_codel_steady_s2.png`](runs/run32_fq_codel_steady_s2.png) |
| **RUN 33** | fq_codel_steady_s3 | fq_codel, steady workload, seed 3 — goodput 9.4266 Mbps, p95 RTT 24.5 ms, backlog 7.07 pkt | [`run33_fq_codel_steady_s3.png`](runs/run33_fq_codel_steady_s3.png) |
| **RUN 34** | fq_pie_staged_s1 | fq_pie, staged workload, seed 1 — goodput 9.2375 Mbps, p95 RTT 23.3 ms, backlog 18.24 pkt | [`run34_fq_pie_staged_s1.png`](runs/run34_fq_pie_staged_s1.png) |
| **RUN 35** | fq_pie_staged_s2 | fq_pie, staged workload, seed 2 — goodput 9.1944 Mbps, p95 RTT 23.2 ms, backlog 18.87 pkt | [`run35_fq_pie_staged_s2.png`](runs/run35_fq_pie_staged_s2.png) |
| **RUN 36** | fq_pie_staged_s3 | fq_pie, staged workload, seed 3 — goodput 9.2358 Mbps, p95 RTT 23.2 ms, backlog 18.71 pkt | [`run36_fq_pie_staged_s3.png`](runs/run36_fq_pie_staged_s3.png) |
| **RUN 37** | fq_pie_steady_s1 | fq_pie, steady workload, seed 1 — goodput 9.4285 Mbps, p95 RTT 23.3 ms, backlog 11.62 pkt | [`run37_fq_pie_steady_s1.png`](runs/run37_fq_pie_steady_s1.png) |
| **RUN 38** | fq_pie_steady_s2 | fq_pie, steady workload, seed 2 — goodput 9.4996 Mbps, p95 RTT 23.2 ms, backlog 12.73 pkt | [`run38_fq_pie_steady_s2.png`](runs/run38_fq_pie_steady_s2.png) |
| **RUN 39** | fq_pie_steady_s3 | fq_pie, steady workload, seed 3 — goodput 9.4297 Mbps, p95 RTT 23.3 ms, backlog 11.47 pkt | [`run39_fq_pie_steady_s3.png`](runs/run39_fq_pie_steady_s3.png) |
| **RUN 40** | pfifo_staged_s1 | pfifo, staged workload, seed 1 — goodput 8.5918 Mbps, p95 RTT 2339.0 ms, backlog 564.36 pkt | [`run40_pfifo_staged_s1.png`](runs/run40_pfifo_staged_s1.png) |
| **RUN 41** | pfifo_staged_s2 | pfifo, staged workload, seed 2 — goodput 8.303 Mbps, p95 RTT 2300.0 ms, backlog 558.08 pkt | [`run41_pfifo_staged_s2.png`](runs/run41_pfifo_staged_s2.png) |
| **RUN 42** | pfifo_staged_s3 | pfifo, staged workload, seed 3 — goodput 8.2458 Mbps, p95 RTT 2315.0 ms, backlog 588.19 pkt | [`run42_pfifo_staged_s3.png`](runs/run42_pfifo_staged_s3.png) |
| **RUN 43** | pfifo_steady_s1 | pfifo, steady workload, seed 1 — goodput 9.4101 Mbps, p95 RTT 2359.0 ms, backlog 778.62 pkt | [`run43_pfifo_steady_s1.png`](runs/run43_pfifo_steady_s1.png) |
| **RUN 44** | pfifo_steady_s2 | pfifo, steady workload, seed 2 — goodput 9.4736 Mbps, p95 RTT 2339.0 ms, backlog 793.82 pkt | [`run44_pfifo_steady_s2.png`](runs/run44_pfifo_steady_s2.png) |
| **RUN 45** | pfifo_steady_s3 | pfifo, steady workload, seed 3 — goodput 9.4757 Mbps, p95 RTT 2334.0 ms, backlog 795.29 pkt | [`run45_pfifo_steady_s3.png`](runs/run45_pfifo_steady_s3.png) |
| **RUN 46** | pie_staged_s1 | pie, staged workload, seed 1 — goodput 9.1959 Mbps, p95 RTT 51.0 ms, backlog 10.75 pkt | [`run46_pie_staged_s1.png`](runs/run46_pie_staged_s1.png) |
| **RUN 47** | pie_staged_s2 | pie, staged workload, seed 2 — goodput 9.2418 Mbps, p95 RTT 47.8 ms, backlog 10.0 pkt | [`run47_pie_staged_s2.png`](runs/run47_pie_staged_s2.png) |
| **RUN 48** | pie_staged_s3 | pie, staged workload, seed 3 — goodput 9.2322 Mbps, p95 RTT 46.9 ms, backlog 10.24 pkt | [`run48_pie_staged_s3.png`](runs/run48_pie_staged_s3.png) |
| **RUN 49** | pie_steady_s1 | pie, steady workload, seed 1 — goodput 9.406 Mbps, p95 RTT 47.4 ms, backlog 8.7 pkt | [`run49_pie_steady_s1.png`](runs/run49_pie_steady_s1.png) |
| **RUN 50** | pie_steady_s2 | pie, steady workload, seed 2 — goodput 9.4254 Mbps, p95 RTT 47.2 ms, backlog 8.77 pkt | [`run50_pie_steady_s2.png`](runs/run50_pie_steady_s2.png) |
| **RUN 51** | pie_steady_s3 | pie, steady workload, seed 3 — goodput 9.4072 Mbps, p95 RTT 46.2 ms, backlog 9.05 pkt | [`run51_pie_steady_s3.png`](runs/run51_pie_steady_s3.png) |
| **RUN 52** | red_staged_s1 | red, staged workload, seed 1 — goodput 9.2535 Mbps, p95 RTT 94.2 ms, backlog 21.39 pkt | [`run52_red_staged_s1.png`](runs/run52_red_staged_s1.png) |
| **RUN 53** | red_staged_s2 | red, staged workload, seed 2 — goodput 9.1977 Mbps, p95 RTT 94.0 ms, backlog 22.31 pkt | [`run53_red_staged_s2.png`](runs/run53_red_staged_s2.png) |
| **RUN 54** | red_staged_s3 | red, staged workload, seed 3 — goodput 9.2849 Mbps, p95 RTT 94.3 ms, backlog 21.73 pkt | [`run54_red_staged_s3.png`](runs/run54_red_staged_s3.png) |
| **RUN 55** | red_steady_s1 | red, steady workload, seed 1 — goodput 9.4726 Mbps, p95 RTT 87.3 ms, backlog 26.57 pkt | [`run55_red_steady_s1.png`](runs/run55_red_steady_s1.png) |
| **RUN 56** | red_steady_s2 | red, steady workload, seed 2 — goodput 9.3863 Mbps, p95 RTT 88.3 ms, backlog 26.63 pkt | [`run56_red_steady_s2.png`](runs/run56_red_steady_s2.png) |
| **RUN 57** | red_steady_s3 | red, steady workload, seed 3 — goodput 9.4894 Mbps, p95 RTT 86.5 ms, backlog 26.85 pkt | [`run57_red_steady_s3.png`](runs/run57_red_steady_s3.png) |
| **RUN 58** | sfq_staged_s1 | sfq, staged workload, seed 1 — goodput 9.1821 Mbps, p95 RTT 57.4 ms, backlog 96.93 pkt | [`run58_sfq_staged_s1.png`](runs/run58_sfq_staged_s1.png) |
| **RUN 59** | sfq_staged_s2 | sfq, staged workload, seed 2 — goodput 9.4066 Mbps, p95 RTT 55.0 ms, backlog 92.86 pkt | [`run59_sfq_staged_s2.png`](runs/run59_sfq_staged_s2.png) |
| **RUN 60** | sfq_staged_s3 | sfq, staged workload, seed 3 — goodput 9.1979 Mbps, p95 RTT 57.4 ms, backlog 99.79 pkt | [`run60_sfq_staged_s3.png`](runs/run60_sfq_staged_s3.png) |
| **RUN 61** | sfq_steady_s1 | sfq, steady workload, seed 1 — goodput 9.3558 Mbps, p95 RTT 36.2 ms, backlog 117.58 pkt | [`run61_sfq_steady_s1.png`](runs/run61_sfq_steady_s1.png) |
| **RUN 62** | sfq_steady_s2 | sfq, steady workload, seed 2 — goodput 9.3542 Mbps, p95 RTT 36.1 ms, backlog 115.49 pkt | [`run62_sfq_steady_s2.png`](runs/run62_sfq_steady_s2.png) |
| **RUN 63** | sfq_steady_s3 | sfq, steady workload, seed 3 — goodput 9.4238 Mbps, p95 RTT 36.0 ms, backlog 116.42 pkt | [`run63_sfq_steady_s3.png`](runs/run63_sfq_steady_s3.png) |
