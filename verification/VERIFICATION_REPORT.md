# Independent Verification Report — ACAPE / ccn-linux-qdisc-study

**Verifier:** automated re-analysis of all 349 log files + live kernel re-testing
**Date:** 2026-09-29
**Environment:** Ubuntu 24.04, kernel 6.18.44 (Firecracker microVM), root, eBPF+BTF available

This report records what could be **confirmed**, what could be **refuted**, and what
**could not be tested** in this environment. Every claim below is backed either by a
recomputation over the committed logs or by a live experiment run in this container.

---

## 0. Summary

| # | Claim | Verdict |
|---|---|---|
| 1 | Jain's Fairness Index ≈ 0.9997 | **CONFIRMED** (recomputed 0.9996–0.99999 over 25 runs) |
| 2 | Aggregate throughput ≈ link capacity | **CONFIRMED** (9.57 Mbps @10 Mbit; 4.78 @5 Mbit) |
| 3 | eBPF program compiles, attaches, JITs | **CONFIRMED** (live: `id 7 ... jited`) |
| 4 | BPF maps readable from host across netns | **CONFIRMED** (live: `map_ids 3,4,5` visible) |
| 5 | C3 — eBPF elephant/mice → fq_codel profiles | **REFUTED** — dead in 100% of 21,128 ticks (3 bugs) |
| 6 | C2 — predictive control acts before transitions | **REFUTED** — prediction never changes the action |
| 7 | "15 AIMD adjustments" as a measured result | **REFUTED** — structurally fixed constant |
| 8 | target staircase 5.00→1.03 ms applied to kernel | **REFUTED** — kernel received 5,4,4,4,3,3,3,2,2,2,2,2,1,1,1,1 |
| 9 | Headline table 434/412/357/314 pkts backlog | **UNSUPPORTED** — measured data gives 21.7/16.4/–/15.6 |
| 10 | Drop rate ~120,000 s⁻¹ is "correct AQM behaviour" | **REFUTED** — artifact of measuring the ACK path |
| 11 | Parts 2–4 testbed creates a data-path bottleneck | **REFUTED** — 2-node topology shapes ACKs only |
| 12 | "prog_id = 49152" | **REFUTED** — 49152 is the tc filter *priority*, not a prog id |
| 13 | rtt_proxy flat due to "namespace fd isolation" | **REFUTED** — real cause is a userspace decode bug |
| 14 | eBPF elephant/mice classification is exercised | **REFUTED** — threshold is unreachable at this link rate |
| 15 | "Adaptive RED" is the Floyd et al. baseline | **REFUTED** — it never instantiates the `red` qdisc; it is a second fq_codel controller |
| 16 | The F1 qdisc-selection bug is confined to `acape_v5.py` | **REFUTED** — present in every measurement path, including the Grafana exporter |
| 17 | The headline figures were plotted from the logs | **REFUTED** — the stabilisation chart, the C2 figure and the summary table are hardcoded literals |

---

## 1. What holds up

### 1.1 Fairness (solid)
Recomputed J = (Σxᵢ)²/(n·Σxᵢ²) directly from per-stream `bits_per_second` in every
iperf3 JSON:

```
static_fqcodel (8 flows)  J = 0.99960 – 0.99999
acape          (8 flows)  J = 0.99990 – 0.99998
adaptive_red   (8 flows)  J = 0.99997 – 0.99999
pie            (20 flows) J = 0.99636   <- only outlier, notably worse
```
The fairness claim is real and reproducible. It is, however, a property of
**fq_codel's DRR**, not of ACAPE — all systems that use fq_codel show it.

### 1.2 Throughput (solid)
8-flow runs deliver 9.47–9.59 Mbps against a 10 Mbit TBF (95–96%); 20-flow runs
deliver 4.78–4.79 Mbps against 5 Mbit. Consistent across 25 runs.

### 1.3 eBPF loads and runs (solid)
Live in this container:
```
clang -O2 -g -target bpf -c tc_monitor.c -o tc_monitor.o     # clean
tc filter add dev veth1 egress bpf da obj tc_monitor.o sec tc_egress
tc filter show dev veth1 egress
  -> ... id 7 name tc_egress_monit tag 64c7d27d385b654b jited
bpftool prog show -> map_ids 3,4,5   (flow_map, global_map, pkt_size_hist)
bpftool map dump id 3 -> 10 live flow entries
```
The kernel side is genuinely correct. The failure is entirely in userspace.

---

## 2. What does not hold up

### 2.1 The 2-node testbed shapes the ACK path, not the data path (Parts 2–4)

README §5 puts the bottleneck on `veth1 root` **inside ns1**, and runs
`iperf3 -c 10.0.0.1` **from ns2**. Data therefore flows ns2 → ns1, but an egress
qdisc on veth1 shapes only ns1 → ns2 — the **acknowledgement** direction.

Reproduced live (TBF 10mbit + child qdisc, identical to README):
```
ns2 -> ns1, 8 flows, 15 s:   delivered 9,777 Mbps   (9.8 Gbit/s — UNSHAPED)
tc -s qdisc show dev veth1:  Sent 18,769,790 bytes / 284,379 pkt
                             => 66 bytes/packet   = pure TCP ACKs
                             overlimits 809,536
eBPF pkt_size_hist:          bucket<128B = 341,243 ;  bucket 512-1500B = 2
```
99.999% of packets crossing the monitored qdisc are sub-128-byte ACKs. Every
Part 2/3/4 backlog, drop and sojourn figure is a measurement of ACK queueing.

**This also explains the impossible drop rates.** A 10 Mbit shaper passes
10e6/(66·8) ≈ 18,900 ACK/s; the unshaped 9.8 Gbit/s data stream generates far more,
so the excess is dropped. Logged rates of 100,000–138,000 drops/s are consistent
with ACK overflow and **inconsistent** with the data path: at 10 Mbit with 1514 B
packets the link carries at most **826 pkt/s**, and iperf3 reports only
**~179 retransmits/s**. The paper's explanation ("CoDel at 1 ms target drops
earlier") is not the mechanism.

Measured: 100% of ticks in 19 of 32 ACAPE runs exceed the physical packet rate,
median logged drop rate up to 128,208 s⁻¹ — i.e. **155× the link's packet rate**.

> The later 3-node topology in `run_one_system.sh`
> (ns2 ↔ ns_router ↔ ns1, AQM on `veth_rs`) **is correct** — the router's egress
> really is the data path. The 4-system comparison logs come from that setup.
> Only the README's Parts 2–4 and the paper's main ACAPE results use the broken one.

### 2.2 C3 (eBPF workload profiles) never executed — three independent bugs

`active_flows` = 0 in **21,128 / 21,128 ticks (100%)** across all 32 runs.
`workload_profile` = MICE in 100% of ticks. `elephant_flows` = 0 always.

`scripts/acape_v5.py::read_flows()` contains three defects, each individually fatal:

**(a) Type error swallowed by a bare `except`.** `bpftool map dump --json` returns
byte arrays as hex *strings* (`['0xa0','0xb8',...]`). `bytes(raw[16:24])` raises
`TypeError: 'str' object cannot be interpreted as an integer`; the surrounding
`except: pass` discards it silently and returns zeros.

**(b) Wrong struct offsets.** The code's comment omits `first_seen_ns`:
```
true  : packets@0  bytes@8  first_seen@16  last_seen@24  gap@32  is_elephant@40
code  : packets@0  bytes@8  last_ns@16     gap@24        is_eleph@32
```
Every field after `bytes` is read from the wrong offset — `is_elephant` is read
from the low 4 bytes of `interpacket_gap_ns`.

**(c) Clock-domain mismatch.** `age = (time.time_ns() - last_ns)/1e9` compares
CLOCK_REALTIME (since 1970) against `bpf_ktime_get_ns()` (CLOCK_MONOTONIC, since
boot). Measured live: age = 1,790,676,853 s ≈ **56.8 years**, so `if age < 2.0` is
never true and no flow is ever counted active.

Consequence: `elephant_ratio` is always 0.0 → `select_workload()` always returns
MICE → `quantum` always forced to 300 B. The paper cites "quantum = 300 B confirms
MICE profile fired" as *evidence the pipeline works*; it is in fact the signature
of the bug. The `rtt_proxy` "Known Limitation" has the same cause — it is a
userspace decode bug, **not** "namespace file-descriptor isolation".

### 2.2b The elephant threshold can never fire at this link rate

Independently of the three decode bugs above, `ebpf/tc_monitor.c` defined:

```c
#define ELEPHANT_BYTES   10000000ULL   /* 10 MB threshold */
```

A 60-second run at 10 Mbit carries 75 MB in total. With 8 concurrent flows a
single flow's maximum possible share is **9.38 MB** — below the threshold. Even
with the decode path fixed, `elephant_flows` is 0 in every sample:

```
elephant_flows across all corrected ACAPE ticks: 0 (of 85 ticks)
needed run length for one flow to reach 10MB with 8 flows: 64 s
```

So `elephant_ratio` is always 0.0, `select_workload()` always returns MICE, and
`quantum` is always 300 B — the same end state the decode bugs produced, by a
different route. **The ELEPHANT and MIXED parameter profiles were unreachable in
every experiment ever run for this project.** C3 has therefore never been
exercised, and no claim about workload-aware profile selection is supported by
any data in this repository.

A second, smaller defect in the same file: `parse_key()` located the transport
header at `(ip + 1)`, assuming a 20-byte IP header, so source and destination
ports are misread whenever IP options are present. Not triggered by this
testbed's traffic, but incorrect in general.

### 2.2c The "Adaptive RED" baseline is not Adaptive RED

`scripts/adaptive_red.py` is presented in the paper and README as the Adaptive
RED comparison (Floyd, Gummadi and Shenker, 2001). It contains **zero**
references to the `red` qdisc:

```
$ grep -c '\bred\b' scripts/adaptive_red.py
0
```

Every adjustment it makes is `tc qdisc change ... fq_codel target ... limit ...`.
It maintains a simulated `max_p` variable and maps it linearly onto
`fq_codel`'s `target` and `limit`:

```python
def maxp_to_target(max_p):
    ratio = min(max_p / MAX_P, 1.0)
    return round(TARGET_MAX - ratio * (TARGET_MAX - TARGET_MIN), 2)
```

So the paper's claim of "24% lower backlog than Adaptive RED" compares ACAPE
against **a second fq_codel controller written for this project**, not against
the published algorithm. The file's own docstring concedes this ("Adapts max_p,
which we map to target — not native fq\_codel params"); the paper does not.

Linux ships Floyd's Adaptive RED as `tc qdisc add ... red ... adaptive`. The
corrected suite uses that, so its RED row is a real baseline.

### 2.2d The qdisc-selection bug affects every measurement path

F1 is not confined to `acape_v5.py`. The same unanchored `re.search()` over the
full `tc -s qdisc show` output appears in:

| File | Lines |
|---|---|
| `scripts/controller.py` | 66, 73, 80 |
| `scripts/record_metrics.py` | 33, 37, 38 |
| `scripts/acape_exporter.py` | 91, 93, 95 |
| `scripts/adaptive_red.py` | 60, 62, 64 |

Every one reads the **root TBF** stanza. This includes the Prometheus exporter,
so the Grafana dashboard panels reproduced in the paper (backlog = 355 p, drop
rate = 22,201 s⁻¹) were displaying the shaper's counters, not fq_codel's,
throughout.

### 2.3 C2 (predictive control) never changes the control action

Across all 32 runs: **375 adjustments — 367 `[REACTIVE]`, 8 `[PREDICTIVE]`**, and the
8 are all in one early run. The distinct control actions ever applied are:
```
mult-decrease β=0.9
mult-decrease β=0.9 (regime=HEAVY pred=HEAVY)
mult-decrease β=0.9 (regime=HEAVY pred=MODERATE)
```
Every adjustment in the entire corpus is the same multiplicative decrease. The
prediction is logged but **never alters the action**. Cause, in `aimd()`:
```python
eff = pred if traj=="WORSENING" else regime
```
`predict()` returns `REGIMES[idx+1]` only `if idx<3`; with regime = HEAVY (idx 3)
that branch cannot fire, so a worsening HEAVY is labelled STABLE. Regime is HEAVY
80.9% of ticks and NORMAL 19.0% (MODERATE 0.04%, LIGHT 0%) — so the 4-state
classifier is effectively binary, and `eff` is always the *current* regime.

The README's example log is also inconsistent with every real log: it shows
`RECOVERING → [PREDICTIVE]`, whereas the code and all logged data produce
`RECOVERING → [REACTIVE]` and `WORSENING → [PREDICTIVE]`.

### 2.4 "15 AIMD adjustments" is a constant, not a measurement

24 of 32 runs log exactly 15 adjustments. This is simply the number of ×0.9 steps
from target = 5 ms to the 1 ms floor (`log(1/5)/log(0.9)` ≈ 15.3). The controller
drives to the floor and stops in every run, because the regime is saturated HEAVY
from t = 0. The testbed never exercises the adaptive logic — it only ever ratchets
down.

### 2.5 The reported target staircase was never applied to the kernel

`apply_params()` emits `target f"{int(round(p['target']))}ms"`. Later versions keep
an internal float and no longer read the value back, so controller state diverges
from qdisc state:
```
logged / in paper : 5.00 4.50 4.05 3.65 3.28 2.95 2.66 2.39 2.15 1.94 1.74 1.57 1.41 1.27 1.14 1.03
actually applied  : 5    4    4    4    3    3    3    2    2    2    2    2    1    1    1    1
```
The paper's "each step ×0.9" staircase is a software variable, not a qdisc parameter.
(fq_codel accepts sub-ms values as `us`; the integer-ms rounding discards them.)

### 2.5b The headline figures are hardcoded, not plotted from data

`scripts/plot_comparison.py` — which produced `comparison_bars.png`,
`comparison_predictive.png` and `comparison_table.png`, all reproduced in the
paper — contains literal values in place of measurements in three places.

**(a) The stabilisation-time chart (lines 433–444).** The entire bar chart, its
labels and its annotation are constants. Nothing is read from any log:

```python
stab = [120, 70, 60, 5]
stab_labels = ["never\n(>120s)", "~70 s", "~60 s", "<5 s  \u2605"]
...
ax.text(2.85, 14, "12\u00d7 faster\nthan A.RED", ...)
```

This is the sole origin of the paper's "12× faster stabilisation" claim and of
the "<5 s vs ~60 s" comparison. No stabilisation time was ever measured.

**(b) The C2 predictive-control figure (lines 307–310).** When the adjustment
logs yield no PREDICTIVE or REACTIVE entries, the script substitutes two
hardcoded timestamp arrays under a comment asserting they are measured:

```python
if not pred_t and not react_t:
    # From actual measured run
    react_t = [5.1, 10.2, 25.7, 30.8, 41.1, 56.5]
    pred_t  = [15.4, 20.5, 35.9, 46.2, 51.3, 61.6, 66.7, 71.9, 77.0]
```

As established in §2.3, 31 of 32 adjustment logs contain zero PREDICTIVE
entries, so this fallback fires and the figure plots invented timestamps.

**(c) The summary table (lines 486–492).** Every cell is a string literal:

```python
["Avg queue backlog", "~450 pkts", "~320 pkts", "~270 pkts", "~240 pkts  " + T],
["Stabilises in",     "never",     "~70 s",     "~60 s",     "<5 s  " + T],
```

**(d) A silent data substitution (lines 259, 398).**
`np.mean(valid(P["bl"])) if valid(P["bl"]) else 270` quietly yields 270
whenever the backlog series is empty.

Note that the two fabricated sets do not even agree with each other: the plot
script uses 450/320/270/240 while the paper's table uses 434/412/357/314, and
the measured data gives 21.7/16.4/–/15.6.

These may well be development placeholders that were never removed. Whatever
the intent, the consequence is the same: **the figures presenting this
project's headline results are not derived from its measurements**, and any
table or claim traceable to them has no evidential basis.

### 2.6 The headline comparison table is not supported by the logs

Paper Table: Static 434 p · Adaptive RED 412 p · Part 3 357 p · **ACAPE 314 p**.
Recomputed from `*_recorded.csv` (t=0 init row excluded):

| system | N | mean backlog | median | mean tput |
|---|---|---|---|---|
| static_fqcodel | 597 | **21.7 p** | 24 | 5.0 |
| adaptive_red | 600 | **16.4 p** | 16 | 5.0 |
| pie | 597 | **7.8 p** | 7 | 5.0 |
| cake | 5 | 7.2 p | 8 | 10.0 | *(run failed — 5 rows)* |
| acape | 600 | **15.6 p** | 15 | 5.0 |

The *ratio* survives — (21.7−15.6)/21.7 = 28.1%, matching the paper's "28% lower
backlog" — but the absolute values are ~20× off and appear in no log file.
Additionally **PIE achieves a lower backlog (7.8 p) than ACAPE (15.6 p)** on the
paper's own primary metric, and PIE and CAKE are omitted from the headline table
despite data existing for both.

### 2.7 Inconsistent identifiers
`prog_id` appears as **527** (README), **91** (paper Fig. grafana_mid), and **49152**
(paper §Known Limitation). Live testing shows 49152 is the **tc filter preference**
(`pref 49152`, tc's default), not a BPF program id.

---

## 3. Not testable in this environment

This container runs a Firecracker kernel (6.18.44-fc-v49) with **no loadable module
support** and `CONFIG_NET_SCH_FQ_CODEL/CODEL/RED/PIE/CAKE/NETEM` all unset; only
`sch_tbf`, `sch_htb` and `pfifo*` are built in. There is no `/dev/kvm` and no
vmx/svm, so a nested VM with a full kernel is not viable either.

Consequently the topology, parsing, eBPF and arithmetic findings above were verified
live using TBF + pfifo (which is sufficient — all of them are qdisc-agnostic), but
**fq_codel-specific numbers cannot be re-measured here**. Re-running the corrected
experiments requires the authors' own Linux machine or any VM with a stock distro
kernel.

---

## 4. Recommended corrections

1. **Re-run Parts 2–4 on the 3-node router topology.** The 2-node data cannot support
   any queueing claim. `run_one_system.sh` already implements the correct topology.
2. **Fix `read_flows()`** (hex-string decode, struct offsets, `CLOCK_MONOTONIC` via
   `time.clock_gettime_ns(time.CLOCK_MONOTONIC)`), and remove the bare `except: pass`
   so failures are visible rather than silently producing zeros.
3. **Fix `read_tc()`** — `re.search` matches the TBF root line, so the controller has
   been reading the parent's counters, never fq_codel's. Parse the `fq_codel` stanza.
4. **Fix `apply_params()`** to emit `us` when target < 1 ms, and read parameters back
   from the kernel each cycle so controller state cannot diverge.
5. **Either fix C2 or drop it.** As written, prediction has no effect. Making HEAVY
   escalate (or making `eff` follow RECOVERING) would give it real behaviour.
6. **Rebuild every table and figure from the corrected runs**, report PIE and CAKE
   alongside, and use multiple seeds with confidence intervals rather than a single run.
7. **Design a workload that actually varies** (step changes in flow count / rate), so
   the regime classifier leaves HEAVY and the adaptive logic is exercised.
