# Independent Verification Report

**Subject:** `ccn-linux-qdisc-study` / ACAPE, as of commit `fab1db5`
**Method:** re-analysis of all 349 committed log files, source review, and live
re-testing on a purpose-built Linux kernel
**Date:** 2026-09-29

Every claim below is backed either by a recomputation over the committed logs
or by an experiment run during this verification. Where a claim is refuted, the
evidence is quoted.

---

## Summary of findings

### Confirmed ✅

| Claim | Evidence |
|---|---|
| Jain's fairness ≈ 0.9997 | Recomputed from per-stream iperf3 data: 0.9996, 0.99999 across 25 runs |
| Aggregate throughput ≈ link capacity | 9.47, 9.59 Mbps at 10 Mbit; 4.78, 4.79 at 5 Mbit, across 25 runs |
| eBPF program compiles, attaches, JITs | Live: `id 7 name tc_egress_monit ... jited` |
| BPF maps readable across namespaces | Live: `map_ids 3,4,5` visible from host; 10 live flow entries |

### Refuted or unsupported ❌

| # | Claim | Finding |
|---|---|---|
| 1 | Part 1 characterised qdiscs on `wlp4s0` | All traffic ran over **loopback at 93-219 Gbit/s**; no log mentions `wlp4s0` |
| 2 | Part 2 RTT: 0.541 / 2.200 / 2.445 / 5.280 ms | **No RTT was ever measured** anywhere in the repository |
| 3 | Part 2 aggregate throughput 10.1 Mbps | Exceeds the 10 Mbit link and every logged value (max 9.59) |
| 4 | Parts 2, 4 created a data-path bottleneck | The two-node topology shaped the **ACK path**; data ran unshaped at 9,777 Mbps |
| 5 | Drop rates ~120,000/s are "correct AQM behaviour" | A 10 Mbit link passes at most **826 pkt/s**; artefact of finding 4 |
| 6 | C3, eBPF workload profiling worked | `active_flows` = 0 in **21,128 / 21,128** samples (three decode bugs) |
| 7 | eBPF elephant classification is exercised | Threshold (10 MB) **exceeds a flow's maximum possible share** (9.38 MB) |
| 8 | C2, predictive control acts before transitions | All **375** logged adjustments applied the identical action |
| 9 | "15 AIMD adjustments" is a result | It is `⌈log(1/5)/log(0.9)⌉`, structural, not measured |
| 10 | `target` followed a 5.00to1.03 ms staircase | The kernel received `5,4,4,4,3,3,3,2,2,2,2,2,1,1,1,1` |
| 11 | Backlog table 434 / 412 / 357 / 314 pkts | Appears in no log. Measured: 21.7 / 16.4 /, / 15.6 |
| 12 | "12× faster stabilisation" | The chart is the **hardcoded array** `[120, 70, 60, 5]` |
| 13 | The C2 predictive figure shows measured data | Falls back to **hardcoded timestamp arrays** when logs are empty, which they are |
| 14 | "Adaptive RED" baseline (Floyd et al.) | `adaptive_red.py` contains **zero** references to the `red` qdisc |
| 15 | `prog_id = 49152` | 49152 is the **tc filter priority**, not a program id |
| 16 | rtt_proxy flat due to "namespace fd isolation" | Maps were populated throughout; the fault was a userspace decode bug |
| 17 | F1 affects only `acape_v5.py` | Present in every measurement path, **including the Grafana exporter** |

---

## 1. What holds up

### 1.1 Fairness

Recomputing `J = (Σxᵢ)² / (n·Σxᵢ²)` directly from per-stream
`bits_per_second` in every iperf3 JSON gives 0.9996, 0.99999 across 25 runs. The
claim is real and reproducible.

It is, however, a property of **fq_codel's DRR scheduler**, not of any
adaptation: every flow-queueing discipline in the corrected suite shows it
equally. A high Jain index is weak evidence for an AQM contribution.

### 1.2 Throughput

8-flow runs deliver 9.47, 9.59 Mbps against a 10 Mbit TBF; 20-flow runs deliver
4.78, 4.79 against 5 Mbit. Consistent and plausible.

### 1.3 The eBPF program itself

Verified live on kernel 6.18:

```
clang -O2 -g -target bpf -c tc_monitor.c -o tc_monitor.o     # clean
tc filter add dev veth1 egress bpf da obj tc_monitor.o sec tc_egress
tc filter show dev veth1 egress
  -> ... id 7 name tc_egress_monit tag 64c7d27d385b654b jited
bpftool prog show -> map_ids 3,4,5
bpftool map dump id 3 -> 10 live flow entries
```

The kernel side is correct. Every failure below is in userspace.

---

## 2. Traffic never reached the system under study

### 2.1 Parts 1, 3 ran over loopback

The README states Part 1 characterised `pfifo_fast` and `fq_codel` on the WiFi
interface `wlp4s0`. The log:

```
$ head -2 logs/phase1_iperf.log
Connecting to host 127.0.0.1, port 5201
[SUM]   0.00-1.00   sec  22.9 GBytes   197 Gbits/sec    0
```

Traffic went to **127.0.0.1**. Loopback does not traverse `wlp4s0`, so
`tc qdisc add dev wlp4s0 root pfifo_fast` had no effect on it. The README's own
command listing shows `iperf3 -c 127.0.0.1 -P 8 -t 30` under text describing
WiFi characterisation.

Peak aggregate rates confirm no shaper was ever in the path:

| Log | Peak aggregate | Nominal bottleneck |
|---|---|---|
| `phase1_iperf.log` | **219 Gbit/s** | pfifo_fast on wlp4s0 |
| `phase2A_iperf.log` | **95.0 Gbit/s** | TBF 5 Mbit |
| `phase2B_iperf.log` | **93.2 Gbit/s** | TBF 5 Mbit |
| `phase3A_iperf.log` | **112 Gbit/s** | TBF + fq_codel |
| `phase3B_iperf.log` | **110 Gbit/s** | TBF + fq_codel |

No file in the repository mentions `wlp4s0`:

```
$ grep -rl "wlp4s0" logs/
(no matches)
```

Every Part 1 finding describes behaviour that could not have been observed:
"bursty drop clusters", "fq_codel distributed drops more evenly",
"Jain ~0.89 vs 0.9997", "P95 latency > 15 ms".

### 2.2 Parts 2, 4 shaped the acknowledgement path

README §5 attaches the bottleneck to `veth1 root` inside `ns1`, then runs
`iperf3 -c 10.0.0.1` from `ns2`. Data flows ns2 to ns1, but an egress qdisc on
`veth1` shapes only ns1 to ns2, the **acknowledgement** direction.

Reproduced live with the README's exact configuration:

```
ns2 -> ns1, 8 flows, 15 s:   delivered 9,777 Mbps        (UNSHAPED)
tc -s qdisc show dev veth1:  18,769,790 bytes / 284,379 pkt
                             = 66 bytes/packet  -> pure TCP ACKs
                             overlimits 809,536
eBPF pkt_size_hist:          <128B: 341,243    512-1500B: 2
```

99.999% of packets crossing the monitored qdisc were sub-128-byte
acknowledgements.

**This explains the impossible drop rates.** A 10 Mbit shaper passes
10e6/(66·8) ≈ 18,900 ACK/s; the unshaped multi-Gbit data stream generates far
more, and the excess is dropped. Logged rates of 100,000-138,000 drops/s are
consistent with ACK overflow and inconsistent with the data path: at 10 Mbit
with 1514-byte packets the link carries at most **826 pkt/s**, and iperf3
reports only ~179 retransmits/s.

Measured: 100% of samples in 19 of 32 ACAPE runs exceed the physical packet
rate; median logged drop rate up to 128,208/s, **155× the link's packet rate**.

> The later three-node topology in `run_one_system.sh` (ns2 ↔ ns_router ↔ ns1,
> AQM on `veth_rs`) **is correct**. Only the README's Parts 2, 4 and the paper's
> main ACAPE results use the broken one.

### 2.3 No RTT was ever measured

The README's Part 2 table reports Avg RTT 0.541 ms, P95 2.200 ms, P99 2.445 ms,
Max 5.280 ms; the paper repeats P95 = 2.2 ms. There is no RTT measurement
anywhere in the repository:

```
$ grep -rlE "icmp_seq|min/avg/max|rtt min/avg/max" logs/
(no matches)
```

No `ping` output, no iperf3 latency mode, no timestamp-based estimate. These
numbers have no source. (The `rtt_proxy` column is the eBPF inter-packet gap,
which is 0.000 in every sample, see §3.)

The claimed 10.1 Mbps aggregate also exceeds both the 10 Mbit link and every
logged value (maximum 9.59 Mbps).

---

## 3. The eBPF telemetry never produced a reading

`active_flows` = 0 in **21,128 of 21,128 samples (100%)** across all 32 runs;
`workload_profile` = MICE in 100%; `elephant_flows` = 0 always.

Four independent defects, each sufficient on its own.

### 3.1 A `TypeError` swallowed by a bare `except`

`bpftool map dump --json` renders byte arrays as hex **strings**
(`['0xa0','0xb8'...]`). `bytes(raw[16:24])` raises
`TypeError: 'str' object cannot be interpreted as an integer`; the surrounding
`except: pass` discarded it and returned zeros.

### 3.2 Wrong struct offsets

The layout comment omitted `first_seen_ns`:

```
true : packets@0  bytes@8  first_seen@16  last_seen@24  gap@32  is_elephant@40
code : packets@0  bytes@8  last_ns@16     gap@24        is_eleph@32
```

Every field after `bytes` was read at the wrong offset; `is_elephant` was read
from the low 4 bytes of `interpacket_gap_ns`.

### 3.3 Clock-domain mismatch

`age = (time.time_ns() - last_ns) / 1e9` compares CLOCK_REALTIME against
`bpf_ktime_get_ns()` (CLOCK_MONOTONIC). Measured live: age = **56.8 years**, so
`if age < 2.0` never matched.

### 3.4 An elephant threshold that cannot fire

Independently of the above, `tc_monitor.c` defined:

```c
#define ELEPHANT_BYTES   10000000ULL   /* 10 MB */
```

A 60-second run at 10 Mbit carries 75 MB in total, so with 8 concurrent flows a
single flow's maximum possible share is **9.38 MB**, below the threshold. Even
with the decode path fixed, `elephant_flows` remained 0 in all 85 corrected
samples.

**Consequence.** `elephant_ratio` is always 0.0, `select_workload()` always
returns MICE, `quantum` is always 300 B. The paper cites "quantum = 300 B
confirms MICE profile fired" as evidence the pipeline works; it is the
signature of the failure. **The ELEPHANT and MIXED profiles were unreachable in
every experiment this project has run.**

The failure was attributed to "a namespace file-descriptor isolation issue".
That diagnosis is wrong: BPF maps are kernel-global and readable from the host
by id, as verified in §1.3.

A further defect in the same file: `parse_key()` located the transport header at
`(ip + 1)`, assuming a 20-byte IP header, so ports are misread when IP options
are present.

---

## 4. The predictive controller never changed the control action

Across all 32 runs: **375 adjustments, 367 `[REACTIVE]`, 8 `[PREDICTIVE]`**,
and the 8 are confined to one early run. The distinct actions ever applied:

```
mult-decrease β=0.9
mult-decrease β=0.9 (regime=HEAVY pred=HEAVY)
mult-decrease β=0.9 (regime=HEAVY pred=MODERATE)
```

Every adjustment in the corpus is the same multiplicative decrease. Cause, in
`aimd()`:

```python
eff = pred if traj=="WORSENING" else regime
```

`predict()` returns `REGIMES[idx+1]` only `if idx<3`; with regime = HEAVY
(idx 3) that branch cannot fire, so a worsening HEAVY is reported STABLE.
Regime is HEAVY in 80.9% of samples and NORMAL in 19.0% (MODERATE 0.04%, LIGHT
0%), a four-state classifier occupying two states.

The README's example adjustment log is also inconsistent with every real log:
it shows `RECOVERING to [PREDICTIVE]`, while the code and all logged data
produce `RECOVERING to [REACTIVE]`.

---

## 5. Reported values that never reached the kernel

### 5.1 The target staircase

`apply_params()` emits `target f"{int(round(p['target']))}ms"`. Later versions
keep an internal float and never read it back, so controller state diverges
from qdisc state:

```
logged / in paper : 5.00 4.50 4.05 3.65 3.28 2.95 ... 1.27 1.14 1.03
actually applied  : 5    4    4    4    3    3    ... 1    1    1
```

Sixteen distinct steps collapse to five values. fq_codel accepts sub-millisecond
targets as `us`; integer-millisecond rounding discards them.

### 5.2 "15 adjustments"

24 of 32 runs log exactly 15 adjustments. This is
`⌈log(1/5)/log(0.9)⌉`, the number of ×0.9 steps from 5 ms to the 1 ms floor.
The controller drove to the floor and stopped in every run because the regime
was saturated HEAVY from t=0. The testbed never exercised the adaptive logic.

---

## 6. The headline figures are hardcoded

`scripts/plot_comparison.py` produced `comparison_bars.png`,
`comparison_predictive.png` and `comparison_table.png`, all reproduced in the
paper. It contains literal values in place of measurements.

**(a) The stabilisation chart (lines 433, 444)** is entirely constant:

```python
stab = [120, 70, 60, 5]
stab_labels = ["never\n(>120s)", "~70 s", "~60 s", "<5 s  ★"]
ax.text(2.85, 14, "12× faster\nthan A.RED", ...)
```

This is the sole origin of the "12× faster stabilisation" claim. No
stabilisation time was ever measured.

**(b) The C2 figure (lines 307, 310)** substitutes hardcoded timestamps under a
comment asserting they are measured:

```python
if not pred_t and not react_t:
    # From actual measured run
    react_t = [5.1, 10.2, 25.7, 30.8, 41.1, 56.5]
    pred_t  = [15.4, 20.5, 35.9, 46.2, 51.3, 61.6, 66.7, 71.9, 77.0]
```

31 of 32 adjustment logs contain zero PREDICTIVE entries, so this fallback
fires.

**(c) The summary table (lines 486, 492)** is string literals:

```python
["Avg queue backlog", "~450 pkts", "~320 pkts", "~270 pkts", "~240 pkts  " + T],
["Stabilises in",     "never",     "~70 s",     "~60 s",     "<5 s  " + T],
```

**(d) A silent substitution (lines 259, 398):**
`np.mean(valid(P["bl"])) if valid(P["bl"]) else 270`.

The two fabricated sets disagree with each other, 450/320/270/240 in the plot
script versus 434/412/357/314 in the paper, and both disagree with the
measured data (21.7/16.4/–/15.6).

These may be development placeholders never removed. Either way, **the figures
presenting the project's headline results are not derived from its
measurements.**

---

## 7. The comparison baselines

### 7.1 "Adaptive RED" is not Adaptive RED

`scripts/adaptive_red.py` is presented as the Floyd et al. (2001) baseline. It
contains **zero** references to the `red` qdisc:

```
$ grep -c '\bred\b' scripts/adaptive_red.py
0
```

Every adjustment it makes is `tc qdisc change ... fq_codel ...`. It maintains a
simulated `max_p` and maps it linearly onto `fq_codel`'s `target` and `limit`.
The claim "24% lower backlog than Adaptive RED" therefore compares ACAPE against
**a second fq_codel controller written for this project**. The file's docstring
concedes this; the paper does not.

Linux ships Floyd's algorithm as `tc qdisc add ... red ... adaptive`.

### 7.2 Selective reporting

The measured `*_recorded.csv` data gives mean backlogs of: static_fqcodel 21.7,
adaptive_red 16.4, **pie 7.8**, acape 15.6 packets. **PIE achieves a lower
backlog than ACAPE** on the paper's own primary metric. PIE and CAKE are
omitted from the headline table despite data existing for both.

### 7.3 The measurement path reads the wrong qdisc

`re.search()` over the full `tc -s qdisc show` output always matches the **root**
stanza. With TBF as root and the AQM as its child, every recorded statistic is
the shaper's. Present in:

| File | Lines |
|---|---|
| `scripts/controller.py` | 66, 73, 80 |
| `scripts/record_metrics.py` | 33, 37, 38 |
| `scripts/acape_exporter.py` | 91, 93, 95 |
| `scripts/adaptive_red.py` | 60, 62, 64 |
| `scripts/acape_v5.py` | 238, 240 |

Because the Prometheus exporter is affected, the Grafana panels reproduced in
the paper (backlog = 355 p, drop rate = 22,201/s) were displaying the TBF
shaper's counters throughout.

### 7.4 Inconsistent identifiers

`prog_id` appears as **527** (README), **91** (paper Fig. grafana), and **49152**
(paper §Known Limitation). Live testing shows 49152 is the tc filter
preference (`pref 49152`, tc's default), not a BPF program id.

---

## 8. What was re-tested, and how

| Finding | Method |
|---|---|
| Loopback in Parts 1, 3 | Direct inspection of committed logs |
| ACK-path topology | Rebuilt the README's exact topology and measured |
| Drop rate impossibility | Arithmetic against link rate; cross-checked with iperf3 retransmits |
| eBPF decode bugs | Reproduced against a live `flow_map` entry |
| Elephant threshold | Arithmetic against link capacity; confirmed on corrected runs |
| Predictive control | Recomputed over all 375 logged adjustments |
| Hardcoded figures | Source inspection |
| RED baseline | Source inspection (`grep -c '\bred\b'`) |
| Fairness, throughput | Recomputed from per-stream iperf3 JSON |

The corrected implementation is in `src/`, with the four userspace defects
pinned by 17 regression tests in `tests/test_acape.py`, each of which fails
against the original behaviour.

---

## 9. Assessment

Parts 1 and 2 measured loopback traffic and report latency figures with no
source. Parts 3 and 4 measured acknowledgement-path queueing. The two claimed
novel contributions (C2 predictive control, C3 eBPF workload profiling) never
functioned. The headline comparison figures are hardcoded. The named baseline
is not the algorithm it is named after.

We do not think this is recoverable by correcting the existing paper. The
apparatus, however, is sound in outline: the eBPF program is correct, the
three-node topology in `run_one_system.sh` is correct, and the fairness and
throughput results hold. The corrected work in `src/`, `paper/` and `results/`
rebuilds on that foundation.

The recurring pattern is worth stating on its own: every one of these failures
produced output that was confident, internally consistent, and wrong. None was
visible from a summary statistic. Each was caught only by checking a physical
invariant, bytes per packet, the link's maximum packet rate, whether a control
input changes its output, whether a threshold is reachable at all.
