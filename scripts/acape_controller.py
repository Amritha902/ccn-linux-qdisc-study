#!/usr/bin/env python3
"""
ACAPE: Adaptive Condition-Aware Packet Engine
Amritha S, Yugeshwaran P, Deepti Annuncia — VIT Chennai 2026

Novel contributions over Adaptive RED (Floyd et al. 2001):
  1. Multi-signal predictive state estimator
     Combines [drop_rate_gradient, backlog_gradient, rtt_gradient]
     into a state vector → predicts regime BEFORE transition occurs.
     (Reactive-only systems act after congestion; ACAPE acts before.)

  2. Three-timescale control architecture
     T1 (eBPF, ~ns)  : per-packet telemetry collection in-kernel
     T2 (100 ms)     : multi-signal state estimation + prediction
     T3 (5 s)        : AIMD parameter adjustment + workload profiling

  3. Workload-aware parameter profiles
     eBPF classifies flows into elephant/mice by byte volume.
     Controller selects different fq_codel target/quantum profiles
     per workload regime — no prior AQM work does this on stock Linux.

  4. Zero kernel modification — runs on unmodified Linux kernel.
     Uses tc qdisc change interface. Deployable on any Linux host.

Usage:
    sudo python3 acape_controller.py --ns ns1 --iface veth1
    python3 acape_controller.py --dry  # test without applying tc changes
"""

import subprocess, re, time, csv, os, sys, signal, argparse
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from datetime import datetime
import math

# ═══════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════

VERSION = "1.0.0"

# fq_codel hard bounds
T_MIN, T_MAX   = 1,   20    # target (ms)
I_MIN, I_MAX   = 50, 300    # interval (ms)
L_MIN, L_MAX   = 256, 4096  # limit (pkts)
Q_MIN, Q_MAX   = 300, 4000  # quantum (bytes)

# AIMD policy (Adaptive RED Section 4, extended)
BETA          = 0.9    # multiplicative decrease factor (HEAVY)
ALPHA_T       = 0.5    # additive increase for target (ms)
ALPHA_L       = 64     # additive increase for limit (pkts)

# Timescale T2: state estimation interval (seconds)
T2_INTERVAL   = 0.1    # 100 ms
# Timescale T3: parameter adjustment interval (multiples of T2)
T3_EVERY_N    = 50     # ~5 s

# Gradient smoothing window (number of T2 samples)
GRAD_WINDOW   = 10     # 1 second of history for gradient

# Stable rounds needed before adjustment
STABLE_ROUNDS = 5

# Congestion thresholds
DR_LIGHT, DR_MOD, DR_HEAVY  = 1, 10, 30    # drops/sec
BL_LIGHT, BL_MOD, BL_HEAVY  = 20, 100, 300 # pkts

# Gradient thresholds for predictive regime
GRAD_WORSENING  =  0.5   # positive gradient → heading toward congestion
GRAD_RECOVERING = -0.5   # negative gradient → recovering

# Workload profiles (target_ms, interval_ms, limit, quantum)
# Selected based on elephant_ratio from eBPF
WORKLOAD_PROFILES = {
    "MICE":     {"target": 2,  "interval": 20,  "limit": 512,  "quantum": 300,  "desc": "latency-optimised (short flows)"},
    "MIXED":    {"target": 5,  "interval": 100, "limit": 1024, "quantum": 1514, "desc": "balanced (default fq_codel)"},
    "ELEPHANT": {"target": 10, "interval": 200, "limit": 2048, "quantum": 3000, "desc": "throughput-optimised (bulk flows)"},
}

# ═══════════════════════════════════════════════════════════════
# Data classes
# ═══════════════════════════════════════════════════════════════

@dataclass
class Params:
    target:   float = 5.0
    interval: float = 100.0
    limit:    int   = 1024
    quantum:  int   = 1514

    def clamp(self):
        self.target   = max(T_MIN, min(T_MAX,   self.target))
        self.interval = max(I_MIN, min(I_MAX,   self.interval))
        self.limit    = max(L_MIN, min(L_MAX,   int(self.limit)))
        self.quantum  = max(Q_MIN, min(Q_MAX,   int(self.quantum)))
        if self.interval <= self.target:
            self.interval = self.target * 10

@dataclass
class Sample:
    """One T2 (100ms) measurement."""
    ts:           float
    drop_rate:    float  # instantaneous drops/sec
    backlog:      float  # packets in queue
    throughput:   float  # Mbps from byte delta
    drops_abs:    int    # cumulative tc counter (absolute)
    # eBPF-enriched fields
    active_flows:   int   = 0
    elephant_flows: int   = 0
    mice_flows:     int   = 0
    elephant_ratio: float = 0.0
    rtt_proxy_ms:   float = 0.0  # mean inter-packet gap from eBPF

@dataclass
class StateVector:
    """Multi-signal state for predictive classification."""
    drop_rate:    float
    backlog:      float
    rtt_ms:       float
    dr_gradient:  float   # Δdrop_rate / Δt (over GRAD_WINDOW)
    bl_gradient:  float   # Δbacklog / Δt
    rtt_gradient: float   # Δrtt / Δt
    trajectory:   str     = "STABLE"  # WORSENING / RECOVERING / STABLE
    regime:       str     = "NORMAL"  # NORMAL / LIGHT / MODERATE / HEAVY
    predicted:    str     = "NORMAL"  # predicted NEXT regime

# ═══════════════════════════════════════════════════════════════
# tc interface
# ═══════════════════════════════════════════════════════════════

def _run(cmd: list) -> str:
    try:
        return subprocess.check_output(
            cmd, stderr=subprocess.DEVNULL, text=True, timeout=2)
    except Exception:
        return ""

def read_tc(ns: str, iface: str) -> Optional[dict]:
    out = _run(["ip","netns","exec",ns,"tc","-s","qdisc","show","dev",iface])
    if not out:
        return None
    d = {"ts": time.time()}
    m = re.search(r"Sent (\d+) bytes (\d+) pkt", out)
    d["bytes"]     = int(m.group(1)) if m else 0
    m = re.search(r"dropped (\d+)", out)
    d["drops_abs"] = int(m.group(1)) if m else 0
    m = re.search(r"backlog \d+b (\d+)p", out)
    d["backlog"]   = int(m.group(1)) if m else 0
    return d

def read_params(ns: str, iface: str) -> Params:
    out = _run(["ip","netns","exec",ns,"tc","qdisc","show","dev",iface])
    p = Params()
    if not out: return p
    m = re.search(r"target (\d+)ms",   out); p.target   = float(m.group(1)) if m else 5.0
    m = re.search(r"interval (\d+)ms", out); p.interval = float(m.group(1)) if m else 100.0
    m = re.search(r"limit (\d+)p?",    out); p.limit    = int(m.group(1))   if m else 1024
    m = re.search(r"quantum (\d+)",    out); p.quantum   = int(m.group(1))   if m else 1514
    return p

def apply_params(ns: str, iface: str, p: Params, dry: bool = False) -> bool:
    cmd = ["ip","netns","exec",ns,
           "tc","qdisc","change","dev",iface,
           "parent","1:1","handle","10:","fq_codel",
           "target",  f"{int(round(p.target))}ms",
           "interval",f"{int(round(p.interval))}ms",
           "limit",   f"{int(p.limit)}",
           "quantum", f"{int(p.quantum)}"]
    if dry:
        print(f"  [DRY] {' '.join(cmd)}")
        return True
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=3)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [ERR] tc change: {e.stderr.decode().strip()}")
        return False

def measure_rtt_ms(ns2: str, target_ip: str = "10.0.0.1") -> float:
    """Measure RTT via single ping from ns2."""
    out = _run(["ip","netns","exec",ns2,"ping","-c","1","-W","1",target_ip])
    m = re.search(r"time=([\d.]+)", out)
    return float(m.group(1)) if m else 0.0

# ═══════════════════════════════════════════════════════════════
# Novel Contribution 1: Multi-signal predictive state estimator
# ═══════════════════════════════════════════════════════════════

def compute_gradient(history: deque, attr: str) -> float:
    """
    Linear regression slope over history window.
    Returns rate of change of `attr` per second.
    More robust than simple delta — uses all window samples.
    """
    vals = [(s.ts, getattr(s, attr)) for s in history if hasattr(s, attr)]
    if len(vals) < 3:
        return 0.0
    n    = len(vals)
    t0   = vals[0][0]
    xs   = [v[0] - t0 for v in vals]
    ys   = [v[1]      for v in vals]
    x_m  = sum(xs) / n
    y_m  = sum(ys) / n
    num  = sum((xi - x_m) * (yi - y_m) for xi, yi in zip(xs, ys))
    den  = sum((xi - x_m) ** 2 for xi in xs)
    return num / den if den > 1e-9 else 0.0

def classify_regime(dr: float, bl: float) -> str:
    if dr > DR_HEAVY  or bl > BL_HEAVY:  return "HEAVY"
    if dr > DR_MOD    or bl > BL_MOD:    return "MODERATE"
    if dr > DR_LIGHT  or bl > BL_LIGHT:  return "LIGHT"
    return "NORMAL"

REGIME_ORDER = ["NORMAL", "LIGHT", "MODERATE", "HEAVY"]

def predict_next_regime(current: str, dr_grad: float, bl_grad: float) -> str:
    """
    Predict next regime from gradient direction.
    If gradients are positive → heading toward worse state.
    This is the PREDICTIVE element — act before transition, not after.
    """
    idx = REGIME_ORDER.index(current)
    composite_grad = 0.6 * dr_grad / max(DR_HEAVY, 1) + \
                     0.4 * bl_grad / max(BL_HEAVY, 1)
    if composite_grad > GRAD_WORSENING and idx < 3:
        return REGIME_ORDER[idx + 1]   # predict worse
    if composite_grad < GRAD_RECOVERING and idx > 0:
        return REGIME_ORDER[idx - 1]   # predict better
    return current                      # stable

def build_state_vector(sample: Sample, history: deque) -> StateVector:
    dr_grad  = compute_gradient(history, "drop_rate")
    bl_grad  = compute_gradient(history, "backlog")
    rtt_grad = compute_gradient(history, "rtt_proxy_ms")
    regime   = classify_regime(sample.drop_rate, sample.backlog)

    dr_grad_n = dr_grad / max(DR_HEAVY, 1)
    bl_grad_n = bl_grad / max(BL_HEAVY, 1)
    composite = 0.6 * dr_grad_n + 0.4 * bl_grad_n
    if composite > GRAD_WORSENING:
        traj = "WORSENING"
    elif composite < GRAD_RECOVERING:
        traj = "RECOVERING"
    else:
        traj = "STABLE"

    predicted = predict_next_regime(regime, dr_grad, bl_grad)

    return StateVector(
        drop_rate   = sample.drop_rate,
        backlog     = sample.backlog,
        rtt_ms      = sample.rtt_proxy_ms,
        dr_gradient = dr_grad,
        bl_gradient = bl_grad,
        rtt_gradient= rtt_grad,
        trajectory  = traj,
        regime      = regime,
        predicted   = predicted,
    )

# ═══════════════════════════════════════════════════════════════
# Novel Contribution 2: Workload-aware profile selection
# ═══════════════════════════════════════════════════════════════

def select_workload_profile(elephant_ratio: float) -> str:
    """
    Select fq_codel parameter profile based on flow-size distribution.
    eBPF-derived elephant_ratio drives the selection.
    - Mice-dominated → small target (protect latency)
    - Elephant-dominated → large target + quantum (protect throughput)
    - Mixed → balanced defaults
    """
    if elephant_ratio < 0.2:
        return "MICE"
    if elephant_ratio > 0.6:
        return "ELEPHANT"
    return "MIXED"

# ═══════════════════════════════════════════════════════════════
# Novel Contribution 3: Three-timescale AIMD adjustment
# ═══════════════════════════════════════════════════════════════

def aimd_adjust(sv: StateVector, params: Params,
                workload: str, use_predicted: bool = True) -> tuple:
    """
    AIMD parameter adjustment using:
    - Current regime (reactive)
    - Predicted next regime (predictive — the novel element)
    - Workload profile (flow-aware — the second novel element)

    If use_predicted=True and prediction differs from current:
    → Start adjusting toward predicted regime's parameters NOW
    → This is the predictive advantage: avoid congestion rather than respond to it
    """
    # Use predicted regime if trajectory is WORSENING (act early)
    if use_predicted and sv.trajectory == "WORSENING":
        effective_regime = sv.predicted
        reason_prefix = "[PREDICTIVE]"
    else:
        effective_regime = sv.regime
        reason_prefix = "[REACTIVE]"

    p = Params(params.target, params.interval, params.limit, params.quantum)

    if effective_regime == "HEAVY":
        p.target   *= BETA
        p.interval *= BETA
        p.limit    *= BETA
        reason = f"{reason_prefix} mult-decrease β={BETA} (regime={sv.regime} pred={sv.predicted})"

    elif effective_regime == "MODERATE":
        p.target -= 0.2
        p.limit  -= 32
        reason = f"{reason_prefix} additive-decrease (regime={sv.regime})"

    elif effective_regime == "LIGHT":
        p.target   += ALPHA_T
        p.interval += 5.0
        p.limit    += ALPHA_L
        reason = f"{reason_prefix} additive-increase α={ALPHA_T}ms (regime={sv.regime})"

    else:  # NORMAL
        # On RECOVERING trajectory: relax parameters slightly
        if sv.trajectory == "RECOVERING":
            p.target += 0.2
            p.limit  += 16
            reason = f"{reason_prefix} gentle-increase (recovering)"
        else:
            return params, f"stable (regime={sv.regime})"

    # Apply workload-profile bounds
    profile = WORKLOAD_PROFILES[workload]
    if workload == "MICE":
        p.target  = min(p.target,  profile["target"] + 2)
        p.quantum = profile["quantum"]
    elif workload == "ELEPHANT":
        p.target  = max(p.target,  profile["target"] - 3)
        p.quantum = profile["quantum"]

    p.clamp()
    reason += f" | workload={workload}"
    return p, reason

# ═══════════════════════════════════════════════════════════════
# eBPF map reader (optional — graceful fallback to tc-only)
# ═══════════════════════════════════════════════════════════════

class EBPFReader:
    def __init__(self, ebpf_obj: str):
        self.b = None
        self.active = False
        try:
            from bcc import BPF
            if not os.path.exists(ebpf_obj):
                print(f"  [eBPF] {ebpf_obj} not found — tc-only mode")
                return
            self.b = BPF(obj=ebpf_obj)
            self.active = True
            print(f"  [eBPF] Loaded {ebpf_obj}")
        except ImportError:
            print("  [eBPF] python3-bpfcc not installed — tc-only mode")
        except Exception as e:
            print(f"  [eBPF] Load failed: {e} — tc-only mode")

    def read(self) -> dict:
        """Returns dict: active_flows, elephant_flows, mice_flows, rtt_proxy_ms"""
        if not self.active or self.b is None:
            return {"active_flows":0,"elephant_flows":0,"mice_flows":0,"rtt_proxy_ms":0.0}
        try:
            now_ns = time.time_ns()
            active = elephant = mice = 0
            total_gap_ns = 0
            flow_map = self.b.get_table("flow_map")
            for _, val in flow_map.items():
                age_s = (now_ns - val.last_seen_ns) / 1e9
                if age_s < 2.0:
                    active += 1
                    total_gap_ns += val.interpacket_gap_ns
                    if val.is_elephant:
                        elephant += 1
                    else:
                        mice += 1
            rtt_proxy = (total_gap_ns / max(active, 1)) / 1e6  # ns → ms
            return {"active_flows":active,"elephant_flows":elephant,
                    "mice_flows":mice,"rtt_proxy_ms":round(rtt_proxy,3)}
        except Exception:
            return {"active_flows":0,"elephant_flows":0,"mice_flows":0,"rtt_proxy_ms":0.0}

# ═══════════════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════════════

class Logger:
    def __init__(self, logdir: str):
        os.makedirs(logdir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.m_path = os.path.join(logdir, f"acape_metrics_{ts}.csv")
        self.a_path = os.path.join(logdir, f"acape_adj_{ts}.csv")
        self.s_path = os.path.join(logdir, f"acape_state_{ts}.csv")
        self.mf = open(self.m_path,"w",newline="")
        self.af = open(self.a_path,"w",newline="")
        self.sf = open(self.s_path,"w",newline="")
        self.mw = csv.writer(self.mf)
        self.aw = csv.writer(self.af)
        self.sw = csv.writer(self.sf)
        self.mw.writerow(["t_s","drop_rate_per_s","drops_exp","backlog_pkts",
                          "throughput_mbps","rtt_proxy_ms",
                          "active_flows","elephant_flows","mice_flows","elephant_ratio",
                          "regime","trajectory","predicted_regime","workload_profile",
                          "target_ms","interval_ms","limit_pkts","quantum_bytes"])
        self.aw.writerow(["t_s","regime","trajectory","predicted",
                          "old_target","new_target","old_interval","new_interval",
                          "old_limit","new_limit","old_quantum","new_quantum",
                          "workload","reason"])
        self.sw.writerow(["t_s","dr_gradient","bl_gradient","rtt_gradient",
                          "regime","trajectory","predicted","workload"])
        for f in (self.mf,self.af,self.sf): f.flush()

    def log_sample(self, t: float, smp: Sample, sv: StateVector,
                   workload: str, p: Params):
        self.mw.writerow([
            f"{t:.3f}", f"{smp.drop_rate:.4f}", int(smp.drops_abs),
            int(smp.backlog), f"{smp.throughput:.4f}", f"{smp.rtt_proxy_ms:.3f}",
            smp.active_flows, smp.elephant_flows, smp.mice_flows,
            f"{smp.elephant_ratio:.3f}",
            sv.regime, sv.trajectory, sv.predicted, workload,
            f"{p.target:.2f}", f"{p.interval:.1f}", p.limit, p.quantum,
        ])
        self.mf.flush()

    def log_state(self, t: float, sv: StateVector, workload: str):
        self.sw.writerow([f"{t:.3f}",
                          f"{sv.dr_gradient:.4f}", f"{sv.bl_gradient:.4f}",
                          f"{sv.rtt_gradient:.4f}",
                          sv.regime, sv.trajectory, sv.predicted, workload])
        self.sf.flush()

    def log_adj(self, t: float, sv: StateVector, old: Params, new: Params,
                workload: str, reason: str):
        self.aw.writerow([
            f"{t:.3f}", sv.regime, sv.trajectory, sv.predicted,
            f"{old.target:.2f}", f"{new.target:.2f}",
            f"{old.interval:.1f}", f"{new.interval:.1f}",
            old.limit, new.limit, old.quantum, new.quantum,
            workload, reason,
        ])
        self.af.flush()

    def paths(self):
        return self.m_path, self.a_path, self.s_path

    def close(self):
        for f in (self.mf, self.af, self.sf): f.close()

# ═══════════════════════════════════════════════════════════════
# Main control loop
# ═══════════════════════════════════════════════════════════════

def run(args):
    ebpf_obj = os.path.join(os.path.dirname(__file__), "../ebpf/tc_monitor.o")
    ebpf     = EBPFReader(ebpf_obj)
    logger   = Logger(args.logdir)
    params   = read_params(args.ns, args.iface)

    m_path, a_path, s_path = logger.paths()
    print(f"\n{'═'*65}")
    print(f"  ACAPE v{VERSION} — Adaptive Condition-Aware Packet Engine")
    print(f"  Amritha S, VIT Chennai 2026")
    print(f"{'─'*65}")
    print(f"  ns={args.ns}  iface={args.iface}  ebpf={'ON' if ebpf.active else 'tc-only'}")
    print(f"  metrics    → {m_path}")
    print(f"  adj log    → {a_path}")
    print(f"  state log  → {s_path}")
    print(f"{'═'*65}\n")

    # Read drop baseline (zero at experiment start)
    first = read_tc(args.ns, args.iface)
    if not first:
        sys.exit("ERROR: Cannot read tc stats — is the namespace running?")
    drops_base = first["drops_abs"]
    prev_tc    = first

    history:    deque = deque(maxlen=GRAD_WINDOW)
    state_buf:  deque = deque(maxlen=8)
    stable_cnt = adj_count = tick = 0
    t0         = time.time()
    workload   = "MIXED"
    sv         = None

    # Measure initial RTT
    rtt_ms = measure_rtt_ms("ns2", "10.0.0.1") if not args.dry else 0.5

    def shutdown(sig=None, frame=None):
        logger.close()
        print(f"\n{'═'*65}")
        print(f"  ACAPE done — {tick} ticks, {adj_count} adjustments")
        print(f"  Run: python3 plot_acape.py")
        print(f"{'═'*65}")
        sys.exit(0)
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # ── Print header ──────────────────────────────────────────
    H = (f"{'t':>7}  {'regime':>10}  {'traj':>10}  {'pred':>10}  "
         f"{'dr/s':>8}  {'bl':>6}  {'RTT':>6}  "
         f"{'flows':>6}  {'eleph':>5}  {'wkld':>8}  "
         f"{'tgt':>6}  {'lim':>5}  {'adj':>4}")
    print(H); print("─"*len(H))

    while True:
        time.sleep(T2_INTERVAL)
        tick += 1
        elapsed = time.time() - t0

        # ── T2: Collect metrics ───────────────────────────────
        tc = read_tc(args.ns, args.iface)
        if not tc:
            continue

        dt         = max(tc["ts"] - prev_tc["ts"], 1e-6)
        drops_exp  = tc["drops_abs"] - drops_base
        delta_d    = max(0, tc["drops_abs"] - prev_tc["drops_abs"])
        drop_rate  = delta_d / dt
        throughput = (max(0, tc["bytes"] - prev_tc.get("bytes",0)) * 8) / (dt * 1e6)
        backlog    = tc["backlog"]

        # eBPF enrichment
        ebpf_data    = ebpf.read()
        active_flows = ebpf_data["active_flows"]
        eleph_flows  = ebpf_data["elephant_flows"]
        mice_flows   = ebpf_data["mice_flows"]
        rtt_proxy    = ebpf_data["rtt_proxy_ms"]
        if rtt_proxy == 0.0:
            rtt_proxy = rtt_ms   # fallback to ping RTT

        eleph_ratio = eleph_flows / max(active_flows, 1)

        # Build sample
        smp = Sample(
            ts=elapsed, drop_rate=drop_rate, backlog=float(backlog),
            throughput=throughput, drops_abs=drops_exp,
            active_flows=active_flows, elephant_flows=eleph_flows,
            mice_flows=mice_flows, elephant_ratio=eleph_ratio,
            rtt_proxy_ms=rtt_proxy,
        )
        history.append(smp)

        # ── Compute state vector ──────────────────────────────
        sv = build_state_vector(smp, history)

        # Workload profile (Novel Contribution 2)
        workload = select_workload_profile(eleph_ratio)

        # Stability tracking
        state_buf.append(sv.regime)
        if len(state_buf) >= STABLE_ROUNDS and \
                len(set(list(state_buf)[-STABLE_ROUNDS:])) == 1:
            stable_cnt += 1
        else:
            stable_cnt = 0

        # ── Log T2 sample ─────────────────────────────────────
        logger.log_sample(elapsed, smp, sv, workload, params)
        if tick % 5 == 0:
            logger.log_state(elapsed, sv, workload)

        # ── T3: Parameter adjustment ──────────────────────────
        if tick % T3_EVERY_N == 0 and stable_cnt >= STABLE_ROUNDS:
            old = Params(params.target, params.interval, params.limit, params.quantum)
            new_p, reason = aimd_adjust(sv, params, workload, use_predicted=True)
            changed = (
                abs(new_p.target   - old.target)   > 0.05 or
                abs(new_p.interval - old.interval) > 0.5  or
                abs(new_p.limit    - old.limit)    > 1    or
                abs(new_p.quantum  - old.quantum)  > 10
            )
            if changed:
                ok = apply_params(args.ns, args.iface, new_p, args.dry)
                if ok:
                    params = new_p
                    adj_count += 1
                    logger.log_adj(elapsed, sv, old, new_p, workload, reason)

        # ── Periodic RTT measurement (every 5 s) ──────────────
        if tick % T3_EVERY_N == 0 and not args.dry:
            rtt_ms = measure_rtt_ms("ns2", "10.0.0.1")

        # ── Print row ─────────────────────────────────────────
        print(f"{elapsed:>7.1f}  {sv.regime:>10}  {sv.trajectory:>10}  "
              f"{sv.predicted:>10}  {drop_rate:>8.1f}  {backlog:>6d}  "
              f"{rtt_proxy:>5.1f}ms  {active_flows:>6d}  {eleph_flows:>5d}  "
              f"{workload:>8}  {params.target:>5.1f}ms  {params.limit:>5d}  "
              f"{adj_count:>4d}", flush=True)

        prev_tc = tc

# ═══════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="ACAPE: Adaptive Condition-Aware Packet Engine — Amritha S 2026",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--ns",      default="ns1",     help="Network namespace")
    p.add_argument("--iface",   default="veth1",   help="Interface in ns")
    p.add_argument("--logdir",  default="../logs",  help="Log directory")
    p.add_argument("--dry",     action="store_true",help="Classify only, no tc changes")
    args = p.parse_args()
    if os.geteuid() != 0 and not args.dry:
        sys.exit("Run as root: sudo python3 acape_controller.py")
    run(args)
