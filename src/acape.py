#!/usr/bin/env python3
"""
ACAPE — Adaptive Condition-Aware Packet Engine (corrected implementation)

This supersedes scripts/acape_v5.py, which is retained only as the record of
what produced the pre-2026-09 logs. Four defects in v5 are fixed here; each is
documented at its call site and covered by tests/test_acape.py:

  F1  read_tc()      v5 used re.search() over the whole `tc -s qdisc show`
                     output, which always matched the ROOT (TBF) stanza. Every
                     backlog/drop/byte figure was the shaper's, never the AQM's.
                     Fixed: parse per-qdisc stanzas and select by handle/kind.

  F2  read_flows()   v5 had three independent fatal bugs:
                     (a) `bytes(raw[16:24])` on bpftool's hex STRINGS raised
                         TypeError, silently swallowed by a bare `except: pass`;
                     (b) struct offsets omitted first_seen_ns, so every field
                         after `bytes` was read from the wrong offset;
                     (c) age compared time.time_ns() (REALTIME) against
                         bpf_ktime_get_ns() (MONOTONIC) -> age ~= 56.8 years,
                         so `age < 2.0` was never true.
                     Result: active_flows == 0 in 21,128/21,128 logged ticks.

  F3  apply_params() v5 emitted f"{int(round(target))}ms", so the reported
                     5.00->1.03ms staircase reached the kernel as
                     5,4,4,4,3,3,3,2,2,2,2,2,1,1,1,1 and sub-ms targets were
                     unrepresentable. Fixed: emit `us` below 1ms, and read the
                     applied values back so controller state cannot drift.

  F4  predict()/aimd()
                     v5's predict() could not escalate from HEAVY (`idx<3`
                     guard), and aimd() used `eff = pred if traj=="WORSENING"
                     else regime`, so the prediction never changed the action:
                     all 375 logged adjustments were the same mult-decrease.
                     Fixed: prediction now selects a genuinely different action,
                     and [PREDICTIVE] is tagged only when it does.
"""

import argparse, csv, json, os, re, signal, struct, subprocess, sys, time
import statistics
from collections import deque
from datetime import datetime

try:
    import bpfmap          # direct bpf(2) syscall access
except ImportError:
    bpfmap = None

VERSION = "6.0.0"

# ── Control constants ─────────────────────────────────────────────────────
# F5. The target and interval bounds were absolute: 0.2 to 20 ms and 20 to
# 300 ms. That is harmless at the 5 ms default but silently wrong anywhere
# else. Started against a qdisc configured with target 80 ms, the controller
# read 80 from tc and the clamp cut it to 20 on the very first tick, a
# fourfold reduction decided by a constant rather than by any control
# decision. A ratio-invariance experiment run that way would have compared a
# static 80 ms target against an adapted 20 ms one and reported a large
# benefit that had nothing to do with control.
#
# The bounds are now a fixed multiple of whatever target the qdisc is
# configured with, so the controller explores the same relative range wherever
# it is deployed. The multipliers are chosen to reproduce the previous
# absolute values exactly at the 5 ms default:
#
#     T_MIN = 0.04 * 5 = 0.2      T_MAX = 4  * 5 = 20
#     I_MIN = 4    * 5 = 20       I_MAX = 60 * 5 = 300
#
# so every run in every earlier campaign is bit-identical under this change,
# and only non-default targets behave differently, where the old behaviour was
# simply a bug.
T_MIN_R, T_MAX_R = 0.04, 4.0      # x configured target
I_MIN_R, I_MAX_R = 4.0, 60.0      # x configured target
T_MIN, T_MAX     = 0.2, 20.0      # ms, overwritten by set_bounds()
I_MIN, I_MAX     = 20.0, 300.0    # ms, overwritten by set_bounds()


def set_bounds(t0):
    """Scale the bounds and the additive step sizes to the operating point."""
    global T_MIN, T_MAX, I_MIN, I_MAX, STEP_SCALE, DR_SCALE, T2_INTERVAL
    if not t0 or t0 <= 0:
        return
    T_MIN, T_MAX = T_MIN_R * t0, T_MAX_R * t0
    I_MIN, I_MAX = I_MIN_R * t0, I_MAX_R * t0
    STEP_SCALE = t0 / BASE_TARGET
    DR_SCALE = BASE_TARGET / t0
    # F8. The control loop period was absolute. CoDel's interval scales with
    # the target, so at a 16x target the controller was sampling every 0.5 s
    # against a 1.6 s AQM interval: three samples inside a single cycle rather
    # than an average over several. The regime classification then flickers
    # between LIGHT, MODERATE and HEAVY, the stable_cnt >= STABLE_ROUNDS gate
    # never opens, and not one adjustment fires in a whole run. Measured at
    # target 80 ms: 86 ticks, regimes split 31/28/27, target unchanged at
    # 80.000 throughout, zero rows in the adjustment log.
    #
    # The loop period is scaled so it stays the same multiple of the AQM's own
    # interval (five times it) wherever the controller is deployed. At the 5 ms
    # default the scale is 1.0 and the period is the 0.5 s it always was.
    T2_INTERVAL = T2_BASE * STEP_SCALE
L_MIN, L_MAX     = 64, 4096       # packets
BETA             = 0.9            # multiplicative decrease (Floyd et al. 2001)
ALPHA_T, ALPHA_L = 0.5, 64        # additive increase
# F6. The multiplicative decrease is scale-free, but the additive steps were
# not. A 0.2 ms step is 4% of a 5 ms target and 0.25% of an 80 ms one, so the
# same controller adapted an order of magnitude more slowly, in relative
# terms, the larger the target it was deployed against. Measured on the first
# ratio-invariance run, a 20 ms target moved only 20 to 18.4 ms over 84 ticks,
# an 8% excursion where 5 ms would have moved 32%.
#
# For a ratio-invariance experiment that is fatal in the opposite direction to
# F5: the controller would do less at large targets, show less benefit, and
# the ratio hypothesis would be recorded as refuted by an artefact of its own
# step size.
#
# The time-valued steps are now scaled by the configured target over the 5 ms
# default, so every step is the same fraction of the operating point. The
# scale is fixed per run rather than tracking the drifting target, which keeps
# the 5 ms default exactly bit-identical: STEP_SCALE is then 1.0 and every
# step is the constant it always was.
# ── Self-gating ───────────────────────────────────────────────────────────
# The scaling law says the benefit of adaptation is governed by
# r = target/RTT, is not statistically distinguishable from zero below
# r = 0.417, and reaches half its ceiling at r = 0.50. Below the crossover the
# controller still pays a cost: measured drop rate and retransmissions rise by
# roughly 10% at r = 0.25 for a 1.4% latency gain that is not significant.
#
# A controller that knows the law can decline to act. GATE_R is set to 0.4,
# just under the lowest ratio at which a benefit was measurable, so the gate
# opens wherever the benefit was real and stays shut where only the cost was.
#
# The ratio has to be computed from what the controller can observe, or the
# gate is not a contribution. RTT comes from the eBPF flow telemetry, and the
# statistic used is the median of a sliding window rather than the running
# minimum that is conventional for base-RTT estimation: measured against a
# known netem delay the median tracked it to 0.7% while the minimum was wrong
# by a factor of five. src/check_rtt_estimator.py is the check.
GATE_R           = 0.4            # gate opens at or above this ratio
GATE_WINDOW      = 20             # ticks of RTT samples behind the median
GATE_MIN_SAMPLES = 8              # do not decide before this many samples

BASE_TARGET      = 5.0            # ms, the target these constants were tuned at
T2_BASE          = 0.5            # s, control loop period at BASE_TARGET
STEP_SCALE       = 1.0            # overwritten by set_bounds()
# F7. The regime thresholds are drop rates in drops per second, a quantity
# with units of 1/time, so they are not scale-free. At ratio 1.0 the measured
# static drop rate is 59.3/s at target 5 ms, 20.2/s at 20 ms and 7.1/s at
# 80 ms, which against the fixed thresholds below classifies the same relative
# congestion as HEAVY, MODERATE and LIGHT respectively. The three cells that
# ratio invariance requires to be treated identically would each have received
# a different control law, and at 80 ms the LIGHT branch increases the target,
# the opposite action.
#
# The thresholds are therefore scaled by BASE_TARGET/t0. Two honest caveats.
# The measured drop rate falls as roughly t^-0.78 rather than the t^-1 this
# scaling assumes, so the correction is not exact. And what P2 actually needs
# is weaker than exactness: it needs every compared cell to receive the same
# control law. Under this scaling all three land in HEAVY with margin (59.3
# against 30, 20.2 against 7.5, 7.1 against 1.875), which is verified from the
# trajectories after the runs rather than assumed here.
#
# Backlog is deliberately not scaled. Measured at ratio 1.0 it moves by only
# x0.90 and x2.17 across a sixteenfold change in target, so it is close to
# invariant already and scaling it would introduce an error rather than remove
# one. composite_gradient() normalises by these thresholds, so it follows
# automatically.
DR_LIGHT, DR_MOD, DR_HEAVY = 1.0, 10.0, 30.0    # drops/s at BASE_TARGET
DR_SCALE = 1.0                                   # overwritten by set_bounds()
BL_LIGHT, BL_MOD, BL_HEAVY = 20, 100, 300       # packets
GRAD_WINDOW   = 10
STABLE_ROUNDS = 5
T2_INTERVAL   = 0.5     # s at BASE_TARGET, scaled by set_bounds()
T3_EVERY_N    = 10
G_THRESH      = 0.5

WORKLOAD_Q = {"MICE": 300, "MIXED": 1514, "ELEPHANT": 3000}
REGIMES    = ["NORMAL", "LIGHT", "MODERATE", "HEAVY"]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EBPF_OBJ   = os.path.join(SCRIPT_DIR, "..", "ebpf", "tc_monitor.o")


# ══ tc output parsing ═════════════════════════════════════════════════════
def split_qdisc_stanzas(out):
    """Split `tc -s qdisc show` into one stanza per qdisc.

    F1: v5 ran re.search() across the whole blob, so `dropped (\\d+)` always
    matched the first (root) qdisc. With `tbf` as root and the AQM as its
    child, every statistic v5 recorded belonged to the shaper.
    """
    stanzas, cur = [], []
    for line in out.splitlines():
        if line.startswith("qdisc "):
            if cur:
                stanzas.append("\n".join(cur))
            cur = [line]
        elif cur:
            cur.append(line)
    if cur:
        stanzas.append("\n".join(cur))
    return stanzas


def parse_stanza(s):
    d = {"kind": None, "handle": None, "bytes": 0, "pkts": 0,
         "drops": 0, "overlimits": 0, "backlog_b": 0, "backlog_p": 0}
    m = re.match(r"qdisc (\S+) (\S+)", s)
    if m:
        d["kind"], d["handle"] = m.group(1), m.group(2).rstrip(":")
    m = re.search(r"Sent (\d+) bytes (\d+) pkt", s)
    if m:
        d["bytes"], d["pkts"] = int(m.group(1)), int(m.group(2))
    m = re.search(r"dropped (\d+)", s)
    if m:
        d["drops"] = int(m.group(1))
    m = re.search(r"overlimits (\d+)", s)
    if m:
        d["overlimits"] = int(m.group(1))
    m = re.search(r"backlog (\d+)b (\d+)p", s)
    if m:
        d["backlog_b"], d["backlog_p"] = int(m.group(1)), int(m.group(2))
    # fq_codel / cake / pie extras
    m = re.search(r"maxpacket (\d+)", s)
    if m:
        d["maxpacket"] = int(m.group(1))
    m = re.search(r"new_flow_count (\d+)", s)
    if m:
        d["new_flow_count"] = int(m.group(1))
    m = re.search(r"ecn_mark (\d+)", s)
    if m:
        d["ecn_mark"] = int(m.group(1))
    return d


def read_tc(ns, iface, want_handle=None, want_kind=None):
    """Read stats for a SPECIFIC qdisc, not whichever one printed first (F1)."""
    out = _run(["ip", "netns", "exec", ns, "tc", "-s", "qdisc", "show", "dev", iface])
    if not out:
        return None
    stanzas = [parse_stanza(s) for s in split_qdisc_stanzas(out)]
    if not stanzas:
        return None
    chosen = None
    if want_handle:
        chosen = next((d for d in stanzas if d["handle"] == want_handle.rstrip(":")), None)
    if chosen is None and want_kind:
        chosen = next((d for d in stanzas if d["kind"] == want_kind), None)
    if chosen is None:
        # Fall back to the last non-root stanza (the AQM under a shaper),
        # never blindly to the first as v5 did.
        chosen = stanzas[-1] if len(stanzas) > 1 else stanzas[0]
    chosen["ts"] = time.time()
    chosen["root"] = stanzas[0]
    return chosen


# ══ qdisc parameters ══════════════════════════════════════════════════════
def _fmt_time(ms):
    """F3: express sub-millisecond values in us instead of rounding to 0/1ms."""
    if ms < 1.0:
        return f"{int(round(ms * 1000))}us"
    return f"{ms:.3f}ms".rstrip("0").rstrip(".") + ("" if f"{ms:.3f}".endswith("ms") else "")


def fmt_time(ms):
    if ms < 1.0:
        return f"{max(1, int(round(ms * 1000)))}us"
    # keep sub-ms precision above 1ms too, e.g. 4.05ms -> 4050us
    return f"{int(round(ms * 1000))}us"


def parse_time_to_ms(tok):
    m = re.match(r"([\d.]+)(us|ms|s)?$", tok)
    if not m:
        return None
    v = float(m.group(1)); u = m.group(2) or "ms"
    return v / 1000.0 if u == "us" else (v * 1000.0 if u == "s" else v)


def get_params(ns, iface, handle=None, kind="fq_codel"):
    out = _run(["ip", "netns", "exec", ns, "tc", "qdisc", "show", "dev", iface])
    p = {"target": 5.0, "interval": 100.0, "limit": 1024, "quantum": 1514}
    for s in split_qdisc_stanzas(out):
        head = s.splitlines()[0]
        if kind and f"qdisc {kind} " not in head:
            continue
        if handle and f" {handle.rstrip(':')}: " not in head:
            continue
        m = re.search(r"target (\S+?)(?:\s|$)", head)
        if m:
            v = parse_time_to_ms(m.group(1))
            if v is not None:
                p["target"] = v
        m = re.search(r"interval (\S+?)(?:\s|$)", head)
        if m:
            v = parse_time_to_ms(m.group(1))
            if v is not None:
                p["interval"] = v
        m = re.search(r"limit (\d+)p?", head)
        if m:
            p["limit"] = int(m.group(1))
        m = re.search(r"quantum (\d+)", head)
        if m:
            p["quantum"] = int(m.group(1))
        break
    return p


# Which parameters each delay-targeting qdisc actually accepts, and under what
# name. Writing fq_codel's four at a plain `codel` or a `pie` makes tc reject
# the whole command, so the controller could only ever drive fq_codel. Keeping
# this as a table is what lets the same control law be tested on a different
# AQM algorithm, which is the point of the cross-AQM experiment: PIE regulates
# a drop probability with a proportional-integral controller rather than a
# sojourn threshold, so if the same ratio governs it, the result is about delay
# targets in general and not about CoDel's mechanism.
#
# `tupdate` is PIE's update period, the closest analogue of CoDel's interval,
# so the controller's interval state maps onto it.
PARAM_SETS = {
    "fq_codel": [("target", "target"), ("interval", "interval"),
                 ("limit", "limit"), ("quantum", "quantum")],
    "codel":    [("target", "target"), ("interval", "interval"),
                 ("limit", "limit")],
    "pie":      [("target", "target"), ("tupdate", "interval"),
                 ("limit", "limit")],
    "fq_pie":   [("target", "target"), ("tupdate", "interval"),
                 ("limit", "limit")],
}
TIME_PARAMS = {"target", "interval", "tupdate"}


def apply_params(ns, iface, p, parent="1:1", handle="10:", kind="fq_codel", dry=False):
    """F3: emit microsecond resolution and verify by reading back."""
    spec = PARAM_SETS.get(kind, PARAM_SETS["fq_codel"])
    cmd = ["ip", "netns", "exec", ns, "tc", "qdisc", "change", "dev", iface,
           "parent", parent, "handle", handle, kind]
    for tc_name, state_key in spec:
        if state_key not in p:
            continue
        cmd += [tc_name, (fmt_time(p[state_key]) if tc_name in TIME_PARAMS
                          else str(int(p[state_key])))]
    if dry:
        print("  [DRY] " + " ".join(cmd))
        return True, dict(p)
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=3)
    except subprocess.CalledProcessError as e:
        print(f"  [ERR] {e.stderr.decode().strip()}")
        return False, dict(p)
    applied = get_params(ns, iface, handle=handle, kind=kind)
    return True, applied


# ══ eBPF telemetry ════════════════════════════════════════════════════════
def _run(cmd, timeout=3):
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL,
                                       text=True, timeout=timeout)
    except Exception:
        return ""


def decode_bpftool_bytes(raw):
    """F2a: bpftool --json emits byte arrays as hex STRINGS ('0xa0'), not ints.

    v5 called bytes(raw[16:24]) directly, which raises
    TypeError: 'str' object cannot be interpreted as an integer.
    A bare `except: pass` hid it, so read_flows() silently returned zeros for
    every tick of every run ever recorded.
    """
    if isinstance(raw, (bytes, bytearray)):
        return bytes(raw)
    out = bytearray()
    for v in raw:
        out.append(int(v, 16) if isinstance(v, str) else int(v))
    return bytes(out)


# struct flow_stats (ebpf/tc_monitor.c), 56 bytes:
#   packets u64 @0 | bytes u64 @8 | first_seen_ns u64 @16
#   last_seen_ns u64 @24 | interpacket_gap_ns u64 @32
#   is_elephant u32 @40 | flow_rate_kbps u32 @44 | pad @48
# F2b: v5 assumed last_ns@16, gap@24, is_elephant@32 -- first_seen_ns was
# omitted from its layout comment, shifting every subsequent field.
OFF_PACKETS, OFF_BYTES, OFF_FIRST, OFF_LAST, OFF_GAP, OFF_ELEPHANT = 0, 8, 16, 24, 32, 40


def parse_flow_value(raw):
    b = decode_bpftool_bytes(raw)
    if len(b) < 44:
        raise ValueError(f"flow_stats value too short: {len(b)}B")
    u64 = lambda o: struct.unpack_from("<Q", b, o)[0]
    return {
        "packets":      u64(OFF_PACKETS),
        "bytes":        u64(OFF_BYTES),
        "first_seen_ns": u64(OFF_FIRST),
        "last_seen_ns": u64(OFF_LAST),
        "gap_ns":       u64(OFF_GAP),
        "is_elephant":  struct.unpack_from("<I", b, OFF_ELEPHANT)[0],
    }


def monotonic_ns():
    """F2c: bpf_ktime_get_ns() is CLOCK_MONOTONIC. v5 compared it against
    time.time_ns() (CLOCK_REALTIME), yielding ages of ~56.8 years."""
    return time.clock_gettime_ns(time.CLOCK_MONOTONIC)


class EBPFPipeline:
    def __init__(self, ns, iface, obj=EBPF_OBJ, quiet=False):
        self.ns, self.iface, self.obj = ns, iface, obj
        self.quiet = quiet
        self.active = False
        self.prog_id = None
        self.flow_map_id = None
        self.map_fd = None
        self.key_size = 16
        self.value_size = 56
        self.use_syscall = False
        self.decode_errors = 0
        self._setup()

    def _log(self, m):
        if not self.quiet:
            print(m, flush=True)

    def _bpftool(self, *args):
        for exe in ("bpftool", "/usr/sbin/bpftool",
                    *(sorted(__import__("glob").glob("/usr/lib/linux-tools/*/bpftool")))):
            out = _run([exe, *args])
            if out:
                return out
        return ""

    def _setup(self):
        if not os.path.exists(self.obj):
            self._log(f"[eBPF] object not found: {self.obj}")
            return
        subprocess.run(["ip", "netns", "exec", self.ns, "tc", "qdisc", "add",
                        "dev", self.iface, "clsact"],
                       capture_output=True)
        r = subprocess.run(["ip", "netns", "exec", self.ns, "tc", "filter", "add",
                            "dev", self.iface, "egress", "bpf", "direct-action",
                            "obj", self.obj, "sec", "tc_egress"],
                           capture_output=True, text=True)
        out = _run(["ip", "netns", "exec", self.ns, "tc", "filter", "show",
                    "dev", self.iface, "egress"])
        m = re.search(r"\bid (\d+)\b", out)
        if not m:
            self._log(f"[eBPF] attach failed: {r.stderr.strip()}")
            return
        self.prog_id = int(m.group(1))
        self.active = "jited" in out
        self._log(f"[eBPF] attached prog_id={self.prog_id} jited={self.active}")
        self._find_maps()

    def _find_maps(self):
        # Preferred: bpf(2) syscall. Spawning bpftool per tick cost ~2.5s in the
        # VM and stretched the 0.5s control interval to 3.17s.
        if bpfmap is not None and bpfmap.available():
            mid, fd, info = bpfmap.find_map_by_name("flow_ma")
            if mid is not None:
                self.flow_map_id = mid
                self.map_fd = fd
                self.key_size = info.key_size
                self.value_size = info.value_size
                self.use_syscall = True
                self._log(f"[eBPF] flow_map id={mid} via bpf(2) "
                          f"(key={info.key_size}B value={info.value_size}B)")
                return
        out = self._bpftool("map", "list", "--json")
        if not out:
            return
        try:
            for mm in json.loads(out):
                if mm.get("name", "").startswith("flow_ma"):
                    self.flow_map_id = mm["id"]
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            self._log(f"[eBPF] map list parse failed: {e}")
        if self.flow_map_id:
            self._log(f"[eBPF] flow_map id={self.flow_map_id} via bpftool (slow path)")

    def read_flows(self, age_limit_s=2.0):
        empty = {"active": 0, "elephant": 0, "mice": 0, "rtt_ms": 0.0, "ratio": 0.0}
        if not self.active or self.flow_map_id is None:
            return empty
        if self.use_syscall:
            try:
                values = [v for _, v in bpfmap.iter_map(
                    self.map_fd, self.key_size, self.value_size)]
            except OSError as e:
                self.decode_errors += 1
                self._log(f"[eBPF] map iteration failed: {e}")
                return empty
        else:
            out = self._bpftool("map", "dump", "id", str(self.flow_map_id), "--json")
            if not out:
                return empty
            try:
                values = [e.get("value", []) for e in json.loads(out)]
            except json.JSONDecodeError as e:
                self.decode_errors += 1
                self._log(f"[eBPF] map dump JSON error: {e}")
                return empty
        now = monotonic_ns()                       # F2c
        active = elephant = mice = 0
        total_gap = 0
        for raw in values:
            try:
                fv = parse_flow_value(raw)         # F2a + F2b
            except (ValueError, struct.error, TypeError):
                self.decode_errors += 1            # no longer silently swallowed
                continue
            if fv["packets"] == 0:
                continue
            if (now - fv["last_seen_ns"]) / 1e9 >= age_limit_s:
                continue
            active += 1
            total_gap += fv["gap_ns"]
            if fv["is_elephant"]:
                elephant += 1
            else:
                mice += 1
        return {
            "active": active, "elephant": elephant, "mice": mice,
            "rtt_ms": (total_gap / active / 1e6) if active else 0.0,
            "ratio": (elephant / active) if active else 0.0,
        }

    def detach(self):
        subprocess.run(["ip", "netns", "exec", self.ns, "tc", "qdisc", "del",
                        "dev", self.iface, "clsact"], capture_output=True)


# ══ Classification, prediction, AIMD ══════════════════════════════════════
def gradient(history, attr):
    vals = [(s["ts"], s.get(attr, 0.0)) for s in history]
    if len(vals) < 3:
        return 0.0
    n = len(vals); t0 = vals[0][0]
    xs = [v[0] - t0 for v in vals]; ys = [v[1] for v in vals]
    xm = sum(xs) / n; ym = sum(ys) / n
    den = sum((x - xm) ** 2 for x in xs)
    if den < 1e-9:
        return 0.0
    return sum((x - xm) * (y - ym) for x, y in zip(xs, ys)) / den


def classify(dr, bl):
    """F7: drop-rate thresholds scale with the operating point, backlog does not."""
    if dr > DR_HEAVY * DR_SCALE or bl > BL_HEAVY:
        return "HEAVY"
    if dr > DR_MOD * DR_SCALE or bl > BL_MOD:
        return "MODERATE"
    if dr > DR_LIGHT * DR_SCALE or bl > BL_LIGHT:
        return "LIGHT"
    return "NORMAL"


def composite_gradient(dr_g, bl_g):
    return 0.6 * dr_g / (DR_HEAVY * DR_SCALE) + 0.4 * bl_g / BL_HEAVY


def predict(regime, dr_g, bl_g):
    """F4: v5 guarded escalation with `idx<3`, so a WORSENING HEAVY fell through
    and was reported STABLE -- and HEAVY is 81% of all ticks. The trajectory is
    now reported on its own terms; saturation at the top regime no longer
    disguises a worsening trend as a stable one."""
    idx = REGIMES.index(regime)
    g = composite_gradient(dr_g, bl_g)
    if g > G_THRESH:
        return REGIMES[min(idx + 1, len(REGIMES) - 1)], "WORSENING"
    if g < -G_THRESH:
        return REGIMES[max(idx - 1, 0)], "RECOVERING"
    return regime, "STABLE"


def select_workload(ratio):
    if ratio < 0.2:
        return "MICE"
    if ratio > 0.6:
        return "ELEPHANT"
    return "MIXED"


def aimd(regime, traj, pred, params, workload):
    """F4: v5 computed `eff = pred if traj=="WORSENING" else regime`. Since
    pred could never differ from regime under WORSENING (the idx<3 guard), eff
    always equalled regime and every one of 375 logged adjustments applied the
    identical mult-decrease. The prediction is now what selects the action.
    """
    p = dict(params)
    eff = pred                                   # prediction drives the action
    predictive = (pred != regime)
    pfx = "[PREDICTIVE]" if predictive else "[REACTIVE]"

    if eff == "HEAVY":
        # A worsening trend at saturation warrants a firmer cut than a steady one.
        beta = BETA ** 2 if traj == "WORSENING" else BETA
        p["target"] *= beta; p["interval"] *= beta; p["limit"] *= beta
        r = f"{pfx} mult-decrease beta={beta:.2f}"
    elif eff == "MODERATE":
        # Recovering out of HEAVY: ease off instead of another full cut.
        p["target"] -= 0.2 * STEP_SCALE; p["limit"] -= 32
        r = f"{pfx} additive-decrease"
    elif eff == "LIGHT":
        p["target"] += ALPHA_T * STEP_SCALE; p["interval"] += 5 * STEP_SCALE
        p["limit"] += ALPHA_L
        r = f"{pfx} additive-increase"
    else:
        if traj == "RECOVERING":
            p["target"] += 0.2 * STEP_SCALE; p["limit"] += 16
            r = f"{pfx} gentle-increase"
        else:
            return params, "stable", False

    p["quantum"] = WORKLOAD_Q[workload]
    p["target"]   = max(T_MIN, min(T_MAX, p["target"]))
    p["interval"] = max(I_MIN, min(I_MAX, p["interval"]))
    p["limit"]    = max(L_MIN, min(L_MAX, int(p["limit"])))
    if p["interval"] <= p["target"] * 10:
        p["interval"] = min(I_MAX, p["target"] * 10)
    return p, f"{r} | regime={regime} pred={pred} wkld={workload}", predictive


# ══ Main control loop ═════════════════════════════════════════════════════
def run(args):
    os.makedirs(args.logdir, exist_ok=True)
    tag = args.tag or datetime.now().strftime("%Y%m%d_%H%M%S")
    mpath = os.path.join(args.logdir, f"acape_metrics_{tag}.csv")
    apath = os.path.join(args.logdir, f"acape_adj_{tag}.csv")
    spath = os.path.join(args.logdir, f"acape_state_{tag}.csv")

    mf = open(mpath, "w", newline=""); af = open(apath, "w", newline="")
    sf = open(spath, "w", newline="")
    mw, aw, sw = csv.writer(mf), csv.writer(af), csv.writer(sf)
    mw.writerow(["t_s", "drop_rate_per_s", "drops_exp", "backlog_pkts", "backlog_bytes",
                 "throughput_mbps", "sojourn_est_ms", "rtt_proxy_ms", "active_flows",
                 "elephant_flows", "mice_flows", "elephant_ratio",
                 "regime", "trajectory", "predicted_regime", "workload_profile",
                 "target_ms", "interval_ms", "limit_pkts", "quantum_bytes",
                 "root_drops", "root_overlimits"])
    aw.writerow(["t_s", "regime", "trajectory", "predicted", "predictive",
                 "old_target", "new_target", "applied_target",
                 "old_limit", "new_limit", "applied_limit", "workload", "reason"])
    sw.writerow(["t_s", "dr_gradient", "bl_gradient", "rtt_gradient",
                 "composite_g", "regime", "trajectory", "predicted", "workload"])
    for f in (mf, af, sf):
        f.flush()

    ebpf = None
    if args.ebpf and not args.dry:
        ebpf = EBPFPipeline(args.ns, args.iface)
    ebpf_on = bool(ebpf and ebpf.active)

    params = get_params(args.ns, args.iface, handle=args.handle, kind=args.kind)
    # F5: scale the parameter bounds to the target the qdisc is actually
    # configured with, before any adjustment can be clamped against them.
    configured_target = params.get("target")
    set_bounds(configured_target)
    print(f"[acape] bounds for target {configured_target}ms: "
          f"target {T_MIN:.3g}-{T_MAX:.3g}ms interval {I_MIN:.3g}-{I_MAX:.3g}ms",
          flush=True)
    history = deque(maxlen=GRAD_WINDOW)
    rttbuf = deque(maxlen=GATE_WINDOW)      # for the self-gate's RTT estimate
    gate_open = None                        # None until enough samples
    gate_flips = 0
    sbuf = deque(maxlen=8)
    stable_cnt = adj_count = pred_count = tick = 0
    t0 = time.time()

    first = read_tc(args.ns, args.iface, args.handle, args.kind)
    if not first:
        sys.exit("ERROR: cannot read tc stats — is the qdisc attached?")
    drops_base = first["drops"]; prev = first

    mode = "eBPF" if ebpf_on else "tc-only"
    print(f"\n{'='*78}")
    print(f"  ACAPE v{VERSION}   mode={mode}   qdisc={args.kind} handle={args.handle}")
    print(f"  metrics -> {mpath}")
    print(f"{'='*78}")
    hdr = (f"{'t':>7} {'regime':>9} {'traj':>11} {'pred':>9} {'dr/s':>8} {'bl':>5} "
           f"{'tput':>7} {'flows':>5} {'eleph':>5} {'tgt_ms':>7} {'lim':>5} {'adj':>4}")
    print(hdr); print("-" * len(hdr))

    stop = {"now": False}

    def shutdown(sig=None, frame=None):
        stop["now"] = True
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    deadline = t0 + args.duration if args.duration else None
    while not stop["now"]:
        time.sleep(T2_INTERVAL)
        tick += 1
        tc = read_tc(args.ns, args.iface, args.handle, args.kind)
        if not tc:
            continue
        elapsed = tc["ts"] - t0
        if deadline and tc["ts"] >= deadline:
            break
        dt = max(tc["ts"] - prev["ts"], 1e-6)
        drops_exp = tc["drops"] - drops_base
        dr = max(0, tc["drops"] - prev["drops"]) / dt
        tp = (max(0, tc["bytes"] - prev["bytes"]) * 8) / (dt * 1e6)
        bl = tc["backlog_p"]; blb = tc["backlog_b"]
        # queue delay estimate: bytes in queue / drain rate
        sojourn = (blb * 8 / (args.rate_mbit * 1e6) * 1000) if args.rate_mbit else 0.0

        ed = ebpf.read_flows() if ebpf_on else {"active": 0, "elephant": 0,
                                                "mice": 0, "rtt_ms": 0.0, "ratio": 0.0}
        workload = select_workload(ed["ratio"])
        regime = classify(dr, bl)

        history.append({"ts": elapsed, "drop_rate": dr, "backlog": float(bl),
                        "rtt_proxy_ms": ed["rtt_ms"]})
        dr_g = gradient(list(history), "drop_rate")
        bl_g = gradient(list(history), "backlog")
        rtt_g = gradient(list(history), "rtt_proxy_ms")
        pred, traj = predict(regime, dr_g, bl_g)

        # ---- self-gate --------------------------------------------------
        # Estimate the path's base RTT from observation, derive r, and decide
        # whether acting is worth its cost. Decided every tick so the decision
        # follows the path rather than being fixed at startup.
        if ed["rtt_ms"] > 0:
            rttbuf.append(ed["rtt_ms"])
        r_est = None
        if args.gate and len(rttbuf) >= GATE_MIN_SAMPLES:
            rtt_est = statistics.median(rttbuf)
            if rtt_est > 0:
                r_est = configured_target / rtt_est
                now_open = r_est >= GATE_R
                if gate_open is not None and now_open != gate_open:
                    gate_flips += 1
                if gate_open is None:
                    print(f"[acape] gate {'OPEN' if now_open else 'SHUT'}: "
                          f"target {configured_target:.3g}ms / est RTT "
                          f"{rtt_est:.2f}ms = r {r_est:.3f} "
                          f"(threshold {GATE_R})", flush=True)
                gate_open = now_open

        sbuf.append(regime)
        stable_cnt = (stable_cnt + 1 if len(sbuf) >= STABLE_ROUNDS and
                      len(set(list(sbuf)[-STABLE_ROUNDS:])) == 1 else 0)

        mw.writerow([f"{elapsed:.3f}", f"{dr:.4f}", drops_exp, bl, blb,
                     f"{tp:.4f}", f"{sojourn:.4f}", f"{ed['rtt_ms']:.3f}",
                     ed["active"], ed["elephant"], ed["mice"], f"{ed['ratio']:.3f}",
                     regime, traj, pred, workload,
                     f"{params['target']:.4f}", f"{params['interval']:.2f}",
                     params["limit"], params["quantum"],
                     tc["root"]["drops"], tc["root"]["overlimits"]])
        mf.flush()

        if tick % 5 == 0:
            sw.writerow([f"{elapsed:.3f}", f"{dr_g:.4f}", f"{bl_g:.4f}", f"{rtt_g:.4f}",
                         f"{composite_gradient(dr_g, bl_g):.4f}",
                         regime, traj, pred, workload])
            sf.flush()

        # The gate withholds adjustment; it does not stop measurement, so a
        # gated run still records what it would have seen.
        gated_off = args.gate and gate_open is False
        if (args.adapt and not gated_off
                and tick % T3_EVERY_N == 0 and stable_cnt >= STABLE_ROUNDS):
            old = dict(params)
            new_p, reason, predictive = aimd(regime, traj, pred, params, workload)
            if (abs(new_p["target"] - old["target"]) > 0.01 or
                    abs(new_p["limit"] - old["limit"]) > 1):
                ok, applied = apply_params(args.ns, args.iface, new_p, args.parent,
                                           args.handle, args.kind, args.dry)
                if ok:
                    # F3: trust the kernel's readback, not the internal float
                    params = applied if not args.dry else new_p
                    adj_count += 1
                    pred_count += int(predictive)
                    aw.writerow([f"{elapsed:.2f}", regime, traj, pred, int(predictive),
                                 f"{old['target']:.4f}", f"{new_p['target']:.4f}",
                                 f"{params['target']:.4f}",
                                 int(old["limit"]), int(new_p["limit"]),
                                 int(params["limit"]), workload, reason])
                    af.flush()

        print(f"{elapsed:>7.1f} {regime:>9} {traj:>11} {pred:>9} {dr:>8.1f} {bl:>5d} "
              f"{tp:>7.2f} {ed['active']:>5d} {ed['elephant']:>5d} "
              f"{params['target']:>7.3f} {params['limit']:>5d} {adj_count:>4d}", flush=True)
        prev = tc

    if ebpf:
        ebpf.detach()
    for x in (mf, af, sf):
        x.close()
    print(f"\nDone — {tick} ticks, {adj_count} adjustments "
          f"({pred_count} predictive), mode={mode}")
    if ebpf and ebpf.decode_errors:
        print(f"WARNING: {ebpf.decode_errors} eBPF decode errors (not silently ignored)")
    summary = {"ticks": tick, "adjustments": adj_count, "predictive": pred_count,
               "mode": mode, "prog_id": ebpf.prog_id if ebpf else None,
               "metrics": mpath, "adj": apath, "state": spath,
               # What the self-gate decided, so an evaluation can tell a gate
               # that stayed shut from a controller that had nothing to do.
               "gate": bool(args.gate),
               "gate_open": gate_open,
               "gate_flips": gate_flips,
               "gate_r_est": (round(configured_target / statistics.median(rttbuf), 4)
                              if rttbuf else None),
               "gate_rtt_est_ms": (round(statistics.median(rttbuf), 3)
                                   if rttbuf else None),
               "gate_threshold": GATE_R}
    with open(os.path.join(args.logdir, f"acape_summary_{tag}.json"), "w") as fh:
        json.dump(summary, fh, indent=2)


def main():
    p = argparse.ArgumentParser(description="ACAPE v6 — corrected controller")
    p.add_argument("--ns", default="ns_router")
    p.add_argument("--iface", default="veth_rs")
    p.add_argument("--parent", default="1:1")
    p.add_argument("--handle", default="10:")
    p.add_argument("--kind", default="fq_codel")
    p.add_argument("--logdir", default="../logs")
    p.add_argument("--tag", default=None)
    p.add_argument("--duration", type=float, default=0)
    p.add_argument("--rate-mbit", type=float, default=10.0)
    p.add_argument("--gate", action="store_true",
                   help="self-gate: compute r = target/RTT from observed telemetry and withhold adaptation below GATE_R")
    p.add_argument("--adapt", action="store_true", help="enable AIMD control")
    p.add_argument("--ebpf", action="store_true", help="attach eBPF telemetry")
    p.add_argument("--dry", action="store_true")
    args = p.parse_args()
    if os.geteuid() != 0 and not args.dry:
        sys.exit("must run as root")
    run(args)


if __name__ == "__main__":
    main()
