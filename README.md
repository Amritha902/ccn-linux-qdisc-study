# ACAPE, Runtime Parameter Adaptation for `fq_codel`

**A measured evaluation of whether adapting `fq_codel`'s parameters at runtime improves on its defaults, and a pre-registered law saying when it does.**

The answer is a dimensionless ratio. Benefit is governed by `r = target/RTT`,
with half of it reached at `r = 0.50`, while a correctly configured deployment
sits five to ten times below that. Adaptation repairs misconfiguration rather
than improving on correct configuration. See `STATUS.md` for the result in
full and `SUBMIT.md` for the deliverables.

Amritha S · Yugeshwaran P · Deepti Annuncia
Department of Electronics and Communication Engineering, SENSE, VIT Chennai

---

## What this project is

Linux's default queue discipline, `fq_codel`, exposes four parameters fixed at
configuration time: `target` (5 ms), `interval` (100 ms), `limit` (10240
packets) and `quantum` (1514 bytes). This project asks whether adapting them
while the system runs improves on leaving them alone, and answers it by
measurement against every other queue discipline Linux ships.

It contains:

- a **three-node namespace testbed** where the bottleneck is on the data path
- an **eBPF flow-telemetry pipeline** at the `tc` egress hook, read through `bpf(2)`
- a **userspace controller** adapting all four parameters by AIMD under a
 gradient-based congestion trajectory estimate
- a **pre-registered scaling law** saying when that adaptation is worth running
- a **reproducible experiment suite** over 9 queue-discipline configurations,
 2 workloads and 3 seeds
- an **analysis pipeline** that generates every table and figure directly from
 the logs

## What this project found

Two things, and the second is more useful than the first.

**1. The dominant effect is flow queueing, not parameter tuning.** On an
identical 10 Mbit bottleneck, an unmanaged FIFO reaches ~2400 ms p95 latency
while every flow-queueing discipline with a delay target holds ~23 ms, at
indistinguishable goodput. That is a ~100× difference. The difference between
static and adaptively-tuned `fq_codel` is far smaller. See
[`paper/`](paper/) for the full results with confidence intervals.

**2. An earlier version of this work reported results that do not survive
scrutiny.** Those results were produced by a testbed that measured the wrong
traffic direction and a telemetry pipeline that silently reported zeros. Both
failures were confident, internally consistent, and invisible from any summary
statistic. The corrections are documented in full in
[`verification/VERIFICATION_REPORT.md`](verification/VERIFICATION_REPORT.md),
and the diagnostic techniques that caught them are, we think, the most
transferable part of this work.

---

## The corrections

Independent re-analysis of all 349 original log files plus live re-testing
established the following. Full evidence in
[`verification/VERIFICATION_REPORT.md`](verification/VERIFICATION_REPORT.md).

### Held up ✅

| Claim | Verdict |
|---|---|
| Jain's fairness ≈ 0.9997 | Confirmed, recomputed 0.9996, 0.99999 across 25 runs |
| Throughput ≈ link capacity | Confirmed, 9.47, 9.59 Mbps against 10 Mbit |
| eBPF program compiles, attaches, JITs | Confirmed live |
| BPF maps readable across namespaces | Confirmed, maps are kernel-global |

### Did not hold up ❌

| Claim | Finding |
|---|---|
| The testbed created a data-path bottleneck | The two-node topology shaped the **ACK path**. Data ran unshaped at 9,777 Mbps; the monitored queue carried 66-byte ACKs |
| Drop rates of ~120,000/s were "correct AQM behaviour" | A 10 Mbit link passes at most **826 packets/s**. The figure is an artefact of the above |
| eBPF workload profiling (C3) worked | `active_flows` was 0 in **21,128 of 21,128 samples**, from three decode bugs, plus a threshold that could never fire |
| Predictive control (C2) acted before transitions | All **375 logged adjustments** applied the identical action; the prediction never changed anything |
| "15 AIMD adjustments" was a result | It is `⌈log(1/5)/log(0.9)⌉`, the steps from 5 ms to a 1 ms floor. Structural, not measured |
| `target` followed a 5.00to1.03 ms staircase | The kernel received `5,4,4,4,3,3,3,2,2,2,2,2,1,1,1,1`, integer-ms rounding |
| Backlog table: 434/412/357/314 pkts | Not present in any log. Recomputed: 21.7 / 16.4 /, / 15.6 |
| `prog_id = 49152` | 49152 is the **tc filter priority**, not a program id |

### The five defects

| # | Where | Defect |
|---|---|---|
| F1 | `read_tc()` | `re.search()` over the whole `tc -s qdisc show` output always matched the **root** qdisc, so every statistic was the shaper's, not the AQM's |
| F2a | `read_flows()` | `bpftool --json` returns hex **strings**; `bytes()` on them raised `TypeError` into a bare `except: pass` |
| F2b | `read_flows()` | Struct layout omitted `first_seen_ns`, so every later field was read at the wrong offset |
| F2c | `read_flows()` | `time.time_ns()` (REALTIME) minus `bpf_ktime_get_ns()` (MONOTONIC) to ages of **56.8 years**, so `age < 2s` never matched |
| F3 | `apply_params()` | `int(round(target))` ms collapsed a 16-step schedule onto 5 values; sub-ms targets unrepresentable |
| F4 | `predict()`/`aimd()` | An `idx<3` guard made a worsening HEAVY report STABLE, and the effective regime always equalled the current one |
| F5 | `tc_monitor.c` | 10 MB elephant threshold exceeds a flow's maximum possible share (9.38 MB), so the classifier could never fire |

All are pinned by regression tests in [`tests/test_acape.py`](tests/test_acape.py)
(17 tests), each of which fails against the original behaviour.

---

## Why the topology mattered

```
 ORIGINAL (incorrect) CORRECTED
 ns2 ────────────────► ns1 ns_client ──► ns_router ──► ns_server
 (client) data (server) │
 [TBF+AQM on veth1 │ [TBF + AQM on
 = ns1 egress │ router egress
 = the ACK path] │ = the data path]

 measured: 9,777 Mbps unshaped measured: 9.38 Mbps shaped
 66 bytes/packet (ACKs) 1509 bytes/packet (data)
 ~130,000 drops/s ~19 drops/s
```

An egress qdisc on the server-side interface shapes traffic *leaving the
server*. With the client as sender, that is the acknowledgement direction.

**Two diagnostics catch this in seconds:**
- bytes ÷ packets on the monitored qdisc, 66 means you are queueing ACKs
- drop rate versus the link's maximum packet rate, you cannot drop more
 packets per second than can arrive

---

## Running it

### Requirements

A Linux kernel with `fq_codel`, `codel`, `cake`, `pie`, `fq_pie`, `red`,
`netem` and `tbf`. Most distribution kernels have these as modules.

If your kernel lacks them (many minimal cloud and container kernels do), build
one and run the experiments in a VM:

```bash
# check what your kernel has
for q in fq_codel codel cake pie fq_pie red netem tbf; do
 ip link add probe type veth peer name probe2 2>/dev/null
 tc qdisc replace dev probe root $q >/dev/null 2>&1 \
 && echo "$q: yes" || echo "$q: NO"
 ip link del probe 2>/dev/null
done
```

Building the VM kernel (see [`src/vm.sh`](src/vm.sh) for the boot parameters):

```bash
curl -O https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.12.48.tar.xz
tar xf linux-6.12.48.tar.xz && cd linux-6.12.48
make defconfig
./scripts/config -e NET_SCH_FQ_CODEL -e NET_SCH_CODEL -e NET_SCH_CAKE \
 -e NET_SCH_PIE -e NET_SCH_FQ_PIE -e NET_SCH_RED -e NET_SCH_NETEM \
 -e NET_CLS_BPF -e DEBUG_INFO_BTF -e NET_9P -e NET_9P_VIRTIO -e 9P_FS \
 -e VETH -e NET_NS -d MODULES
make olddefconfig && make -j$(nproc) bzImage
```

### Dependencies

```bash
sudo apt install -y iproute2 iperf3 iputils-ping clang llvm libbpf-dev \
 linux-tools-$(uname -r) qemu-system-x86
pip3 install matplotlib numpy --break-system-packages
```

### One experiment

```bash
sudo python3 src/run_experiment.py --aqm fq_codel --seed 1 \
 --duration 60 --flows 8 --workload steady --outdir results
```

With the adaptive controller and eBPF telemetry:

```bash
sudo python3 src/run_experiment.py --aqm fq_codel --seed 1 \
 --duration 60 --flows 8 --workload staged --adapt --ebpf \
 --outdir results
```

### The full suite

```bash
sudo DUR=60 SEEDS="1 2 3" WORKLOADS="steady staged" bash src/run_suite.sh
```

Inside a VM, wrap any command with [`src/invm.sh`](src/invm.sh):

```bash
bash src/invm.sh 'DUR=60 SEEDS="1 2 3" bash src/run_suite.sh'
```

### Analysis

```bash
python3 src/analyse.py --results results --outdir figures # tables + figures
python3 src/findings.py --results results # significance tests
python3 tests/test_acape.py # regression tests
```

`analyse.py` also emits `table_*.tex` and `facts.tex`, which the paper
`\input`s, no number in the paper is typed by hand.

---

## Repository layout

```
src/
 acape.py corrected controller (supersedes scripts/acape_v5.py)
 bpfmap.py BPF map access via bpf(2) 4.5× faster than bpftool
 testbed.sh three-node router topology
 run_experiment.py one run: traffic, queue time series, ping RTT
 run_suite.sh the full matrix
 recorder.py per-qdisc statistics sampler
 analyse.py tables, figures, LaTeX generation
 findings.py effect sizes and Welch's t-tests
 capture.py step-numbered evidence rendering
 make_evidence.py generates the numbered evidence set
 vm.sh / invm.sh local VM with an AQM-capable kernel
 dump_flows.py live flow_map contents

ebpf/tc_monitor.c TC egress telemetry program
tests/test_acape.py 17 regression tests pinning the defects
verification/ verification report, citation audit, bug demonstrations
docs/ literature survey
paper/ the paper; all numbers generated from results/
results/ per-run logs and summaries
figures/ generated figures, including numbered evidence
scripts/ ORIGINAL implementation, retained unchanged as the record
logs/ ORIGINAL logs, retained unchanged
```

`scripts/` and `logs/` are kept exactly as they were. They are the evidence for
the verification report and should not be treated as current.

---

## Honest scope

- Tested at a **10 Mbit bottleneck with 8, 24 bulk TCP CUBIC flows** and a 20 ms
 base RTT. Not validated at datacentre or backbone rates.
- `--seed` indexes an **independent repetition**, not a PRNG seed; iperf3
 exposes no seed. Confidence intervals describe run-to-run variance.
- **Runtime adaptation of an AQM's delay target is not novel.** DESiRED
 (*Computer Networks*, 2024) does it with deep RL and In-band Network
 Telemetry in P4. What differs here is the deployment surface, stock Linux,
 no kernel or data-plane change, eBPF, and a transparent AIMD rule.
- All flows are bulk transfers. **Mixed workloads with sparse latency-sensitive
 flows are exactly where `fq_codel`'s new-flow heuristic and an adaptive
 `quantum` might matter**, and we did not test them.
- Single bottleneck; no multi-hop topologies.
- Experiments run under QEMU without hardware virtualisation. TBF shaping
 accuracy was validated under emulation before results were collected, but
 results at much higher rates would need re-validation.
- CoDel's authors argue its defaults are RTT-relative and need no tuning. Any
 gain from adaptation must be demonstrated against that position, not assumed
 past it.

---

## Documents

| Document | What it is |
|---|---|
| [`verification/VERIFICATION_REPORT.md`](verification/VERIFICATION_REPORT.md) | What held up, what did not, with the evidence for each |
| [`verification/CITATION_AUDIT.md`](verification/CITATION_AUDIT.md) | Every reference checked against the published record |
| [`docs/LITERATURE_SURVEY.md`](docs/LITERATURE_SURVEY.md) | 30 verified references through 2026, plus an assessment of this work against the current field |
| [`docs/PARAMETER_COMPARISON.md`](docs/PARAMETER_COMPARISON.md) | Every qdisc's parameters; this work vs. Adaptive RED, ACoDel, QueuePilot, DESiRED, AQM-LLM and L4S |
| [`figures/INDEX.md`](figures/INDEX.md) | Numbered index of every figure: STEP (evidence), RUN (per-experiment), FIG (analysis) |
| [`paper/acape.tex`](paper/acape.tex) | The paper. Every number is generated from the logs |

## Measurement notes

Three things this study does that the original did not, and that we think any
AQM measurement should:

1. **Report both sparse-probe and bulk-flow latency.** `fq_codel`'s new-flow
 heuristic privileges a sparse ICMP probe, so the probe and the bulk flows
 sharing the link report substantially different RTT. Quoting only the probe
 overstates the benefit to bulk traffic.
2. **Take goodput from `sum_received`, never `sum_sent`.** Under a bloated
 buffer the sender reports more than the link can carry, 12.16 Mbps on a
 10 Mbit link in one `pfifo` run.
3. **Run a sham-controller condition.** The controller polls at the same
 cadence but applies nothing, so its CPU cost can be separated from its
 control decisions. Without it the two are confounded in any latency
 comparison.

## License

GPL-2.0 (the eBPF program is GPL-licensed as the kernel requires).
